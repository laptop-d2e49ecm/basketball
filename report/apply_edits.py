# -*- coding: utf-8 -*-
"""实验3报告合并稿：换模板封面 + 删合并稿说明 + 新增五.8 关联分析 + 表6 加 ORT 列。"""
import copy
import docx
from docx.shared import Pt
from docx.oxml import OxmlElement
from docx.oxml.ns import qn
from docx.enum.text import WD_ALIGN_PARAGRAPH

SRC = 'docs/实验3报告_合并稿.docx'
TPL = 'report/模板_converted.docx'

d = docx.Document(SRC)
t = docx.Document(TPL)


def get_style(p_el):
    pPr = p_el.find(qn('w:pPr'))
    if pPr is None:
        return None
    ps = pPr.find(qn('w:pStyle'))
    return ps.get(qn('w:val')) if ps is not None else None


def set_run_text(r_el, text):
    for c in list(r_el):
        if c.tag not in (qn('w:rPr'),):
            r_el.remove(c)
    t_el = OxmlElement('w:t')
    t_el.text = text
    t_el.set(qn('xml:space'), 'preserve')
    r_el.append(t_el)


def set_tc_text(tc, text):
    ps = tc.findall(qn('w:p'))
    for extra in ps[1:]:
        tc.remove(extra)
    p = ps[0]
    runs = p.findall(qn('w:r'))
    if runs:
        keep = runs[0]
        for r in runs[1:]:
            p.remove(r)
        set_run_text(keep, text)
    else:
        r = OxmlElement('w:r')
        t_el = OxmlElement('w:t')
        t_el.text = text
        t_el.set(qn('xml:space'), 'preserve')
        r.append(t_el)
        p.append(r)


def make_rpr(bold=False, sz=None):
    rPr = OxmlElement('w:rPr')
    rf = OxmlElement('w:rFonts')
    rf.set(qn('w:ascii'), 'Times New Roman')
    rf.set(qn('w:hAnsi'), 'Times New Roman')
    rf.set(qn('w:eastAsia'), '宋体')
    rPr.append(rf)
    if bold:
        rPr.append(OxmlElement('w:b'))
        rPr.append(OxmlElement('w:bCs'))
    if sz:
        e = OxmlElement('w:sz')
        e.set(qn('w:val'), str(sz))
        rPr.append(e)
        e2 = OxmlElement('w:szCs')
        e2.set(qn('w:val'), str(sz))
        rPr.append(e2)
    return rPr


# ========== 1. 封面替换（模板封面切片 -> 替换旧封面与合并稿说明） ==========
tbody = t.element.body
cover_elems = []
for ch in tbody:
    if ch.tag == qn('w:p') and '实验目的' in ''.join(ch.itertext()):
        break
    if ch.tag == qn('w:sectPr'):
        continue
    cover_elems.append(copy.deepcopy(ch))

rbody = d.element.body
children = list(rbody)
h1_idx = next(i for i, ch in enumerate(children)
              if ch.tag == qn('w:p') and get_style(ch) == 'Heading1')
removed = h1_idx  # 旧封面 + 【合并稿说明】一并删除
for ch in children[:h1_idx]:
    rbody.remove(ch)
first = list(rbody)[0]
for el in cover_elems:
    first.addprevious(el)

# 题目段重建：去掉模板短下划线（VML 线），长标题 16pt 粗体单行
title_p = next(p for p in d.paragraphs[:25] if p.text.strip().startswith('题目'))
tp = title_p._element
for r in tp.findall(qn('w:r')):
    tp.remove(r)
pPr = tp.find(qn('w:pPr'))
if pPr is None:
    pPr = OxmlElement('w:pPr')
    tp.insert(0, pPr)
for tag in ('w:pStyle', 'w:ind', 'w:spacing'):
    e = pPr.find(qn(tag))
    if e is not None:
        pPr.remove(e)
