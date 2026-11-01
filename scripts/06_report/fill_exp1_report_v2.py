# -*- coding: utf-8 -*-
"""实验1报告 v2：在用户改过的版本上，严格按《实验1任务书》“六、实验报告要求”8条逐项补齐。

输入（只读）：D:/Downloads/AI全栈开发实验1报告.docx   （用户改过内容、表格未动）
输出：      D:/Downloads/AI全栈开发实验1报告_updated.docx

补齐对照（任务书 报告要求 → 本次动作）：
  第2条 代码片段          → “3．代码实现”补 5 段真实代码片段（原只有脚本职责表）
  第2条 结构              → 恢复被删的“五．实验结果与分析”标题 + 补（1）总览条
  第4条 增强效果展示      → 新增 表4 数据增强前后对比
  第5条 README/结构图/链接 → 新增 附录：文档说明 + 图1 结构图（重绘）+ 补 MultiSports 下载链接
  第6条 策展配置说明      → （3）之后补六算子配置说明段
  第7条 Data Card+合规    → 新增 表5 数据集卡片、表6 隐私合规检查清单
  第8条 合成数据（选做）  → 在（6）中声明未采用
  顺带：统一标题编号（4.→4．、六、→六．）；用户新增的3张表若无边框则补边框。
"""
import copy
from pathlib import Path

import docx
from docx.enum.text import WD_ALIGN_PARAGRAPH
from docx.oxml import parse_xml
from docx.oxml.ns import qn
from docx.table import Table
from docx.text.paragraph import Paragraph

SRC = Path(r"D:/Downloads/AI全栈开发实验1报告.docx")
DST = Path(r"D:/Downloads/AI全栈开发实验1报告_updated.docx")
FIG = Path(__file__).resolve().parents[2] / "report/figures/fig4_dataset_tree.png"
XML_SPACE = "{http://www.w3.org/XML/1998/namespace}space"

doc = docx.Document(str(SRC))

# ---------- 基础工具 ----------

def copy_para_fmt(ref: Paragraph, p: Paragraph, text: str, bold=None):
    """新段落整体套用 ref 的段落格式与首个 run 字体。"""
    rf, pf = ref.paragraph_format, p.paragraph_format
    pf.alignment = rf.alignment
    pf.first_line_indent = rf.first_line_indent
    pf.line_spacing, pf.line_spacing_rule = rf.line_spacing, rf.line_spacing_rule
    pf.space_before, pf.space_after = rf.space_before, rf.space_after
    run = p.add_run(text)
    rr = ref.runs[0] if ref.runs else None
    if rr is not None:
        rpr = rr._element.rPr
        if rpr is not None:
            run._element.insert(0, copy.deepcopy(rpr))
    if bold is not None:
        run.font.bold = bold
    return p


def new_para(ref: Paragraph, text: str, bold=None) -> Paragraph:
    p = doc.add_paragraph()
    copy_para_fmt(ref, p, text, bold)
    return p


def new_code_para(code: str) -> Paragraph:
    p = doc.add_paragraph()
    pf = p.paragraph_format
    pf.alignment = WD_ALIGN_PARAGRAPH.LEFT
    pf.first_line_indent = 0
    pf.line_spacing = 1.0
    pf.space_before, pf.space_after = None, None
    run = p.add_run()
    rpr = parse_xml(
        '<w:rPr xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main">'
        '<w:rFonts w:ascii="Consolas" w:hAnsi="Consolas" w:eastAsia="宋体"/>'
        '<w:sz w:val="18"/><w:szCs w:val="18"/></w:rPr>')
    run._element.insert(0, rpr)
    lines = code.split("\n")
    for i, line in enumerate(lines):
        run.add_text(line)
        if i < len(lines) - 1:
            run.add_break()
    for t in p._p.iter(qn("w:t")):
        t.set(XML_SPACE, "preserve")
    p._p.get_or_add_pPr().append(parse_xml(
        '<w:shd xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main" '
        'w:val="clear" w:color="auto" w:fill="F2F2F2"/>'))
    return p


