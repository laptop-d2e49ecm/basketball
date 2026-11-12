# -*- coding: utf-8 -*-
"""实验5 九章总报告生成器（python-docx）。

用法：backend\\.venv\\Scripts\\python.exe -X utf8 report/build_exp5_report.py
输出：report/实验5报告.docx

排版口径（按模板要求）：正文宋体小四（12pt）、英文 Times New Roman、行距 20 磅、
首行缩进 2 字符；标题黑体；图表标题五号（10.5pt）居中。
"""
from __future__ import annotations

import datetime as dt
from pathlib import Path

from docx import Document
from docx.enum.section import WD_SECTION
from docx.enum.table import WD_ALIGN_VERTICAL, WD_TABLE_ALIGNMENT
from docx.enum.text import WD_ALIGN_PARAGRAPH, WD_LINE_SPACING
from docx.oxml import OxmlElement
from docx.oxml.ns import qn
from docx.shared import Cm, Pt, RGBColor

REPO = Path(__file__).resolve().parents[1]
FIG = REPO / "report" / "figures"
OUT = REPO / "report" / "实验5报告.docx"
TEMPLATE = REPO / "report" / "template_cover.docx"

BODY_FONT_CN = "宋体"
BODY_FONT_EN = "Times New Roman"
HEAD_FONT = "黑体"


# ---------------------------------------------------------------- 样式工具
def _set_run_font(run, size=12, bold=False, cn=BODY_FONT_CN, en=BODY_FONT_EN, color=None):
    run.font.size = Pt(size)
    run.font.bold = bold
    run.font.name = en
    run._element.rPr.rFonts.set(qn("w:eastAsia"), cn)
    if color:
        run.font.color.rgb = color


def _trim_after_cover(doc: Document) -> None:
    """保留模板封面（到“时　间：”那一段），删掉其后的示例大纲。"""
    body = doc.element.body
    children = list(body.iterchildren())
    cut = None
    from docx.text.paragraph import Paragraph

    for i, ch in enumerate(children):
        if ch.tag.endswith("}p"):
            text = Paragraph(ch, doc).text.strip()
            if text.startswith("摘要"):
                cut = i
                break
    # 封面的“项目名称”用的是 Heading 1，会被目录抓进去；把它的大纲级别设为正文
    for ch in children[:cut]:
        if ch.tag.endswith("}p"):
            para_el = Paragraph(ch, doc)
            if para_el.text.strip().startswith("项目名称"):
                # 直接把封面的“项目名称”从 Heading 1 改成正文样式（目录只认标题样式），
                # 再给文字补粗体，位置与横线由段内 VML 线保持，不受影响。
                pPr = ch.get_or_add_pPr()
                style_el = pPr.find(qn("w:pStyle"))
                if style_el is not None:
                    style_el.set(qn("w:val"), doc.styles["Normal"].style_id)
                for run_el in ch.findall(qn("w:r")):
                    if run_el.find(qn("w:t")) is None:
                        continue
                    rPr = run_el.find(qn("w:rPr"))
                    if rPr is None:
                        rPr = OxmlElement("w:rPr")
                        run_el.insert(0, rPr)
                    if rPr.find(qn("w:b")) is None:
                        rPr.insert(0, OxmlElement("w:b"))

    if cut is None:
        return
    for ch in children[cut:]:
        if ch.tag.endswith("}sectPr"):
            continue
        body.remove(ch)


def setup_document() -> Document:
    """以学校模板为底（保留封面版式），再套用本报告的正文样式。"""
    if TEMPLATE.is_file():
        doc = Document(str(TEMPLATE))
        _trim_after_cover(doc)
    else:
        doc = Document()

    sec = doc.sections[0]
    sec.page_width = Cm(21.0)
    sec.page_height = Cm(29.7)
    sec.left_margin = Cm(3.0)
    sec.right_margin = Cm(2.6)
    sec.top_margin = Cm(2.5)
    sec.bottom_margin = Cm(2.5)
    sec.different_first_page_header_footer = True

    for style_name, size in (("Heading 1", 16), ("Heading 2", 14), ("Heading 3", 12)):
        st = doc.styles[style_name]
        st.font.name = BODY_FONT_EN
        st.font.size = Pt(size)
        st.font.bold = True
        st.font.color.rgb = RGBColor(0, 0, 0)
        st.element.rPr.rFonts.set(qn("w:eastAsia"), HEAD_FONT)

    # 目录样式：右对齐制表位 + 点线前导符，页码落在右边距
    from docx.enum.text import WD_TAB_ALIGNMENT, WD_TAB_LEADER

    for toc_name, indent in (("toc 1", 0.0), ("toc 2", 0.75)):
        if toc_name not in [x.name for x in doc.styles]:
            continue          # 模板里还没有 TOC 样式，等 Word 生成目录后再由脚本补
        st = doc.styles[toc_name]
        st.font.name = BODY_FONT_CN
        st.font.size = Pt(12)
        st.element.rPr.rFonts.set(qn("w:eastAsia"), BODY_FONT_CN)
        pf = st.paragraph_format
        pf.left_indent = Cm(indent)
        pf.first_line_indent = Cm(0)
        pf.line_spacing_rule = WD_LINE_SPACING.SINGLE
        pf.space_before = Pt(0)
        pf.space_after = Pt(2)
        pf.tab_stops.clear_all()
        pf.tab_stops.add_tab_stop(Cm(15.4), WD_TAB_ALIGNMENT.RIGHT, WD_TAB_LEADER.DOTS)

    # 专用正文样式：不动模板的 Normal，避免把封面行距改坏
    from docx.enum.style import WD_STYLE_TYPE

    if "正文CN" not in [st.name for st in doc.styles]:
        body_style = doc.styles.add_style("正文CN", WD_STYLE_TYPE.PARAGRAPH)
        body_style.base_style = doc.styles["Normal"]
    else:
        body_style = doc.styles["正文CN"]
    body_style.font.name = BODY_FONT_EN
    body_style.font.size = Pt(12)
    body_style.element.rPr.rFonts.set(qn("w:eastAsia"), BODY_FONT_CN)
    bpf = body_style.paragraph_format
    bpf.line_spacing_rule = WD_LINE_SPACING.EXACTLY
    bpf.line_spacing = Pt(20)
    bpf.space_before = Pt(0)
    bpf.space_after = Pt(0)
    return doc


def add_page_number_footer(doc: Document) -> None:
    footer = doc.sections[0].footer
    p = footer.paragraphs[0]
    p.alignment = WD_ALIGN_PARAGRAPH.CENTER
    run = p.add_run()
    for instr in ("PAGE",):
        fld_begin = OxmlElement("w:fldChar")
        fld_begin.set(qn("w:fldCharType"), "begin")
        instr_el = OxmlElement("w:instrText")
        instr_el.set(qn("xml:space"), "preserve")
        instr_el.text = f" {instr} "
        fld_end = OxmlElement("w:fldChar")
        fld_end.set(qn("w:fldCharType"), "end")
        run._r.append(fld_begin)
        run._r.append(instr_el)
        run._r.append(fld_end)
    _set_run_font(run, 9)


def _heading(doc: Document, text: str, level: int, size: int, before: int, after: int,
             spacing: int, page_break: bool = False):
    """用内置 Heading 样式（目录域才能识别），再覆盖字体与间距。"""
    p = doc.add_heading(level=level)
    pf = p.paragraph_format
    if page_break:
        pf.page_break_before = True
    pf.space_before = Pt(before)
    pf.space_after = Pt(after)
    pf.line_spacing = Pt(spacing)
    pf.keep_with_next = True
    r = p.add_run(text)
    _set_run_font(r, size, bold=True, cn=HEAD_FONT, en=HEAD_FONT)
    r.font.color.rgb = RGBColor(0, 0, 0)
    return p


def h1(doc: Document, text: str, page_break: bool = False) -> None:
    # 正文各章连续排版（模板本身连续）；摘要/参考文献/附录另起一页
    _heading(doc, text, 1, 16, 24, 12, 32, page_break=page_break)


def h2(doc: Document, text: str) -> None:
    _heading(doc, text, 2, 14, 12, 6, 24)


def h3(doc: Document, text: str) -> None:
    _heading(doc, text, 3, 12, 8, 4, 20)


def para(doc: Document, text: str, indent: bool = True, align=None) -> None:
    p = doc.add_paragraph(style="正文CN")
    pf = p.paragraph_format
    pf.first_line_indent = Pt(24) if indent else Pt(0)
    pf.alignment = align if align is not None else WD_ALIGN_PARAGRAPH.JUSTIFY
    r = p.add_run(text)
    _set_run_font(r, 12)


def bullet(doc: Document, text: str) -> None:
    p = doc.add_paragraph(style="正文CN")
    p.paragraph_format.left_indent = Pt(36)
    p.paragraph_format.first_line_indent = Pt(-12)   # 悬挂缩进，换行对齐到文字
    r = p.add_run("· " + text)
    _set_run_font(r, 12)


def caption(doc: Document, text: str) -> None:
    p = doc.add_paragraph()
    p.alignment = WD_ALIGN_PARAGRAPH.CENTER
    p.paragraph_format.space_before = Pt(4)
    p.paragraph_format.space_after = Pt(8)
    r = p.add_run(text)
    _set_run_font(r, 10.5, bold=True)


