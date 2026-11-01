# -*- coding: utf-8 -*-
"""填写实验 1 报告：将模板中的黄底红字说明替换为项目实际内容（AI 解说员故事线）。

输入：D:/Downloads/AI全栈开发实验报告模板-2025-黄底红字请删除.docx（.doc 已由 LibreOffice 转换）
输出：<stem>_filled.docx（不动原文件）
格式：正文小四（12pt）宋体/Times New Roman，行距固定 20 磅，首行缩进 2 字符；表格内五号。
"""
from docx import Document
from docx.shared import Pt
from docx.enum.text import WD_ALIGN_PARAGRAPH
from docx.oxml.ns import qn

SRC = r"D:\Downloads\AI全栈开发实验报告模板-2025-黄底红字请删除.docx"
DST = r"D:\Downloads\AI全栈开发实验报告模板-2025-黄底红字请删除_filled.docx"

doc = Document(SRC)


# ---------- 基础格式工具 ----------
def fmt_run(run, size=12, bold=False):
    run.font.name = "Times New Roman"
    run.font.size = Pt(size)
    run.bold = bold
    rpr = run._element.get_or_add_rPr()
    rf = rpr.find(qn("w:rFonts"))
    if rf is None:
        rf = rpr.makeelement(qn("w:rFonts"), {})
        rpr.append(rf)
    rf.set(qn("w:eastAsia"), "宋体")


def para(text, size=12, bold=False, indent=True, align=WD_ALIGN_PARAGRAPH.JUSTIFY,
         before=0, after=0):
    p = doc.add_paragraph()
    r = p.add_run(text)
    fmt_run(r, size=size, bold=bold)
    pf = p.paragraph_format
    pf.line_spacing = Pt(20)
    pf.alignment = align
    pf.space_before, pf.space_after = Pt(before), Pt(after)
    if indent:
        pf.first_line_indent = Pt(size * 2)
    return p


def anchor_insert(anchor_p, new_p):
    anchor_p._p.addprevious(new_p._p)
    return new_p


def body(anchor, text):
    return anchor_insert(anchor, para(text))


def head3(anchor, text):
    return anchor_insert(anchor, para(text, bold=True, indent=False,
                                      align=WD_ALIGN_PARAGRAPH.LEFT, before=6))


def add_table(anchor, headers, rows, caption=None):
    if caption:
        c = para(caption, size=10.5, bold=True, indent=False,
                 align=WD_ALIGN_PARAGRAPH.CENTER, before=6)
        anchor_insert(anchor, c)
    t = doc.add_table(rows=len(rows) + 1, cols=len(headers))
    try:
        t.style = "Table Grid"
    except KeyError:
        pass
    for j, h in enumerate(headers):
        cell = t.rows[0].cells[j]
        cell.text = ""
        r = cell.paragraphs[0].add_run(h)
        fmt_run(r, size=10.5, bold=True)
        cell.paragraphs[0].alignment = WD_ALIGN_PARAGRAPH.CENTER
    for i, row in enumerate(rows):
        for j, v in enumerate(row):
            cell = t.rows[i + 1].cells[j]
            cell.text = ""
            r = cell.paragraphs[0].add_run(str(v))
            fmt_run(r, size=10.5)
            cell.paragraphs[0].alignment = WD_ALIGN_PARAGRAPH.LEFT
    anchor._p.addprevious(t._tbl)
    return t


# ---------- 1) 删除模板黄底红字说明与脚手架 ----------
TO_DEL = [
    "正文字号小四，中文宋体",
    "需要涵盖三部分内容",
    "1.1 多源数据获取",
    "1.2 数据清洗与增强",
    "1.3 数据集建设",
    "1．需求分析",
    "2．设计思路",
    "3．代码实现",
    "4. 测试优化",
    "获取至少2-3类数据",
]
removed = 0
for p in list(doc.paragraphs):
    t = p.text.strip()
    if any(t.startswith(k) for k in TO_DEL):
        p._element.getparent().remove(p._element)
        removed += 1
print(f"[1] 删除模板说明段落 {removed} 个")


