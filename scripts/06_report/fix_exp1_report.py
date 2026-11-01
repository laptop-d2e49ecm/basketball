# -*- coding: utf-8 -*-
"""修复实验 1 报告的视觉验收问题：
① 删除黄底模板残留"软硬件环境"；② 全部表格加边框；③ 表格行禁止跨页撕裂 +
表头行设置为重复表头；④ 小节标题 keepNext 防止孤立页尾；⑤ 分工表压缩字号行距
使其回到封面一页内。
"""
from docx import Document
from docx.shared import Pt
from docx.oxml import OxmlElement
from docx.oxml.ns import qn

F = r"D:\Downloads\AI全栈开发实验报告模板-2025-黄底红字请删除_filled.docx"
doc = Document(F)

# ① 删除黄底残留
for p in list(doc.paragraphs):
    if p.text.strip() == "软硬件环境":
        p._element.getparent().remove(p._element)
        print("[1] 已删除黄底残留：软硬件环境")

# ② 表格边框 + ③ 行不撕裂 + 表头重复
def fix_table(tbl, header=True):
    tblPr = tbl._tbl.tblPr
    old = tblPr.find(qn("w:tblBorders"))
    if old is not None:
        tblPr.remove(old)
    borders = OxmlElement("w:tblBorders")
    for edge in ("top", "left", "bottom", "right", "insideH", "insideV"):
        el = OxmlElement(f"w:{edge}")
        el.set(qn("w:val"), "single")
        el.set(qn("w:sz"), "4")
        el.set(qn("w:color"), "000000")
        borders.append(el)
    tblPr.append(borders)
    for i, row in enumerate(tbl.rows):
        trPr = row._tr.get_or_add_trPr()
        if trPr.find(qn("w:cantSplit")) is None:
            trPr.append(OxmlElement("w:cantSplit"))
        if header and i == 0 and trPr.find(qn("w:tblHeader")) is None:
            trPr.append(OxmlElement("w:tblHeader"))

for i, tbl in enumerate(doc.tables):
    fix_table(tbl, header=(i > 0))  # 封面分工表无表头重复需求
print(f"[2/3] {len(doc.tables)} 个表格：边框 + 行不撕裂 + 表头重复 已设置")

# ④ 小节标题 keepNext
keys = ("1．需求分析", "2．设计思路", "3．代码实现", "4. 测试优化", "1.1 ", "1.2 ", "1.3 ")
n = 0
for p in doc.paragraphs:
    t = p.text.strip()
    if any(t.startswith(k) for k in keys):
        p.paragraph_format.keep_with_next = True
        n += 1
print(f"[4] {n} 个小节标题设置 keepNext")

# ⑤ 分工表压缩：字号 10pt、行距 16 磅、单元格段距 0
tbl = doc.tables[0]
for row in tbl.rows:
    for cell in row.cells:
        for p in cell.paragraphs:
            p.paragraph_format.line_spacing = Pt(16)
            p.paragraph_format.space_before = Pt(0)
            p.paragraph_format.space_after = Pt(0)
            for r in p.runs:
                r.font.size = Pt(10)
print("[5] 分工表已压缩（10pt / 行距16磅）")

doc.save(F)
print(f"[OK] 修复已保存 -> {F}")