def table(doc: Document, headers: list[str], rows: list[list[str]], cap: str | None = None,
          widths: list[float] | None = None, spacer: bool = True) -> None:
    if cap:
        p = doc.add_paragraph()
        p.alignment = WD_ALIGN_PARAGRAPH.CENTER
        p.paragraph_format.keep_with_next = True
        p.paragraph_format.space_before = Pt(6)
        p.paragraph_format.space_after = Pt(4)
        r = p.add_run(cap)
        _set_run_font(r, 10.5, bold=True)

    t = doc.add_table(rows=1, cols=len(headers))
    t.style = "Table Grid"
    t.alignment = WD_TABLE_ALIGNMENT.CENTER
    t.autofit = False

    # 列宽（未指定则按可用宽度平均分配）
    text_w = 15.4
    if widths is None:
        widths = [text_w / len(headers)] * len(headers)
    for i, w in enumerate(widths):
        for cell in t.columns[i].cells:
            cell.width = Cm(w)

    for i, h in enumerate(headers):
        cell = t.rows[0].cells[i]
        cell.text = ""
        p = cell.paragraphs[0]
        p.alignment = WD_ALIGN_PARAGRAPH.CENTER
        p.paragraph_format.line_spacing_rule = WD_LINE_SPACING.SINGLE
        p.paragraph_format.space_before = Pt(2)
        p.paragraph_format.space_after = Pt(2)
        r = p.add_run(h)
        _set_run_font(r, 10.5, bold=True)

    for row in rows:
        cells = t.add_row().cells
        for i, v in enumerate(row):
            cells[i].text = ""
            p = cells[i].paragraphs[0]
            p.paragraph_format.line_spacing_rule = WD_LINE_SPACING.SINGLE
            p.paragraph_format.space_before = Pt(2)
            p.paragraph_format.space_after = Pt(2)
            r = p.add_run(str(v))
            _set_run_font(r, 10.5)

    # 尽量避免整表跨页（最后一行不加，否则会拖着后面的正文）
    for row in t.rows[:-1]:
        for cell in row.cells:
            for p in cell.paragraphs:
                p.paragraph_format.keep_with_next = True

    # 表头行跨页重复 + 每行禁止被拆到两页
    for idx, row in enumerate(t.rows):
        trPr = row._tr.get_or_add_trPr()
        cant = OxmlElement("w:cantSplit")
        trPr.append(cant)
        if idx == 0:
            hdr = OxmlElement("w:tblHeader")
            trPr.append(hdr)

    if spacer:
        sp = doc.add_paragraph()
        sp.paragraph_format.space_before = Pt(0)
        sp.paragraph_format.space_after = Pt(6)
        sp.paragraph_format.line_spacing = Pt(6)


def figure(doc: Document, filename: str, cap: str, width_cm: float = 14.0) -> None:
    path = FIG / filename
    if not path.is_file():
        para(doc, f"（缺图：{filename}）")
        return
    p = doc.add_paragraph(style="正文CN")
    pf = p.paragraph_format
    # 关键：图片段落必须单倍行距，否则会被 Normal 的“固定 20 磅”裁成一条边
    pf.line_spacing_rule = WD_LINE_SPACING.SINGLE
    pf.space_before = Pt(6)
    pf.space_after = Pt(2)
    pf.keep_with_next = True
    p.alignment = WD_ALIGN_PARAGRAPH.CENTER
    p.add_run().add_picture(str(path), width=Cm(width_cm))
    caption(doc, cap)


# ---------------------------------------------------------------- 封面 / 摘要
def _bottom_border(cell) -> None:
    tcPr = cell._tc.get_or_add_tcPr()
    borders = OxmlElement("w:tcBorders")
    bottom = OxmlElement("w:bottom")
    bottom.set(qn("w:val"), "single")
    bottom.set(qn("w:sz"), "8")
    bottom.set(qn("w:space"), "0")
    bottom.set(qn("w:color"), "000000")
    borders.append(bottom)
    tcPr.append(borders)


def cover(doc: Document) -> None:
    """按学校模板封面复刻：校名 / 实验名 / 项目总结报告 / 项目名称 / 组号 /
    组员信息（学号-姓名-分工 小表）/ 时间。"""
    for _ in range(2):
        doc.add_paragraph()

    p = doc.add_paragraph()
    p.alignment = WD_ALIGN_PARAGRAPH.CENTER
    r = p.add_run("西 安 邮 电 大 学")
    _set_run_font(r, 28, bold=True, cn=HEAD_FONT, en=HEAD_FONT)

    doc.add_paragraph()
    p = doc.add_paragraph()
    p.alignment = WD_ALIGN_PARAGRAPH.CENTER
    r = p.add_run("AI 全栈开发实验")
    _set_run_font(r, 22, bold=True, cn=HEAD_FONT, en=HEAD_FONT)

    doc.add_paragraph()
    p = doc.add_paragraph()
    p.alignment = WD_ALIGN_PARAGRAPH.CENTER
    r = p.add_run("项目总结报告")
    _set_run_font(r, 18, bold=True, cn=HEAD_FONT, en=HEAD_FONT)

    for _ in range(3):
        doc.add_paragraph()

    def field_row(label: str) -> None:
        t = doc.add_table(rows=1, cols=2)
        t.autofit = False
        t.alignment = WD_TABLE_ALIGNMENT.LEFT
        tblPr = t._tbl.tblPr
        tblW = OxmlElement("w:tblW")
        tblW.set(qn("w:w"), str(int(13.8 / 2.54 * 1440)))  # 3.4 + 10.4
        tblW.set(qn("w:type"), "dxa")
        tblPr.append(tblW)
        layout = OxmlElement("w:tblLayout")
        layout.set(qn("w:type"), "fixed")
        tblPr.append(layout)
        row = t.rows[0]
        row.height = Cm(1.0)
        c0, c1 = row.cells
        c0.width = Cm(3.4)
        c1.width = Cm(10.4)
        p0 = c0.paragraphs[0]
        p0.alignment = WD_ALIGN_PARAGRAPH.RIGHT
        p0.paragraph_format.line_spacing_rule = WD_LINE_SPACING.SINGLE
        r0 = p0.add_run(label + "：")
        _set_run_font(r0, 14)
        c0.vertical_alignment = WD_ALIGN_VERTICAL.BOTTOM
        c1.vertical_alignment = WD_ALIGN_VERTICAL.BOTTOM
        _bottom_border(c1)

    field_row("项目名称")
    field_row("组　　号")

    p = doc.add_paragraph()
    p.alignment = WD_ALIGN_PARAGRAPH.RIGHT
    p.paragraph_format.right_indent = Cm(12.0)   # 让标签右端与 3.4cm 标签列对齐
    p.paragraph_format.space_before = Pt(10)
    p.paragraph_format.space_after = Pt(4)
    r = p.add_run("组员信息：")
    _set_run_font(r, 14)

    members = doc.add_table(rows=1, cols=3)
    members.style = "Table Grid"
    members.autofit = False
    members.alignment = WD_TABLE_ALIGNMENT.LEFT
    # 与上面三条横线左端对齐：缩进 3.4cm，总宽 10.4cm
    tblPr = members._tbl.tblPr
    tbl_ind = OxmlElement("w:tblInd")
    tbl_ind.set(qn("w:w"), str(int(3.4 / 2.54 * 1440)))
    tbl_ind.set(qn("w:type"), "dxa")
    tblPr.append(tbl_ind)
    # 固定表格布局与总宽，避免 Word 自动撑到页宽
    tblW = OxmlElement("w:tblW")
    tblW.set(qn("w:w"), str(int(10.4 / 2.54 * 1440)))
    tblW.set(qn("w:type"), "dxa")
    tblPr.append(tblW)
    layout = OxmlElement("w:tblLayout")
    layout.set(qn("w:type"), "fixed")
    tblPr.append(layout)

    headers = [("学号", 3.6), ("姓名", 2.8), ("分工", 4.0)]
    for j, (h, w) in enumerate(headers):
        cell = members.rows[0].cells[j]
        cell.width = Cm(w)
        pc = cell.paragraphs[0]
        pc.alignment = WD_ALIGN_PARAGRAPH.CENTER
        pc.paragraph_format.line_spacing_rule = WD_LINE_SPACING.SINGLE
        rr = pc.add_run(h)
        _set_run_font(rr, 10.5, bold=True)
    for _ in range(5):
        cells = members.add_row().cells
        for j, w in enumerate([3.6, 2.8, 4.0]):
            cells[j].width = Cm(w)
        for j in range(3):
            pc = cells[j].paragraphs[0]
            pc.paragraph_format.line_spacing_rule = WD_LINE_SPACING.SINGLE
            pc.add_run("")

    doc.add_paragraph()
    field_row("时　　间")

    for _ in range(3):
        doc.add_paragraph()
    p = doc.add_paragraph()
    p.alignment = WD_ALIGN_PARAGRAPH.CENTER
    r = p.add_run("2026 年 11 月")
    _set_run_font(r, 12)


def toc(doc: Document) -> None:
    """目录页：TOC 域（打开后按 F9 或在导出前由脚本更新）。"""
    p = doc.add_paragraph()
    p.paragraph_format.page_break_before = True
    p.alignment = WD_ALIGN_PARAGRAPH.CENTER
    p.paragraph_format.space_after = Pt(14)
    r = p.add_run("目　录")
    _set_run_font(r, 18, bold=True, cn=HEAD_FONT, en=HEAD_FONT)

    p2 = doc.add_paragraph()
    run = p2.add_run()
    begin = OxmlElement("w:fldChar")
    begin.set(qn("w:fldCharType"), "begin")
    instr = OxmlElement("w:instrText")
    instr.set(qn("xml:space"), "preserve")
    instr.text = ' TOC \\o "1-2" \\h \\z \\u '
    sep = OxmlElement("w:fldChar")
    sep.set(qn("w:fldCharType"), "separate")
    placeholder = OxmlElement("w:t")
    placeholder.text = "（目录将在 Word 中自动生成）"
    end = OxmlElement("w:fldChar")
    end.set(qn("w:fldCharType"), "end")
    for el in (begin, instr, sep, placeholder, end):
        run._r.append(el)


