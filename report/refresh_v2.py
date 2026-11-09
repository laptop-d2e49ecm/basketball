# -*- coding: utf-8 -*-
"""实验3报告 v2 刷新：把 aug0 缺陷修复前的 v1 数字整链替换为 v2 重训版（A2′ 基座）。

输入：report/实验3报告.docx（v1 定稿，组内已在 Word 中手工定稿封面/表号/表7）
输出：report/实验3报告_v2.docx（原件不动）
为什么不重跑 .report_build/generate_report.js：定稿含 Word 手工修改且 apply_edits.py 依赖的
模板已不在仓库，重新生成会丢失这些修改；故在定稿上按段落精准替换。

数字来源（全部实测记录，脚本直接读取）：
  models/exp2_v2/eval_test190.json      A1′/A2′/M1′ 与蒸馏 dis3/6/9（test 190）
  models/exp3_v2/quant_chain_v2.json    ONNX FP32 / INT8 E1/E2/E4 / 叠加
  models/exp3_v2/eval_detail_v2.json    分层 AP / 逐图 ΔAP / 噪声
  models/exp3_v2/overfit_check.json     训练帧子集 vs 测试集
  models/exp3_v2/protocol_check.json    PyTorch(rect) 与 ONNX(640) 口径差核查
P2（速度线）章节为 v1 权重实测，本轮未重跑：数字逐字保留，仅改与精度线 v2 结论冲突的措辞。
用法：.venv/Scripts/python.exe report/refresh_v2.py
"""
import copy
import json
import os

import docx
from docx.opc.packuri import PackURI
from docx.oxml.ns import qn
from PIL import Image

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))  # report/ -> 仓库根
SRC = os.path.join(ROOT, "report", "实验3报告.docx")
DST = os.path.join(ROOT, "report", "实验3报告_v2.docx")
V2 = os.path.join(ROOT, "models", "exp3_v2")
EMU = 914400  # 1 英寸


def load(p):
    with open(os.path.join(ROOT, p), encoding="utf-8") as f:
        return json.load(f)


EV = {r["name"]: r for r in load("models/exp2_v2/eval_test190.json")["results"]}
QC = {r["name"]: r for r in load("models/exp3_v2/quant_chain_v2.json")["quant_chain"]}
DET = load("models/exp3_v2/eval_detail_v2.json")
OFC = load("models/exp3_v2/overfit_check.json")
PCK = load("models/exp3_v2/protocol_check.json")
assert PCK["pt_rect_false_equals_onnx"], "PT(rect=False) 应与 ONNX 逐位一致，否则表注口径说明不成立"


def mb(rel):
    return os.path.getsize(os.path.join(ROOT, rel)) / 1e6


A1, A2, M1 = EV["A1_yolov8n"], EV["A2_yolov8n"], EV["A2_yolov8m"]
D3, D6, D9 = EV["蒸馏dis3"], EV["蒸馏dis6"], EV["蒸馏dis9"]
F32, E1, E2, E4 = QC["A2′ ONNX FP32"], QC["A2′ INT8 E1(val173)"], QC["A2′ INT8 E2(train500)"], QC["A2′ INT8 E4(per-ch)"]
D6F, D6I = QC["dis6 ONNX FP32"], QC["dis6+INT8 叠加"]
SZ_F32 = mb("models/exp3_v2/models/a2v2_fp32.onnx")
SZ_E1 = mb("models/exp3_v2/models/a2v2_int8_val173.onnx")
RED = (1 - SZ_E1 / SZ_F32) * 100  # 体积压缩率按字节计
pp = lambda a, b: (a - b) * 100  # noqa: E731
f4 = lambda v: f"{v:.4f}"  # noqa: E731
DA = DET["per_image_delta_ap"]
SELF_F32 = DET["fp32"]["map50"]  # 自研评估器 FP32 mAP50

d = docx.Document(SRC)
P = d.paragraphs


# ---------- 工具：只改文字，保留段落格式与首 run 的字体 ----------
def set_runs(p, *texts):
    """重建 run；(text, True) 的引导语仅在原段首 run 本身加粗时才加粗——组内定稿的引导语均不加粗。"""
    donor = p.runs[0]._element.find(qn("w:rPr")) if p.runs else None
    orig_bold = bool(p.runs[0].bold) if p.runs else False
    for r in list(p.runs):
        r._element.getparent().remove(r._element)
    for t in texts:
        text, bold = (t if isinstance(t, tuple) else (t, False))
        r = p.add_run(text)
        if donor is not None:
            r._element.insert(0, copy.deepcopy(donor))
        if bold and orig_bold:
            r.bold = True


def find(prefix):
    hits = [i for i, p in enumerate(P) if p.text.startswith(prefix)]
    assert len(hits) == 1, f"段落定位不唯一/缺失: {prefix!r} -> {hits}"
    return P[hits[0]]


def para(prefix, *texts):
    set_runs(find(prefix), *texts)


def set_cell(c, text, bold=False):
    for extra in c.paragraphs[1:]:
        extra._element.getparent().remove(extra._element)
    set_runs(c.paragraphs[0], (text, bold))


