# -*- coding: utf-8 -*-
"""实验1报告 v2 修复：视觉验收问题闭环。

1) 全局行距统一为模板规范“固定值20磅”（视觉验收根因：两套行距并存，
   部分段落约3倍行宽，跨页还出现段内行距跳变）——正文段落全部改为
   EXACT 20pt、段前段后0、关闭文档网格对齐；标题/封面/参考文献/代码块/题注不动。
2) 相邻双空段收敛为单空段（消除成片空白）。
3) 参考文献[1]（Yao H, MultiSports…）首行缩进错位 → 对齐[2]-[5]的悬挂缩进。
"""
import copy

import docx
from docx.enum.text import WD_LINE_SPACING
from docx.oxml import parse_xml
from docx.oxml.ns import qn
from docx.shared import Pt
from docx.text.paragraph import Paragraph

PATH = r"D:/Downloads/AI全栈开发实验1报告_updated.docx"
doc = docx.Document(PATH)

W = "http://schemas.openxmlformats.org/wordprocessingml/2006/main"


def is_code(p: Paragraph) -> bool:
    ppr = p._p.pPr
    return ppr is not None and ppr.find(qn("w:shd")) is not None


def has_drawing(p: Paragraph) -> bool:
    return p._p.find(qn("w:r")) is not None and (
        p._p.iter(qn("w:drawing")) or p._p.iter(qn("w:pict"))
    ) and (list(p._p.iter(qn("w:drawing"))) or list(p._p.iter(qn("w:pict"))))


# 找到正文起点（第一个 Heading 之后才处理）
first_head = next(i for i, p in enumerate(doc.paragraphs)
                  if p.style.name.startswith("Heading"))

normalized = 0
for i, p in enumerate(doc.paragraphs):
    if i <= first_head:            # 封面 + 首个标题前
        continue
    name = p.style.name
    if name.startswith("Heading") or name == "List Paragraph":
        continue
    if is_code(p):                 # 代码块保持单倍行距
        continue
    if has_drawing(p):             # 图片段落只管对齐，不动行距
        continue
    pf = p.paragraph_format
    pf.line_spacing_rule = WD_LINE_SPACING.EXACTLY
    pf.line_spacing = Pt(20)
    pf.space_before = Pt(0)
    pf.space_after = Pt(0)
    ppr = p._p.get_or_add_pPr()
    if ppr.find(qn("w:snapToGrid")) is None:
        ppr.insert(0, parse_xml(f'<w:snapToGrid xmlns:w="{W}" w:val="0"/>'))
    else:
        ppr.find(qn("w:snapToGrid")).set(qn("w:val"), "0")
    normalized += 1

# 相邻双空段 → 只留一个
body = [el for el in doc.element.body.iterchildren() if el.tag == qn("w:p")]
removed = 0
prev_empty = False
for el in body[first_head + 1:]:
    p = Paragraph(el, doc)
    empty = (not p.text.strip()) and (not list(el.iter(qn("w:drawing"))))
    if empty and prev_empty:
        el.getparent().remove(el)
        removed += 1
        continue
    prev_empty = empty

# 参考文献[1] 对齐 [2]-[5]
refs = [p for p in doc.paragraphs if p.style.name == "List Paragraph" and p.text.strip()]
if len(refs) >= 2 and refs[0].text.startswith("Yao"):
    p1, p2 = refs[0]._p, refs[1]._p
    old_ppr = p1.find(qn("w:pPr"))
    if old_ppr is not None:
        p1.remove(old_ppr)
    src_ppr = p2.find(qn("w:pPr"))
    if src_ppr is not None:
        p1.insert(0, copy.deepcopy(src_ppr))
    print("ref[1] pPr 已对齐 ref[2]:", refs[0].text[:40])

doc.save(PATH)
print(f"normalized={normalized} removed_empty={removed}")