def set_cell(cell, text: str):
    for extra in cell.paragraphs[1:]:
        extra._p.getparent().remove(extra._p)
    p = cell.paragraphs[0]
    rpr = None
    if p.runs and p.runs[0]._element.rPr is not None:
        rpr = copy.deepcopy(p.runs[0]._element.rPr)
    for r in list(p.runs):
        r._element.getparent().remove(r._element)
    run = p.add_run(text)
    if rpr is not None:
        run._element.insert(0, rpr)


def clone_table(src: Table, data: list[list[str]], col_frac=None) -> Table:
    """深拷贝源表 XML（继承边框/表头加粗/cantSplit），改行数、重写文本、可选调列宽。"""
    tbl_el = copy.deepcopy(src._tbl)
    trs = tbl_el.findall(qn("w:tr"))
    while len(trs) < len(data):
        tbl_el.append(copy.deepcopy(trs[-1]))
        trs = tbl_el.findall(qn("w:tr"))
    while len(trs) > len(data):
        tbl_el.remove(trs[-1])
        trs = tbl_el.findall(qn("w:tr"))
    t = Table(tbl_el, doc)
    if col_frac:
        grid = tbl_el.find(qn("w:tblGrid"))
        cols = grid.findall(qn("w:gridCol"))
        total = sum(int(c.get(qn("w:w"))) for c in cols)
        for c, frac in zip(cols, col_frac):
            c.set(qn("w:w"), str(int(total * frac)))
        for row in t.rows:
            for cell, frac in zip(row.cells, col_frac):
                cell.width = docx.shared.Emu(int(total * frac) * 635)
    for row, rowdata in zip(t.rows, data):
        for cell, text in zip(row.cells, rowdata):
            set_cell(cell, text)
    return t


def ensure_borders(t: Table):
    """无边框的表补全边框 + cantSplit + 表头行重复。"""
    tbl_pr = t._tbl.tblPr
    if tbl_pr.find(qn("w:tblBorders")) is None:
        tbl_pr.append(parse_xml(
            '<w:tblBorders xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main">'
            + "".join(f'<w:{s} w:val="single" w:sz="4" w:space="0" w:color="000000"/>'
                      for s in ("top", "left", "bottom", "right", "insideH", "insideV"))
            + "</w:tblBorders>"))
    for row in t.rows:
        tr_pr = row._tr.get_or_add_trPr()
        if tr_pr.find(qn("w:cantSplit")) is None:
            tr_pr.append(parse_xml(
                '<w:cantSplit xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main"/>'))
    tr0 = t.rows[0]._tr.get_or_add_trPr()
    if tr0.find(qn("w:tblHeader")) is None:
        tr0.append(parse_xml(
            '<w:tblHeader xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main"/>'))


# ---------- 锚点（插入前一次性捕获） ----------
P = doc.paragraphs
T = doc.tables
p_code_head, tbl_scripts = P[25], T[2]._tbl          # 3．代码实现 + 脚本职责表
p_r2 = P[36]                                         # （2）清洗前后…
p_r3 = P[39]                                         # （3）效率对比
tbl3_el = T[5]._tbl                                  # 表3
p_ana = P[45]                                        # 分析：
p_dl, p_dl_img, p_dl_txt = P[57], P[58], P[59]       # 下载链接三行
p_test, p_sum = P[26], P[46]                         # 4.测试优化 / 六、总结
ref_body, ref_cap = P[36], P[42]                     # 正文/题注格式参照

# 用户新增的 3 张表（分工/环境/脚本）补边框
for t in (T[0], T[1], T[2]):
    ensure_borders(t)