def replace_image(p, img_path, width_in, height_in, idx):
    """就地换图：保留 relId，替换 blob 与显示尺寸（宽度=出图 figsize 宽度，文字 1:1 印刷）。"""
    rid = p._element.find(".//" + qn("a:blip")).get(qn("r:embed"))
    part = d.part.related_parts[rid]
    with open(img_path, "rb") as f:
        part._blob = f.read()
    ext = p._element.find(".//" + qn("wp:extent"))
    ext.set("cx", str(int(width_in * EMU)))
    ext.set("cy", str(int(height_in * EMU)))
    axt = p._element.find(".//" + qn("a:ext"))
    if axt is not None:
        axt.set("cx", str(int(width_in * EMU)))
        axt.set("cy", str(int(height_in * EMU)))
    if img_path.lower().endswith((".jpg", ".jpeg")):
        part.partname = PackURI(f"/word/media/imageV2_{idx}.jpg")
        part._content_type = "image/jpeg"  # ImagePart.content_type 无 setter


# ============ 一 / 三：数据与协议 ============
para("团队两人分工",
     "团队两人分工：精度线负责量化、特征蒸馏与误差分析；速度线负责复合损失蒸馏（v1 方法研究）、TensorRT FP16 GPU 部署与 CPU "
     "后端对照。两条线在同一测试集（test 190 原始帧）下汇总，共同为实验4 提供部署选型矩阵：体积优先的 CPU 场景用 INT8 ONNX，"
     "精度保守的 CPU 场景用 OpenVINO FP32，GPU 场景用 TensorRT FP16 引擎。")

para("实验4 的篮球 AI 解说系统",
     "实验4 的篮球 AI 解说系统要求在 Web 后端对视频流做实时目标检测，部署环境以 CPU 为主，因此压缩的首要目标是体积与延迟，"
     f"同时精度不能显著下降。实验2（v2 重训）的结论给出了两个锚点：部署候选 A2′（YOLOv8n，3.13M 参数 / 8.6 GFLOPs，"
     f"test 190 mAP50 {f4(A2['map50'])}）与精度上限 M1′（YOLOv8m，25.9M 参数，{f4(M1['map50'])}）。据此选择三个优化维度：")

para("量化管线",
     f"量化管线：A2′ best.pt → 导出 ONNX FP32（{SZ_F32:.1f}MB，输出形状 (1,5,8400)，含坐标/尺寸/得分解码）→ onnxruntime "
     "quantize_static（QDQ 格式，默认 per-tensor）→ INT8 ONNX。校准数据使用自定义 CalibReader，前处理与训练/推理严格一致"
     "（LetterBox 640×640、BGR→RGB、像素值 /255），避免校准分布与推理分布不一致引入的系统性误差。")

para("校准实验设计",
     "校准实验设计：E1（val 集 173 张原始帧，部署选型）、E2（train 集 500 张，验证校准量增益）、E4（per-channel 权重量化，"
     "验证精细化增益）三组对比。")

para("训练配置",
     "训练配置：教师 M1′ 全程冻结（eval + no_grad），学生以 A2′ 权重初始化；学习率 lr0=0.002（实验2 原训练 0.01 的 1/5，"
     "任务书口径）；12 epoch（任务书 10-15 区间）；cos_lr、seed=42、AMP 沿用 v1 蒸馏协议，保证 v1/v2 蒸馏结果可比"
     "（实验2 v2 重训为 Kaggle 训练脚本默认 seed=0、cos_lr=false，A1′/A2′/M1′ 三者同协议）；训练在 Kaggle T4 上完成。"
     "工具上采用 ultralytics 8.4 内置 DistillationModel，训练结束自动 fuse 剥离蒸馏包装，best.pt 即纯学生权重，"
     "可直接复用本实验量化管线。另设计蒸馏权重消融 dis ∈ {3, 6, 9} 三组对比。")

para("自研评估器",
     f"自研评估器（all-point 插值 AP）先以 A2′ FP32 ONNX 与 ultralytics 官方口径对齐验证（mAP50 {SELF_F32:.4f} 对 "
     f"{f4(F32['map50'])}，差 {abs(pp(SELF_F32, F32['map50'])):.2f}pp，来自插值方式与 max_det 设置的实现差异；"
     "v1 对齐时两者同为 0.419），证明评估器可靠后再承担 FP32/INT8 同口径的相对分析。分析手段包括：（1）COCO 风格分层 AP："
     "按真值框面积将目标分为小（<32²）/中（32²-96²）/大（>96²）三档（640×640 像素口径），跨档匹配予以忽略，用于定位量化误差"
     "集中的目标尺度；（2）逐图 ΔAP 分布：逐张图片计算 INT8 与 FP32 的 AP 差，绘制直方图；（3）噪声鲁棒性：对测试图注入 "
     "σ=0.02 高斯噪声后重新评估，验证量化模型的精度稳定性。")

para("口径说明：P2 评估所用",
     "口径说明：P2 评估所用 190 张原始帧即本报告表3 测试集（原始帧 test 划分，与训练集零重叠），其基线绝对精度（mAP50 97.95%）"
     f"为 v1 权重实测，与本轮 v2 基线（{f4(A2['map50'])}）同量级；v1 测试集混入缺陷副本导致数值偏低的原因及 v2 重训经过详见 5.1。"
     f"部署选型综合两条线：CPU 环境采用精度线 a2v2_int8_val173.onnx（{SZ_E1:.1f}MB），具备 GPU 的环境采用 TensorRT FP16 引擎"
     "（v2 由 A2′ 直接构建；v1 同一流水线实测单图 P50 未蒸馏 10.76ms、蒸馏学生 9.69ms）。")

