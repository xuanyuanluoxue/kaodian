#!/usr/bin/env python3
"""从完整内容仓库导出一份可随框架分发的起始内容。

公开仓库不包含完整题库：只带每个科目 3 页讲义和对应考点的题目，
保证 clone 后无需额外仓库就能跑通「阅读 → 作答 → 统计」。

用法：

    python scripts/export-starter-content.py \
        --source content --dest starter-content
"""
from __future__ import annotations

import argparse
import json
import re
import shutil
import sys
from pathlib import Path

# 每个科目挑 3 页，覆盖不同章节，且都是 ≤120 行的「一课一概念」。
LESSONS = {
    "computer": ["l01-first-program.md", "l02-variables-and-types.md", "l06-1-for.md"],
    "math": ["m01-1-domain-composite.md", "m01-3-one-sided-limits.md", "m02-1-derivative-definition.md"],
    "english": ["e05-1-present-simple-vs-continuous.md", "e07-1-relative-pronouns.md", "e10-1-subjunctive-if.md"],
    "politics": ["p02-1-mao-live-soul.md", "p03-1-new-democratic-revolution.md", "p07-1-deng-socialism.md"],
}

MEDIA = re.compile(r"/media/([a-z0-9-]+)/([^)\s]+)")
CODES = re.compile(r"^outline_codes:\s*(\[[^\]]*\])", re.M)


def outline_codes(text: str) -> list[str]:
    match = CODES.search(text)
    if not match:
        return []
    try:
        value = json.loads(match.group(1))
    except json.JSONDecodeError:
        return []
    return [str(item) for item in value]


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--source", default="content")
    parser.add_argument("--dest", default="starter-content")
    args = parser.parse_args()

    source = Path(args.source).resolve()
    dest = Path(args.dest).resolve()
    registry = json.loads((source / "registry.json").read_text(encoding="utf-8"))

    if dest.exists():
        shutil.rmtree(dest)
    dest.mkdir(parents=True)

    for name in ("LICENSES.md",):
        if (source / name).is_file():
            shutil.copy2(source / name, dest / name)

    total_lessons = 0
    total_questions = 0
    total_assets = 0
    (dest / "registry.json").write_text(
        json.dumps(registry, ensure_ascii=False, indent=2) + "\n", encoding="utf-8",
    )

    for entry in registry.get("packs", []):
        pack_id = entry["id"]
        src_pack = source / entry["path"]
        dst_pack = dest / entry["path"]
        (dst_pack / "lessons").mkdir(parents=True)
        (dst_pack / "questions").mkdir()
        (dst_pack / "assets").mkdir()

        for name in ("pack.json", "outline.json", "LICENSES.md"):
            if (src_pack / name).is_file():
                shutil.copy2(src_pack / name, dst_pack / name)

        codes: set[str] = set()
        assets: set[str] = set()
        for lesson in LESSONS.get(pack_id, []):
            file = src_pack / "lessons" / lesson
            if not file.is_file():
                print(f"跳过不存在的讲义：{file}", file=sys.stderr)
                continue
            text = file.read_text(encoding="utf-8")
            codes.update(outline_codes(text))
            assets.update(rel for _, rel in MEDIA.findall(text))
            shutil.copy2(file, dst_pack / "lessons" / lesson)
            total_lessons += 1

        for code in sorted(codes):
            file = src_pack / "questions" / f"{code.lower()}.json"
            if not file.is_file():
                print(f"缺少题目文件：{file}", file=sys.stderr)
                continue
            items = json.loads(file.read_text(encoding="utf-8"))
            shutil.copy2(file, dst_pack / "questions" / file.name)
            total_questions += len(items)

        for rel in sorted(assets):
            file = src_pack / "assets" / rel
            if not file.is_file():
                print(f"缺少素材：{file}", file=sys.stderr)
                continue
            shutil.copy2(file, dst_pack / "assets" / rel)
            total_assets += 1

    (dest / "README.md").write_text(
        "# starter-content\n\n"
        "随框架分发的起始内容：每个科目 3 页讲义，以及这些考点的全部练习题。\n"
        "完整题库是独立内容仓库，挂载方式见根目录 `README.md`。\n\n"
        "```bash\n"
        "bin/kaodian content validate\n"
        "bin/kaodian content sync\n"
        "```\n",
        encoding="utf-8",
    )

    print(
        f"导出到 {dest}：{total_lessons} 页讲义 / "
        f"{total_questions} 题 / {total_assets} 个素材"
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