# ---------- 0. 重建脚本职责表（旧表为上一版方案，缺视频线/解说线脚本） ----------
SCRIPTS = [
    ("01_acquire/download_multisports_hf.py", "视频线下载：MultiSports为HF门控仓库，Bearer鉴权直连官方域名（15.55GB含标注trainval）"),
    ("01_acquire/download_sportsmot_hf.py", "检测主数据集下载：SportsMOT经hf-mirror镜像分段断点续传，自动检测并绕过本机DNS劫持"),
    ("01_acquire/extract_basketball.py", "从tar包仅提取篮球子集，过滤macOS垃圾文件"),
    ("01_acquire/mot_to_yolo.py", "MOT标注转YOLO归一化坐标，每5帧抽样"),
    ("01_acquire/multisports_to_events.py", "GT标注转动作事件表（6247行：动作/起止帧与秒/框位置）"),
    ("01_acquire/multisports_to_yolo.py", "视频按2fps截取有标注帧，生成补充检测集（7746帧/9094框）"),
    ("01_acquire/crawl_zhibo8_livetext.py", "解说语料爬取：文字直播接口逆向、0.5秒/页限速、断点续爬、翻页死循环防护"),
    ("01_acquire/crawl_basketball_news.py", "资讯背景语料合规爬虫：robots.txt检查、2秒限速、GBK编码自动探测"),
    ("02_clean/clean_multisports.py", "526段视频逐段校验：首/中/尾帧解码、帧数与标注对齐（±2帧）、分辨率帧率核对"),
    ("02_clean/clean_images.py", "图像清洗：损坏检测、EXIF抹除、感知哈希近重复剔除、标注越界校验"),
    ("02_clean/clean_livetext.py", "解说清洗：去空/超短/重复，33字段统一为5字段，按场次8:1:1划分防泄漏"),
    ("02_clean/clean_texts.py＋run_dj.py", "资讯文本规范化；Data-Juicer六算子自动化策展流水线（本机DLL兼容启动器）"),
    ("03_augment/augment_images.py", "torchvision v2增强（水平翻转/仿射/色彩抖动），检测框同步几何变换"),
    ("04_standardize/standardize_and_split.py", "统一640×640、按比赛序列8:1:1划分、生成YOLO标准目录与data.yaml"),
    ("05_evaluate/quality_report.py", "四维数据质量评分（完整性/一致性/代表性/时效性）"),
]
t_scripts = T[2]
while len(t_scripts.rows) < len(SCRIPTS) + 1:
    t_scripts._tbl.append(copy.deepcopy(t_scripts.rows[-1]._tr))
while len(t_scripts.rows) > len(SCRIPTS) + 1:
    t_scripts._tbl.remove(t_scripts.rows[-1]._tr)
for row, (name, duty) in zip(t_scripts.rows[1:], SCRIPTS):
    set_cell(row.cells[0], name)
    set_cell(row.cells[1], duty)

# ---------- 0b. 彻底移除结构化线表述（用户决定：正文+表4+脚本表一起拿掉） ----------
def rewrite(p: Paragraph, new_text: str):
    rpr = None
    if p.runs and p.runs[0]._element.rPr is not None:
        rpr = copy.deepcopy(p.runs[0]._element.rPr)
    for r in list(p.runs):
        r._element.getparent().remove(r._element)
    run = p.add_run(new_text)
    if rpr is not None:
        run._element.insert(0, rpr)


p_aug4 = next(p for p in doc.paragraphs if p.text.startswith("（4）增强效果"))
rewrite(p_aug4,
    "（4）增强效果：图像数据经torchvisionv2（水平翻转+仿射平移缩放+色彩抖动，框同步变换）增强一倍，"
    "2521→5042张，仅51个过小出画框被丢弃，抽样核对标注坐标分布正常（汇总对比见表4）。")

p_split5 = next(p for p in doc.paragraphs if p.text.startswith("（5）数据集划分"))
rewrite(p_split5,
    p_split5.text.replace("结构化与文本数据按行同比例划分", "文本数据按行同比例划分"))