# ---------- 2) 封面：时间 ----------
for p in doc.paragraphs:
    if p.text.strip().startswith("时    间"):
        for r in p.runs:
            pass
        r = p.add_run("2026年10月17日")
        fmt_run(r, size=14)
        print("[2] 封面时间已填")


# ---------- 3) 找章节锚点 ----------
anchor = {}
for p in doc.paragraphs:
    t = p.text.strip()
    for key in ("实验目的", "实验环境", "三．实验内容与步骤", "四．实验关键技术与难点",
                "五、实验结果与分析", "六、实验总结与展望", "七．参考文献"):
        if t.startswith(key) and key not in anchor:
            anchor[key] = p
print("[3] 锚点:", list(anchor))

# ---------- 4) 填写各章 ----------
# 一、实验目的
a = anchor["实验环境"]
body(a, "本实验为“篮球AI赛事解说员”系统建设数据底座，具体目标：（1）掌握多源异构数据（视频、图像、非结构化文本）的合规获取方法，覆盖公开数据集下载、接口逆向与合规爬取三条路径；（2）掌握数据清洗、数据增强、数据标准化的完整流水线，并完成自动化策展（Data-Juicer）与手工处理的效率对比；（3）构建可直接支撑后续实验的高质量数据集：检测帧数据集（实验2训练）、带动作标注的视频与事件表（实验5动作识别）、解说语料三分卷（实验5大模型微调与RAG检索）；（4）建立数据质量与溯源意识，理解“数据预处理质量决定模型上限”的工程逻辑。")

# 二、实验环境
a = anchor["三．实验内容与步骤"]
body(a, "硬件：AMD Ryzen 7 6800H（8核16线程）CPU、16GB内存、无独立GPU，全部数据处理在CPU完成。")
body(a, "软件：Windows 11，Python 3.11（venv虚拟环境）；关键依赖：pandas、numpy、opencv-python、Pillow、requests、beautifulsoup4、torch/torchvision（CPU版）、py-data-juicer 1.6.0、imagehash、ultralytics 8.4。各步骤运行日志与指标统一归档于logs/与data/processed/*/，处理链路完整记录于docs/PROVENANCE.md。")

# 三、实验内容与步骤
a = anchor["四．实验关键技术与难点"]
head3(a, "1．需求分析")
body(a, "系统最终形态：上传比赛视频→检测每个球员→识别场上动作（投篮/传球/抢断等）→结合真实解说风格生成逐事件中文解说。据此推导三类数据需求：①比赛视频与逐帧球员框、动作实例标注（支撑动作识别与演示）；②视频/序列截取的图像帧（支撑检测模型训练）；③真实赛事解说文本（支撑大模型风格学习与检索）。三类数据对应“看得见人（检测）→看得懂事（动作）→说得出话（解说）”的能力闭环。")
head3(a, "2．设计思路")
body(a, "按“获取→清洗→增强→标准化划分”四阶段流水线设计，每阶段输出指标json与运行日志，全过程可追溯。所有数据集统一按8:1:1划分并固定随机种子（seed=42）：视觉按“比赛序列”划分、解说语料按“场次”划分，从源头防止同源数据跨集合造成的信息泄漏（同一场比赛的内容绝不跨train/val/test）。")
head3(a, "3．代码实现")
body(a, "1.1 多源数据获取：视觉主数据集SportsMOT篮球子集经hf-mirror镜像下载（download_sportsmot_hf.py，分段断点续传）；视频与动作标注取自MultiSports官方HuggingFace门控仓库（download_multisports_hf.py，Bearer鉴权直连，15.55GB，仅下载含标注的trainval拆分）；解说语料来自直播吧文字直播缓存接口（crawl_zhibo8_livetext.py，逆向自页面JS：分页JSON、每页10条、33字段；限速0.5秒/页、3并发、断点续爬、课程UA标识），共采集41场完整比赛40,923条原始记录；另合规爬取篮球资讯122篇作为背景知识语料。")
body(a, "1.2 数据清洗与增强：视频清洗（clean_multisports.py）对526段mp4逐段校验首/中/尾帧解码、帧数与标注对齐（±2帧）、分辨率与帧率，526/526全部通过；图像清洗（clean_images.py）以感知哈希剔除近重复帧4981→2521；图像增强（augment_images.py）做水平翻转+仿射+色彩抖动并同步变换标注框，2521帧→5042帧；解说清洗（clean_livetext.py）去除空行、超短行、重复记录，33字段统一为5字段（场次/时间/文本/解说员/比分）。")
body(a, "1.3 数据集建设：标准YOLO目录（standardize_and_split.py）统一640×640、按序列8:1:1划分出train 4316/val 346/test 380；动作标注转事件表（multisports_to_events.py，6247行：视频/动作/起止帧与秒/框坐标）；视频截帧转检测补充数据（multisports_to_yolo.py，2fps取有标注帧，7746帧/9094框）；解说语料按场次8:1:1划分（33/4/4场，共40,376条）；数据集摘要统一写入split_summary.json，并实现PyTorch Dataset封装（src/basketball_dataset.py）供训练直接加载。")
head3(a, "4．测试优化")
body(a, "每条数据线落地后均做独立验证：视觉数据集经ultralytics加载冒烟（346张验证图3104个标注框全部正确解析、训练循环跑通）；视频与标注做帧号级一致性核对；解说说料清洗前后条数与丢弃原因全部落盘可查。针对验证中发现的问题迭代修复：如txt训练清单相对路径导致标签配对失败（改为运行时生成绝对路径清单）、torchvision v2增强坐标系错误导致框塌缩（入参乘宽高转像素、出画框丢弃）等。")

