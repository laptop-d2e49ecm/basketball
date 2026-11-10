# -*- coding: utf-8 -*-
"""LoRA 后端：用实验5 微调的 Qwen3-1.7B 适配器做"解说→动作类别"分类。

设计（段5 轻量接入）：不改工具名、不改入参、不改返回结构，只给 `commentary_classify`
加一个后端开关：

    backend/.env:  EXP5_TEXT_BACKEND=joblib   # 默认，实验4 的 TF-IDF+LinearSVC
                   EXP5_TEXT_BACKEND=lora     # 实验5 微调模型（4-bit，4090/5060 均可）

模型路径用环境变量覆盖（模型不进 git）：
    EXP5_LORA_BASE=C:\\...\\models\\Qwen3-1.7B
    EXP5_LORA_ADAPTER=C:\\...\\repo\\exp5\\adapters\\qwen3-1.7b-lora

懒加载：首次调用才加载（约 10 秒、1.2GB 显存），之后单例复用；加载失败只影响该工具。
"""
from __future__ import annotations

import re
import sys
import time
from pathlib import Path

BACKEND_DIR = Path(__file__).resolve().parents[2]
REPO_ROOT = BACKEND_DIR.parents[2]


def _load_prompt_module():
    """复用评测用的同一份 prompt（唯一来源），避免训练/评测/线上三处漂移。"""
    eval_dir = REPO_ROOT / "exp5" / "eval"
    if str(eval_dir) not in sys.path:
        sys.path.insert(0, str(eval_dir))
    from prompt import LABELS, build_prompt, parse_label  # noqa: WPS433

    return LABELS, build_prompt, parse_label


class LoraCommentaryClassifier:
    """4-bit Qwen3 + LoRA 适配器的推理封装。"""

    def __init__(self) -> None:
        from app.agent.providers import load_env

        cfg = load_env()
        base = cfg.get("EXP5_LORA_BASE", "").strip()
        adapter = cfg.get("EXP5_LORA_ADAPTER", "").strip()
        self.base_path = Path(base) if base else Path(r"C:\sofeware\AI Api\dsh workspace\fish\work\models\Qwen3-1.7B")
        if adapter:
            self.adapter_path = Path(adapter)
        else:
            self.adapter_path = REPO_ROOT / "exp5" / "adapters" / "qwen3-1.7b-lora"
        if not self.base_path.is_dir():
            raise FileNotFoundError(f"LoRA 基座模型不存在：{self.base_path}（用 EXP5_LORA_BASE 指定）")
        if not self.adapter_path.is_dir():
            raise FileNotFoundError(f"LoRA 适配器不存在：{self.adapter_path}（用 EXP5_LORA_ADAPTER 指定）")

        import torch
        from peft import PeftModel
        from transformers import AutoModelForCausalLM, AutoTokenizer, BitsAndBytesConfig

        self.torch = torch
        self.labels, self.build_prompt, self.parse_label = _load_prompt_module()

        self.tokenizer = AutoTokenizer.from_pretrained(str(self.base_path), trust_remote_code=True)
        if self.tokenizer.pad_token is None:
            self.tokenizer.pad_token = self.tokenizer.eos_token

        # 量化方式可切：EXP5_LORA_QUANT=4bit（默认）| fp16
        self.quant = (cfg.get("EXP5_LORA_QUANT", "4bit") or "4bit").strip().lower()
        if self.quant == "fp16":
            model = AutoModelForCausalLM.from_pretrained(
                str(self.base_path), device_map="auto",
                torch_dtype=torch.float16, trust_remote_code=True,
            )
        else:
            bnb = BitsAndBytesConfig(
                load_in_4bit=True,
                bnb_4bit_quant_type="nf4",
                bnb_4bit_use_double_quant=True,
                bnb_4bit_compute_dtype=torch.bfloat16,
            )
            model = AutoModelForCausalLM.from_pretrained(
                str(self.base_path), quantization_config=bnb, device_map="auto",
                torch_dtype=torch.bfloat16, trust_remote_code=True,
            )
        self.model = PeftModel.from_pretrained(model, str(self.adapter_path))
        self.model.eval()

    def predict(self, text: str) -> dict:
        torch = self.torch
        prompt = self.tokenizer.apply_chat_template(
            [{"role": "user", "content": self.build_prompt(text)}],
            tokenize=False, add_generation_prompt=True,
        ) + "<think>\n\n</think>\n\n"  # 预填空思考块：Qwen3 否则会先"思考"，拖慢且易截断
        inputs = self.tokenizer(prompt, return_tensors="pt").to(self.model.device)

        started = time.perf_counter()
        with torch.no_grad():
            out = self.model.generate(
                **inputs, max_new_tokens=8, do_sample=False,
                output_scores=True, return_dict_in_generate=True,
                pad_token_id=self.tokenizer.eos_token_id,
            )
        elapsed_ms = round((time.perf_counter() - started) * 1000)

        new_ids = out.sequences[0][inputs["input_ids"].shape[1]:]
        raw = self.tokenizer.decode(new_ids, skip_special_tokens=True)
        clean = re.sub(r"<think>.*?</think>", "", raw, flags=re.S).strip()
        label = self.parse_label(clean)

        # 置信度：答案各 token 概率的几何平均（粗略但可解释）
        conf = 0.0
        try:
            import math

            probs = []
            for score, token_id in zip(out.scores, new_ids.tolist()):
                dist = torch.softmax(score[0], dim=-1)
                probs.append(max(float(dist[token_id]), 1e-9))
            if probs:
                conf = math.exp(sum(math.log(p) for p in probs) / len(probs))
        except Exception:  # noqa: BLE001 - 置信度只是展示，失败不影响结论
            conf = 0.0

        return {
            "label": label or "其他",
            "confidence": round(conf, 4),
            "raw": raw.strip(),
            "infer_ms": elapsed_ms,
            "backend": "lora",
        }