# ---------- 1. “3．代码实现”：补代码片段（插在脚本职责表之前） ----------
intro = new_para(ref_body,
    "全部脚本按流水线阶段编号组织于 scripts/ 目录（01获取→02清洗→03增强→04标准化→05评估），"
    "职责一览见下表；限于篇幅，以下摘录五处最能体现“获取—清洗—增强—划分”关键设计与踩坑解法的"
    "代码片段（对应任务书报告第2条“含代码片段”要求，完整代码随工程提交）。")
snippets = [
    ("片段1　镜像分段断点续传（scripts/01_acquire/download_sportsmot_hf.py，13GB主数据集可靠下载）：",
     'def download_chunk(url, out_path, start, end, hf_ip):   # HTTP Range 分段下载\n'
     '    cmd = curl_base_args(hf_ip) + ["-r", f"{start}-{end}", "-o", str(tmp), url]\n'
     '    ...\n'
     '# 断点续传：已完成且大小一致的分段直接跳过，失败分段最后统一补漏\n'
     'todo = [(s, e, p) for s, e, p in jobs\n'
     '        if not (p.exists() and p.stat().st_size == e - s + 1)]'),
    ("片段2　翻页死循环防护（scripts/01_acquire/crawl_zhibo8_livetext.py，接口对超界页码返回末页）：",
     'new = [e for e in data if e.get("live_id") and e["live_id"] not in seen]\n'
     'if not new:\n'
     '    break                    # 整页重复 = 服务端把超界页码夹取回末页，正常到头\n'
     'entries.extend(new)\n'
     'seen.update(e["live_id"] for e in new)\n'
     'page += 10\n'
     'time.sleep(SLEEP)            # 限速：每页 0.5 秒'),
    ("片段3　感知哈希近重复剔除（scripts/02_clean/clean_images.py，隔离而非删除、可追溯）：",
     'h = image_hash(im)                              # 感知哈希\n'
     'dup = any(hamming(h, prev) <= args.hash_th for prev, _ in hashes)  # 距离<=6 判近重复\n'
     'if dup:\n'
     '    metrics["near_duplicates"] += 1\n'
     '    shutil.move(str(img_path), quarantine / "images" / img_path.name)\n'
     '    continue'),
    ("片段4　增强与标注框同步变换（scripts/03_augment/augment_images.py，坐标系互转防框塌缩）：",
     'boxes = tv_tensors.BoundingBoxes([...cx*W, cy*H...], format="XYXY", canvas_size=(H, W))\n'
     '# 归一化坐标必须先乘宽高转像素、变换后再除回，否则框会塌缩到原点附近\n'
     'out_img, out_boxes = transform(np.array(img), boxes)   # 翻转/仿射/色彩，框同步几何变换\n'
     'if x2 - x1 < 0.002 * W or x1 > W or ...:\n'
     '    continue                  # 变换后过小/完全出画的框丢弃并计数'),
    ("片段5　按序列划分防泄漏（scripts/04_standardize/standardize_and_split.py，8:1:1，seed=42）：",
     'seq_of = {p.name: p.stem.split("__")[0] for p in images}   # 帧名 → 所属比赛序列\n'
     'train_seqs, val_seqs, test_seqs = split_list(sequences)    # 先划序列，帧再跟随落位\n'
     'for img_path in images:\n'
     '    split = seq2split[seq_of[img_path.name]]\n'
     '    im.convert("RGB").resize((imgsz, imgsz), Image.LANCZOS).save(...)  # 统一640×640'),
]
for el in [intro]:
    tbl_scripts.addprevious(el._p)
for lead, code in snippets:
    tbl_scripts.addprevious(new_para(ref_body, lead)._p)
    tbl_scripts.addprevious(new_code_para(code)._p)

