"""独立内容包：读取、校验与同步。

契约见 ``docs/dev/content-packs.md``。这里不引入 PyYAML：Markdown frontmatter
只支持契约里列出的简单字段（标量、内联数组、true/false/null）。
"""

from __future__ import annotations

import json
import os
import re
import sqlite3
import tempfile
from datetime import datetime
from pathlib import Path
from typing import Any

from . import paths
from .blocks import iter_media_urls, validate_blocks, validate_layout, validate_theme
from .grading import fingerprint, validate_media, validate_question

PACK_SCHEMA = 1
KINDS = {"lesson", "outline", "note", "daily"}
STATUSES = {"draft", "published", "archived"}
LESSON_FIELDS = {
    "lesson_key", "title", "summary", "kind", "status", "sort_order", "outline_codes",
    "layout", "theme", "blocks",
}
LESSON_FORMATS = {"markdown", "blocks"}
_MEDIA_RE = re.compile(r"/media/([A-Za-z0-9._-]+)/([^\s)\]\}\"'<>]+)")


class PackError(RuntimeError):
    """内容包结构错误。"""


# ---------------------------------------------------------------- frontmatter

def _scalar(raw: str) -> Any:
    value = raw.strip()
    if not value:
        return ""
    lowered = value.lower()
    if lowered in {"null", "none", "~"}:
        return None
    if lowered in {"true", "false"}:
        return lowered == "true"
    if value[0] == '"':
        try:
            return json.loads(value)
        except json.JSONDecodeError as exc:
            raise PackError(f"frontmatter 字符串格式错误：{value}") from exc
    if value[0] == "'" and value.endswith("'"):
        return value[1:-1].replace("''", "'")
    if value.startswith("[") and value.endswith("]"):
        inner = value[1:-1].strip()
        if not inner:
            return []
        try:
            return json.loads(value)
        except json.JSONDecodeError:
            return [_scalar(part) for part in inner.split(",") if part.strip()]
    try:
        return int(value)
    except ValueError:
        pass
    try:
        return float(value)
    except ValueError:
        pass
    return value


def parse_frontmatter(text: str) -> tuple[dict[str, Any], str]:
    """返回 ``(meta, body)``；没有 frontmatter 时 meta 为空。"""
    text = text.lstrip("\ufeff")
    lines = text.splitlines(keepends=True)
    if not lines or lines[0].strip() != "---":
        return {}, text
    end = None
    for index in range(1, len(lines)):
        if lines[index].strip() == "---":
            end = index
            break
    if end is None:
        raise PackError("frontmatter 没有结束的 --- 行")

    meta: dict[str, Any] = {}
    for line in lines[1:end]:
        if not line.strip():
            continue
        if line[:1].isspace() or line.lstrip().startswith("- "):
            raise PackError("frontmatter 不支持嵌套或块状列表")
        if ":" not in line:
            raise PackError(f"frontmatter 行缺少冒号：{line.strip()}")
        key, raw = line.split(":", 1)
        key = key.strip()
        if not key:
            raise PackError("frontmatter 键不能为空")
        if key in meta:
            raise PackError(f"frontmatter 键重复：{key}")
        meta[key] = _scalar(raw)

    body = "".join(lines[end + 1:])
    return meta, body.lstrip("\r\n")


def _parse_theme(value: Any, label: str) -> dict[str, Any] | None:
    """frontmatter 里 theme 可以是对象，也可以是 JSON 字符串。"""
    if value in (None, ""):
        return None
    if isinstance(value, dict):
        return value
    if isinstance(value, str):
        try:
            parsed = json.loads(value)
        except json.JSONDecodeError as exc:
            raise PackError(f"{label} 的 theme 不是合法 JSON：{exc}") from exc
        if isinstance(parsed, dict):
            return parsed
    raise PackError(f"{label} 的 theme 必须是对象")


def _lesson_from_markdown(file: Path) -> dict[str, Any]:
    meta, body = parse_frontmatter(file.read_text(encoding="utf-8"))
    label = str(file)
    return {
        **meta,
        "body": body,
        "blocks": None,
        "layout": meta.get("layout") or "article",
        "theme": _parse_theme(meta.get("theme"), label),
        "format": "markdown",
        "file": file,
        "source_key": meta.get("lesson_key") or file.stem,
    }