# 3.2 首段：保留速度线 v1 方法描述，补一句 v2 分工（蒸馏不重复做的理由）
_p = find("速度线方案与两条线的关系")
_lead = "速度线方案与两条线的关系。"
assert _p.text.startswith(_lead)
set_runs(_p, (_lead, True), _p.text[len(_lead):] +
         "v2 重训后，蒸馏是否有效由精度线在同一师生对（M1′→A2′）上的消融统一判定（强基座下无增益，见五.4），速度线不再重复"
         "蒸馏，部署学生改为 A2′ 直接构建 TensorRT FP16 引擎；本节复合损失蒸馏（含温度系数考察）作为 v1 方法研究保留，"
         "它是本报告落实任务书“软标签 KL + 温度 T”字面要求的部分。")

# ============ 四：难点 ============
para("1. 量化算子选择",
     ("1. 量化算子选择与校准集优化。", True),
     "检测头解码输出的数值范围跨度极大（0-640 像素与 0-1 概率共存），直接全图量化会使分数全部舍入 0；通过按算子类型排除非加权"
     f"算子解决。校准集实验表明 val 173 张已充分，train 500 张无增益（mAP50 {f4(E2['map50'])} 对 {f4(E1['map50'])}，"
     f"分布一致性比数量更重要），per-channel 只换来 mAP50-95 {pp(E4['map50_95'], E1['map50_95']):+.2f}pp 而 mAP50 "
     f"{pp(E4['map50'], E1['map50']):+.2f}pp，无一致收益——说明本任务量化难度不在校准精度，而在结构选择。")

para("3. 蒸馏与量化叠加",
     ("3. 蒸馏与量化叠加的精度敏感现象。", True),
     f"A2′ 直接量化的定位代价为 mAP50-95 {pp(E1['map50_95'], F32['map50_95']):+.2f}pp（{f4(F32['map50_95'])}→"
     f"{f4(E1['map50_95'])}），蒸馏学生 dis=6 再量化为 {pp(D6I['map50_95'], D6F['map50_95']):+.2f}pp（{f4(D6F['map50_95'])}→"
     f"{f4(D6I['map50_95'])}），多出约 {abs(pp(D6I['map50_95'], D6F['map50_95']) - pp(E1['map50_95'], F32['map50_95'])):.1f}pp："
     "蒸馏使学生特征拟合教师分布，对权重舍入扰动的容限略有下降，两类压缩的组合存在轻微交互损失，提示叠加使用需重校准或量化感知"
     "训练（QAT）。v1 在缺陷测试集上曾观察到 0.6pp 的交互损失，v2 证实其中大部分为评测伪影（与 v1 干净口径复核的 -1.9pp 对 "
     "-1.7pp 一致）。")

para("4. 量化误差的结构性分布",
     ("4. 量化误差的结构性分布。", True),
     f"误差并非均匀分布：判定精度全档无损（中目标 AP50 {DET['fp32']['ap50_medium']:.3f}→{DET['int8']['ap50_medium']:.3f}、"
     f"大目标 {DET['fp32']['ap50_large']:.3f}→{DET['int8']['ap50_large']:.3f}），代价集中显形于定位精度（mAP50-95 "
     f"{pp(E1['map50_95'], F32['map50_95']):+.2f}pp）；逐图 ΔAP 中 {DA['n_unchanged']}/{DA['n_images']} 张完全不变、"
     f"|Δ|≤0.05 的达 {DA['n_within_0.05']}/{DA['n_images']} 张——误差具有明确的结构性而非普遍性。v1 曾测得“大目标 -3.0pp”"
     "的集中现象，v2 证实系 _aug0 错位标注的伪影（详见 5.1），这也构成一次方法教训：误差归因结论依赖评测集质量。")

# ============ 五.1 ============
para("全集口径",
     f"口径说明：test 190 张原始帧（1792 框），所有行同一测试集，与实验2 终评同一把尺子；全部模型基于 v2 数据重训（实验1 增强缺陷"
     "修复后，训练集 4316 = 2158 原始帧 + 2158 修复增强副本，增强副本只进训练集），横向可比。各版本汇总如表3。")

para("表3 模型优化前后", "表3 模型优化前后对比总表（test 190 原始帧，v2 单口径）")