def abstract(doc: Document) -> None:
    h1(doc, "摘　要", page_break=True)
    for text in [
        "本项目以“AI 篮球赛事解说员”为主线，把课程五个实验串成一条从数据到产品的完整链路："
        "实验 1 采集并清洗多源异构数据，实验 2 训练球员检测模型，实验 3 做量化与蒸馏压缩，"
        "实验 4 把模型封装成前后端 Web 系统，实验 5 在此基础上接入大模型 Agent，"
        "让系统能听懂自然语言、自己决定调用哪个工具，并把结果显示在对话页上。",
        "数据侧，建成三类资产：篮球视频 526 段、YOLO 格式检测数据集 5,042 帧（含增强）、"
        "解说语料 41 场共 40,376 条（按场次 8:1:1 划分，杜绝跨集合泄漏）。"
        "模型侧，A2′ 检测模型在 clean190 单口径下 mAP50 达 0.992，INT8 量化后体积由 12.8 MB 压缩到 3.5 MB（−72.5%），"
        "mAP50 仅降 0.02pp。系统侧，实验 4 交付了视频工作台、球员检测、解说分类、图文匹配四个页面与 12 个 REST 接口；"
        "实验 5 新增 5 个 Agent 工具与 /api/v1/agent/chat，工具选择准确率 10/10，"
        "官方直连端到端均值 1.77 s（对比中转方案 49.96 s），前端 /agent 页三场景闭环通过。",
        "微调侧，用 100 条指令数据对 Qwen3-1.7B 做 4-bit QLoRA，10 道考题上从基座 80% 提升到 100%，"
        "86 条 held-out 上从 79.1% 提升到 94.2%，反超 DeepSeek 零样本的 86.0%；"
        "并把 LoRA 后端接进 Agent 工具，实现“微调模型参与线上推理”的闭环。",
        "本报告同时记录了工程过程中的真实问题与修复：数据增强缺陷导致的重训、"
        "中转链路 186 秒的长尾、量化并未降低延迟的反直觉结论、"
        "以及评测脚本里“PeftModel 就地改写基座”这类会让结论造假的坑。",
    ]:
        para(doc, text)

    p = doc.add_paragraph()
    p.paragraph_format.space_before = Pt(12)
    r = p.add_run("关键词：")
    _set_run_font(r, 12, bold=True)
    r = p.add_run("目标检测；模型量化；大模型 Agent；LoRA 微调；LangChain；FastAPI；Vue 3")
    _set_run_font(r, 12)


# ---------------------------------------------------------------- 第一、二章
def chapter1(doc: Document) -> None:
    h1(doc, "第一章　项目背景与概述", page_break=True)

    h2(doc, "1.1　项目背景与研究意义")
    para(doc, "体育赛事视频正在从“看”走向“读懂”。一场业余或职业篮球比赛，人工剪辑与解说需要小时级投入，"
              "而比赛画面里真正影响观感的信息——谁在场上、球在谁手里、发生了什么动作、比分怎么变——"
              "本质上都是可以被视觉模型结构化出来的。近两年，目标检测与多模态大模型的成熟，"
              "让“自动看懂比赛并说出人话”第一次具备了工程可行性。")
    para(doc, "本项目的意义有三层。其一是工程闭环：从原始视频到可交互产品，完整走一遍数据、训练、压缩、"
              "服务化、智能体的全链路，而不是停留在 notebook 里的一次训练。其二是数据意识："
              "课程反复强调 Data-Centric AI，本项目用“增强缺陷导致重训”的真实事故说明了数据质量如何决定上限。"
              "其三是资源约束下的取舍：在 8 GB 显存的笔记本上，如何用 4-bit 量化、LoRA、"
              "以及“小模型做领域任务、大模型做通用推理”的分工，把大模型能力真正落到一台普通电脑上。")

    figure(doc, "fig1_loop.png", "图 1-1　实验 1→5 全流程闭环与数据流", 15.0)

    h2(doc, "1.2　需求分析与应用场景")
    para(doc, "目标用户是球队助教、赛事剪辑与普通球迷。核心需求可以拆成四问：场上有几个人（检测）、"
              "这段解说在说什么动作（文本分类）、这段画面和这句话对不对得上（图文匹配）、"
              "以及“我能不能直接用一句话问系统”（对话式 Agent）。")
    para(doc, "对应的典型场景包括：赛后快速回看某个时间段的人员变化；把解说文字自动归到动作类别做统计；"
              "检查一段解说与配图是否属于同一场比赛；以及用自然语言让系统“看一眼这张图”“翻一句真人解说”。"
              "这些场景共同决定了一个约束：系统必须能在普通笔记本上跑起来，且响应时间可接受。")

    h2(doc, "1.3　技术选型依据")
    para(doc, "检测模型选 YOLOv8 系列，理由是单阶段、部署成熟、ONNX 导出链路完整，且 nano/m 两档可以覆盖"
              "“能跑”与“更准”两种需求。压缩路线选 INT8 静态量化 + 知识蒸馏，因为部署环境以 CPU 为主，"
              "量化的体积与吞吐收益最直接。Web 层选 FastAPI + Vue 3：前者与 Python 模型同进程、"
              "自带 OpenAPI 文档，后者组件生态成熟、上手快。")
    para(doc, "Agent 层选 LangChain 1.x 的 create_agent，原因是它把“工具调用—多轮—状态”封装成图结构，"
              "与课程要求的“工具编排”直接对应；模型接入统一走 OpenAI 兼容端点，"
              "使得“换厂商只改三个环境变量”成为可能。微调选 QLoRA，是在 8 GB 显存下唯一现实的全参数替代方案。")

    h2(doc, "1.4　项目目标与预期成果")
    para(doc, "项目目标按五个实验分解：")
    bullet(doc, "实验 1：产出可直接训练的三类数据资产，并通过独立验证（解码、标注配对、防泄漏划分）。")
    bullet(doc, "实验 2：在同一数据、同一超参下完成模型对比，用 test 集指标说明“增强是否有效、容量是否值得”。")
    bullet(doc, "实验 3：在精度不显著下降的前提下，把检测模型压到 4 MB 以内，并给出误差结构分析。")
    bullet(doc, "实验 4：交付可运行的前后端系统，接口体系统一、错误码统一、页面在三个断点下可用。")
    bullet(doc, "实验 5：在系统上接入大模型 Agent，工具调用准确率 ≥90%、端到端 ≤5 s，并完成一次真实微调。")
    table(doc,
          ["实验", "输入", "主要产出"],
          [["1 数据采集", "公开数据集、直播接口", "526 段视频、5,042 帧检测集、40,376 条解说语料"],
           ["2 模型训练", "检测集（原始/增强）", "A1/A2/M1 三组权重与对比结论"],
           ["3 算法优化", "A2′ 权重", "3.5 MB INT8 模型、蒸馏学生、部署矩阵"],
           ["4 前后端", "检测模型 + 数据资产", "五页前端、12 个接口、视频 Worker"],
           ["5 Agent", "实验4 接口 + 解说语料", "5 个工具、/agent 对话页、LoRA 适配器"]],
          "表 1-1　五个实验的输入与产出",
          widths=[3.0, 5.2, 7.2])
    para(doc, "预期成果是一套“能演示、能复现、能讲清取舍”的系统：一条命令起服务，一个页面走完主流程，"
              "一份报告说清每个数字从哪来。")


def chapter2(doc: Document) -> None:
    h1(doc, "第二章　实验环境与技术栈")

    h2(doc, "2.1　硬件环境配置")
    para(doc, "本项目跨两台机器完成：本地笔记本负责数据处理、量化、Web 开发与 Agent 集成；"
              "云端 Kaggle T4 负责检测模型的训练与蒸馏。两边的指标口径在报告中分别标注，不混用。")
    table(doc,
          ["环境", "配置", "承担的工作"],
          [["本地笔记本", "Windows 11 家庭中文版；AMD Ryzen 9 7945HX（16 核）；16 GB 内存；NVIDIA RTX 5060 Laptop 8 GB（驱动 591.97）",
            "数据清洗、ONNX 量化、前后端开发、Agent 集成、QLoRA 微调"],
           ["云端 Kaggle", "Tesla T4 ×2（16 GB ×2）", "YOLOv8 训练（A1/A2/M1）、知识蒸馏"],
           ["推理设备", "CPU（部署默认）与 GPU（可选）", "实验 4/5 的服务端推理，默认 CPU 即可跑通"]],
          "表 2-1　硬件环境")

    h2(doc, "2.2　软件与开发环境")
    table(doc,
          ["类别", "组件与版本"],
          [["操作系统", "Windows 11；云端为 Kaggle Linux 镜像"],
           ["Python", "本地 3.12.16（后端 venv）；训练机 3.11.5"],
           ["深度学习", "PyTorch 2.11.0+cu128（本地）/ 2.14.0（训练机）；ultralytics 8.4.176（锁定版本）"],
           ["推理与压缩", "ONNX Runtime；onnxruntime quantize_static（QDQ）；OpenVINO/TensorRT（对照）"],
           ["大模型", "Qwen3-1.7B（本地 4-bit）；DeepSeek（OpenAI 兼容 API）"],
           ["微调栈", "transformers 5.22、peft 0.21、trl 1.17、bitsandbytes 0.50、datasets"],
           ["Agent", "LangChain 1.x（create_agent）、langchain-openai"],
           ["后端", "FastAPI、Uvicorn、SQLite（WAL）、Celery + Redis（可选）"],
           ["前端", "Vue 3、TypeScript、Vite、Vue Router、Pinia、Ant Design Vue"],
           ["测试", "pytest、vitest、Playwright（Edge/Firefox）"]],
          "表 2-2　软件与依赖版本")

    h2(doc, "2.3　主要技术框架与工具")
    para(doc, "系统在运行时分四个进程：前端开发服务器（5173）、FastAPI 接口进程（8000）、视频处理 Worker"
              "（独立进程，轮询 SQLite 认领任务）、以及可选的 Celery 消费者。四者共享同一个 SQLite 数据库"
              "与任务目录，接口与 Worker 通过任务状态机解耦，避免长任务阻塞请求。")
    para(doc, "模型侧分三条运行路径：图像检测走 ONNX Runtime（INT8，CPU）；文本分类走 scikit-learn 的"
              "TF-IDF + LinearSVC（毫秒级）；对话与工具编排走 LangChain + 大模型 API，"
              "需要本地模型时切到 4-bit Qwen3 + LoRA（懒加载）。")

    h2(doc, "2.4　版本管理与协作工具")
    para(doc, "代码托管在 GitHub 私有仓库，主分支 master。协作遵循三条约定：一是“先改契约再改代码”，"
              "接口字段、错误码、工具清单都先在 CONTRACT.md 定稿；二是大文件不入库（模型权重、适配器、"
              "视频样本走网盘或本地目录，.gitignore 明确排除）；三是每次提交只做一件事，"
              "commit message 带实验编号，便于回溯“这个数字是哪次提交产生的”。")
    para(doc, "密钥管理上，大模型 API Key 只存在于后端 .env（已 gitignore），不写进代码、不进报告截图；"
              "团队交接时通过私发渠道传递，仓库里只保留 .env.example 模板。")


