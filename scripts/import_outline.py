#!/usr/bin/env python3
"""把 学习/01-计划/大纲/*.md 的考点表转成 config/subjects/*.json。

用法：
    python scripts/import_outline.py --src /path/to/01-计划/大纲

作者维护大纲时只改 markdown，重新跑这个脚本即可。仓库里提交的是生成后的 JSON，
所以别人 clone 下来不需要有源 markdown 也能跑。
"""
from __future__ import annotations

import argparse
import json
import re
from pathlib import Path

SUBJECTS = {
    "01-计算机基础与程序设计.md": {
        "id": "computer", "name": "计算机基础与程序设计", "short": "计算机",
        "exam": {"score": 200, "minutes": 150},
    },
    "02-高等数学.md": {
        "id": "math", "name": "高等数学", "short": "高数",
        "exam": {"score": 100, "minutes": 120},
    },
    "03-英语.md": {
        "id": "english", "name": "英语", "short": "英语",
        "exam": {"score": 100, "minutes": 120},
    },
    "04-政治理论.md": {
        "id": "politics", "name": "政治理论", "short": "政治",
        "exam": {"score": 100, "minutes": 120},
    },
}

PREFIX_SECTION = {
    "C": "C 语言",
    "D": "数据结构",
}

HEADING_RE = re.compile(r"^#{2,3}\s+(.+?)\s*$")
ROW_RE = re.compile(r"^\|\s*([A-Z])-(\d+)\s*\|(.*)\|\s*$")


def clean_heading(text: str) -> str:
    text = re.sub(r"（[^）]*）", "", text).strip()
    text = re.sub(r"^\d+[、.．]\s*", "", text)
    text = re.sub(r"^第\s*\d+\s*章\s*", "", text)
    text = re.sub(r"\s*[—–-]\s*.*$", "", text).strip()
    return text.strip()


def parse(path: Path, meta: dict) -> dict:
    rows: list[dict] = []
    section = ""
    for line in path.read_text(encoding="utf-8").splitlines():
        m = HEADING_RE.match(line)
        if m:
            section = clean_heading(m.group(1))
            continue
        m = ROW_RE.match(line)
        if not m:
            continue
        prefix, num, rest = m.group(1), m.group(2), m.group(3)
        cells = [c.strip() for c in rest.split("|")]
        code = f"{prefix}-{num}"
        if prefix in PREFIX_SECTION:
            if len(cells) < 6:
                continue
            title, kaogang, req, freq, hours, stage = cells[:6]
            row = {
                "code": code, "title": title, "section": PREFIX_SECTION[prefix],
                "requirement": req or None, "frequency": freq or None,
                "hours": to_int(hours), "stage": stage or None,
                "assessment": None, "kaogang": kaogang or None,
            }
        elif prefix in {"M", "E"} and len(cells) >= 5:
            title, req, freq, hours, stage = cells[:5]
            row = {
                "code": code, "title": title, "section": section,
                "requirement": req or None, "frequency": freq or None,
                "hours": to_int(hours), "stage": stage or None,
                "assessment": None, "kaogang": None,
            }
        elif prefix in {"M", "E"} and len(cells) == 4:
            title, hours, stage = cells[:3]
            row = {
                "code": code, "title": title, "section": section,
                "requirement": None, "frequency": None,
                "hours": to_int(hours), "stage": stage or None,
                "assessment": None, "kaogang": None,
            }
        elif prefix == "P" and len(cells) >= 5:
            title, assess, freq, hours = cells[:4]
            row = {
                "code": code, "title": title, "section": section,
                "requirement": None, "frequency": freq or None,
                "hours": to_int(hours), "stage": "P3",
                "assessment": assess or None, "kaogang": None,
            }
        elif prefix == "P" and len(cells) == 4:
            title, hours, stage = cells[:3]
            row = {
                "code": code, "title": title, "section": section,
                "requirement": None, "frequency": None,
                "hours": to_int(hours), "stage": stage or "P3",
                "assessment": None, "kaogang": None,
            }
        else:
            continue
        row["kind"] = "training" if re.search(r"专项|训练|套卷|真题", row["title"]) else "point"
        rows.append(row)

    seen = {}
    for row in rows:
        seen.setdefault(row["section"], []).append(row)
    sections = [{"title": k, "nodes": v} for k, v in seen.items() if k]
    return {
        **meta,
        "sections": sections,
        "nodes": rows,
        "total_hours": sum(r["hours"] or 0 for r in rows),
    }


def to_int(value: str) -> int | None:
    m = re.search(r"\d+", value)
    return int(m.group()) if m else None


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--src", required=True, help="大纲 markdown 所在目录")
    ap.add_argument("--out", default="config/subjects", help="输出目录")
    args = ap.parse_args()

    src = Path(args.src)
    out = Path(args.out)
    out.mkdir(parents=True, exist_ok=True)
    for filename, meta in SUBJECTS.items():
        path = src / filename
        if not path.exists():
            print(f"跳过（不存在）：{path}")
            continue
        data = parse(path, meta)
        target = out / f"{meta['id']}.json"
        target.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        print(f"{target}: {len(data['nodes'])} 条，{data['total_hours']} h")


if __name__ == "__main__":
    main()