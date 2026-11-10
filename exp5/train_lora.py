# -*- coding: utf-8 -*-
"""实验5 微调：Qwen3-1.7B + QLoRA（任务书 5.2.2 的三件套：4-bit 量化 / LoRA / 梯度累积 8 步）。

- 数据：exp5/data/agent_finetune_data.json（60 分类 + 40 生成）
- 分类题与评测共用同一 prompt（exp5/eval/prompt.py），保证"变量只有上没上过课"
- 产物：exp5/adapters/qwen3-1.7b-lora/ + exp5/eval/train_log.json

用法：
  .venv\\Scripts\\python.exe -X utf8 exp5/train_lora.py --model work/models/Qwen3-1.7B
"""
from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(Path(__file__).parent / "eval"))

import torch  # noqa: E402
from datasets import Dataset  # noqa: E402
from peft import LoraConfig, get_peft_model, prepare_model_for_kbit_training  # noqa: E402
from transformers import (  # noqa: E402
    AutoModelForCausalLM,
    AutoTokenizer,
    BitsAndBytesConfig,
)
from trl import SFTConfig, SFTTrainer  # noqa: E402

from prompt import build_prompt  # noqa: E402

DATA = REPO / "exp5/data/agent_finetune_data.json"
ADAPTER = REPO / "exp5/adapters/qwen3-1.7b-lora"
LOG = REPO / "exp5/eval/train_log.json"


def build_tokenized(tokenizer, items):
    """手工做 completion-only 掩码：prompt 部分 label=-100，只监督 assistant 回答。

    Qwen3 的 chat 模板没有 {% generation %} 标记，TRL 的 completion_only_loss
    对它会退化成"全序列都算损失"；这里自己切前缀，确保只在答案上学。
    """
    rows, kinds = [], []
    for item in items:
        if "动作类别" in item["instruction"]:
            user, assistant, kind = build_prompt(item["input"]), item["output"], "classify"
        else:
            user, assistant, kind = f'{item["instruction"]}\n{item["input"]}', item["output"], "generate"
        msgs = [{"role": "user", "content": user}, {"role": "assistant", "content": assistant}]
        full_text = tokenizer.apply_chat_template(msgs, tokenize=False, add_generation_prompt=False)
        prompt_text = tokenizer.apply_chat_template(msgs[:1], tokenize=False, add_generation_prompt=True)
        if not full_text.startswith(prompt_text):
            raise RuntimeError(f"chat 模板前缀不一致：{prompt_text!r} vs {full_text[:len(prompt_text)]!r}")
        suffix = full_text[len(prompt_text):]
        prompt_ids = tokenizer(prompt_text, add_special_tokens=False).input_ids
        answer_ids = tokenizer(suffix, add_special_tokens=False).input_ids
        full = prompt_ids + answer_ids
        labels = [-100] * len(prompt_ids) + answer_ids
        rows.append({
            "input_ids": full,
            "labels": labels,
            "attention_mask": [1] * len(full),
        })
        kinds.append(kind)
    return rows, kinds


