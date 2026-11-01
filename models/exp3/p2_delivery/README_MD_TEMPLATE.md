# 实验3：模型优化与对比验证

当前正式报告为 [模型优化与对比验证](reports/实验3报告_模型优化与对比验证.pdf)，可编辑正文在同目录。报告沿用原封面及七章结构。旧CPU专项报告仅作对应实验留档。

## 对照与结果

未优化基线是实验二 A2_yolov8n/weights/best.pt，单类 player。CPU与GPU硬件迁移、同GPU TensorRT优化、蒸馏训练分别比较。具体数字见 results/md_comparison.csv 和 results/md_summary.json，原始计时数组、完整预测与校验文件均保留。不把任务执行完成当作所有数值指标均达标。

## 目录

- data：原始 train2158、val173、test190 图片与标签。
- models / scripts / results：CPU量化、ORT、OpenVINO与相应验证。
- gpu/models：实验二原模型、教师、新蒸馏学生及实际TensorRT引擎。
- gpu/scripts：蒸馏、TensorRT构建、GPU测速和统一推理接口。
- gpu/results：训练曲线、checkpoint、原始测速、精度、噪声、独立复测与来源验证。
- reports：正式报告、可编辑正文及图表。

## 环境

本机可用解释器：C:/Users/87273/Documents/Codex/2026-10-20/gei/work/yolov8s/.venv/Scripts/python.exe。
使用GPU时必须安装支持该GPU/驱动的CUDA版PyTorch，不能用CPU-only包代替。共享依赖见 requirements.txt，TensorRT依赖见 requirements-gpu.txt。原运行版本记录在 results/environment.json 与 gpu/results/trt_build.json。
TensorRT引擎为本机RTX3050生成；换GPU/软件环境需要重新构建。没有Kaggle T4实测记录。

## 推理示例

在本目录打开PowerShell。已有环境可把 python 替换为上述解释器完整路径。

```powershell
python gpu/scripts/infer.py --model gpu/models/a2_distilled_trt_fp16.engine --image data/images/test/选定图片.jpg --out results/GPU推理示例.json --device cuda --pipeline --conf 0.25
python scripts/run_cpu.py --model models/a2_cpu_tuned/model.xml --image data/images/test/选定图片.jpg --out results/CPU推理示例.json --conf 0.25
```

运行GPU推理.ps1 会自动选择测试集第一张图片。统一GPU接口支持 .pt/.onnx/.xml/.engine，输入BGR数组，返回原图坐标Nx6框；每个工作线程单独创建Detector。

## 复现训练与评价

```powershell
python gpu/scripts/distill_yolo.py --epochs 12 --microbatch 16
python gpu/scripts/build_trt.py
python gpu/scripts/export_student_fp16.py
python gpu/scripts/build_student_trt.py
python gpu/scripts/bench_exp3.py --model models/a2_original.pt --device cuda
python gpu/scripts/bench_exp3.py --model models/a2_trt_fp16.engine --device cuda
python gpu/scripts/eval_detail.py --model models/a2_distilled.pt
python gpu/scripts/eval_detail.py --model models/a2_distilled.pt --noise 0.02
python gpu/scripts/native_val.py --models models/a2_original.pt,models/a2_distilled.pt,models/m1_teacher.pt --device 0
```

训练默认从轮次断点恢复；全新训练请先另行备份模型和结果，再加 --fresh。训练、校准和测速必须顺序执行，不同时占用设备。模型参数路径由各脚本自身项目根解析；推理CLI使用传入路径。

## 数据与解释边界

使用实际原始数据，保留历史集合身份；离线_aug副本不加入本次训练与评测。历史数据包含同源视频跨集合情况，结果不能证明跨比赛泛化提升。主指标为COCOeval AP50/AP50-95，原生Ultralytics结果单独列出。AP-S只有1个GT，不作稳健小目标结论。蒸馏未做等预算纯微调消融，不把全部精度变化归因于蒸馏损失。

GPU最终提速路径使用 infer.py --pipeline；API可直接 from optimized_trt import Detector。参考路径不加 --pipeline，保留用于后端与流程收益对照。

温度对比：python gpu/scripts/temperature_study.py，T5/8/10等预算首轮筛选，选定温度续训至12轮；随后 python gpu/scripts/finish_temperature.py 完成验证。auto_infer.py提供GPU优先的统一接口，CPU回退使用同一A2权重的OpenVINO版本。

默认GPU部署：models/a2_distilled_trt_fp16.engine，在本机已测候选中按验证精度门槛与单张p50选出；选择记录在gpu/results/gpu_selection_lock.json，锁定后最终测试在gpu/results/gpu_recommendation.json。运行GPU推理.ps1与报告推荐使用同一模型。
