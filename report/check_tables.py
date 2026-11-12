# -*- coding: utf-8 -*-
"""检查表格是否跨页：用“表题 + 末行整行文字”定位。"""
from __future__ import annotations

import docx
import pymupdf
from docx.table import Table
from docx.text.paragraph import Paragraph

DOCX = r"C:\sofeware\AI Api\dsh workspace\fish\work\basketball-git\report\实验5报告.docx"
PDF = r"C:\sofeware\AI Api\dsh workspace\fish\work\basketball-git\report\实验5报告.pdf"

doc = docx.Document(DOCX)
pdf = pymupdf.open(PDF)
pages = ["".join(p.get_text().split()) for p in pdf]


def row_text(row) -> str:
    return "".join(c.text for c in row.cells)


def find_page(text: str, start: int = 0) -> int | None:
    key = "".join(text.split())
    if len(key) < 6:
        return None
    for i in range(start, len(pages)):
        if key in pages[i]:
            return i + 1
    return None


body = doc.element.body
caption = None
cap_page = None
results = []
for child in body.iterchildren():
    if child.tag.endswith("}p"):
        p = Paragraph(child, doc)
        if p.text.strip().startswith("表 "):
            caption = p.text.strip()
            cap_page = find_page(caption)
    elif child.tag.endswith("}tbl"):
        t = Table(child, doc)
        last = row_text(t.rows[-1])
        last_page = find_page(last, (cap_page or 1) - 1)
        results.append((caption, cap_page, last_page, len(t.rows)))

split = [r for r in results if r[1] and r[2] and r[1] != r[2]]
unknown = [r for r in results if not r[1] or not r[2]]
print(f"带表题的表格 {len(results)} 张")
print("跨页:", split if split else "无")
if unknown:
    print("定位失败:", [(u[0], u[3]) for u in unknown])