def chapter3(doc: Document) -> None:
    h1(doc, "第三章　数据采集与预处理")

    h2(doc, "3.1　数据需求分析")
    para(doc, "系统的三种能力（看得见人、看得懂事、说得出话）对应三类数据：检测图像、动作标注视频、解说文本。"
              "检测图像需要逐帧的球员框；动作标注需要“什么时间、什么动作、框在哪”；解说文本需要真实的中文"
              "直播语料，既能做分类标注，也能做大模型微调与检索。三类数据的使用边界在实验 1 就写进了数据集卡片："
              "仅用于课程实验与学术研究，SportsMOT 遵守 CC BY-NC 4.0 非商业条款，直播语料不对外分发。")

    h2(doc, "3.2　数据采集与收集")
    para(doc, "三条数据线的获取方式各不相同，各自解决了不同的工程问题：")
    bullet(doc, "检测主数据集：SportsMOT 篮球子集（ICCV 2023，约 13 GB），经 hf-mirror 镜像以 HTTP Range 分段断点续传，"
                "已完成分段跳过、失败分段统一补漏；下载器内置 DoH 解析真实 IP 并用 curl --resolve 钉住，绕过本机 DNS 劫持。")
    bullet(doc, "动作标注：MultiSports（ICCV 2021）为门控仓库，镜像站不转发 Authorization 头导致 401，"
                "改为携带 Bearer token 直连官方域名，仅下载含标注的 trainval 拆分（15.55 GB），token 只经环境变量传递。")
    bullet(doc, "解说语料：直播吧文字直播，接口由页面 JS 逆向（分页 JSON、每页 10 条、33 字段），"
                "限速 0.5 秒/页、3 并发、断点续爬、UA 带课程标识；针对“超界页码返回末页”导致的翻页死循环，"
                "用“整页记录 ID 与已爬集合完全重复即终止 + 200 页硬上限”双重防护。共采集 41 场 40,923 条原始记录。")
    table(doc,
          ["数据线", "来源", "原始规模", "授权/合规"],
          [["检测图像", "SportsMOT 篮球子集", "约 13 GB", "CC BY-NC 4.0（非商业）"],
           ["动作标注", "MultiSports trainval", "15.55 GB", "学术使用，token 不落盘"],
           ["解说文本", "直播吧文字直播", "40,923 条 / 41 场", "课程内使用，不对外分发"],
           ["背景语料", "篮球资讯", "122 篇", "公开网页，限速爬取"]],
          "表 3-1　数据来源与授权")

    h2(doc, "3.3　数据预处理流程")
    para(doc, "全部脚本按阶段编号组织在 scripts/ 下：01 获取 → 02 清洗 → 03 增强 → 04 标准化 → 05 评估。"
              "原始数据目录只读不覆盖，处理结果写入 data/processed 与 data/splits；每一步的输入、输出、参数与"
              "检查结果以 clean_metrics.json、convert_metrics.json 与日志形式落盘，配合 PROVENANCE.md 实现全链路可追溯。")
    para(doc, "划分单元的选择是防泄漏的关键：视觉数据按“比赛序列”划分，同一序列的所有帧及其增强副本跟随序列"
              "落到同一子集；解说语料按“场次”划分。这样从源头保证同一场比赛的内容不跨 train/val/test，"
              "避免指标虚高。随机种子固定为 42。")

    h2(doc, "3.4　数据清洗与增强")
    para(doc, "视频清洗对 526 段 mp4 逐段校验首/中/尾帧解码、帧数与标注对齐（±2 帧）、分辨率与帧率，526/526 全部通过。"
              "图像清洗用感知哈希剔除近重复帧，4,981 → 2,521，剔除率 49.4%——根源是 MOT 转 YOLO 时相邻抽样帧画面几乎不变，"
              "这批高相似帧若进入训练集会同时造成训练冗余与验证指标虚高。")
    para(doc, "图像增强做水平翻转 + 仿射 + 色彩抖动，并同步变换标注框，2,521 → 5,042 帧，仅 51 个过小出画框被丢弃。"
              "解说清洗去除空行、超短行与重复记录，33 字段统一为 5 字段（场次/时间/文本/解说员/比分），40,923 → 40,376 条。")
    para(doc, "实验中段发现的一个严重问题值得单独记录：torchvision v2 的变换以 numpy 数组为输入时，图像没有被变换、"
              "标注框却被变换，导致全部 _aug0 副本实为“原图 + 随机平移的框”。修复后以三层校验重建增强集，"
              "并把 A1′/A2′/M1′ 在同一协议下重训——这也是本报告最终采用 clean190 单口径的原因。")
    figure(doc, "fig1_vision_before_after.png", "图 3-1　视觉数据清洗前后帧数归因与划分结果", 14.0)

    h2(doc, "3.5　数据集建设")
    para(doc, "图像统一 640×640 后按序列 8:1:1 划分，train/val/test = 4,316/346/380 帧（24/3/3 个序列）；"
              "动作标注转为 6,247 行事件表（视频/动作/起止帧与秒/框坐标），并按 2 fps 截取有标注帧生成补充检测集"
              "（7,746 帧 / 9,094 框）；解说语料按场次切分为 33/4/4 场、共 40,376 条，供实验 5 的微调与 RAG 使用。")
    table(doc,
          ["数据资产", "规模", "用途"],
          [["YOLO 检测集（增强后）", "5,042 帧（train 4,316 / val 346 / test 380）", "实验 2 训练、实验 3 压缩"],
           ["补充检测帧", "7,746 帧 / 9,094 框", "扩充样本多样性"],
           ["动作事件表", "6,247 行（18 类动作）", "画面事件→解说的结构化桥梁"],
           ["解说语料", "41 场 40,376 条（33/4/4 划分）", "实验 5 微调与 RAG 检索"],
           ["资讯背景语料", "122 篇", "背景知识、数据策展对比实验"]],
          "表 3-2　数据资产总览")
    figure(doc, "fig4_dataset_tree.png", "图 3-2　数据目录与文件组织", 12.5)
    para(doc, "数据质量按四维评分：完整性 100、一致性 100（保留集内重复为 0）、代表性 81.2（序列帧数基尼系数 0.188）、"
              "时效性 90，综合 92.8/100。另用 Data-Juicer 对同一批 122 篇语料做自动化策展对照："
              "六算子流水线耗时 134 s、输出 120 篇，而手工脚本 0.29 s——小语料下自动化不占优，"
              "但其参数化与可复现性在语料扩大后才有价值，这个结论也写进了报告。")
    para(doc, "三类资产在下游的消费关系是明确的：检测集直接喂给实验 2 的训练脚本；"
              "A2′ 权重进入实验 3 做量化与蒸馏；量化后的 ONNX 被实验 4 的检测接口加载；"
              "解说语料一分为二——训练卷供实验 5 抽样微调，全量供 RAG 检索。"
              "这条链路也解释了为什么数据版本必须可追溯：任何一次重训都会沿着链路影响下游全部指标。")
    table(doc,
          ["数据资产", "消费者", "消费方式"],
          [["YOLO 检测集", "实验 2 / 实验 3", "训练、验证、量化校准"],
           ["A2′ 权重", "实验 3 / 实验 4", "导出 ONNX、INT8 量化后上线"],
           ["解说语料", "实验 5", "抽 100 条微调；全量建 RAG 索引"],
           ["动作事件表", "实验 5（规划）", "事件→解说配对，供后续动作识别"]],
          "表 3-3　数据资产与下游实验的对应关系",
          widths=[4.2, 4.6, 6.6])


def chapter4(doc: Document) -> None:
    h1(doc, "第四章　模型设计与训练")

    h2(doc, "4.1　模型选型分析")
    para(doc, "任务是单类实时目标检测（标注只有 player 一类），因此需要单阶段检测器。选型设计为 8 组对比"
              "（v5/v8/11 三代 × n/s 两档 + v8m 容量组），实际执行核心 3 组：A1（YOLOv8n + 原始帧 2,158）、"
              "A2（YOLOv8n + 增强后 4,316）、M1（YOLOv8m + 增强后 4,316）。A2−A1 用于回答“增强有没有用”，"
              "M1−A2 用于回答“容量还值不值得加”。")

    h2(doc, "4.2　模型架构设计")
    para(doc, "YOLOv8 采用 CSPDarknet 主干 + PAN-FPN 颈部 + 解耦检测头，输出 (1, 5, 8400) 的张量"
              "（4 个坐标 + 1 个类别分数），单类场景下分类分支只有一个通道。这一结构决定了后续量化的一个关键点："
              "检测头里的 DFL、Softmax 与坐标变换必须保持浮点，否则 0–640 的像素坐标与 0–1 的概率共存会让量化误差失控。")

    h2(doc, "4.3　训练策略与配置")
    para(doc, "三组共用同一套超参：imgsz=640、batch=16（M1 因显存改为 8）、epochs=50、patience=15 早停、"
              "cos_lr=True、AMP 混合精度、seed=42；按综合适应度 0.1×mAP50 + 0.9×mAP50-95 选轮。"
              "训练在 Kaggle T4 上完成，权重与 results.csv 全部归档到 models/exp2/。")

    h2(doc, "4.4　模型训练过程")
    para(doc, "第一轮（v1 数据）结果如下：A1 的 mAP50/mAP50-95 为 0.371/0.245，A2 为 0.418/0.262，M1 为 0.424/0.271。"
              "三个结论很清楚：数据增强带来 +4.7pp mAP50 的提升（A2−A1），这是增强有效性的直接证据；"
              "容量从 n 升到 m 只多 0.6pp（M1−A2），代价却是参数量 3.2M → 25.9M，性价比不高；"
              "因此部署选型定在 A2 这一档。")
    table(doc,
          ["超参", "取值", "说明"],
          [["imgsz", "640", "与实验1标准化尺寸一致"],
           ["batch", "16（M1 为 8）", "受显存限制"],
           ["epochs / patience", "50 / 15", "早停，三组均在第 43–50 轮收敛"],
           ["optimizer / lr", "SGD / 0.01", "ultralytics 默认，配合余弦调度"],
           ["cos_lr / AMP", "True / True", "平滑收敛、省显存"],
           ["seed", "42", "三组一致，保证可比"]],
          "表 4-1　训练超参（三组共用）",
          widths=[3.6, 4.2, 7.6])
    para(doc, "训练过程的观察也值得记录：A1 因为样本少，验证集 loss 在第 20 轮后开始震荡，早停在 49 轮；"
              "A2 与 M1 的收敛更平稳，但 M1 在 batch=8 下每轮耗时约为 A2 的两倍，"
              "这也是“容量换精度”在工程上不划算的另一面——训练成本同样要计入选型。")
    table(doc,
          ["组", "模型", "训练数据", "参数量(M)", "mAP50", "mAP50-95"],
          [["A1", "YOLOv8n", "原始 2,158 帧", "3.2", "0.371", "0.245"],
           ["A2", "YOLOv8n", "增强 4,316 帧", "3.2", "0.418", "0.262"],
           ["M1", "YOLOv8m", "增强 4,316 帧", "25.9", "0.424", "0.271"]],
          "表 4-2　实验 2 三组对比（v1 口径，test 380）")
    para(doc, "中期复核时发现实验 1 的增强缺陷（见 3.4），三组模型全部在同一协议下重训，并把测试集统一到"
              "“clean190 原始帧”这一单一口径：A1′ 0.990、A2′ 0.992、M1′ 0.993，INT8 量化后 0.990。"
              "新旧口径不能混用，报告中凡涉及精度的地方均标注口径。这一“发现缺陷—重做—统一口径”的过程本身，"
              "比任何单点精度都更能说明数据质量对结论的决定性作用。")


