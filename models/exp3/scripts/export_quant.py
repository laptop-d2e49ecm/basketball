"""实验3 P1：自定义 ONNX INT8 静态量化（校准集/量化粒度可控）.

用途：ultralytics 内置导出只提供 per-tensor 粒度与固定校准流程；本脚本暴露
校准集（split + 数量）与 per-channel 两个变量，供校准实验矩阵 E2-E4 使用。
量化范围与内置导出保持一致（仅 Conv/Gemm/MatMul，检测头解码保持 FP32），
确保对照实验只隔离目标变量。

用法（项目根目录运行）：
  python exp3/scripts/export_quant.py --src exp3/models/a2_fp32.onnx \
      --out exp3/models/a2_int8_val346_pc.onnx --split val --n 346 --per-channel
"""
import argparse
import glob
import os

import cv2
import numpy as np
import onnx
from onnxruntime.quantization import CalibrationDataReader, quantize_static
from ultralytics.data.augment import LetterBox

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))  # models/exp3/scripts -> 仓库根（2026-11 目录搬迁后修正层级）
IMGS = {"val": "data/splits/yolo/images/val", "train": "data/splits/yolo/images/train"}


class YoloCalibReader(CalibrationDataReader):
    """逐张产出与 ultralytics 推理一致的预处理张量：LetterBox 640 + BGR->RGB + /255."""

    def __init__(self, split: str, n: int, imgsz: int = 640):
        paths = sorted(glob.glob(os.path.join(ROOT, IMGS[split], "*")))
        assert paths, f"no images under {IMGS[split]}"
        # 前 n 张固定顺序取样（可复现；train 即任务书"训练集前 N 样本"口径）
        self.paths = paths[:n]
        self.box = LetterBox(imgsz, auto=False, stride=32)
        self.it = iter(self.paths)

    def get_next(self):
        try:
            p = next(self.it)
        except StopIteration:
            return None
        im0 = cv2.imread(p)
        im = self.box(image=im0)[:, :, ::-1].transpose(2, 0, 1)
        im = np.ascontiguousarray(im, dtype=np.float32) / 255.0
        return {"images": im[None]}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--src", required=True, help="FP32 ONNX 源模型")
    ap.add_argument("--out", required=True, help="INT8 输出路径")
    ap.add_argument("--split", default="val", choices=list(IMGS))
    ap.add_argument("--n", type=int, default=346, help="校准图片数")
    ap.add_argument("--per-channel", action="store_true", help="权重 per-channel 量化（默认 per-tensor）")
    a = ap.parse_args()

    # 与 ultralytics 内置一致：非加权节点排除在量化外
    graph = onnx.load(a.src).graph
    exclude = [n.name for n in graph.node if n.op_type not in {"Conv", "Gemm", "MatMul"}]
    del graph

    print(f"quantizing {a.src} -> {a.out}  calib={a.split}:{a.n}  per_channel={a.per_channel}")
    quantize_static(
        a.src,
        a.out,
        YoloCalibReader(a.split, a.n),
        nodes_to_exclude=exclude,
        per_channel=a.per_channel,
    )
    print(f"done, size = {os.path.getsize(a.out) / 1e6:.1f} MB")


if __name__ == "__main__":
    main()