PT_N = mb("models/exp2_v2/A2_yolov8n/weights/best.pt")
rows3 = [
    ["模型版本", "精度", "体积(MB)", "参数量(M)", "FLOPs(G)", "mAP50", "mAP50-95", "P", "R"],
    ["A2′ YOLOv8n（PyTorch，部署基座）", "FP32", f"{PT_N:.1f}", "3.13", "8.6", f4(A2["map50"]), f4(A2["map50_95"]),
     f4(A2["P"]), f4(A2["R"])],
    ["A2′ YOLOv8n（ONNX，量化基准）", "FP32", f"{SZ_F32:.1f}", "3.13", "8.6", f4(F32["map50"]), f4(F32["map50_95"]),
     f4(F32["P"]), f4(F32["R"])],
    ["A1′ YOLOv8n（无增强消融）", "FP32", f"{mb('models/exp2_v2/A1_yolov8n/weights/best.pt'):.1f}", "3.13", "8.6",
     f4(A1["map50"]), f4(A1["map50_95"]), f4(A1["P"]), f4(A1["R"])],
    ["INT8 E1（val 173 校准，部署选型）", "INT8", f"{SZ_E1:.1f}", "3.13", "8.6", f4(E1["map50"]), f4(E1["map50_95"]),
     f4(E1["P"]), f4(E1["R"])],
    ["INT8 E2（train 500 校准）", "INT8", f"{mb('models/exp3_v2/models/a2v2_int8_train500.onnx'):.1f}", "3.13", "8.6",
     f4(E2["map50"]), f4(E2["map50_95"]), f4(E2["P"]), f4(E2["R"])],
    ["INT8 E4（per-channel）", "INT8", f"{mb('models/exp3_v2/models/a2v2_int8_val173_pc.onnx'):.1f}", "3.13", "8.6",
     f4(E4["map50"]), f4(E4["map50_95"]), f4(E4["P"]), f4(E4["R"])],
    ["A2′ 蒸馏（dis=3）", "FP32", f"{mb('models/exp3_v2/exp3-v3/a2v2_distill_dis3_best.pt'):.1f}", "3.13", "8.6",
     f4(D3["map50"]), f4(D3["map50_95"]), f4(D3["P"]), f4(D3["R"])],
    ["A2′ 蒸馏（dis=6，三组最优）", "FP32", f"{mb('models/exp3_v2/exp3-v3/a2v2_distill_dis6_best.pt'):.1f}", "3.13", "8.6",
     f4(D6["map50"]), f4(D6["map50_95"]), f4(D6["P"]), f4(D6["R"])],
    ["A2′ 蒸馏（dis=9）", "FP32", f"{mb('models/exp3_v2/exp3-v3/a2v2_distill_dis9_best.pt'):.1f}", "3.13", "8.6",
     f4(D9["map50"]), f4(D9["map50_95"]), f4(D9["P"]), f4(D9["R"])],
    ["蒸馏 dis=6 + INT8（叠加）", "INT8", f"{mb('models/exp3_v2/models/dis6v2_int8_val173.onnx'):.1f}", "3.13", "8.6",
     f4(D6I["map50"]), f4(D6I["map50_95"]), f4(D6I["P"]), f4(D6I["R"])],
    ["蒸馏(T6)+TRT FP16（速度线，v1 权重）", "FP16", "9.3", "3.13", "8.6", "0.9766", "0.7286", "—", "—"],
    ["M1′ YOLOv8m（教师）", "FP32", f"{mb('models/exp2_v2/A2_yolov8m/weights/best.pt'):.1f}", "25.9", "79.3",
     f4(M1["map50"]), f4(M1["map50_95"]), f4(M1["P"]), f4(M1["R"])],
]
t3 = d.tables[3]
assert len(t3.columns) == 9 and t3.rows[0].cells[0].text.startswith("模型版本")
while len(t3.rows) > len(rows3):
    t3._tbl.remove(t3.rows[-1]._tr)
for ri, row in enumerate(rows3):
    for ci, v in enumerate(row):
        set_cell(t3.rows[ri].cells[ci], v, bold=(ri == 0))

para("注：PyTorch .pt 为半精度存储",
     f"注：PyTorch .pt 为半精度存储，ONNX 为 FP32 全精度，故 .pt {PT_N:.1f}MB 小于 ONNX {SZ_F32:.1f}MB；量化体积与精度代价一律"
     f"以 ONNX FP32 为基准（同一推理路径）。PyTorch 行按 ultralytics 默认 rect 口径评测（640 图补边至 672 推理），ONNX 行为静态 "
     f"640 输入；两者原始输出逐位等价（框差 <{PCK['raw_output_equivalence']['max_abs_box_px']:.3f}px），PyTorch 改用 640 输入后与 "
     "ONNX 结果完全一致，故两行 0.1-0.2pp 的差异系推理尺寸口径所致，不跨行比较。P/R 取 ultralytics 验证的 F1 最优置信度处。"
     "速度线行为 P2 自研 COCO 口径在 TRT FP16 管线上实测（v1 权重，待以 v2 权重重放）。")

para("干净口径复核与数据质量说明",
     ("数据缺陷发现与 v2 重训（本报告全部数字的基线）。", True),
     "本实验中期复核发现实验1 数据增强缺陷：torchvision v2 变换以 numpy 数组输入时图像不被变换、标注框却被变换，全部 _aug0 副本"
     "实为原图加随机平移的错位标注；v1 全部模型训练时混入了这些副本（约占训练集一半），当时的 test 380 也有一半是此类副本，"
     "训练与评测同源污染。据此完成 v2 整链重做：修复增强脚本（改为 PIL 直传）并以三层校验（逐像素差、仿射对齐后框 IoU 中位 0.96、"
     "合成图单测）重新生成全部副本，坏数据归档不删；划分改为增强副本只进训练集（train 4316 / val 173 / test 190 原始帧，原始帧"
     "划分不变）；A1′/A2′/M1′ 同协议重训。v2 下两项关键修正：其一，增强收益由负转正——A2′（"
     f"{f4(A2['map50'])}/{f4(A2['map50_95'])}）对比 A1′（{f4(A1['map50'])}/{f4(A1['map50_95'])}）为 "
     f"{pp(A2['map50'], A1['map50']):+.2f}pp mAP50 / {pp(A2['map50_95'], A1['map50_95']):+.2f}pp mAP50-95 / "
     f"{pp(A2['R'], A1['R']):+.2f}pp R，增强策略本身有效，v1 得出的“增强无效”系标注污染伪影；其二，0.99 级精度不是过拟合——"
     f"训练帧子集 200 张复测 mAP50 {f4(OFC['train200_seen']['map50'])}，仅比测试集高 {OFC['gap_pp']['map50']:.2f}pp，"
     f"mAP50-95 差 {OFC['gap_pp']['map50_95']:.2f}pp 属正常泛化差距；高分来自任务本身（单类、近景、目标清晰）。需如实说明的"
     "泛化边界：全部原始帧来自 7 场比赛视频（30 个片段），测试集 3 个片段未在训练中出现，但所属 2 场比赛均有其他片段进入训练集，"
     "故 0.99 代表“已见比赛的新片段”水平，跨比赛、跨转播风格的泛化未经验证。本实验全部量化、蒸馏与误差分析均基于 v2 基座重做。")

