# -*- coding: utf-8 -*-
"""动作模型导出 ONNX（FP32 + 动态 INT8）并验证 onnxruntime 等价性与 CPU 延迟。

产物（--out-dir，默认与训练输出同目录）：
    action_<arch>.onnx / action_<arch>.int8.onnx
    export_meta.json        # pt/onnx/int8 精度对齐、体积、CPU 每秒每 clip 延迟

worker 部署用 meta（类别顺序、中文标签、归一化参数）由 --emit-worker-meta
另写到 backend/weights/action_clf_meta.json（与 text_clf_meta.json 同模式）。
"""
from __future__ import annotations

import argparse
import json
import time
from pathlib import Path

import numpy as np
import onnxruntime as ort
import torch

from train_action import KINETICS_MEAN, KINETICS_STD, build_model


def _pt_predict(model: torch.nn.Module, x: np.ndarray) -> np.ndarray:
    model.eval()
    with torch.no_grad():
        return model(torch.from_numpy(x)).numpy()


def _ort_predict(path: Path, x: np.ndarray) -> np.ndarray:
    sess = ort.InferenceSession(str(path), providers=["CPUExecutionProvider"])
    (name,) = [i.name for i in sess.get_inputs()]
    return sess.run(None, {name: x})[0]


def _latency(path: Path, x: np.ndarray, runs: int = 20) -> float:
    sess = ort.InferenceSession(str(path), providers=["CPUExecutionProvider"])
    (name,) = [i.name for i in sess.get_inputs()]
    sess.run(None, {name: x[:1]})  # warmup
    t0 = time.perf_counter()
    for _ in range(runs):
        sess.run(None, {name: x[:1]})
    return (time.perf_counter() - t0) / runs * 1000


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--ckpt", required=True, help="训练产出的 best.pt")
    ap.add_argument("--out-dir", default=None, help="默认 ckpt 同目录")
    ap.add_argument("--emit-worker-meta", default=None,
                    help="把部署 meta 写到该路径（backend/weights/action_clf_meta.json）")
    ap.add_argument("--int8", action=argparse.BooleanOptionalAction, default=True)
    args = ap.parse_args()

    ckpt = torch.load(args.ckpt, map_location="cpu", weights_only=True)
    classes = ckpt["classes"]
    num_frames, frame_size = ckpt["num_frames"], ckpt["frame_size"]
    arch = ckpt["arch"]
    model = build_model(arch, len(classes), pretrained=False)
    model.load_state_dict(ckpt["model_state"])
    model.eval()

    out_dir = Path(args.out_dir) if args.out_dir else Path(args.ckpt).parent
    out_dir.mkdir(parents=True, exist_ok=True)
    fp32_path = out_dir / f"action_{arch}.onnx"
    dummy = torch.randn(1, 3, num_frames, frame_size, frame_size)
    # dynamo=False 走传统 TorchScript 导出器：产物可被动态 INT8 量化（同实验3 检测模型链路）
    torch.onnx.export(model, dummy, str(fp32_path), opset_version=17, dynamo=False,
                      input_names=["clip"], output_names=["logits"],
                      dynamic_axes={"clip": {0: "batch"}, "logits": {0: "batch"}})
    size_fp32 = fp32_path.stat().st_size / 1e6

    # 随机批次对齐验证（pt vs onnx）
    x = np.random.randn(4, 3, num_frames, frame_size, frame_size).astype(np.float32)
    ref = _pt_predict(model, x)
    got = _ort_predict(fp32_path, x)
    max_diff = float(np.abs(ref - got).max())
    if max_diff > 1e-3:
        raise SystemExit(f"FP32 ONNX 与 PyTorch 输出差异过大：{max_diff}")

    meta = {
        "arch": arch,
        "classes": classes,
        "zh_names": ckpt.get("zh_names"),
        "num_frames": num_frames,
        "frame_size": frame_size,
        "mean": list(KINETICS_MEAN),
        "std": list(KINETICS_STD),
        "onnx_fp32": {"path": fp32_path.name, "size_mb": round(size_fp32, 2),
                      "max_abs_diff_vs_pt": max_diff},
    }

    if args.int8:
        from onnxruntime.quantization import QuantType, quantize_dynamic

        int8_path = out_dir / f"action_{arch}.int8.onnx"
        quantize_dynamic(str(fp32_path), str(int8_path), weight_type=QuantType.QInt8)
        got8 = _ort_predict(int8_path, x)
        # INT8 动态量化与 FP32 的 top-1 一致率（不是逐位对齐）
        agree = float((got8.argmax(1) == ref.argmax(1)).mean())
        meta["onnx_int8"] = {
            "path": int8_path.name,
            "size_mb": round(int8_path.stat().st_size / 1e6, 2),
            "top1_agree_vs_fp32": round(agree, 4),
            "max_abs_diff_vs_pt": round(float(np.abs(got8 - ref).max()), 4),
        }

    meta["cpu_latency_ms_per_clip"] = {
        "fp32": round(_latency(fp32_path, x), 1),
    }
    if args.int8:
        meta["cpu_latency_ms_per_clip"]["int8"] = round(_latency(int8_path, x), 1)
    # 3D 卷积上动态 INT8 常见反优化（本机实测慢一个数量级），部署推荐写进 meta
    lat = meta["cpu_latency_ms_per_clip"]
    meta["deployment_recommendation"] = (
        "int8" if "int8" in lat and lat["int8"] < lat["fp32"] else "fp32"
    )

    (out_dir / "export_meta.json").write_text(
        json.dumps(meta, ensure_ascii=False, indent=2), encoding="utf-8")

    if args.emit_worker_meta:
        dest = Path(args.emit_worker_meta)
        dest.parent.mkdir(parents=True, exist_ok=True)
        worker_meta = {
            "arch": arch,
            "classes": classes,
            "zh_names": ckpt.get("zh_names") or {},
            "background_class": "_none",
            "num_frames": num_frames,
            "frame_size": frame_size,
            "mean": list(KINETICS_MEAN),
            "std": list(KINETICS_STD),
        }
        dest.write_text(json.dumps(worker_meta, ensure_ascii=False, indent=2), encoding="utf-8")
        print(f"worker meta → {dest}")

    print(json.dumps(meta, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