sp = OxmlElement('w:spacing')
sp.set(qn('w:before'), '340')
sp.set(qn('w:after'), '330')
sp.set(qn('w:line'), '578')
sp.set(qn('w:lineRule'), 'auto')
pPr.append(sp)
r = OxmlElement('w:r')
r.append(make_rpr(bold=True, sz=32))
tt = OxmlElement('w:t')
tt.text = '题目：A2 YOLOv8n 量化、蒸馏与 TensorRT FP16 推理优化'
tt.set(qn('xml:space'), 'preserve')
r.append(tt)
tp.append(r)

# 校名字体显式化（模板未显式指定，防止继承目标文档默认字体）
for p in d.paragraphs[:25]:
    if '西' in p.text and '邮' in p.text:
        for run in p.runs:
            rPr = run._element.find(qn('w:rPr'))
            if rPr is None:
                rPr = OxmlElement('w:rPr')
                run._element.insert(0, rPr)
            rf = rPr.find(qn('w:rFonts'))
            if rf is None:
                rf = OxmlElement('w:rFonts')
                rPr.insert(0, rf)
            rf.set(qn('w:ascii'), 'Times New Roman')
            rf.set(qn('w:hAnsi'), 'Times New Roman')
            rf.set(qn('w:eastAsia'), '宋体')


# 组号/时间填值 + 正文分页符
def append_value(p, val, add_break=False):
    el = p._element
    donor_rpr = None
    for rr in el.findall(qn('w:r')):
        t_el = rr.find(qn('w:t'))
        rp = rr.find(qn('w:rPr'))
        if t_el is not None and t_el.text and '：' in t_el.text and rp is not None:
            donor_rpr = copy.deepcopy(rp)
            break
    nr = OxmlElement('w:r')
    if donor_rpr is not None:
        nr.append(donor_rpr)
    tt = OxmlElement('w:t')
    tt.text = val
    tt.set(qn('xml:space'), 'preserve')
    nr.append(tt)
    el.append(nr)
    if add_break:
        br_r = OxmlElement('w:r')
        br = OxmlElement('w:br')
        br.set(qn('w:type'), 'page')
        br_r.append(br)
        el.append(br_r)


for p in d.paragraphs[:25]:
    txt = p.text
    if '组' in txt and '号' in txt and '：' in txt and '17' not in txt:
        append_value(p, '17')
    if '时' in txt and '间' in txt and '：' in txt and '2026' not in txt:
        append_value(p, '2026 年 10 月', add_break=True)

# 封面成员表：表头保留，填 2 行分工（学号/姓名留空待填），删多余空行
tbl = d.tables[0]
assert '学号' in tbl.rows[0].cells[0].text
rows_data = [
    ('', '', '精度线（P1）：INT8 静态量化、特征蒸馏与误差分析'),
    ('', '', '速度线（P2）：复合损失蒸馏、TensorRT FP16 与 CPU 后端对照'),
]
for ri, vals in enumerate(rows_data, start=1):
    for ci, val in enumerate(vals):
        cp = tbl.rows[ri].cells[ci].paragraphs[0]
        for rr in list(cp.runs):
            rr._r.getparent().remove(rr._r)
        if val:
            run = cp.add_run(val)
            run.font.name = 'Times New Roman'
            run._element.rPr.rFonts.set(qn('w:eastAsia'), '宋体')
            run.font.size = Pt(12)
        cp.alignment = WD_ALIGN_PARAGRAPH.CENTER
while len(tbl.rows) > 3:
    tbl._tbl.remove(tbl.rows[-1]._tr)
print('[1] 封面替换完成（删除旧元素', removed, '个，模板封面元素', len(cover_elems), '个）')

# ========== 2. 五.8 关联分析 ==========
body_tpl = next(p for p in d.paragraphs if p.text.startswith('CPU 线主结果'))._element
h2_tpl = next(p for p in d.paragraphs if p.text.startswith('7. CPU'))._element
six_h1 = next(p for p in d.paragraphs
              if p.text.strip().startswith('六') and get_style(p._element) == 'Heading1')._element