# ---------- 2. 恢复“五．实验结果与分析”标题 + （1）总览 ----------
p1 = new_para(ref_body,
    "（1）数据成果总览（对应报告第1、2条）：三条数据线全部落地并通过独立验证——视频526/526段通过"
    "解码与帧对齐校验；检测主数据集经ultralytics加载冒烟（346张验证图、3104个标注框全部正确配对，"
    "训练循环跑通）；解说语料41场40,376条完成按场次防泄漏划分。各数据线规模与划分见表1，获取全流程"
    "记录见“2．设计思路”，遇到的问题及解决方案见“四．实验关键技术与难点”。")
h5 = doc.add_paragraph(style="Heading 2")
h5.add_run("五．实验结果与分析")
p_r2._p.addprevious(h5._p)
p_r2._p.addprevious(p1._p)

# ---------- 3. （3）之后补策展流水线配置说明（报告第6条“配置说明”部分） ----------
cfg = new_para(ref_body,
    "策展流水线配置说明（对应报告第6条）：流水线由configs/data_juicer_text.yaml定义，共6个算子，"
    "覆盖任务书要求的去重、过滤、规范化、质量筛选与语言识别五类——clean_html_mapper（HTML标签清理）、"
    "whitespace_normalization_mapper（空白规范化）、language_id_score_filter（中文得分≥0.5保留）、"
    "text_length_filter（50–10000字）、clean_email_mapper（邮箱等隐私标识清理）、"
    "document_minhash_deduplicator（字符级MinHash、128置换、Jaccard阈值0.7去重）；执行器为单机default"
    "（规避1.6.0默认ray执行器的额外安装），全部参数、版本与运行耗时已记录于docs/PROVENANCE.md。")
p_r3._p.addnext(cfg._p)

# ---------- 4. 表3之后：表4 增强对比 → （6） → 表5 Data Card → 表6 合规清单 ----------
tbl4 = clone_table(T[5], [
    ["数据线", "增强前", "增强后", "一致性与评估"],
    ["图像（检测主集）", "2521帧",
     "5042帧（水平翻转＋仿射平移缩放＋色彩抖动，标注框同步几何变换）",
     "出画/过小框仅51个被丢弃；抽样核对坐标分布正常"],
    ["解说文本", "40,376条", "本实验不做同义替换类增强",
     "避免语义失真（任务书“避免无效增强”）；实验5再构造“事件—解说”指令对"],
    ["增强的模型级收益", "—", "—",
     "留待实验2消融组定量验证：A1（原始2521帧）vs A2（增强5042帧），仅增强一个变量，对比mAP"],
], col_frac=[0.16, 0.13, 0.40, 0.31])
cap4 = new_para(ref_cap, "表4　数据增强前后对比（对应报告第4条）", bold=True)

p6 = new_para(ref_body,
    "（6）数据集卡片与隐私合规检查（对应报告第7条）：在README.md基础上编写了标准化数据集卡片"
    "（表5，完整版见docs/DATA_CARD.md），并按任务书四项要求逐条完成隐私合规专项检查（表6）；"
    "数据全链路溯源（每一步清洗、增强、转换的参数与版本）记录于docs/PROVENANCE.md。"
    "任务书第8条合成数据生成（选做）本项目未采用，故无对应内容。")
