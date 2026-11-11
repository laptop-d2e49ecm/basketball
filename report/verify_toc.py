# -*- coding: utf-8 -*-
"""核对目录页码：解析 PDF 目录页，逐条比对正文实际所在页。"""
from __future__ import annotations

import re
import sys

import pymupdf

PDF = r"C:\sofeware\AI Api\dsh workspace\fish\work\basketball-git\report\实验5报告.pdf"
TOC_PAGES = (2, 3)  # 1-based，目录所在页


def norm(s: str) -> str:
    return re.sub(r"[\s.·…]+", "", s)


def main() -> int:
    doc = pymupdf.open(PDF)
    entries: list[tuple[str, int]] = []
    for pno in TOC_PAGES:
        text = doc[pno - 1].get_text()
        for line in text.splitlines():
            m = re.match(r"^(.*?)\s*[.…\s]{3,}\s*(\d+)\s*$", line.strip())
            if not m:
                continue
            title, page = m.group(1), int(m.group(2))
            if not title.strip() or title.strip().isdigit():
                continue
            entries.append((title.strip(), page))

    # 正文页文本（跳过目录页）
    body = {}
    for i in range(len(doc)):
        if i + 1 in TOC_PAGES:
            continue
        body[i + 1] = norm(doc[i].get_text())

    bad = 0
    for title, page in entries:
        target = norm(title)
        hit = None
        for pno, txt in body.items():
            if target and target in txt:
                hit = pno
                break
        status = "OK " if hit == page else "BAD"
        if hit != page:
            bad += 1
        print(f"{status} {title[:34]:<36} 目录={page:<4} 实际={hit}")

    print(f"\n共 {len(entries)} 条，异常 {bad} 条")
    return 0 if bad == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
