# 实验3：实验二A2模型的CPU优化

本目录是本次完整交付。代码入口固定在CPU运行，报告只按CPU同设备结果判断优化。

原模型：模型设计与训练.zip / A2_yolov8n/weights/best.pt，单类别player，3,138,003参数。
SHA256：2e8624bf93eba97a0adc7f899fbb8e4cd9fd90e42f6546c74f32cc9ba9134776。

## 实测推荐

CPU默认方案：{{LABEL}}（{{MODEL}}，{{MODE}}）。
原A2 CPU单张p50 {{BASE_MS}} ms，推荐方案 {{MS}} ms，下降{{GAIN}}%；batch32吞吐提高{{FPS_GAIN}}%。
COCO测试mAP50-95为{{AP}}%。推荐先按验证集AP50-95损失<=1pp筛选，再在单张p50距最快值5%以内的候选中优先batch32吞吐。
INT8候选保留作体积/速度/精度对照，不默认等于最佳方案。
当前推荐方案的批量延迟与吞吐达到所列门槛；单张延迟下降约22%，仍未达到任务书40%的单张目标，不能宣称全部指标达标。

报告：reports/实验3报告_CPU推理优化与验证.pdf。
可编辑正文：reports/实验3报告_CPU推理优化可编辑正文.md。

## 本机运行

解释器：C:/Users/87273/Documents/Codex/2026-10-20/gei/work/yolov8s/.venv/Scripts/python.exe。
解释器所在文件夹的旧名称不决定本项目模型；本项目权重以以上A2来源与SHA256为准。
直接运行 运行CPU推理.ps1，自动选第一张测试图，并输出 results/CPU推理示例.json。

从本目录执行：

```powershell
python scripts/run_cpu.py --model {{MODEL}} --image data/images/test/实际文件名.jpg --out result.json --conf .25 --ov-mode {{MODE}}
python scripts/bench_exp3.py --model {{MODEL}} --ov-mode {{MODE}}
python scripts/eval_detail.py --model {{MODEL}}
python scripts/native_val.py --models models/a2_original.pt,{{MODEL}}
```

Python接口：将scripts加入sys.path，from resolution_runtime import Detector；det=Detector(model_path,conf=.25,ov_mode="{{MODE}}")；det(img_bgr)返回原图xyxy、score、class数组；predict_batch接受BGR数组列表。
推理只支持.pt、.onnx和OpenVINO .xml。ORT只注册CPUExecutionProvider，OpenVINO固定CPU，PyTorch模型固定.cpu()。

## 移机安装

```powershell
python -m pip install torch torchvision --index-url https://download.pytorch.org/whl/cpu
python -m pip install -r requirements.txt
```

依赖目录不放入压缩包。源码会先使用当前环境/本目录dependencies，再使用原项目已配置的CPU依赖。
提供完整原始train2158、val173、test190图片和标签。native_val.py会按当前路径生成data.yaml。

## 导出与量化复现

```powershell
python scripts/export_fp32.py
python scripts/export_fp16.py
python scripts/export_quant.py
python scripts/quant_ov_dfl.py
python scripts/eval_detail.py --validation-matrix
python scripts/lock_selection.py
```

这些命令会重建相应导出物与选择记录，请先备份已交付结果。原始A2权重不应改写。
所有校准使用原始train；val校准E1只作诊断。模型选择与测试标签分离。

## 证据与边界

- results/cpu_comparison.csv/json：CPU统一表；bench_*.json保留100次单张、20次B32原始计时与1000次RSS采样。
- results/cpu_recommendation.json：默认CPU方案及相对原A2的收益。
- results/eval_*.json、pred_*.npz：COCO、分层、噪声和预测归档；native_*.json独立列出原生指标。
- results/verification_cpu.json：原件校验、动态batch、宽高比、CPU接口与预测一致性。
- 标准对照4线程/640输入；额外CPU执行调优比较2/4/8线程及Conv-BN融合、channels_last；576/512输入另按验证AP50-95损失<=1pp筛选，实际配置在models/cpu_tuned_config.json或调优IR目录中。
- 主方向是3.1.4 CPU推理加速；另有3.1.1量化实验。未将剪枝、蒸馏或鲁棒性训练列为完成。
- 计时从内存JPEG到CPU检测框，排除磁盘、冷启动与视频/Web；不等于完整视频应用FPS。
- 历史集合含同源视频，AP-S只有1个目标；不据此作跨比赛泛化结论。
- 实验二报告的0.418与本次原始test评价口径不同，不能直接相减当作优化收益。

成员分工留空。