def chapter5(doc: Document) -> None:
    h1(doc, "第五章　算法优化")

    h2(doc, "5.1　性能评估基准")
    para(doc, "优化效果必须在同一把尺子上比较。本实验固定测试集为 test 划分的 190 张原始帧（1,792 个标注框），"
              "与训练集零重叠；评估器为自研 all-point 插值 AP，先与 ultralytics 官方口径对齐验证"
              "（A2′ FP32 ONNX 得 0.9903，官方 0.9910，差 0.07pp，来自插值方式差异）。"
              "速度指标统一记录单图 P50/P95 与 Batch 32 吞吐，跨后端对照时锁定输入尺寸与预处理。")

    h2(doc, "5.2　算法优化一：INT8 静态量化")
    para(doc, "管线为 A2′ best.pt → ONNX FP32（12.8 MB）→ onnxruntime quantize_static（QDQ，per-tensor）→ INT8 ONNX。"
              "关键工程点是算子选择：只量化 Conv/Gemm/MatMul 等含权重的算子，检测头的 DFL、Softmax 与坐标变换保持 FP32，"
              "否则分数会被整体舍入为 0。校准集做了三组对照：E1（val 173 张原始帧，部署选型）、E2（train 500 张，验证校准量增益）、"
              "E4（per-channel 权重量化，验证精细化增益）。")
    para(doc, "结果是体积 12.8 MB → 3.5 MB（−72.5%，接近 INT8 理论极限 75%），判定精度几乎无损"
              "（mAP50 0.9910 → 0.9908，−0.02pp），代价集中在定位精度 mAP50-95（−2.19pp）。"
              "误差结构分析显示：中目标 AP50 0.989→0.989、大目标 0.962→0.976，小目标样本仅 1 框无统计意义——"
              "也就是说量化没有损害“判断这里有没有人”，损害的是“框得多准”。")
    table(doc,
          ["模型", "体积", "mAP50", "mAP50-95", "说明"],
          [["A2′ FP32 ONNX", "12.8 MB", "0.9910", "0.7563", "量化基线"],
           ["A2′ INT8 ONNX", "3.5 MB", "0.9908", "0.7344", "−72.5% 体积，定位 −2.19pp"],
           ["蒸馏学生 dis=6", "12.8 MB", "0.9907", "0.7587", "精度略优于 A2′"],
           ["蒸馏学生 + INT8", "3.5 MB", "0.9901", "0.7348", "叠加后定位 −2.39pp"]],
          "表 5-1　量化与蒸馏结果（test 190 原始帧）")

    h2(doc, "5.3　算法优化二：知识蒸馏")
    para(doc, "单类检测下，分类 logit 只有一维，传统的 KL 软标签蒸馏信息量近乎为零，温度系数也失去意义。"
              "因此改用前景加权特征蒸馏：教师 M1′（0.9932/0.7894）全程冻结，学生以 A2′ 权重初始化，"
              "lr0=0.002、12 epoch，蒸馏权重 dis 取 3/6/9 做消融。结果表明三组学生都没有超过未蒸馏的 A2′，"
              "任务书“优于同量级未蒸馏模型”一项**未达成**——报告如实记录，并分析原因是教师与学生容量差过大、"
              "单类任务下特征蒸馏的增益被数据质量差掩盖。")

    h2(doc, "5.4　算法优化三：推理后端与硬件加速")
    para(doc, "CPU 侧对 PyTorch、ONNX Runtime、OpenVINO 三后端做同机对照：ORT FP32 单图 81.42 ms 略慢于 PyTorch 的 72.22 ms"
              "（单图调度与预处理开销占比高），但 Batch 32 吞吐 13.97 图/秒 vs 8.98 图/秒，提升 55.6%。"
              "GPU 侧由队友完成 TensorRT FP16 + 端到端流水线，单图延迟下降 58.0%、批量吞吐提升 264.4%、"
              "mAP50 差 0.29pp，三项门槛全部达标。")
    para(doc, "由此形成部署矩阵：有 GPU 走 TensorRT FP16 组合；纯 CPU 且重吞吐走 ORT INT8 + 批处理；"
              "纯 CPU 且重单张延迟则保留 PyTorch。实验 4 的后端默认走 ORT INT8，正是这张矩阵的直接落地。")

    h2(doc, "5.5　优化测试与验证")
    para(doc, "三条线交叉验证了同一个结论：INT8 的精度代价稳定在“判定无损、定位 1.6–2.4pp”这个量级"
              "（精度线 v1 干净口径 1.7pp、v2 复测 2.19pp，速度线独立测得 1.58pp）。"
              "鲁棒性上补充了噪声与模糊扰动测试，量化模型在扰动下的退化幅度与 FP32 同向，未出现异常崩塌。"
              "结论写入部署矩阵，并作为实验 4 模型选型（a2_int8_val346.onnx，3.6 MB）的依据。")


def chapter6(doc: Document) -> None:
    h1(doc, "第六章　前后端开发")

    h2(doc, "6.1　系统架构设计")
    para(doc, "系统采用前后端分离 + 独立 Worker 的四进程结构：Vue 3 单页应用（5173）、FastAPI 接口进程（8000）、"
              "视频处理 Worker（独立进程，轮询 SQLite 认领任务）、可选 Celery 消费者（Redis 作 broker）。"
              "接口与 Worker 通过任务状态机（pending → running → ready/failed）解耦，长任务不阻塞请求；"
              "视频进度通过 WebSocket 推送到前端。")

    h2(doc, "6.2　前端开发")
    para(doc, "前端用 Vue 3 + TypeScript + Vite + Ant Design Vue，共五个页面：视频分析工作台（v3，独立整页 iframe）、"
              "球员图像检测、解说文本分类、图文匹配，以及实验 5 新增的 AI 解说对话页。"
              "导航与布局在 App.vue 统一管理，视频页因沿用第三版独立页面而单独渲染。")
    para(doc, "对话页 AgentChatView.vue 是实验 5 的主要前端产出：气泡区渲染 Agent 回复，工具调用以"
              "“🔧 球员检测 · 成功 · 81ms”形式呈现并可展开看入参/结果，错误按契约区分 400/404/429/500/504，"
              "超时与失败会给出“重试上一句”按钮；移动端用 max-width + word-break 保证气泡不溢出。")
    figure(doc, "agent_03_multiturn.png", "图 6-1　/agent 页多轮对话（Edge）", 14.5)

    h2(doc, "6.3　后端开发")
    para(doc, "后端以 FastAPI 组织，所有 JSON 接口使用统一信封 {code, result, msg}，成功 code=0，"
              "失败 code 为 HTTP 状态码、result 为 null、msg 给原因；异常体系把 InputError→400、NotFoundError→404、"
              "ModelError→500 统一注册为全局 handler。接口版本统一为 /api/v1。")
    table(doc,
          ["方法", "路径", "作用"],
          [["GET", "/api/v1/health", "服务与模型加载状态"],
           ["POST", "/api/v1/detect", "单图球员检测（ONNX INT8）"],
           ["POST", "/api/v1/detect/batch", "批量检测（≤20 张，异步）"],
           ["POST", "/api/v1/text/classify", "解说文本动作分类"],
           ["POST", "/api/v1/match", "图文相关性检查"],
           ["POST", "/api/v1/tasks", "上传视频，创建分析任务"],
           ["GET", "/api/v1/tasks/{id}", "任务状态与进度"],
           ["GET", "/api/v1/tasks/{id}/events", "事件与解说列表"],
           ["POST", "/api/v1/agent/chat", "实验 5：AI 解说对话"],
           ["WS", "/ws/task/{id}", "任务进度推送"]],
          "表 6-1　主要接口（节选）")

    h2(doc, "6.4　前后端联调与测试")
    para(doc, "联调遵循“契约先行”：接口字段、错误码、坐标约定先写进文档，前后端各自按契约实现，"
              "用 Postman 集合与 pytest 双向验证。后端 pytest 覆盖坐标往返、契约字段、异常路径与任务状态机；"
              "前端 vitest 覆盖坐标换算，Playwright 覆盖响应式布局与上传交互（Chromium 通过本机 Edge 运行）。")
    para(doc, "性能上，图像检测端到端均值 132.8 ms（P95 137.1 ms），文本分类 7.9 ms，图文匹配 139.0 ms，"
              "均远低于任务书 2 秒的合格线。跨域只放行 5173，前后端通过 Vite 代理对接，避免把 CORS 开成通配。")
    table(doc,
          ["项", "方法", "结果"],
          [["图像检测端到端", "10 次均值/P95", "132.8 ms / 137.1 ms"],
           ["文本分类", "同上", "7.9 ms"],
           ["图文匹配", "同上", "139.0 ms"],
           ["后端测试", "pytest", "14 项全绿"],
           ["前端单测", "vitest", "坐标契约 2 项"],
           ["浏览器 e2e", "Playwright", "24 项通过"]],
          "表 6-2　实验 4 性能与测试记录", spacer=False)