def make_body_para(lead, rest):
    el = copy.deepcopy(body_tpl)
    runs = el.findall(qn('w:r'))
    r0 = runs[0]
    for rr in runs[1:]:
        el.remove(rr)
    set_run_text(r0, lead)
    rpr = r0.find(qn('w:rPr'))
    b = OxmlElement('w:b')
    rf = rpr.find(qn('w:rFonts'))
    rpr.insert(list(rpr).index(rf) + 1 if rf is not None else 0, b)
    bcs = OxmlElement('w:bCs')
    b.addnext(bcs)
    r1 = copy.deepcopy(r0)
    rpr1 = r1.find(qn('w:rPr'))
    for tag in ('w:b', 'w:bCs'):
        e = rpr1.find(qn(tag))
        if e is not None:
            rpr1.remove(e)
    set_run_text(r1, rest)
    el.append(r1)
    return el


P1_LEAD = '实验 1 数据特点对量化误差的影响。'
P1_REST = (
    '本实验量化误差的分布与实验 1 数据构成强相关，可归纳为三点。其一，样本多样性受限放大了校准集敏感性：'
    '数据来自连续视频抽帧，相邻帧高度相似，test 380 实为 190 张原始帧与其 _aug0 增强副本，有效样本多样性约减半，'
    '校准集与测试分布的贴近程度直接决定量化参数质量——val 346（E1）与 train 500（E2）校准的全集 mAP50 差异'
    '（0.420 vs 0.418）即源于此。其二，目标尺寸长尾分布使误差集中于稀缺尺寸段：大目标样本占比低（全集大目标 AP '
    '基数仅 0.212），INT8 使大目标 AP 下降 3.0pp（0.212→0.182）而中目标无损，且逐图 ΔAP 集中于少数图片（图3）'
    '——稀疏尺寸与帧型上的量化误差无法被平均摊薄。其三，数据质量决定误差分析口径：实验 1 复核发现 _aug0 副本为'
    '错位标注（框随机平移而图像未变），这些帧上 FP32 与 INT8 同步劣化（mAP50 仅 0.095），使全集口径系统性低估'
    '绝对精度；切换到干净口径（190 张原始帧）后，量化真实代价显形为 mAP50-95 的 1.7pp 定位损失（各尺寸档 mAP50 '
    '均无损）——正是两条口径的对照得到"量化影响框回归而非检测判定"的结论。三点共同表明：量化误差不是模型的孤立'
    '属性，而是模型与数据分布的联合结果，部署前应保证校准集与目标场景在尺寸、帧型多样性上一致。')
P2_LEAD = '实验 2 模型特性对剪枝敏感性的影响（定性关联分析）。'
P2_REST = (
    '任务书以 ResNet 的相加式残差结构为参照——恒等映射使残差支路可被整体剪除、精度回退平缓且可经微调恢复。'
    '本实验对象 A2（YOLOv8n）与之存在三点结构性差异，剪枝敏感性显著更高。其一，残差形式不同：主干 C2f 模块的'
    '多分支 Bottleneck 输出经 Concat 拼接而非逐元素相加，通道冗余分散于各拼接分支，剪除任一支路都会削弱拼接特征'
    '的通道表达，不存在"整支冗余、剪之无损"的恒等通路。其二，模型本已高度紧凑：A2 仅 3.13M 参数 / 8.6 GFLOPs'
    '（约为教师 YOLOv8m 的 1/8），冗余度远低于 ResNet-50 级骨干，同等剪枝率下精度代价更高。其三，解耦检测头对'
    '剪枝非对称敏感：DFL 分布式框回归分支对通道裁剪的敏感度远高于分类分支——本实验 INT8 量化已证实精度代价集中'
    '于回归定位（mAP50 无损而 mAP50-95 -1.7pp），通道剪枝预计呈现同样的结构性风险；且浅层检测支路（P3）通道规模'
    '最小，剪枝易造成小目标召回的不可逆损失。据此，在体积目标已由 INT8 达成（-72.9%）、精度已由蒸馏逼近教师'
    '（dis=9 全集 mAP50 0.422，为教师 0.424 的 99.5%）的情况下，剪枝的边际收益低而结构性风险高——本实验选择'
    '"量化+蒸馏"路线、将结构化剪枝及剪枝率-精度敏感性曲线留作后续工作（见六、展望），该取舍即实验 2 模型特性'
    '驱动的优化维度决策。')