def _lesson_from_json(file: Path) -> dict[str, Any]:
    data = _read_json(file)
    if not isinstance(data, dict):
        raise PackError(f"{file} 必须是 lesson 对象")
    label = str(file)
    return {
        **data,
        "body": data.get("body") or "",
        "blocks": data.get("blocks"),
        "layout": data.get("layout") or "article",
        "theme": _parse_theme(data.get("theme"), label),
        "format": "blocks",
        "file": file,
        "source_key": data.get("lesson_key") or file.stem,
    }


def _load_lessons(root: Path) -> list[dict[str, Any]]:
    lessons_dir = root / "lessons"
    files = sorted(
        (*lessons_dir.glob("*.md"), *lessons_dir.glob("*.json")),
        key=lambda path: (path.stem, path.suffix),
    ) if lessons_dir.is_dir() else []
    lessons: list[dict[str, Any]] = []
    for file in files:
        if file.suffix == ".md":
            lessons.append(_lesson_from_markdown(file))
        else:
            lessons.append(_lesson_from_json(file))
    return lessons


# ---------------------------------------------------------------- load

def _read_json(file: Path) -> Any:
    try:
        return json.loads(file.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise PackError(f"无法读取 {file}：{exc}") from exc


def _question_items(file: Path, data: Any) -> list[dict[str, Any]]:
    if isinstance(data, list):
        return data
    if isinstance(data, dict) and isinstance(data.get("questions"), list):
        if data.get("groups"):
            raise PackError(f"{file} 不支持 groups；内容包只收题目数组")
        return data["questions"]
    raise PackError(f"{file} 必须是题目数组或 {{questions: [...]}} 对象")


def load_pack(entry: dict[str, Any]) -> dict[str, Any]:
    """读取一个 pack 为结构化 dict（不做业务校验）。"""
    root = Path(entry["path"])
    pack_file = root / "pack.json"
    if not pack_file.is_file():
        raise PackError(f"找不到 {pack_file}")
    meta = _read_json(pack_file)
    if not isinstance(meta, dict):
        raise PackError(f"{pack_file} 必须是对象")

    outline_file = root / "outline.json"
    nodes = _read_json(outline_file) if outline_file.is_file() else []
    if not isinstance(nodes, list):
        raise PackError(f"{outline_file} 必须是数组")

    lessons: list[dict[str, Any]] = _load_lessons(root)

    questions: list[dict[str, Any]] = []
    for file in sorted((root / "questions").glob("*.json")):
        for item in _question_items(file, _read_json(file)):
            if not isinstance(item, dict):
                raise PackError(f"{file} 里有非对象题目")
            questions.append({**item, "file": file})

    assets_dir = root / "assets"
    assets = sorted(
        str(path.relative_to(assets_dir)).replace("\\", "/")
        for path in assets_dir.rglob("*")
        if path.is_file()
    ) if assets_dir.is_dir() else []

    return {
        "id": meta.get("id") or entry["id"],
        "name": meta.get("name"),
        "version": meta.get("version"),
        "schema": meta.get("schema"),
        "path": root,
        "subject": meta.get("subject") or {},
        "nodes": nodes,
        "lessons": lessons,
        "questions": questions,
        "assets": assets,
    }


def load_all() -> list[dict[str, Any]]:
    return [load_pack(entry) for entry in paths.packs()]


# ---------------------------------------------------------------- validate

_NAME_RE = re.compile(r"^[a-z0-9]+(?:-[a-z0-9]+)*\.(md|json|svg|png|jpg|jpeg|gif|mp3|mp4|webm)$")


def _check_name(path_str: str, label: str, errors: list[str]) -> None:
    name = Path(path_str).name
    if not _NAME_RE.match(name):
        errors.append(f"{label} 文件名必须是小写 kebab-case：{name}")


def _outline_map(pack: dict[str, Any], errors: list[str]) -> dict[str, str]:
    subject_id = (pack.get("subject") or {}).get("id")
    mapping: dict[str, str] = {}
    for index, node in enumerate(pack.get("nodes") or []):
        if not isinstance(node, dict):
            errors.append(f"outline[{index}] 必须是对象")
            continue
        code = node.get("code")
        if not code or not isinstance(code, str):
            errors.append(f"outline[{index}] 缺少 code")
            continue
        if code in mapping:
            errors.append(f"考点编号重复：{code}")
            continue
        if not node.get("title"):
            errors.append(f"outline {code} 缺少 title")
        mapping[code] = subject_id or ""
    if not mapping:
        errors.append("outline.json 至少要有一个考点")
    return mapping


def _check_media(
    pack: dict[str, Any], text: Any, label: str, errors: list[str],
) -> None:
    if not isinstance(text, str):
        return
    assets = set(pack.get("assets") or [])
    for match in _MEDIA_RE.finditer(text):
        pack_id, rel = match.group(1), match.group(2)
        rel = rel.split("?", 1)[0].split("#", 1)[0].rstrip(".,;:!?，。；：！？")
        if pack_id != pack["id"]:
            errors.append(f"{label} 引用了其它内容包：/media/{pack_id}/{rel}")
        elif rel not in assets:
            errors.append(f"{label} 引用的素材不存在：/media/{pack_id}/{rel}")


def validate_pack(pack: dict[str, Any]) -> list[str]:
    """校验单个 pack，返回错误列表（空表示通过）。"""
    errors: list[str] = []
    for key in ("id", "name", "version"):
        if not pack.get(key):
            errors.append(f"pack.json 缺少 {key}")
    if not re.match(r"^[a-z][a-z0-9]*(?:-[a-z0-9]+)*$", str(pack.get("id") or "")):
        errors.append("pack.id 必须是英文小写 kebab-case")
    if pack.get("schema") != PACK_SCHEMA:
        errors.append(f"schema 必须是 {PACK_SCHEMA}，当前是 {pack.get('schema')!r}")

    subject = pack.get("subject") or {}
    if not isinstance(subject, dict):
        errors.append("subject 必须是对象")
        subject = {}
    for key in ("id", "name", "short"):
        if not subject.get(key):
            errors.append(f"subject 缺少 {key}")
    exam = subject.get("exam") or {}
    if not isinstance(exam, dict):
        errors.append("subject.exam 必须是对象")

    outline = _outline_map(pack, errors)

    for name in pack.get("assets") or []:
        _check_name(str(name), f"asset {name}", errors)

    questions_dir = pack["path"] / "questions"
    if questions_dir.is_dir():
        for file in questions_dir.glob("*.json"):
            _check_name(str(file), f"question file {file.name}", errors)

    lesson_keys: set[str] = set()
    for index, lesson in enumerate(pack.get("lessons") or []):
        label = f"lesson[{index}]"
        file = lesson.get("file")
        if file:
            label = str(file.relative_to(pack["path"])) if file.is_relative_to(pack["path"]) else str(file)
            _check_name(label, label, errors)
        unknown = set(lesson) - LESSON_FIELDS - {
            "body", "file", "source_key", "format",
        }
        if unknown:
            errors.append(f"{label} 含不支持的 frontmatter 字段：{', '.join(sorted(unknown))}")
        for key in ("title", "kind", "status", "sort_order", "outline_codes"):
            if lesson.get(key) in (None, "", []):
                errors.append(f"{label} 缺少 {key}")
        kind = lesson.get("kind")
        if kind and kind not in KINDS:
            errors.append(f"{label} 的 kind 必须是 {'/'.join(sorted(KINDS))}")
        status = lesson.get("status")
        if status and status not in STATUSES:
            errors.append(f"{label} 的 status 必须是 {'/'.join(sorted(STATUSES))}")
        order = lesson.get("sort_order")
        if order is not None and (not isinstance(order, int) or isinstance(order, bool)):
            errors.append(f"{label} 的 sort_order 必须是整数")
        codes = lesson.get("outline_codes")
        if codes is not None and not isinstance(codes, list):
            errors.append(f"{label} 的 outline_codes 必须是数组")
            codes = []
        for code in codes or []:
            if code not in outline:
                errors.append(f"{label} 的 outline_codes {code} 不在大纲里")
        lesson_key = lesson.get("lesson_key")
        if kind in {"lesson", "note", "daily"} and not lesson_key:
            errors.append(f"{label} 缺少 lesson_key")
        if lesson_key:
            if not isinstance(lesson_key, str):
                errors.append(f"{label} 的 lesson_key 必须是字符串")
            elif lesson_key in lesson_keys:
                errors.append(f"lesson_key 重复：{lesson_key}")
            else:
                lesson_keys.add(lesson_key)
        fmt = lesson.get("format") or "markdown"
        if fmt not in LESSON_FORMATS:
            errors.append(f"{label} 的 format 必须是 markdown/blocks")
        errors.extend(f"{label}: {err}" for err in validate_layout(lesson.get("layout")))
        errors.extend(f"{label}: {err}" for err in validate_theme(lesson.get("theme")))
        if fmt == "blocks" or lesson.get("blocks") is not None:
            errors.extend(
                f"{label}: {err}"
                for err in validate_blocks(lesson.get("blocks"), label=f"{label} blocks")
            )
            for index, url in enumerate(iter_media_urls(lesson.get("blocks"))):
                _check_media(pack, url, f"{label} 块媒体[{index}]", errors)
        _check_media(pack, lesson.get("body"), f"{label} 正文", errors)

    question_ids: set[str] = set()
    for index, item in enumerate(pack.get("questions") or []):
        label = f"question[{index}]"
        if item.get("id"):
            label = f"question {item['id']}"
            if item["id"] in question_ids:
                errors.append(f"题目 id 重复：{item['id']}")
            question_ids.add(item["id"])
        else:
            errors.append(f"{label} 缺少 id")
        errors.extend(f"{label}: {err}" for err in validate_question(item, outline))
        for code in item.get("outline_codes") or []:
            if code not in outline:
                errors.append(f"{label} 的 outline_codes {code} 不在大纲里")
        _check_media(pack, item.get("stem"), f"{label} 题干", errors)
        _check_media(pack, item.get("explanation"), f"{label} 解析", errors)
        for media_index, media in enumerate(item.get("media") or []):
            if isinstance(media, dict) and isinstance(media.get("url"), str):
                _check_media(
                    pack, media["url"], f"{label} media[{media_index}]", errors,
                )
        errors.extend(f"{label}: {err}" for err in validate_media(
            item.get("media"), f"{label}.media",
        ))

    return errors


def validate_all() -> list[dict[str, Any]]:
    """校验全部 pack，供 CLI 使用。"""
    results: list[dict[str, Any]] = []
    for entry in paths.packs():
        try:
            pack = load_pack(entry)
        except PackError as exc:
            results.append({"id": entry["id"], "ok": False, "errors": [str(exc)]})
            continue
        errors = validate_pack(pack)
        results.append({
            "id": pack.get("id") or entry["id"],
            "ok": not errors,
            "errors": errors,
            "nodes": len(pack["nodes"]),
            "lessons": len(pack["lessons"]),
            "questions": len(pack["questions"]),
        })
    return results


# ---------------------------------------------------------------- sync

def _json(value: Any) -> str | None:
    return json.dumps(value, ensure_ascii=False) if value is not None else None


def _now() -> str:
    return datetime.now().strftime("%Y-%m-%dT%H:%M:%S")


def _sync_subject(conn: sqlite3.Connection, pack: dict[str, Any]) -> str:
    subject = pack["subject"]
    exam = subject.get("exam") or {}
    conn.execute(
        """INSERT INTO subject(id, name, short, exam_score, exam_minutes,
                               color, icon, sort, code_language, pack_id, source_key)
           VALUES (?,?,?,?,?,?,?,?,?,?,?)
           ON CONFLICT(id) DO UPDATE SET
             name=excluded.name, short=excluded.short,
             exam_score=excluded.exam_score, exam_minutes=excluded.exam_minutes,
             color=excluded.color, icon=excluded.icon, sort=excluded.sort,
             code_language=excluded.code_language,
             pack_id=excluded.pack_id, source_key=excluded.source_key""",
        (
            subject["id"], subject["name"], subject["short"],
            exam.get("score", 100), exam.get("minutes", 120),
            subject.get("color"), subject.get("icon"), subject.get("sort", 0),
            subject.get("code_language"), pack["id"], subject["id"],
        ),
    )
    return subject["id"]


def _sync_outline(
    conn: sqlite3.Connection, pack: dict[str, Any], subject_id: str,
) -> dict[str, str]:
    mapping: dict[str, str] = {}
    for index, node in enumerate(pack["nodes"]):
        mapping[node["code"]] = subject_id
        conn.execute(
            """INSERT INTO outline_node
               (code, subject_id, section, title, requirement, frequency, hours,
                stage, assessment, kind, sort, parent_code, pack_id)
               VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)
               ON CONFLICT(code) DO UPDATE SET
                 subject_id=excluded.subject_id, section=excluded.section,
                 title=excluded.title, requirement=excluded.requirement,
                 frequency=excluded.frequency, hours=excluded.hours,
                 stage=excluded.stage, assessment=excluded.assessment,
                 kind=excluded.kind, sort=excluded.sort,
                 parent_code=excluded.parent_code, pack_id=excluded.pack_id""",
            (
                node["code"], subject_id, node.get("section"), node["title"],
                node.get("requirement"), node.get("frequency"), node.get("hours"),
                node.get("stage"), node.get("assessment"),
                node.get("kind", "point"), node.get("sort", index),
                node.get("parent"), pack["id"],
            ),
        )
    _update_depths(conn, subject_id)
    return mapping


def _update_depths(conn: sqlite3.Connection, subject_id: str) -> None:
    rows = conn.execute(
        "SELECT code, parent_code FROM outline_node WHERE subject_id = ?", (subject_id,)
    ).fetchall()
    parents = {row["code"]: row["parent_code"] for row in rows}
    cache: dict[str, int] = {}

    def depth(code: str, seen: set[str]) -> int:
        if code in cache:
            return cache[code]
        parent = parents.get(code)
        if not parent or parent not in parents or parent in seen:
            cache[code] = 0
        else:
            cache[code] = depth(parent, seen | {code}) + 1
        return cache[code]

    for code in parents:
        conn.execute(
            "UPDATE outline_node SET depth = ? WHERE code = ?",
            (depth(code, set()), code),
        )


def _sync_question(
    conn: sqlite3.Connection, pack: dict[str, Any], subject_id: str,
    item: dict[str, Any], outline: dict[str, str],
) -> None:
    source_key = str(item.get("id") or fingerprint(item["stem"]))
    fp = fingerprint(item["stem"])
    existing = None
    if item.get("id"):
        existing = conn.execute(
            "SELECT id FROM question WHERE id = ?", (item["id"],)
        ).fetchone()
    if not existing:
        existing = conn.execute(
            "SELECT id FROM question WHERE fingerprint = ?", (fp,)
        ).fetchone()

    values = (
        item.get("subject_id") or outline[item["outline_code"]],
        item["outline_code"], item.get("group_position", 0), item["type"],
        item["stem"], _json(item.get("options")), _json(item.get("answer")),
        item.get("explanation", ""), item.get("reference_answer"),
        _json(item.get("rubric")), item.get("score", 1),
        item.get("difficulty", 2), _json(item.get("source", {"kind": "seed"})),
        _json(item.get("tags", [])), 1 if item.get("verified") else 0,
        item.get("language"), _json(item.get("media")) if item.get("media") else None,
        fp, pack["id"], source_key,
    )
    if existing:
        conn.execute(
            """UPDATE question SET
                 subject_id=?, outline_code=?, group_position=?, type=?, stem=?,
                 options=?, answer=?, explanation=?, reference_answer=?, rubric=?,
                 score=?, difficulty=?, source=?, tags=?, verified=?, language=?,
                 media=?, fingerprint=?, pack_id=?, source_key=?
               WHERE id=?""",
            (*values, existing["id"]),
        )
        question_id = existing["id"]
    else:
        question_id = item["id"] or f"q_{fp}"
        conn.execute(
            """INSERT INTO question
               (id, subject_id, outline_code, group_position, type, stem, options,
                answer, explanation, reference_answer, rubric, score, difficulty,
                source, tags, verified, language, media, fingerprint, pack_id,
                source_key, status, created_at)
               VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
            (
                question_id, *values,
                item.get("status", "approved"), _now(),
            ),
        )

    linked = [item["outline_code"], *(item.get("outline_codes") or [])]
    for code in dict.fromkeys(linked):
        conn.execute(
            "INSERT OR IGNORE INTO question_outline(question_id, outline_code) VALUES (?,?)",
            (question_id, code),
        )


def _relative_content_file(file: Path) -> str | None:
    """内容文件相对 content/ 的路径；不在内容目录内时返回 None。"""
    try:
        return file.resolve().relative_to(paths.content_dir().resolve()).as_posix()
    except (OSError, ValueError):
        return None


def _sync_page(
    conn: sqlite3.Connection, pack: dict[str, Any], subject_id: str,
    lesson: dict[str, Any],
) -> None:
    kind = lesson.get("kind") or "lesson"
    lesson_key = lesson.get("lesson_key")
    if kind == "outline":
        source_key = lesson_key or "outline"
        existing = conn.execute(
            """SELECT id FROM page
               WHERE subject_id = ? AND kind = 'outline'
               ORDER BY CASE WHEN pack_id = ? THEN 0 WHEN pack_id IS NULL THEN 1 ELSE 2 END
               LIMIT 1""",
            (subject_id, pack["id"]),
        ).fetchone()
    else:
        source_key = str(lesson_key or lesson["file"].stem)
        existing = conn.execute(
            """SELECT id FROM page
               WHERE subject_id = ? AND lesson_key = ?
               ORDER BY CASE WHEN pack_id = ? THEN 0 WHEN pack_id IS NULL THEN 1 ELSE 2 END
               LIMIT 1""",
            (subject_id, source_key, pack["id"]),
        ).fetchone()

    file = _relative_content_file(lesson["file"]) if lesson.get("file") else None
    values = (
        subject_id, lesson.get("title"), lesson.get("summary"),
        lesson["body"], _json(lesson.get("blocks")),
        lesson.get("layout") or "article", _json(lesson.get("theme")),
        lesson.get("format") or "markdown",
        source_key, _json(lesson.get("outline_codes") or []),
        kind, lesson.get("status") or "published",
        lesson.get("sort_order", 1000), pack["id"], source_key, file,
    )
    if existing:
        conn.execute(
            """UPDATE page SET subject_id=?, title=?, summary=?, body=?, blocks=?,
                 layout=?, theme=?, format=?, lesson_key=?, outline_codes=?,
                 kind=?, status=?, sort_order=?, pack_id=?, source_key=?, file=?,
                 updated_at=?
               WHERE id=?""",
            (*values, _now(), existing["id"]),
        )
        return

    slug = re.sub(r"[^A-Za-z0-9_-]+", "-", source_key).strip("-") or "page"
    page_id = f"p_{pack['id']}_{slug}"
    now = _now()
    conn.execute(
        """INSERT INTO page(id, subject_id, title, summary, body, blocks, layout,
                            theme, format, lesson_key, outline_codes, kind, status,
                            sort_order, created_at, updated_at, pack_id, source_key,
                            file)
           VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
        (
            page_id, subject_id, lesson.get("title"), lesson.get("summary"),
            lesson["body"], _json(lesson.get("blocks")),
            lesson.get("layout") or "article", _json(lesson.get("theme")),
            lesson.get("format") or "markdown",
            source_key, _json(lesson.get("outline_codes") or []),
            kind, lesson.get("status") or "published",
            lesson.get("sort_order", 1000), now, now, pack["id"], source_key, file,
        ),
    )


def _sync_pack(conn: sqlite3.Connection, pack: dict[str, Any]) -> dict[str, int]:
    conn.execute(
        """INSERT INTO content_pack(id, name, version, schema, path, synced_at)
           VALUES (?,?,?,?,?,?)
           ON CONFLICT(id) DO UPDATE SET
             name=excluded.name, version=excluded.version, schema=excluded.schema,
             path=excluded.path, synced_at=excluded.synced_at""",
        (
            pack["id"], pack.get("name") or pack["id"], str(pack.get("version") or ""),
            pack.get("schema") or PACK_SCHEMA, str(pack["path"]), _now(),
        ),
    )
    subject_id = _sync_subject(conn, pack)
    outline = _sync_outline(conn, pack, subject_id)
    for item in pack["questions"]:
        _sync_question(conn, pack, subject_id, item, outline)
    for lesson in pack["lessons"]:
        _sync_page(conn, pack, subject_id, lesson)
    return {
        "nodes": len(pack["nodes"]),
        "lessons": len(pack["lessons"]),
        "questions": len(pack["questions"]),
    }


def sync_content(conn: sqlite3.Connection) -> list[dict[str, int]]:
    """把内容仓库同步进库；只 upsert，不删除本地内容。"""
    totals: list[dict[str, int]] = []
    for entry in paths.packs():
        pack = load_pack(entry)
        errors = validate_pack(pack)
        if errors:
            raise PackError(f"内容包 {entry['id']} 校验失败：\n" + "\n".join(errors))
        totals.append({"id": pack["id"], **_sync_pack(conn, pack)})
    return totals


# ---------------------------------------------------------------- editing（网页草稿写回）

def _field(obj: Any, key: str, default: Any = None) -> Any:
    """从 sqlite3.Row 或 dict 里取字段。"""
    if obj is None:
        return default
    if isinstance(obj, dict):
        return obj.get(key, default)
    try:
        return obj[key]
    except (IndexError, KeyError):
        return default


def _json_value(value: Any, label: str) -> Any:
    if value is None or value == "":
        return None
    if isinstance(value, (list, dict)):
        return value
    try:
        return json.loads(value)
    except (TypeError, json.JSONDecodeError) as exc:
        raise PackError(f"{label} 不是合法 JSON：{exc}") from exc


def page_file_path(content_dir: Path, page_row: Any) -> Path:
    """``page.file`` 解析为绝对路径，并保证仍在内容目录内。"""
    raw = _field(page_row, "file")
    if not raw:
        raise PackError("页面没有可写的内容文件")
    base = Path(content_dir).resolve()
    target = (base / str(raw)).resolve()
    if not target.is_relative_to(base):
        raise PackError(f"内容文件路径越界：{raw}")
    return target


def lesson_from_draft(page_row: Any, draft: Any, file: Path | None = None) -> dict[str, Any]:
    """把 page + 草稿合成一个 lesson dict（用于校验与写文件）。"""
    blocks = _json_value(_field(draft, "blocks"), "草稿 blocks")
    theme = _parse_theme(_field(draft, "theme"), "草稿")
    body = _field(draft, "body")
    body = body if isinstance(body, str) else ""

    fmt = "blocks" if blocks is not None else "markdown"
    if file is not None:
        suffix = file.suffix.lower()
        if suffix == ".json":
            fmt = "blocks"
        elif suffix == ".md":
            fmt = "markdown"

    codes = _json_value(_field(page_row, "outline_codes"), "页面 outline_codes") or []
    if not isinstance(codes, list):
        raise PackError("页面 outline_codes 不是数组")
    lesson_key = _field(page_row, "lesson_key")
    return {
        "lesson_key": lesson_key,
        "title": _field(page_row, "title"),
        "summary": _field(page_row, "summary"),
        "kind": _field(page_row, "kind") or "lesson",
        "status": _field(page_row, "status") or "published",
        "sort_order": _field(page_row, "sort_order", 1000),
        "outline_codes": codes,
        "layout": _field(draft, "layout") or _field(page_row, "layout") or "article",
        "theme": theme,
        "body": body if fmt == "markdown" else "",
        "blocks": blocks if fmt == "blocks" else None,
        "format": fmt,
        "file": file,
        "source_key": _field(page_row, "source_key") or lesson_key or "",
    }


def _yaml_scalar(value: Any) -> str:
    if isinstance(value, bool):
        return "true" if value else "false"
    if isinstance(value, (int, float)):
        return str(value)
    if isinstance(value, list):
        return json.dumps(value, ensure_ascii=False)
    if isinstance(value, dict):
        text = json.dumps(value, ensure_ascii=False)
        return f"'{text}'" if "'" not in text else json.dumps(text, ensure_ascii=False)
    text = str(value).replace("\r", " ").replace("\n", " ")
    return f"'{text}'" if "'" not in text else json.dumps(text, ensure_ascii=False)


def _render_markdown(lesson: dict[str, Any]) -> str:
    lines = ["---"]
    for key in (
        "lesson_key", "title", "summary", "kind", "status", "sort_order",
        "layout", "theme", "outline_codes",
    ):
        value = lesson.get(key)
        if value is None or value == "":
            continue
        lines.append(f"{key}: {_yaml_scalar(value)}")
    lines.append("---")
    body = (lesson.get("body") or "").lstrip("\r\n")
    if body and not body.endswith("\n"):
        body += "\n"
    return "\n".join(lines) + "\n\n" + body


_JSON_LESSON_FIELDS = (
    "lesson_key", "title", "summary", "kind", "status", "sort_order", "outline_codes",
)


def _lesson_json_data(lesson: dict[str, Any], target: Path) -> dict[str, Any]:
    """保留原 JSON 的其它字段，只覆盖页面可编辑的元信息与块。"""
    data: dict[str, Any] = {}
    if target.is_file():
        try:
            existing = json.loads(target.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            existing = None
        if isinstance(existing, dict):
            data = existing
    for key in _JSON_LESSON_FIELDS:
        if lesson.get(key) is not None:
            data[key] = lesson[key]
    data["layout"] = lesson.get("layout") or "article"
    if lesson.get("theme") is not None:
        data["theme"] = lesson["theme"]
    else:
        data.pop("theme", None)
    data["blocks"] = lesson.get("blocks") or []
    for key in ("body", "file", "format", "source_key"):
        data.pop(key, None)
    return data


def _atomic_write(target: Path, text: str) -> None:
    target.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp = tempfile.mkstemp(
        prefix=f".{target.name}.", suffix=".tmp", dir=str(target.parent),
    )
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as handle:
            handle.write(text)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(tmp, target)
    except BaseException:
        try:
            os.unlink(tmp)
        except OSError:
            pass
        raise


def write_lesson_file(content_dir: Path, page_row: Any, draft: Any) -> Path:
    """把草稿写回内容文件（Markdown 或 JSON），原子替换。"""
    target = page_file_path(content_dir, page_row)
    lesson = lesson_from_draft(page_row, draft, target)
    suffix = target.suffix.lower()
    if suffix == ".md":
        text = _render_markdown(lesson)
    elif suffix == ".json":
        text = json.dumps(
            _lesson_json_data(lesson, target), ensure_ascii=False, indent=2,
        ) + "\n"
    else:
        raise PackError(f"不支持的内容文件类型：{target.name}")
    _atomic_write(target, text)
    return target


def validate_page_draft(content_dir: Path, page_row: Any, draft: Any) -> list[str]:
    """用磁盘上的 pack 加上草稿后的 lesson 做一次完整校验。"""
    try:
        target = page_file_path(content_dir, page_row)
        lesson = lesson_from_draft(page_row, draft, target)
    except PackError as exc:
        return [str(exc)]

    pack_id = _field(page_row, "pack_id")
    entry = next((item for item in paths.packs() if item["id"] == pack_id), None)
    if entry is None:
        return [f"找不到内容包：{pack_id}"]
    try:
        pack = load_pack(entry)
    except PackError as exc:
        return [str(exc)]

    lessons: list[dict[str, Any]] = []
    replaced = False
    for item in pack["lessons"]:
        item_file = item.get("file")
        if item_file is not None and Path(item_file).resolve() == target:
            lessons.append(lesson)
            replaced = True
        else:
            lessons.append(item)
    if not replaced:
        return [f"内容包里找不到文件：{_field(page_row, 'file')}"]
    return validate_pack({**pack, "lessons": lessons})