tbl5 = clone_table(T[1], [
    ["维度", "内容"],
    ["数据集名称", "篮球AI解说员多源数据底座（视频＋图像＋解说文本三条数据线）"],
    ["数据来源", "MultiSports（HuggingFace门控仓库 MCG-NJU/MultiSports）；SportsMOT（MCG-NJU/SportsMOT，CC BY-NC 4.0）；直播吧文字直播（robots.txt合规爬取）"],
    ["收集方法", "Bearer鉴权直连官方域名下载；hf-mirror镜像分段断点续传；文字直播接口逆向＋0.5秒/页限速＋断点续爬"],
    ["标注流程", "视频线沿用官方逐帧球员框与18类动作实例标注；图像线官方MOT框转YOLO归一化坐标；文本线逐条携带时间戳/解说员/比分"],
    ["清洗与增强", "见表2、表4；每步参数与版本记录于docs/PROVENANCE.md（数据溯源）"],
    ["划分方式", "8:1:1（seed=42）；视觉按比赛序列、解说按场次划分，防止同源数据跨集合泄漏"],
    ["使用限制", "CC BY-NC 4.0非商业使用；直播语料仅课程使用、不再分发"],
    ["伦理与隐私", "无个人敏感信息；图像EXIF元数据全部抹除；未引入合成数据"],
])
cap5 = new_para(ref_cap, "表5　数据集卡片（Data Card摘要）", bold=True)
tbl6 = clone_table(T[0], [
    ["检查项", "结论", "说明"],
    ["数据来源合法授权", "通过", "两个公开数据集均按官方协议获取（CC BY-NC 4.0/研究用途）"],
    ["遵守robots.txt与平台AI数据声明", "通过", "爬取前检查直播吧robots.txt，未触碰Disallow路径；限速0.5秒/页；User-Agent带课程标识"],
    ["合成数据监管要求", "不适用", "本实验未引入合成数据"],
    ["个人信息处理", "通过", "语料仅含公开赛事信息与解说员公开署名，无身份/联系类敏感字段；图像EXIF全部抹除"],
    ["课程作业授权范围", "通过", "数据仅用于《AI全栈开发》课程实验，不对外再分发原始语料"],
], col_frac=[0.30, 0.11, 0.59])
cap6 = new_para(ref_cap, "表6　隐私与合规检查清单", bold=True)

for el in reversed([cap4._p, tbl4._tbl, p6._p, cap5._p, tbl5._tbl, cap6._p, tbl6._tbl]):
    tbl3_el.addnext(el)

# ---------- 5. 附录：文档说明 + 图1 结构图 + 下载链接 ----------
h_app = doc.add_paragraph(style="Heading 2")
h_app.add_run("附录：数据集文档、结构与下载")
note = new_para(ref_body,
    "数据集文档随工程一并提交（对应报告第5条）：README.md（数据来源与授权、格式说明、清洗与增强"
    "步骤记录、隐私说明）、docs/DATA_CARD.md（数据集卡片完整版）、docs/PROVENANCE.md（数据溯源："
    "每步操作的参数、版本与产物指标）、docs/CLEANUP_LOG.md（清理日志）。最终数据集目录结构如图1所示。")
pic_p = doc.add_paragraph()
pic_p.alignment = WD_ALIGN_PARAGRAPH.CENTER
pic_p.add_run().add_picture(str(FIG), width=docx.shared.Cm(15))
cap_fig = new_para(ref_cap, "图1　最终数据集目录结构（三条数据线）", bold=True)
for el in [h_app, note, pic_p, cap_fig]:
    p_dl._p.addprevious(el._p)

video_link = new_para(ref_body,
    "视频与动作标注：https://huggingface.co/datasets/MCG-NJU/MultiSports"
    "（门控仓库，登录同意条款后可下载；仅含标注的trainval拆分15.55GB）")
p_dl_img._p.addnext(video_link._p)

# 文本行改写为完整说明
for r in list(p_dl_txt.runs):
    r._element.getparent().remove(r._element)
run = p_dl_txt.add_run(
    "文本：直播吧（zhibo8.com）文字直播自爬语料（robots.txt合规、限速），原始语料不再分发，"
    "清洗后格式与字段见docs/DATA_CARD.md")
rr = p_r2.runs[0]
if rr._element.rPr is not None:
    run._element.insert(0, copy.deepcopy(rr._element.rPr))

# ---------- 6. 标题编号统一 ----------
for r in p_test.runs:
    if "4.测试优化" in r.text:
        r.text = r.text.replace("4.测试优化", "4．测试优化")
for r in p_sum.runs:
    if "六、" in r.text:
        r.text = r.text.replace("六、", "六．")

doc.save(str(DST))
print(f"saved {DST}")
print(f"paragraphs={len(doc.paragraphs)} tables={len(doc.tables)}")
