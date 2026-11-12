# -*- coding: utf-8 -*-
"""报告终检：页数、目录、图片、表格、字体、页码、占位符。"""
from __future__ import annotations

import re
import sys

import docx
import pymupdf

DOCX = r"C:\sofeware\AI Api\dsh workspace\fish\work\basketball-git\report\实验5报告.docx"
PDF = r"C:\sofeware\AI Api\dsh workspace\fish\work\basketball-git\report\实验5报告.pdf"

ok = True


def check(cond: bool, msg: str) -> None:
    global ok
    print(("  OK  " if cond else "  !!  ") + msg)
    if not cond:
        ok = False


doc = docx.Document(DOCX)
pdf = pymupdf.open(PDF)

print("== 基本 ==")
check(len(pdf) == 33, f"PDF 页数 = {len(pdf)}（期望 33）")
check(doc.core_properties.title is not None, "docx 可被 python-docx 正常读取")

print("== 图片 ==")
shapes = doc.inline_shapes
check(len(shapes) == 10, f"内联图片数 = {len(shapes)}（期望 10：图 1-1/3-1/3-2/6-1/7-1/7-2/7-3/7-4/8-1/8-2）")
for i, s in enumerate(shapes, 1):
    w_cm = s.width / 360000
    h_cm = s.height / 360000
    check(w_cm >= 10 and h_cm >= 3, f"图 {i}: {w_cm:.1f}×{h_cm:.1f} cm（未被压扁）")

print("== PDF 中图片实际渲染尺寸 ==")
rendered = 0
for pno in range(len(pdf)):
    for info in pdf[pno].get_image_info():
        x0, y0, x1, y1 = info["bbox"]
        w_cm = (x1 - x0) / 72 * 2.54
        h_cm = (y1 - y0) / 72 * 2.54
        rendered += 1
        if not (w_cm > 8 and h_cm > 2.5):
            check(False, f"第 {pno+1} 页图片异常：{w_cm:.1f}×{h_cm:.1f} cm")
check(rendered == 10, f"PDF 中图片实例 = {rendered}（图 7-3/7-4 各一张，其余 8 张，共 10）")

print("== 表格 ==")
check(len(doc.tables) >= 20, f"表格数 = {len(doc.tables)}（含封面组员表）")

print("== 字体与行距 ==")
body = [p for p in doc.paragraphs if p.style.name == "正文CN" and p.text.strip()]
check(len(body) > 100, f"正文段落数 = {len(body)}")
style_size = doc.styles["正文CN"].font.size
check(style_size is not None and abs(style_size.pt - 12) < 0.1, f"正文字号（样式）= {style_size.pt if style_size else None}（期望 12）")
spacing = doc.styles["正文CN"].paragraph_format.line_spacing
check(spacing is not None and abs(spacing.pt - 20) < 0.1, f"正文行距 = {spacing.pt if spacing else None} 磅（期望 20）")

print("== 页码 ==")
def has_footer_number(page) -> bool:
    h = page.rect.height
    for b in page.get_text("blocks"):
        if b[1] > h * 0.92 and re.fullmatch(r"\s*\d+\s*", b[4] or ""):
            return True
    return False

missing = [i + 1 for i in range(1, len(pdf)) if not has_footer_number(pdf[i])]
check(not missing, f"缺页码的页 = {missing}")
cover_text = pdf[0].get_text().strip()
check(not re.search(r"^\s*\d+\s*$", cover_text), "封面无页码")

print("== 目录 ==")
toc_text = pdf[1].get_text() + pdf[2].get_text()
entries = re.findall(r"^(.*?)\s*[.…]{3,}\s*(\d+)\s*$", toc_text, re.M)
check(len(entries) >= 55, f"目录条目数 = {len(entries)}")

print("== 占位符/残留 ==")
full = "\n".join(p.text for p in doc.paragraphs)
for bad in ["缺图", "TODO", "待补", "XXX", "（目录将在 Word 中自动生成）"]:
    check(bad not in full, f"无残留：{bad}")

print("== 图表编号 ==")
caps = [p.text.strip() for p in doc.paragraphs if re.match(r"^(表|图)\s*\d+-\d+", p.text.strip())]
tables = [c for c in caps if c.startswith("表")]
figs = [c for c in caps if c.startswith("图")]
check(len(tables) == 20, f"表标题 = {len(tables)}（表 1-1~8-4 + 附录 A/B/C）")
check(len(figs) == 10, f"图标题 = {len(figs)}")

print("== docx/pdf 一致性 ==")
docx_text = full.replace(" ", "")
pdf_text = "".join(p.get_text() for p in pdf).replace(" ", "")
sample = "视频解说生成（产品主线收官）"
check(sample.replace(" ", "") in docx_text and sample.replace(" ", "") in pdf_text, "7.5 节标题两端一致")

print("\n结论：" + ("全部通过" if ok else "存在异常"))
sys.exit(0 if ok else 1)