# 四、实验关键技术与难点
a = anchor["五、实验结果与分析"]
body(a, "（1）门控数据集下载：MultiSports为HuggingFace门控仓库，镜像站不转发Authorization头导致401。解决：携带Bearer token直连官方域名，token仅经环境变量传递、不落盘。（2）本机网络异常：Clash TUN接管DNS（域名解析为fake-ip）且系统代理极慢，爬虫单页耗时分钟级。解决：DoH查询真实IP并用curl --resolve钉住；urllib用ProxyHandler({})构建绕过系统代理的opener，恢复0.5秒/页。（3）文字直播接口逆向与翻页死循环：接口对超范围页码返回末页而非空页。解决：整页记录ID与已爬集合完全重复即终止，并设200页硬上限。（4）增强与标注一致性：增强副本与框必须同步变换，坐标系错误会把框压成一点。解决：像素/归一化坐标显式互转，出画与过小框按阈值丢弃并计数。（5）数据泄漏防护：同比赛序列/同场次内容必须落在同一侧集合，否则验证指标虚高。解决：视觉按序列、解说按场次作为划分单元，而非按行随机划分。")

# 五、实验结果与分析
a = anchor["六、实验总结与展望"]
add_table(a, ["数据线", "内容", "规模", "划分（8:1:1）"], [
    ["视频+动作标注", "MultiSports篮球子集（mp4+逐帧框+18类动作）", "526段/6247动作实例", "随官方train/val（379/147）"],
    ["检测图像（主）", "YOLO格式球员框（640×640）", "5042帧（含增强副本）", "序列24/3/3→帧4316/346/380"],
    ["检测图像（补充）", "MultiSports有标注帧截取", "7746帧/9094框", "随视频官方split"],
    ["解说文本", "直播吧文字直播逐条记录", "41场40,376条", "按场次33/4/4场"],
    ["事件表", "动作实例结构化（起止时间/位置）", "6247行CSV", "随视频官方split"],
], "表1 数据成果总览")
add_table(a, ["数据线", "清洗前", "清洗后", "主要操作"], [
    ["视频", "526段", "526段（0剔除）", "解码校验/帧数对齐/分辨率与帧率核对"],
    ["图像", "4981帧", "2521帧（剔近重复2460）", "感知哈希去重；增强后回到5042帧"],
    ["解说", "40,923条", "40,376条", "去空386/超短159/重复1/无字1"],
    ["资讯", "122篇", "120篇", "Data-Juicer MinHash去重2篇"],
], "表2 清洗前后质量指标对比")
add_table(a, ["方式", "工具", "耗时", "结果"], [
    ["手工清洗", "clean_texts.py（自写规则）", "0.29秒", "122→122篇（轻量规则）"],
    ["自动化策展", "Data-Juicer 1.6.0（6算子）", "134秒", "122→120篇（MinHash近似去重）"],
], "表3 自动化策展与手工清洗效率对比")
body(a, "分析：（1）三类数据均达到“获取即可训练”标准——检测数据集经ultralytics管道冒烟验证、解说语料完成防泄漏划分，实验2/5可直接消费；（2）近重复剔除使图像训练集约减一半，避免高度相似帧导致验证指标虚高，这是后续消融实验结论可信的前提；（3）Data-Juicer单次运行含模型加载开销，小语料下耗时不占优，但其算子可配置、过程可复现，适合后续解说语料扩大规模后的策展；两者效率对比也直接满足任务书对自动化策展的要求；（4）4.0万条解说语料覆盖41场完整比赛时间线（含时间戳与当时比分），为实验5的RAG检索与风格微调提供了规模足够的中文领域语料。")

