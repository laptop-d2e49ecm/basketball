# -*- coding: utf-8 -*-
"""生成 P2 test190 子集的清单与 data.yaml（指向项目标准 test 目录中的同名原始帧）。"""
import os

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
os.chdir(ROOT)

p2 = sorted(os.listdir("优化/data/images/test"))
txt = os.path.abspath("exp3/p2_check/test190.txt").replace("\\", "/")
with open("exp3/p2_check/test190.txt", "w") as f:
    for n in p2:
        f.write(os.path.abspath(os.path.join("data/splits/yolo/images/test", n)).replace("\\", "/") + "\n")
with open("exp3/p2_check/yaml190.yaml", "w") as f:
    f.write("path: data/splits/yolo\ntrain: " + txt + "\nval: " + txt + "\ntest: " + txt + "\nnames:\n  0: player\n")
print("ok", len(p2))