# ============ 五.2 / 五.3 ============
para("如图1 所示",
     f"如图1 所示，INT8 量化将模型体积从 {SZ_F32:.1f}MB 压缩至 {SZ_E1:.1f}MB（-{RED:.1f}%，接近 INT8 相对 FP32 的理论上限 "
     f"75%），判定精度 mAP50 无损（{f4(F32['map50'])}→{f4(E1['map50'])}，{pp(E1['map50'], F32['map50']):+.2f}pp），"
     f"真实代价集中于定位精度 mAP50-95（{f4(F32['map50_95'])}→{f4(E1['map50_95'])}，"
     f"{pp(E1['map50_95'], F32['map50_95']):+.2f}pp）。按任务书“精度损失 ≤2%”判定：以主指标 mAP50 计相对损失 0.02%，达标；"
     f"以更严的 mAP50-95 计相对损失 {abs(pp(E1['map50_95'], F32['map50_95'])) / F32['map50_95']:.1f}%，超出——如实分项记录。"
     "三组校准实验（E1/E2/E4）mAP50 差异 <0.3pp、mAP50-95 差异 <0.4pp，证明对本任务而言校准集选择不敏感，部署选型采用 E1"
     "（a2v2_int8_val173.onnx）。")

para("分层 AP 结果",
     f"分层 AP 结果（图2）显示判定精度各档均无损：中目标 AP50 {DET['fp32']['ap50_medium']:.3f}→"
     f"{DET['int8']['ap50_medium']:.3f}（n={DET['fp32']['n_gt_medium']}），大目标 {DET['fp32']['ap50_large']:.3f}→"
     f"{DET['int8']['ap50_large']:.3f}（n={DET['fp32']['n_gt_large']}，INT8 略高，属小样本统计波动），小目标仅 "
     f"{DET['fp32']['n_gt_small']} 框无统计意义。结合 mAP50-95 下降 {abs(pp(E1['map50_95'], F32['map50_95'])):.2f}pp，"
     "量化影响的是高 IoU 阈值下的框回归精度而非检测判定——框仍能与真值重叠过半，但边界精度轻微劣化、在 0.75 以上的严格阈值处"
     f"匹配减少。逐图 ΔAP 直方图（图3）进一步表明误差非普遍：{DA['n_images']} 张图中 {DA['n_unchanged']} 张 ΔAP 完全为 0，"
     f"|Δ|≤0.05 的达 {DA['n_within_0.05']} 张，均值 {DA['mean']:+.4f}，最大单图波动 {DA['min']:+.3f}/{DA['max']:+.3f}。"
     "v1 曾据缺陷测试集得出“大目标 -3.0pp”的集中结论，v2 证实为标注噪声伪影：错位标注使大框匹配失败主导了当时的大目标 AP。"
     "该分析对应任务书“分析误差集中的类别”要求：本任务单类，误差集中的维度是定位精度而非目标尺寸。")

para("噪声鲁棒性（图4）",
     f"噪声鲁棒性（图4）：注入 σ=0.02 高斯噪声后，FP32 与 INT8 的 mAP50 分别从 {DET['fp32']['map50']:.4f}/"
     f"{DET['int8']['map50']:.4f} 降至 {DET['fp32_noise']['map50']:.4f}/{DET['int8_noise']['map50']:.4f}，"
     f"降幅 {abs(pp(DET['fp32_noise']['map50'], DET['fp32']['map50'])):.2f}pp/"
     f"{abs(pp(DET['int8_noise']['map50'], DET['int8']['map50'])):.2f}pp，两者均基本无损，说明量化未放大噪声敏感性，"
     "精度稳定性满足实际部署场景需求。")

