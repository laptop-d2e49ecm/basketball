# -*- coding: utf-8 -*-
"""给已生成目录的 docx 补 TOC 样式（右对齐制表位 + 点线前导符）。

Word 生成目录后才会出现 "toc 1"/"toc 2" 样式，所以要在首次导出之后运行本脚本，
再导出一次 PDF。用法：python report/fix_toc_style.py
"""
from __future__ import annotations

import sys
from pathlib import Path

import docx
from docx.enum.text import WD_TAB_ALIGNMENT, WD_TAB_LEADER, WD_LINE_SPACING
from docx.oxml.ns import qn
from docx.shared import Cm, Pt

REPO = Path(__file__).resolve().parents[1]
DOCX = REPO / "report" / "实验5报告.docx"


def main() -> int:
    d = docx.Document(str(DOCX))
    names = [s.name for s in d.styles]
    changed = []
    for toc_name, indent in (("toc 1", 0.0), ("toc 2", 0.75)):
        if toc_name not in names:
            continue
        st = d.styles[toc_name]
        st.font.name = "宋体"
        st.font.size = Pt(12)
        st.element.rPr.rFonts.set(qn("w:eastAsia"), "宋体")
        pf = st.paragraph_format
        pf.left_indent = Cm(indent)
        pf.first_line_indent = Cm(0)
        pf.line_spacing_rule = WD_LINE_SPACING.SINGLE
        pf.space_before = Pt(0)
        pf.space_after = Pt(2)
        pf.tab_stops.clear_all()
        pf.tab_stops.add_tab_stop(Cm(15.4), WD_TAB_ALIGNMENT.RIGHT, WD_TAB_LEADER.DOTS)
        changed.append(toc_name)
    d.save(str(DOCX))
    print("TOC 样式已处理：", changed)
    return 0


if __name__ == "__main__":
    sys.exit(main())