h2el = copy.deepcopy(h2_tpl)
h2runs = h2el.findall(qn('w:r'))
for rr in h2runs[1:]:
    h2el.remove(rr)
set_run_text(h2runs[0], '8. 关联分析')
for el in (h2el, make_body_para(P1_LEAD, P1_REST), make_body_para(P2_LEAD, P2_REST)):
    six_h1.addprevious(el)
print('[2] 五.8 关联分析已插入')

# ========== 3. 表6 加 ONNX Runtime 列 + 补充说明段 ==========
cpu_tbl = None
for tb in d.tables:
    if len(tb.columns) < 4:
        continue
    hdr = tb.rows[0].cells[1].text + tb.rows[0].cells[2].text
    if 'OpenVINO' in hdr and len(tb.rows) >= 2 and tb.rows[1].cells[0].text.strip().startswith('单图'):
        cpu_tbl = tb
        break
assert cpu_tbl is not None, '未找到 CPU 对照表'

grid = cpu_tbl._tbl.find(qn('w:tblGrid'))
gridcols = grid.findall(qn('w:gridCol'))
widths = [int(gc.get(qn('w:w'))) for gc in gridcols]
grid.insert(list(grid).index(gridcols[2]), copy.deepcopy(gridcols[2]))
others = (widths[1] + widths[2] + widths[3]) // 4
new_widths = [widths[0]] + [others] * 4
for gc, w in zip(grid.findall(qn('w:gridCol')), new_widths):
    gc.set(qn('w:w'), str(w))

ORT = ['ONNX Runtime FP32', '81.42 ms', '96.67 ms', '2290.6 ms',
       '13.97 图/秒', '1745 MB', '0.00pp（逐位一致）']
for ri, tr in enumerate(cpu_tbl._tbl.findall(qn('w:tr'))):
    tcs = tr.findall(qn('w:tc'))
    donor = tcs[2]
    newtc = copy.deepcopy(donor)
    donor.addprevious(newtc)
    set_tc_text(newtc, ORT[ri])
    for tc, w in zip(tr.findall(qn('w:tc')), new_widths):
        tcPr = tc.find(qn('w:tcPr'))
        if tcPr is not None:
            tcW = tcPr.find(qn('w:tcW'))
            if tcW is not None:
                tcW.set(qn('w:w'), str(w))
                tcW.set(qn('w:type'), 'dxa')
hdr_tcs = cpu_tbl._tbl.findall(qn('w:tr'))[0].findall(qn('w:tc'))
set_tc_text(hdr_tcs[4], '变化（OpenVINO）')

note = copy.deepcopy(body_tpl)
note_runs = note.findall(qn('w:r'))
for rr in note_runs[1:]:
    note.remove(rr)
set_run_text(note_runs[0],
             '三后端同机对照补充（表6）：ONNX Runtime FP32 单图延迟与 PyTorch 持平略慢（81.42 ms vs 72.22 ms，'
             '单图调度与预处理开销占比高），但 Batch 32 吞吐提升 55.6%（13.97 图/秒 vs 8.98 图/秒）；另有 FP16 存储'
             '变体单图 P50 可至 55.47 ms（较基线 -23.2%）。OpenVINO FP32 调优版在单图（-22.4%）与批量（+99.5%）上均'
             '最优。三者 test 190 的 mAP50-95 与基线逐位一致或等效无损（0.00pp / ≈0.00pp），满足任务书 3.2.1 的精度'
             '一致性要求（误差≤0.5%）。')
cpu_tbl._tbl.addnext(note)
print('[3] 表6 已插入 ORT 列并加补充说明')

d.save(SRC)
print('已保存:', SRC)