# ============ 五.4 蒸馏：结论反转 ============
para("蒸馏权重消融",
     f"蒸馏权重消融（图5）：教师 M1′（{f4(M1['map50'])}/{f4(M1['map50_95'])}）→ 学生以 A2′ 初始化，dis=3/6/9 三组 test 190 "
     f"结果分别为 {f4(D3['map50'])}/{f4(D3['map50_95'])}、{f4(D6['map50'])}/{f4(D6['map50_95'])}、"
     f"{f4(D9['map50'])}/{f4(D9['map50_95'])}——三组均未超过未蒸馏基座 A2′（{f4(A2['map50'])}/{f4(A2['map50_95'])}），"
     f"最优 dis=6 距基座 {pp(D6['map50'], A2['map50']):+.2f}pp mAP50 / {pp(D6['map50_95'], A2['map50_95']):+.2f}pp mAP50-95。"
     "结论为诚实负结果：在 0.99 量级的强基座上，12 epoch 特征蒸馏不再产生增益。与 v1 对照：v1 基座受缺陷数据拖累（干净口径 "
     "mAP50-95 0.734），dis=9 曾有 +0.2pp 增益；v2 基座提升到 0.7585 后增益消失——基座越强，蒸馏的边际收益越小（两个数据点的"
     "对照，尚不足以给出定量规律）。训练过程（图6）支持“未能突破”而非“训练失败”：三组验证 mAP50-95 首轮即约 0.80（以基座"
     "初始化），第 2-6 轮受微调扰动回落至 0.763-0.786，后段回升至 0.805-0.811，逼近而未超过基座验证水平 0.814；蒸馏项"
     "（除以权重后）在 0.35-1.0 之间波动、无持续下降，第 4、11 轮三组同步出现尖峰（相同随机种子、相同数据顺序所致），"
     "说明学生特征未被持续拉近教师。体积与架构不变（学生 6.5MB，为教师 52.0MB 的 1/8），部署不采用蒸馏学生。")

para("任务书 3.1.3 指标复核",
     "任务书 3.1.3 指标复核（按 v2 如实判定）：精度项一达一未达——“相对教师损失 ≤1%”以 mAP50 计 "
     f"{pp(D6['map50'], M1['map50']):+.2f}pp 达标（以更严的 mAP50-95 计 {pp(D6['map50_95'], M1['map50_95']):+.2f}pp 未达）；"
     f"“优于同量级未蒸馏模型”未达成（dis=6 {f4(D6['map50'])}/{f4(D6['map50_95'])} 均低于 A2′ "
     f"{f4(A2['map50'])}/{f4(A2['map50_95'])}）。v1 曾以 0.422 对 0.419 判定双达标，系缺陷数据弱基座下的结论，v2 不再成立。"
     "速度与体积两项属结构性不适用——学生结构与 A2′ 完全一致（3.13M 参数 / 8.6 GFLOPs 不变），蒸馏仅更新权重、不改变计算量与"
     "文件规模（P2 在同一 TensorRT FP16 流水线上测得未蒸馏学生 10.757 ms、蒸馏学生 9.69 ms，约 -9.9%，未达 ≥20% "
     "门槛）。两项指标的实际收益分别由任务 3.1.4（PyTorch 23.08 ms → TensorRT FP16 9.69 ms，-58.0%，P2 实测）与任务 3.1.1 "
     f"量化（ONNX {SZ_F32:.1f} MB → {SZ_E1:.1f} MB，-{RED:.1f}%）承担，按任务书分项如实判定。")

# ============ 五.5 叠加 ============
para("叠加实验",
     f"叠加实验：将蒸馏 dis=6 学生（ONNX FP32 {f4(D6F['map50'])}/{f4(D6F['map50_95'])}）再做 E1 同口径 INT8 量化，得到 "
     f"{f4(D6I['map50'])}/{f4(D6I['map50_95'])}（{mb('models/exp3_v2/models/dis6v2_int8_val173.onnx'):.1f}MB）——体积目标达标，"
     f"mAP50 无损，定位代价 {pp(D6I['map50_95'], D6F['map50_95']):+.2f}pp，较 A2′ 直接量化"
     f"（{pp(E1['map50_95'], F32['map50_95']):+.2f}pp）多约 0.2pp，交互损失轻微；由于蒸馏本身无增益，叠加方案与直接量化基本"
     f"持平（{f4(D6I['map50_95'])} 对 {f4(E1['map50_95'])}），不构成更优部署选项。目标一致性：量化预期“-75% 体积且精度损失 "
     f"≤2%”，实测 -{RED:.1f}%、mAP50 无损（定位口径代价见五.2），与目标一致；蒸馏预期“损失 ≤1% 且优于未蒸馏同量级”，v2 实测"
     "仅前者以 mAP50 计达成（负结果，见五.4）；叠加“近似可加”成立。与实际应用的关联：精度线向实验4 Web 系统交付的 CPU 部署模型为 "
     f"a2v2_int8_val173.onnx（{SZ_E1:.1f}MB / mAP50 {f4(E1['map50'])}），替换 v1 的 a2_int8_val346.onnx，输入输出形状"
     "（1×3×640×640 → 1×5×8400）不变、可原位替换；若部署环境具备 GPU，可切换 P2 的 TensorRT FP16 引擎（单图 P50 9.69ms，"
     "见 3.2 与五.6）获得更高实时吞吐。")

# ============ 五.6 / 五.7（P2）：只改与 v2 冲突的措辞 ============
para("速度线最终交付为蒸馏学生",
     "速度线最终交付为蒸馏学生 + TensorRT FP16 端到端组合方案，与实验二未优化 A2 PyTorch FP32 基线在同一 190 张测试集（与表3 "
     "同一测试集）上对照；Precision/Recall 按 conf=0.25、IoU=0.50 统计，mAP 按 COCO 口径汇总。本节与五.7 的全部数字为速度线"
     "基于 v1 权重的实测，已与速度线交付包的原始 results 记录逐一核对一致。v2 部署学生改为 A2′ 直接构建引擎（不再重复蒸馏，"
     "理由见 3.2）：推理延迟与吞吐主要由网络结构决定（v2 与 v1 结构完全相同），同一流水线下 v1 未蒸馏与蒸馏两版引擎实测分别为 "
     "10.76/9.69ms，均远优于任务书门槛；精度行以 A2′ 引擎实测为准。")