def chapter7(doc: Document) -> None:
    h1(doc, "第七章　大模型 Agent 部署")

    h2(doc, "7.1　模型部署方案")
    para(doc, "Agent 服务没有另起一个 8001 端口，而是直接挂进实验 4 的后端（8000），路径为 /api/v1/agent/chat。"
              "这样做的理由有三条：与前端的 Vite 代理、CORS 白名单、统一信封、错误码全部复用；"
              "工具可以直接调用同进程的 services 层（避免 async 路由内同步 httpx 自调用 8000 导致死锁）；"
              "会话表与任务表同库（SQLite），便于“断点续聊”和运维。")
    para(doc, "Agent 采用懒加载：首次请求时才构建 LangChain 图，配置缺失不影响系统其他功能启动。"
              "工具层遵循一条纪律——失败不抛异常，返回“工具调用失败：…”字符串，让 Agent 带着错误信息继续组织回复；"
              "LLM 调用失败重试 3 次（退避 1/2/4 s），仍失败则按契约映射为 500/504/429。"
              "每轮对话写一行 logs/agent.jsonl（session_id、user、tool_calls、耗时、provider），既是排障依据也是性能数据来源。")

    h2(doc, "7.2　模型选择与微调")
    para(doc, "基座选 Qwen3-1.7B：8 GB 显存可 4-bit 加载，中文与指令跟随能力满足短文本分类；"
              "微调目标是“教格式”——让模型只输出 10 个类别名之一，而不是长篇解释。"
              "训练数据 100 条（60 条分类 + 40 条生成），来自实验 1 的解说语料，按类别分层抽样；"
              "10 道考题从 test 卷人工挑定，与练习题零重叠。")
    para(doc, "训练配置为 4-bit nf4 + LoRA（r=16、α=32、dropout=0.05、target=q/k/v/o）+ 梯度累积 8 步 + lr 2e-4 + "
              "cosine + max_len 512，损失只算在 assistant 回答上（prompt 部分 label=−100）。"
              "在 RTX 5060 上 3 epoch 训练 116 s、8 epoch 320 s，最终 loss 从 7.2 收敛到 0.77。")
    table(doc,
          ["考生", "10 道考题", "86 条 held-out"],
          [["实验 4 joblib 分类器", "100%", "100%（标签同源，存在循环偏置）"],
           ["DeepSeek 零样本", "90%", "86.0%"],
           ["本地基座 Qwen3-1.7B", "80%", "79.1%"],
           ["+ LoRA（3 epoch）", "80%", "83.7%"],
           ["+ LoRA（8 epoch）", "100%", "94.2%"]],
          "表 7-1　四方对比（同一批题、同一 prompt、同一解码参数；LoRA 含 3/8 epoch 两档）")
    para(doc, "两个结论值得一提。其一，微调把本地小模型从 79.1% 提到 94.2%（+15.1pp），并反超 DeepSeek 零样本的 86%——"
              "在“只输出 10 类之一”这种强格式约束下，领域小模型经过少量样本对齐后可以打过通用大模型。"
              "其二，收益集中在“类间区分”：基座把“阵容战术”全部答成“暂停换人”（0/10），微调后 9/10；"
              "基座还会输出“走步”“突破”这种体系外词，微调后 10 类输出稳定。")
    para(doc, "微调成果最终接进了 Agent：给 commentary_classify 加后端开关（EXP5_TEXT_BACKEND=joblib|lora），"
              "工具名、入参、返回结构全部不变，前端与契约零改动。切到 lora 时懒加载 4-bit 模型与适配器，"
              "单次分类 0.22–0.24 s，端到端仍稳定在 2.2 s。")
    figure(doc, "exp5_loss_curve.png", "图 7-1　QLoRA 训练损失曲线（8 epoch）", 13.5)

    h2(doc, "7.3　Agent 框架集成")
    para(doc, "Agent 用 LangChain 1.x 的 create_agent 构建，系统提示词本身就是“工具路由规则”：给图像路径问人数→player_detect；"
              "给一句解说问类别→commentary_classify；问“真人会怎么说”→retrieve_commentary；图+文问一致性→image_text_match；"
              "给任务编号问事件→query_video_events。工具描述里写清输入类型，是准确率的主要来源。")
    table(doc,
          ["工具", "入参", "返回", "对应实验"],
          [["player_detect", "图像路径（支持 f000005 简写）", "人数、平均置信度、耗时", "实验 4 /detect"],
           ["commentary_classify", "解说文本", "类别、置信度（可切 joblib/LoRA）", "实验 4 /text/classify"],
           ["retrieve_commentary", "局面关键词", "3 条真人原句 + 相似度", "实验 1 语料（BM25/TF-IDF）"],
           ["image_text_match", "图像路径 + 文本", "是否同属篮球内容 + 两侧证据", "实验 4 /match"],
           ["query_video_events", "任务编号", "事件列表（时间、类型）", "实验 4 /tasks/{id}/events"]],
          "表 7-2　五个 Agent 工具")
    para(doc, "工具选择准确率用 10 轮任务书式问句测试，结果为 10/10 = 100%（目标 ≥90%），其中 2 轮是“应当不调工具”的闲聊，"
              "Agent 正确地直接回答。多轮能力靠 session_id + SQLite 历史实现，先问“怎么判断图里有没有球员”，"
              "再追问“那 f000025 呢”，第二轮能正确继承上下文并调用检测工具。")
    para(doc, "RAG 工具用字符级 TF-IDF 检索 32,377 条解说语料，零额外依赖。实测检索质量一般："
              "问“突破上篮得分怎么说”，召回的是“上篮不中/被犯规”，相似度仅 0.45–0.53——"
              "字符切分对“得分/不中”区分不足。Agent 对此的处理是诚实的：它会说“检索到的句子相似度不高”，"
              "再按风格另写一句，而不是硬编。这条限制写进了第八章的改进项。")

    h2(doc, "7.4　部署与测试")
    para(doc, "前端新增 /agent 页（AgentChatView.vue），导航在 SPA 侧栏与视频页独立侧栏两处都补齐——"
              "此前首页默认进视频页，从首页根本看不到 AI 解说入口，这是本轮修掉的一个真实体验缺陷。"
              "页面包含气泡区、可展开的工具过程条、快捷提问、会话信息与“开始新会话”，"
              "错误按契约区分并给出重试按钮，移动端 390×844 下气泡不溢出。")
    figure(doc, "agent_01_image.png", "图 7-2　/agent 场景一：图像路径 → 检测工具", 13.0)
    para(doc, "端到端测试覆盖任务书三场景：图像（f000005→10 名球员）、文本（抢断句→抢断）、多轮（概念问答→追问）。"
              "延迟方面，同一批 10 条问句：ChatAnywhere 中转均值 49.96 s、P95 186 s（10 轮里 7 轮超 5 秒）；"
              "DeepSeek 官方直连均值 1.77 s、P95 2.20 s、0 轮超 5 秒。这组对照说明——"
              "**瓶颈在链路而不在模型**，换一条直连通道就把“不达标”变成了“大幅达标”。")
    table(doc,
          ["口径", "模型", "均值", "P95", "超 5 秒轮数"],
          [["ChatAnywhere 中转", "deepseek-v4.1-flash-1017", "49.96 s", "186.0 s", "7/10"],
           ["DeepSeek 官方直连", "deepseek-chat", "1.77 s", "2.20 s", "0/10"]],
          "表 7-3　两口径端到端延迟")

    h3(doc, "与实验 2 小模型微调的对比")
    para(doc, "实验 2 是“小模型全参微调”，实验 5 是“大模型参数高效微调”，两者在同一台 8 GB 显存的机器上完成，"
              "对比下来差别不在“谁更强”，而在“什么在决定效果”。实验 2 的 YOLOv8n 只有 3.2 M 参数，4,316 帧数据"
              "把全部权重都推了一遍，瓶颈是数据质量——增强缺陷直接让 mAP 掉了 4 个百分点，修数据比调参有效。"
              "实验 5 的 Qwen3-1.7B 有 20 亿参数，只训练 0.42% 的 LoRA 增量，100 条指令就够，因为模型原本就会说话，"
              "缺的只是“只输出 10 个类别名之一”这个格式约束；一旦格式对齐，准确率从 79.1% 跳到 94.2%。"
              "换句话说：全参微调在教模型“认识世界”，PEFT 在教模型“按规矩说话”。")
    table(doc,
          ["维度", "实验 2（YOLOv8n，全参）", "实验 5（Qwen3-1.7B，QLoRA）"],
          [["任务", "单类球员检测", "10 类解说文本分类"],
           ["参数量", "3.2 M", "2.0 B（约 1,988 M）"],
           ["可训练参数", "100%（3.2 M）", "0.42%（8.4 M）"],
           ["显存占用", "8 GB 内（batch 16）", "4-bit 权重约 1.1 GB，峰值约 3 GB"],
           ["训练数据", "4,316 帧（+2,521 原始）", "100 条指令（60 分类 + 40 生成）"],
           ["训练时长", "50 轮，T4 约 40 min", "8 epoch，320 s（RTX 5060）"],
           ["关键超参", "SGD lr 0.01，余弦调度", "AdamW lr 2e-4，r=16／α=32"],
           ["决定效果的因素", "数据质量（增强缺陷即掉点）", "任务格式与指令质量"],
           ["部署形态", "ONNX INT8，3.5 MB", "4-bit + LoRA 适配器，约 1.1 GB"]],
          "表 7-4　小模型全参微调与大模型 PEFT 的对比",
          widths=[3.0, 5.6, 6.8])

    h2(doc, "7.5　视频解说生成（产品主线收官）")
    para(doc, "此前视频页的解说由模板句生成——“画面中检测到约 9 名球员”这类句子信息准确，但读起来不像解说。"
              "本轮把事件表交给大模型，按解说员口吻写成一句直播解说，补上了“上传视频 → 画框 → AI 解说”的最后一环。")
    para(doc, "做法是“结构化事实 + 语言生成”分离：事件表只提供人数、聚集、方向反转这几类事实，"
              "提示词明确要求只使用这些事实，禁止编造比分、投篮、球员姓名、终场等情节，并要求句式有变化、每条不超过 30 字。"
              "模型客户端在 Worker 进程内复用，每任务只初始化一次。")
    para(doc, "工程上有三条护栏。其一是 10 秒硬超时：调用放在线程池里取结果，客户端自身的超时不可靠，必须兜底。"
              "其二是同键去重：同类型同人数的事件 5 秒内只调一次，复用上一条文案，避免密集事件把接口打满。"
              "其三是单任务调用上限（默认 12 次，演示环境放到 24 次），超出部分直接走模板句。"
              "任何异常、超时、401 都回退模板句并记 WARN 日志，Worker 不崩、任务照常完成。")
    para(doc, "关于“解说词从哪来”的说明：事实来自视觉事件表，风格来自真人解说语料与大模型的语言能力，"
              "两者并非同一场比赛，因此不做逐句对齐评估，只考核两点——事实是否只用了事件里给出的信息、口吻是否像直播解说。"
              "这种非配对的生成方式与第 3 章的“按场次划分防泄漏”是同一条底线在不同环节的体现。")
    para(doc, "实测（36 秒 demo 视频，451 帧、20 个事件）：模板句版本整任务 8.4 秒；切到大模型后三次运行分别为"
              "24.1、26.7、29.5 秒，即 24~30 秒、20 次调用平均 0.8~1.0 秒，多出的 16~22 秒全部是接口耗时。注入错误 key 后接口返回 401，"
              "两次事件均自动回退模板句（stats: fallbacks=2），任务仍然 ready。")
    figure(doc, "exp5_video_commentary.png", "图 7-3　视频工作台：事件面板中的解说由大模型生成", 15.0)
    table(doc,
          ["配置", "解说来源", "demo 任务耗时", "异常时", "适用场景"],
          [["stub（默认）", "模板句", "8.4 s", "—", "无 key 的机器、离线演示"],
           ["llm（正常）", "大模型一句话", "24~30 s", "内部回退", "演示与答辩主用"],
           ["llm（key 错误）", "模板句（自动回退）", "未单独计时（同 stub）", "WARN 日志 + 任务完成", "容错验证"]],
          "表 7-5　三种解说配置对比（36 秒 demo，20 个事件）",
          widths=[3.2, 3.6, 2.8, 4.0, 4.4])
    para(doc, "注：错 key 一档只验证“任务仍能完成并回退”，未单独计时；调用上限默认 12 次，演示环境配置为 24 次。", indent=False)
    para(doc, "聊天页也做了联动：把 SYSTEM_PROMPT 第 5 条从“调用 query_video_events”扩成“拿到事件后以解说员口吻逐事件播报”，"
              "于是用户只要给一个任务编号加一句“给这个视频配解说”，Agent 就会按时间顺序把事件讲一遍（图 7-4，20 条事件、3.5 秒、1 次工具调用）。"
              "工具的事件返回条数也从写死的 8 条改成了显式参数（默认 20、上限 50），超出时返回值会注明“还有 N 个未展示”，"
              "模型据此如实说明覆盖范围，不会假装看全。这次提示词改动没有影响工具路由——10 轮工具选择测试仍是 10/10。")
    figure(doc, "exp5_agent_video_narration.png", "图 7-4　/agent：输入任务编号后逐事件播报", 15.0)



