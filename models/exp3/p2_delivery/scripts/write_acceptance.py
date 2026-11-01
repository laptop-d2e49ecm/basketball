from pathlib import Path
import json,hashlib
P=Path(__file__).resolve().parents[1]
def load(f):return json.loads(f.read_text(encoding='utf-8'))
assert load(P/'results/final_verification.json')['passed']
s=load(P/'results/md_summary.json');c=s['comparisons']['same_GPU_TensorRT'];r=s['independent_repeats'][0]
checks={'single_latency_reduction_ge40':min(c['single_reduction_pct'],r['single_reduction_pct'])>=40,'batch32_latency_reduction_ge40':min(c['batch_reduction_pct'],r['batch_reduction_pct'])>=40,'batch32_fps_increase_ge50':min(c['fps_increase_pct'],r['fps_increase_pct'])>=50,'accuracy_difference_le1pp':max(abs(c['ap50_difference_pp']),abs(c['ap95_difference_pp']))<=1,'stability_1000_RSS_le5pct':s['rows'][2]['stability']['within_5pct']}
assert all(checks.values()),checks
t=load(P/'gpu/results/temperature_verification.json')
result={'primary_task':'3.1.4 GPU inference acceleration','all_primary_targets_passed':all(checks.values()),'target_checks':checks,'main_measurement':c,'independent_repeat':r,'temperature_study':{'screened':[5,8,10],'screening_epochs_each':1,'selected':t['selected_temperature'],'selected_full_epochs':12,'T6_reference_full_epochs':12},'CPU_role':'original baseline and requested ORT/OpenVINO comparison','GPU':'RTX3050 local actual execution','Kaggle_T4_executed':False,'supplemental_experiments':['static quantization E1-E5 and mixed precision','teacher/student distillation','scale AP, per-image error distribution and heatmap','fixed-seed noise tests','native Ultralytics cross-check','GPU-first API with OpenVINO fallback'],'not_claimed':['all six optimization directions selected','all supplemental quantitative goals passed','Kaggle T4 measurement','matched fine-tuning ablation'],'reference_sha256':{f.name:hashlib.sha256(f.read_bytes()).hexdigest() for f in (P/'references').glob('*') if f.is_file()}}
(P/'results/任务书与MD验收.json').write_text(json.dumps(result,ensure_ascii=False,indent=2),encoding='utf-8')
text=f"""# 优化说明与验收

主优化方向：任务3.1.4，GPU TensorRT FP16与推理流水线优化。对照模型为实验二原A2 YOLOv8n，使用同一GPU、数据和评价口径。

| 指标 | 主测 | 独立复测 | 要求 |
|---|---:|---:|---:|
| 单张延迟下降 | {c['single_reduction_pct']:.2f}% | {r['single_reduction_pct']:.2f}% | ≥40% |
| batch32延迟下降 | {c['batch_reduction_pct']:.2f}% | {r['batch_reduction_pct']:.2f}% | ≥40% |
| batch32吞吐提高 | {c['fps_increase_pct']:.2f}% | {r['fps_increase_pct']:.2f}% | ≥50% |

AP50与AP50-95最大变化 {max(abs(c['ap50_difference_pp']),abs(c['ap95_difference_pp'])):.2f} 个百分点，满足≤1个百分点。主方向速度及精度目标两轮均通过。

EXP3_IMPL_2P.md中的量化矩阵、m到n蒸馏、分层误差与噪声分析、统一测速和部署接口已纳入同一交付。温度T5/8/10各1轮等预算筛选，选中T={t['selected_temperature']}后续训至12轮；T6的12轮完整结果单独保留。

任务书要求六个方向至少选择一个。本交付以3.1.4作为完整验收方向，量化和蒸馏按实际指标列出，不将实验执行完成等同于每个补充目标全部达标。GPU主实验在本机RTX3050执行；Kaggle T4仅提供重建复现入口，未列为实测。成员分工按用户要求留空。

正式报告：[模型优化与对比验证](reports/实验3报告_模型优化与对比验证.pdf)。代码和复现入口见[README](README.md)。原始数值与逐项检查见results/任务书与MD验收.json、results/md_summary.json及gpu/results。
"""
(P/'优化说明与验收.md').write_text(text,encoding='utf-8');print('PRIMARY_TASK_ALL_TARGETS_PASSED')