# 六、实验总结与展望
a = anchor["七．参考文献"]
body(a, "本实验完成了“AI篮球赛事解说员”的三类数据底座建设：视频（526段，全部通过清洗校验）、图像（YOLO标准数据集5042帧+补充帧7746帧）、解说文本（41场40,376条，按场次防泄漏划分），并沉淀了事件表、指标json、溯源文档与清理日志，实现每一步可追溯、可复现。踩坑与解决集中在网络环境（门控仓库、DNS劫持、系统代理）、接口逆向（分页死循环防护）与标注一致性（框同步增强、坐标系转换）三方面，具备较强的工程复用价值。")
body(a, "展望：（1）构造“画面事件特征—解说词”指令对（利用事件表的动作/时间/位置与解说时间戳对齐），作为实验5大模型微调的增强数据；（2）解说语料可经爬虫按需增量补充（当前规模已满足学习需要）；（3）实验2将基于本次数据集开展7组YOLO系列对比训练，进一步验证数据增强对检测性能的因果收益。")

# 七、参考文献（追加文末）
refs = [
    "[1] Yao H, et al. MultiSports: A Multi-Person Video Dataset of Spatio-Temporally Dense Sports Actions. ICCV 2021.",
    "[2] Cui Y, et al. SportsMOT: A Large Multi-Object Tracking Dataset in Multiple Sports Scenes. ICCV 2023.",
    "[3] Ultralytics. YOLOv8: 基于PyTorch的实时目标检测框架. https://github.com/ultralytics/ultralytics.",
    "[4] Alibaba. Data-Juicer: 面向大模型的数据处理系统. https://github.com/modelscope/data-juicer.",
    "[5] 直播吧文字直播平台. https://www.zhibo8.com（数据获取遵守robots协议与限速，仅课程用途）.",
    "[6] 《AI全栈开发》课程实验1任务书，西安邮电大学，2025.",
]
for ref in refs:
    p = para(ref, size=10.5, indent=False, align=WD_ALIGN_PARAGRAPH.LEFT)
    doc.paragraphs[-1]._p.addprevious(p._p) if False else None
# 参考文献追加到文档末尾（上面 para 已 add 到末尾，顺序天然正确）

# ---------- 5) 分工表 ----------
tbl = doc.tables[0]
duties = [
    "视觉数据获取（MultiSports/SportsMOT）与视频清洗校验",
    "MOT→YOLO转换、图像清洗（近重复剔除）与Data-Juicer自动化策展",
    "直播吧文字直播接口逆向、解说语料爬取",
    "解说语料清洗、按场次8:1:1划分与事件表构建",
    "图像框同步增强、数据集标准化与数据卡/溯源/合规文档、报告执笔",
]
for i, d in enumerate(duties):
    if i + 1 < len(tbl.rows):
        cell = tbl.rows[i + 1].cells[2]
        cell.text = ""
        r = cell.paragraphs[0].add_run(d)
        fmt_run(r, size=10.5)
print("[5] 分工表已填（学号姓名留空待填）")

doc.save(DST)
print(f"[OK] 已保存 -> {DST}")