def chapter8(doc: Document) -> None:
    h1(doc, "第八章　系统测试与评估")

    h2(doc, "8.1　功能测试")
    para(doc, "功能测试分三层：接口层用 pytest 与契约测试脚本，界面层用 Playwright 驱动真实浏览器，"
              "业务层按任务书三场景逐条走通并截图存档。")
    table(doc,
          ["测试项", "方法", "结果"],
          [["Agent 接口 5 用例", "exp5/test_agent_api.py", "5/5 通过"],
           ["错误码映射", "exp5/eval/error_injection.py（故障注入）", "6/6 通过"],
           ["三场景端到端", "Playwright + Edge", "全部通过（3 张截图）"],
           ["工具选择准确率", "10 轮问句", "10/10 = 100%"],
           ["RAG 冒烟", "2 条检索/生成问句", "2/2 通过（检索质量见 7.3）"]],
          "表 8-1　功能测试结果")
    para(doc, "异常处理单独做了真实故障验证：把 EXP5_LLM_TIMEOUT 设为 0.3 s 打真实接口，3 次请求全部返回 504 与"
              "“AI 响应超时，请重试”；把 key 换成无效值重启后端，前端显示“AI 服务暂时不可用，点下面「重试」再来一次”，"
              "并出现“重试上一句”按钮。")
    figure(doc, "agent_05_error_retry.png", "图 8-1　错误态：失败提示与重试按钮", 11.0)

    h2(doc, "8.2　性能测试")
    para(doc, "性能分三个层次记录，避免把“模型耗时”当成“Agent 响应时间”：")
    table(doc,
          ["层次", "指标", "4-bit", "fp16"],
          [["模型单条推理（10 句 × 3 轮）", "均值 ± 标准差", "293.8 ± 38.5 ms", "241.8 ± 30.6 ms"],
           ["模型单条推理", "P95", "418.8 ms", "294.6 ms"],
           ["模型单条推理", "显存峰值", "1.30 GB", "3.25 GB"],
           ["Agent 工具耗时（10 次）", "均值 ± 标准差", "240.1 ± 52.0 ms", "224.9 ± 38.1 ms"],
           ["Agent 端到端（10 次）", "均值", "2198.9 ms", "2179.2 ms"]],
          "表 8-2　量化前后对比（模型层与 Agent 层）")
    para(doc, "这张表最值得说的是“分层”：量化让模型单条推理差 18%，但 Agent 端到端只差 0.9%——"
              "因为 2.2 秒里有 2.0 秒是 API 往返。所以任务书“用 4-bit 降低 Agent 响应时间”在本项目中不成立，"
              "4-bit 的真实收益是显存（省 60%），不是延迟。报告按此如实表述。")
    para(doc, "并发方面测了 15/30/60 三档：15 并发时 15/15 成功但 3 个请求被拉长到 30 s；30 与 60 并发反而在 10 s 内完成。"
              "据此判断长尾更可能来自上游偶发抖动 + SDK 退避重试，而非“并发越高越慢”。"
              "60 并发仍未触发 429，说明当前配额足够，429 分支只能通过注入验证。")
    table(doc,
          ["并发", "成功/总数", "总耗时", "最长单请求"],
          [["15", "15/15", "30.4 s", "30.4 s"],
           ["30", "30/30", "10.0 s", "10.0 s"],
           ["60", "60/60", "6.5 s", "6.5 s"]],
          "表 8-3　并发压测")

    h2(doc, "8.3　用户测试")
    para(doc, "本项目未做正式的用户可用性测试（无外部用户、无问卷），仅有组内走查：按任务书三场景由组员独立操作一遍，"
              "记录到两个问题——其一，首页默认进入视频页导致找不到 AI 解说入口（已修，见 7.4）；"
              "其二，首次进入 /agent 时没有引导，用户不知道该输入什么（已通过“快捷提问”与空态提示缓解）。"
              "这两条属于“能自己发现”的问题，但严格的可用性结论仍需真实用户样本，这里如实标注为局限。")

    h2(doc, "8.4　与预期目标对比分析")
    table(doc,
          ["任务书指标", "目标", "实测", "判定"],
          [["工具调用准确率", "≥90%（10 轮）", "10/10 = 100%", "达标"],
           ["Agent 响应时间（直连）", "≤5 s", "均值 1.77 s / P95 2.20 s", "达标"],
           ["Agent 响应时间（中转）", "≤5 s", "均值 49.96 s", "不达标（链路问题）"],
           ["微调前后对比", "有数据", "80% → 100%（10 题）；79.1% → 94.2%（86 条）", "达标"],
           ["跨平台", "Chrome/Firefox/移动端", "Edge 全流程、Firefox 渲染+交互、移动端视口", "基本达标（缺 WebKit）"],
           ["错误处理", "超时/失败有提示", "504/500 真实触发，前端重试按钮", "达标"],
           ["并发协调", "Redis+Celery 队列", "未接入（工具为同步轻调用）", "未做，报告中说明理由"]],
          "表 8-4　任务书指标对照")
    para(doc, "总体判断：功能类指标全部达标，性能类指标在“直连”口径下大幅达标、在“中转”口径下不达标，"
              "这一差异本身是项目最有价值的发现之一——它说明部署链路的选型比模型选型更能决定用户体感。")
    figure(doc, "firefox_agent_chat.png", "图 8-2　Firefox 下的 /agent 交互（10 名球员 / 81ms / 4.4s）", 13.0)