def main() -> int:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    ap = argparse.ArgumentParser()
    ap.add_argument("--model", required=True, help="本地模型目录")
    ap.add_argument("--epochs", type=float, default=3.0)
    ap.add_argument("--lr", type=float, default=2e-4)
    ap.add_argument("--max-length", type=int, default=512)
    ap.add_argument("--no-4bit", action="store_true", help="禁用 4-bit（显存够或 bnb 不可用时）")
    ap.add_argument("--max-steps", type=int, default=0, help=">0 时只跑这么多步（冒烟用）")
    args = ap.parse_args()

    items = json.loads(DATA.read_text(encoding="utf-8"))
    print(f"数据 {len(items)} 条；torch {torch.__version__} | cuda={torch.cuda.is_available()}"
          f" | {torch.cuda.get_device_name(0) if torch.cuda.is_available() else 'CPU'}")

    tokenizer = AutoTokenizer.from_pretrained(args.model, trust_remote_code=True)
    if tokenizer.pad_token is None:
        tokenizer.pad_token = tokenizer.eos_token
    tokenizer.padding_side = "right"

    use_4bit = not args.no_4bit
    load_kwargs = dict(trust_remote_code=True, device_map="auto")
    if use_4bit:
        load_kwargs["quantization_config"] = BitsAndBytesConfig(
            load_in_4bit=True,
            bnb_4bit_quant_type="nf4",
            bnb_4bit_use_double_quant=True,
            bnb_4bit_compute_dtype=torch.bfloat16,
        )
        load_kwargs["torch_dtype"] = torch.bfloat16
    else:
        load_kwargs["torch_dtype"] = torch.float16
    model = AutoModelForCausalLM.from_pretrained(args.model, **load_kwargs)

    if use_4bit:
        model = prepare_model_for_kbit_training(model, use_gradient_checkpointing=True)
    model.config.use_cache = False

    lora = LoraConfig(
        r=16, lora_alpha=32, lora_dropout=0.05,
        target_modules=["q_proj", "k_proj", "v_proj", "o_proj"],
        bias="none", task_type="CAUSAL_LM",
    )
    model = get_peft_model(model, lora)
    model.print_trainable_parameters()

    rows, kinds = build_tokenized(tokenizer, items)
    ds = Dataset.from_list(rows)
    print(f"分类题 {kinds.count('classify')} / 生成题 {kinds.count('generate')}；数据集 {len(rows)} 条")

    targs = SFTConfig(
        output_dir=str(REPO / "exp5/adapters/_trainer_tmp"),
        per_device_train_batch_size=1,
        gradient_accumulation_steps=8,          # 任务书：梯度累积 8 步
        num_train_epochs=args.epochs,
        max_steps=args.max_steps if args.max_steps > 0 else -1,
        learning_rate=args.lr,
        logging_steps=1,
        save_strategy="no",
        report_to=[],
        gradient_checkpointing=True,
        lr_scheduler_type="cosine",
        bf16=torch.cuda.is_available() and torch.cuda.is_bf16_supported(),
        fp16=torch.cuda.is_available() and not torch.cuda.is_bf16_supported(),
        optim="paged_adamw_8bit" if use_4bit else "adamw_torch",
        max_length=args.max_length,
        packing=False,
    )

    trainer = SFTTrainer(
        model=model,
        args=targs,
        train_dataset=ds,
        processing_class=tokenizer,
    )

    # 审计：确认"到底训练了哪些 token"（TRL 可能做 assistant-only 掩码）
    tr_ds = trainer.train_dataset
    print(f"trainer 数据集条数：{len(tr_ds)}")
    ex = tr_ds[0]
    sup = [i for i, lab in zip(ex["input_ids"], ex["labels"]) if lab != -100]
    print(f"第 1 条被监督 token 数：{len(sup)} / 总长 {len(ex['input_ids'])}")
    print(f"监督片段：{tokenizer.decode(sup)[:160]!r}")

    started = time.time()
    result = trainer.train()
    elapsed = time.time() - started

    ADAPTER.mkdir(parents=True, exist_ok=True)
    model.save_pretrained(str(ADAPTER))
    tokenizer.save_pretrained(str(ADAPTER))

    history = [h for h in trainer.state.log_history if "loss" in h]
    payload = {
        "base_model": args.model,
        "epochs": args.epochs,
        "lr": args.lr,
        "max_length": args.max_length,
        "quantization": "4bit-nf4" if use_4bit else "fp16",
        "lora": {"r": 16, "alpha": 32, "dropout": 0.05, "targets": ["q_proj", "k_proj", "v_proj", "o_proj"]},
        "grad_accum": 8,
        "train_seconds": round(elapsed, 1),
        "train_loss": round(result.training_loss, 4),
        "history": [{"step": h.get("step"), "loss": round(h["loss"], 4)} for h in history],
        "n_items": len(items),
        "gpu": torch.cuda.get_device_name(0) if torch.cuda.is_available() else "CPU",
    }
    LOG.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"\n训练完成：{elapsed:.0f}s，final loss {result.training_loss:.4f}，适配器 -> {ADAPTER}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