para("精度呈方向分化",
     "精度呈方向分化：定位质量指标 mAP50-95 与 Recall 分别提高 0.47 与 0.50 个百分点，Precision 与 mAP50 小幅下降 0.95 与 "
     "0.29 个百分点——蒸馏与半精度组合改善了框回归质量，同时判定阈值附近的取舍发生变化，不能以单一指标概括。需要说明的是，"
     "该收益建立在 v1 弱基座上且未设同轮次的非蒸馏对照：起点 A2 v1 本身受缺陷数据影响，在干净原始帧上继续训练 12 轮即可能"
     "带来部分提升，故不能单独归因于蒸馏；精度线 v2 在同一师生对上的消融显示强基座下蒸馏无增益（见五.4），v2 部署因此不采用"
     "蒸馏学生。")

para("与精度线的交叉验证与部署矩阵",
     ("与精度线的交叉验证与部署矩阵。", True),
     "P2 独立测得 INT8 的验证集 AP50-95 代价为 1.58pp（v1 权重），精度线 v1 干净口径实测 1.7pp、v2 复测 "
     f"{abs(pp(E1['map50_95'], F32['map50_95'])):.2f}pp——两条线、两个数据版本得到量级一致的量化定位代价，互为印证。"
     "据此形成部署矩阵：体积优先的 CPU 场景（实验4）采用精度线 a2v2_int8_val173.onnx"
     f"（{SZ_E1:.1f}MB，mAP50 无损、mAP50-95 {pp(E1['map50_95'], F32['map50_95']):+.2f}pp）；精度保守或只需后端加速的 CPU "
     "场景采用 OpenVINO FP32（精度无损、吞吐 +99.5%）；具备 GPU 的场景采用 A2′ TensorRT FP16 引擎（v1 同流水线实测单图 "
     "9.69–10.76ms，v2 以重建后实测为准）。两条线的"
     "推理入口已统一为端到端 infer 脚本（预处理→多后端推理→NMS→坐标还原），实验4 Web 系统直接集成。任务书 3.1.4 的 CPU 侧"
     "门槛未全部达到（单图延迟 -40% 未达标，实测 -22.4%；批量吞吐 +50% 达标，实测 +99.5%），GPU 侧全部达标（见五.6）——"
     "按任务书分项如实判定，不以单项达标替代联合判据。")

# ============ 五.8 关联分析 ============
para("实验 1 数据特点对量化误差的影响",
     ("实验 1 数据特点对量化误差的影响。", True),
     "本实验量化误差的分布与实验 1 数据构成强相关，可归纳为三点。其一，场景单一使判定精度饱和：数据来自 7 场比赛的连续视频抽帧，"
     "相邻帧高度相似，单类近景目标下模型精度本身即达 0.99 级，判定精度已无区分空间，量化代价只能显形于更严的定位口径"
     f"（mAP50-95）；同理校准集不敏感——val 173 与 train 500 来自同分布，E1/E2 的 mAP50 仅差 "
     f"{abs(pp(E1['map50'], E2['map50'])):.1f}pp。其二，目标尺寸长尾分布：test 190 中中目标 {DET['fp32']['n_gt_medium']} 框、"
     f"大目标 {DET['fp32']['n_gt_large']} 框、小目标仅 {DET['fp32']['n_gt_small']} 框，大目标样本少使该档 AP 统计波动大"
     f"（v2 中 INT8 大目标反升即属此类），逐图 ΔAP 多数为 0（{DA['n_unchanged']}/{DA['n_images']}），稀疏帧型上的量化误差"
     "无法被平均摊薄。其三，数据质量决定误差归因的可信度：v1 曾在含错位标注的测试集上得出“大目标 -3.0pp”的结构性结论，"
     "v2 复核证实为标注噪声伪影（各档判定均无损）——正是两个数据版本的对照，确立了“量化影响框回归而非检测判定”的结论。"
     "三点共同表明：量化误差不是模型的孤立属性，而是模型与数据分布的联合结果，部署前应保证校准集与目标场景在尺寸、帧型多样性上"
     "一致。")

para("实验 2 模型特性对剪枝敏感性",
     ("实验 2 模型特性对剪枝敏感性的影响（定性关联分析）。", True),
     "任务书以 ResNet 的相加式残差结构为参照——恒等映射使残差支路可被整体剪除、精度回退平缓且可经微调恢复。本实验对象 A2′"
     "（YOLOv8n）与之存在三点结构性差异，剪枝敏感性显著更高。其一，残差形式不同：主干 C2f 模块的多分支 Bottleneck 输出经 "
     "Concat 拼接而非逐元素相加，通道冗余分散于各拼接分支，剪除任一支路都会削弱拼接特征的通道表达，不存在“整支冗余、剪之无损”"
     "的恒等通路。其二，模型本已高度紧凑：A2′ 仅 3.13M 参数 / 8.6 GFLOPs（约为教师 YOLOv8m 的 1/8），冗余度远低于 ResNet-50 "
     "级骨干，同等剪枝率下精度代价更高。其三，解耦检测头对剪枝非对称敏感：DFL 分布式框回归分支对通道裁剪的敏感度远高于分类"
     f"分支——本实验 INT8 量化已证实精度代价集中于回归定位（mAP50 无损而 mAP50-95 {pp(E1['map50_95'], F32['map50_95']):+.2f}pp），"
     "通道剪枝预计呈现同样的结构性风险；且浅层检测支路（P3）通道规模最小，剪枝易造成小目标召回的不可逆损失。据此，在体积目标"
     f"已由 INT8 达成（-{RED:.1f}%）、A2′ 基座精度已达教师的 {A2['map50'] / M1['map50'] * 100:.1f}%（mAP50）的情况下，"
     "剪枝的边际收益低而结构性风险高——本实验选择“量化+蒸馏”路线、将结构化剪枝及剪枝率-精度敏感性曲线留作后续工作"
     "（见六、展望），该取舍即实验 2 模型特性驱动的优化维度决策。")