def chapter9(doc: Document) -> None:
    h1(doc, "第九章　项目总结与展望")

    h2(doc, "9.1　项目成果总结")
    para(doc, "五个实验串成一条完整链路：实验 1 产出三类数据资产（视频 526 段、检测集 5,042 帧、解说 40,376 条）；"
              "实验 2 完成 YOLOv8 三组对比并选定 A2 档；实验 3 把模型压到 3.5 MB 且判定精度无损；"
              "实验 4 交付四页前端 + 12 个接口的可运行系统；实验 5 接入 5 工具的 Agent、完成一次真实 QLoRA 微调，"
              "并把微调模型接回线上工具。系统在普通笔记本上可一键起服务、可完整演示。")

    h2(doc, "9.2　技术创新点")
    bullet(doc, "**两口径延迟对照**：同一脚本、同一批问句，中转 49.96 s vs 直连 1.77 s，把“慢”从模型问题定位成链路问题。")
    bullet(doc, "**区分层次的量化结论**：模型单条差 18%、Agent 端到端只差 0.9%，避免了“4-bit 能降 Agent 延迟”的误判。")
    bullet(doc, "**契约不动的 LoRA 接入**：只加后端开关，工具名/入参/返回不变，前端与已有测试零改动。")
    bullet(doc, "**数据审计机制化**：从“抽 100 条”升级为“规则复算 + 模型交叉 + 人工判读 + 断言”，并产出可追溯的 audit.md。")

    h2(doc, "9.3　遇到的挑战与解决方案")
    para(doc, "（1）**数据增强缺陷**：torchvision v2 以 numpy 输入时图像不变、标注却变，导致增强集实为“原图 + 错框”。"
              "通过可视化抽查发现，随后三层校验重建并重训全部模型。")
    para(doc, "（2）**中转链路长尾**：10 轮里 4 轮 60–186 s。定位为代理劫持 httpx 与中转排队，改为直连 + trust_env=False，"
              "并把这一条写进项目坑清单。")
    para(doc, "（3）**评测脚本会骗人**：`PeftModel.from_pretrained` 就地改写基座，导致“基座”一列实际跑的是微调模型，"
              "两组预测 86/86 完全相同。改为先跑基座再 wrap，数字才回到 79.1% vs 94.2%。")
    para(doc, "（4）**Qwen3 的思考块**：默认先输出 `<think>`，48 token 截断后解析抓到的是提示词里复述的类别名。"
              "评测时预填空思考块，让模型直接出答案。")
    para(doc, "（5）**8 GB 显存的取舍**：全参数微调不可行，选 4-bit QLoRA；推理时 4-bit 与 fp16 都能跑，按显存与速度取舍。")
    para(doc, "（6）**浏览器自动化受限**：Playwright 的 Firefox 构建与 geckodriver 在本机均无法启动 Firefox，"
              "改用 `firefox --headless --screenshot` 完成渲染验证 + 人工完成交互验证，并在报告中标注限制。")

    h2(doc, "9.4　项目局限性分析")
    para(doc, "其一，微调数据只有 100 条、标签来自弱监督规则，94.2% 说明的是“格式与类间区分”，不能宣称“模型理解了篮球”。"
              "其二，10 道考题的统计效力有限（±1 题 = 10pp），86 条 held-out 也只是补充口径。"
              "其三，跨浏览器缺 WebKit/Safari，移动端是视口模拟不是真机。"
              "其四，并发协调未接 Redis+Celery，429 分支只能注入验证。"
              "其五，视频事件仍是启发式规则（人数变化、聚集、方向突变），不解说具体战术。")

    h2(doc, "9.5　未来展望与改进方向")
    para(doc, "短期可做三件事：把 RAG 的字级 TF-IDF 换成 jieba 分词或字二元组，解决“得分/不中”召回混淆；"
              "用 500–1,000 条数据做数据量消融，看 94.2% 还能不能往上走；把工具调用接入 Celery 队列，"
              "在高并发下做请求排队与优先级。")
    para(doc, "中期可以把视频事件从启发式升级为动作识别模型（实验 1 的 6,247 行事件表已经具备监督信号），"
              "让“AI 解说员”从“看人数”走到“看动作”。长期则可考虑多模态大模型直接吃视频帧，"
              "把检测、动作、解说合成一个端到端模型——那时本项目的价值就变成了“高质量数据与评测口径”的沉淀。")


def references(doc: Document) -> None:
    h1(doc, "参考文献", page_break=True)
    refs = [
        "Jocher G, Chaurasia A, Qiu J. Ultralytics YOLOv8[CP/OL]. https://github.com/ultralytics/ultralytics, 2023.",
        "Cui Y, Song T, Wang K, et al. SportsMOT: A Large Multi-Object Tracking Dataset in Multiple Sports Scenes[C]//ICCV. 2023.",
        "Li Y, Chen L, He R, et al. MultiSports: A Multi-Person Video Dataset of Spatio-Temporally Localized Sports Actions[C]//ICCV. 2021.",
        "Dettmers T, Pagnoni A, Holtzman A, et al. QLoRA: Efficient Finetuning of Quantized LLMs[C]//NeurIPS. 2023.",
        "Hu E J, Shen Y, Wallis P, et al. LoRA: Low-Rank Adaptation of Large Language Models[C]//ICLR. 2022.",
        "Qwen Team. Qwen3 Technical Report[J]. arXiv preprint, 2025.",
        "Chase H. LangChain: Building applications with LLMs through composability[CP/OL]. https://github.com/langchain-ai/langchain.",
        "Ramírez S. FastAPI: Modern, fast web framework for building APIs with Python[CP/OL]. https://fastapi.tiangolo.com.",
        "Jacob B, Kligys S, Chen B, et al. Quantization and Training of Neural Networks for Efficient Integer-Arithmetic-Only Inference[C]//CVPR. 2018.",
        "Alibaba. Data-Juicer: A One-Stop Data Processing System for Large Language Models[CP/OL]. https://github.com/modelscope/data-juicer.",
    ]
    for i, r in enumerate(refs, 1):
        p = doc.add_paragraph()
        pf = p.paragraph_format
        pf.left_indent = Pt(24)
        pf.first_line_indent = Pt(-24)      # 悬挂缩进：序号顶格，续行对齐
        pf.line_spacing_rule = WD_LINE_SPACING.SINGLE
        pf.space_after = Pt(4)
        run = p.add_run(f"[{i}] {r}")
        _set_run_font(run, 10.5)


def appendix(doc: Document) -> None:
    h1(doc, "附　录", page_break=True)

    h2(doc, "附录 A　代码结构说明")
    table(doc,
          ["目录", "内容"],
          [["scripts/01_acquire … 06_report", "数据获取、清洗、增强、标准化、评估、报告脚本"],
           ["src/basketball_dataset.py", "PyTorch Dataset 封装"],
           ["exp4/complete_web_system/backend/app", "FastAPI 应用（api/core/services/db/agent/ws）"],
           ["exp4/complete_web_system/backend/worker", "视频处理 Worker 与事件服务"],
           ["exp4/complete_web_system/frontend/src", "Vue 3 前端（views/api/stores）"],
           ["exp5/data", "微调数据集、考题、构建脚本与审计记录"],
           ["exp5/eval", "基线、微调评测、量化、异常注入、并发脚本与结果"],
           ["exp5/train_lora.py", "QLoRA 训练脚本"],
           ["report/", "报告生成脚本、图表与各实验报告"]],
          "表 A-1　代码结构")

    h2(doc, "附录 B　数据集详细统计")
    table(doc,
          ["数据", "数量", "划分"],
          [["检测图像（增强后）", "5,042 帧", "train 4,316 / val 346 / test 380"],
           ["检测图像（原始）", "2,521 帧", "按序列 24/3/3"],
           ["动作事件", "6,247 行", "18 类动作"],
           ["解说语料", "40,376 条", "33/4/4 场"],
           ["微调数据", "100 条", "60 分类 + 40 生成"],
           ["考题", "10 条", "test 卷，10 类各 1"]],
          "表 B-1　数据集统计")

    h2(doc, "附录 C　模型参数配置表")
    table(doc,
          ["项", "配置"],
          [["检测模型", "YOLOv8n，imgsz 640，单类 player"],
           ["训练", "epochs 50，patience 15，batch 16，cos_lr，AMP，seed 42"],
           ["量化", "INT8 静态量化（QDQ），Conv/Gemm/MatMul，检测头保持 FP32"],
           ["微调基座", "Qwen3-1.7B，4-bit nf4"],
           ["LoRA", "r=16，alpha=32，dropout=0.05，q/k/v/o"],
           ["微调训练", "grad_accum 8，lr 2e-4，cosine，max_len 512，3/8 epoch"],
           ["推理", "贪心解码，max_new_tokens 8，预填空 think 块"]],
          "表 C-1　模型与训练配置")

    h2(doc, "附录 D　系统部署文档")
    para(doc, "（1）后端：进入 backend 目录，创建 Python 3.11/3.12 虚拟环境并安装 requirements-dev.txt；"
              "复制 exp5/.env.example 为 backend/.env 并填入大模型 key；"
              "执行 uvicorn app.main:app --host 127.0.0.1 --port 8000。")
    para(doc, "（2）前端：进入 frontend 目录，pnpm install 后 pnpm dev --host 127.0.0.1 --port 5173。")
    para(doc, "（3）Worker（视频分析需要）：另开终端执行 python -m worker.main；不跑视频功能可跳过。")
    para(doc, "（4）验证：访问 /api/v1/health 应返回 detector_loaded 与 text_clf_loaded 为 true；"
              "浏览器打开 5173 可见四个页面与 AI 解说。")
    para(doc, "（5）模型文件：weights/best.pt、weights/a2v2_int8_val173.onnx、app/ml/text_action_clf.joblib 需就位；"
              "LoRA 适配器放 exp5/adapters/qwen3-1.7b-lora，并在 .env 设置 EXP5_TEXT_BACKEND=lora 时才会加载。")

    h2(doc, "附录 E　用户使用手册")
    para(doc, "视频分析：进入“视频分析工作台”，选择 MP4、可填名称，点“上传并分析”，等待进度完成后查看检测框、"
              "关键事件与人数曲线；点事件可定位到对应时间。")
    para(doc, "球员检测：进入“球员图像检测”，拖入 PNG/JPG，点“开始检测”，查看人数、框、置信度与耗时。")
    para(doc, "解说分类：进入“解说文本分类”，输入 1–2000 字解说，提交后查看类别、是否篮球文本、置信度与 Top3。")
    para(doc, "图文匹配：同时上传图片与文本，查看两侧判断与汇总结论（注意：只判断是否同属篮球内容，不判断动作一致性）。")
    para(doc, "AI 解说：进入“AI 解说”，可直接给图像路径（如 f000005）、贴一句解说、或让它“来一句解说”；"
              "工具调用会以过程条展示，点开可看入参/结果；出错时可点“重试上一句”。")


def build() -> Path:
    doc = setup_document()
    add_page_number_footer(doc)
    toc(doc)
    abstract(doc)
    chapter1(doc)
    chapter2(doc)
    chapter3(doc)
    chapter4(doc)
    chapter5(doc)
    chapter6(doc)
    chapter7(doc)
    chapter8(doc)
    chapter9(doc)
    references(doc)
    appendix(doc)
    doc.save(str(OUT))
    return OUT


if __name__ == "__main__":
    path = build()
    print(f"生成：{path}（{path.stat().st_size/1024:.0f} KB，{dt.datetime.now():%H:%M:%S}）")