# ============ 六 ============
para("本实验完成了篮球球员检测模型的三维度优化",
     "本实验完成了篮球球员检测模型的轻量化与推理优化闭环，并在中期完成一次数据缺陷的发现与全链重做：实验1 增强缺陷（图像未变换、"
     "标注错位）被发现、修复并以三层校验重建，A1′/A2′/M1′ 同协议重训（test 190：A2′ "
     f"{f4(A2['map50'])}/{f4(A2['map50_95'])}、M1′ {f4(M1['map50'])}/{f4(M1['map50_95'])}），增强收益由 v1 的负值修正为"
     f"真实正收益（{pp(A2['map50'], A1['map50']):+.2f}pp mAP50 / {pp(A2['map50_95'], A1['map50_95']):+.2f}pp mAP50-95），"
     f"全部结论重建于单一干净口径之上。量化主线：INT8 静态量化实现体积 -{RED:.1f}%（{SZ_F32:.1f}→{SZ_E1:.1f}MB），mAP50 "
     f"无损、mAP50-95 代价 {abs(pp(E1['map50_95'], F32['map50_95'])):.2f}pp，校准集不敏感，蒸馏+量化叠加交互损失约 0.2pp；"
     f"误差分析显示判定全档无损、{DA['n_unchanged']}/{DA['n_images']} 张逐图 ΔAP 为 0、噪声下降幅 <0.1pp。蒸馏主线为诚实"
     "负结果：强基座上 dis=3/6/9 均未超基座，与 v1 弱基座上的小幅增益对照，表明基座越强、蒸馏边际收益越小。速度线以 TensorRT "
     "FP16 端到端流水线实现单图 P50 延迟 -53.4%（未蒸馏引擎）～-58.0%（蒸馏学生引擎）、Batch 32 吞吐 2.79～3.64 倍"
     "（v1 权重实测；延迟主要由结构决定，v2 以 A2′ 引擎实测为准）。"
     "所有结论均在统一版本与口径下得出，脚本与评测记录随交付包提供，可复现、可追溯。")

para("展望：后续可将结构化剪枝",
     "展望：后续可将结构化剪枝+微调引入 YOLOv8 压缩管线，弥补本次未实施的剪枝任务；蒸馏方向可尝试更长训练、更强或异构教师，"
     "检验强基座下蒸馏增益是否确已饱和；针对量化的定位代价，可尝试量化感知训练（QAT）或令框回归分支保持高精度的混合精度方案；"
     "泛化方面应补充未见比赛、不同转播机位的测试集；并在边缘设备（如树莓派）上验证 INT8 模型的实际吞吐与内存表现。")

# ============ 图 1-7 ============
FIGS = [  # (图注前缀, 文件, 宽英寸, 高英寸, 新图注)；尺寸与 make_figures_v2.FIG_W 一致
    ("图1 ", "fig1_quant_overview.png", 6.0, 2.9, "图1 量化主线总览：体积与相对 FP32 的精度变化（test 190）"),
    ("图2 ", "fig2_layered_ap.png", 4.8, 3.0, "图2 按目标尺寸分层的量化误差：判定精度各档均无损（test 190）"),
    ("图3 ", "fig3_delta_hist.png", 4.8, 3.0,
     f"图3 逐图 ΔAP50 分布：{DA['n_unchanged']}/{DA['n_images']} 张完全不变（test 190）"),
    ("图4 ", "fig4_noise.png", 4.8, 3.0, "图4 噪声鲁棒性：σ=0.02 高斯噪声下两类模型均基本无损（test 190）"),
    ("图5 ", "fig5_distill.png", 6.0, 2.9, "图5 蒸馏消融：强基座下三组均未超过未蒸馏基座（test 190）"),
    ("图6 ", "fig6_curves.png", 6.0, 2.9, "图6 蒸馏训练过程：验证精度回升至基座附近但未突破，蒸馏项无持续下降"),
    ("图7 ", "fig7_qualitative.jpg", 5.2, 5.2, "图7 A2′ 部署基座定性检测效果（test 样例，conf≥0.35，左上角为预测/标注人数）"),
]
for k, (prefix, fname, w, h, cap) in enumerate(FIGS):
    cap_p = find(prefix)
    ci = [i for i, p in enumerate(P) if p is cap_p][0]
    img_p = P[ci - 1]
    assert img_p._element.find(".//" + qn("a:blip")) is not None, f"{prefix} 上一段不是图片"
    with Image.open(os.path.join(V2, "figures", fname)) as im:
        h = w * im.height / im.width  # 以实际像素比例定高，避免拉伸
    replace_image(img_p, os.path.join(V2, "figures", fname), w, h, k)
    set_runs(cap_p, cap)

d.save(DST)
print("saved:", DST)
