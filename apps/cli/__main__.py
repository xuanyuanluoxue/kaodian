from __future__ import annotations

import argparse
import json
import sqlite3
import sys
from datetime import datetime
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from apps.api.app import content, paths  # noqa: E402
from apps.api.app import db as database  # noqa: E402


def _emit(data: dict[str, Any], as_json: bool, text: str | None = None) -> None:
    if as_json:
        print(json.dumps(data, ensure_ascii=False, indent=2))
    elif text:
        print(text)
    else:
        print(json.dumps(data, ensure_ascii=False, indent=2))


def _content_rows() -> list[dict[str, Any]]:
    rows = []
    for entry in paths.packs():
        pack = content.load_pack(entry)
        errors = content.validate_pack(pack)
        rows.append({
            "id": pack.get("id") or entry["id"],
            "name": pack.get("name"),
            "version": pack.get("version"),
            "schema": pack.get("schema"),
            "path": str(pack["path"]),
            "nodes": len(pack["nodes"]),
            "lessons": len(pack["lessons"]),
            "questions": len(pack["questions"]),
            "assets": len(pack["assets"]),
            "ok": not errors,
            "errors": errors,
        })
    return rows


def cmd_content_list(args: argparse.Namespace) -> int:
    try:
        rows = _content_rows()
    except Exception as exc:  # noqa: BLE001 - CLI 边界统一转成非 0
        _emit({"ok": False, "error": str(exc)}, args.json)
        return 1
    ok = all(row["ok"] for row in rows)
    lines = [
        f"{row['id']}  {row['version']}  {row['nodes']} 考点 / "
        f"{row['lessons']} 页 / {row['questions']} 题"
        for row in rows
    ]
    _emit(
        {"ok": ok, "content_dir": str(paths.content_dir()), "packs": rows},
        args.json,
        "\n".join(lines) or f"内容目录为空：{paths.content_dir()}",
    )
    return 0 if ok else 1


def cmd_content_validate(args: argparse.Namespace) -> int:
    try:
        results = content.validate_all()
    except Exception as exc:  # noqa: BLE001
        _emit({"ok": False, "error": str(exc)}, args.json)
        return 1
    ok = all(item["ok"] for item in results)
    lines = []
    for item in results:
        if item["ok"]:
            lines.append(f"✓ {item['id']}")
        else:
            lines.append(f"✗ {item['id']}")
            lines.extend(f"  - {error}" for error in item["errors"])
    _emit(
        {"ok": ok, "content_dir": str(paths.content_dir()), "packs": results},
        args.json,
        "\n".join(lines) or f"没有内容包：{paths.content_dir()}",
    )
    return 0 if ok else 1


def cmd_content_sync(args: argparse.Namespace) -> int:
    path = Path(args.db) if args.db else paths.db_path()
    try:
        database.init_db(path)
        with database.session(path) as conn:
            counts = {
                "packs": conn.execute("SELECT COUNT(*) FROM content_pack").fetchone()[0],
                "subjects": conn.execute("SELECT COUNT(*) FROM subject").fetchone()[0],
                "nodes": conn.execute("SELECT COUNT(*) FROM outline_node").fetchone()[0],
                "questions": conn.execute("SELECT COUNT(*) FROM question").fetchone()[0],
                "pages": conn.execute("SELECT COUNT(*) FROM page").fetchone()[0],
            }
            version = conn.execute("PRAGMA user_version").fetchone()[0]
    except Exception as exc:  # noqa: BLE001
        _emit({"ok": False, "error": str(exc), "db": str(path)}, args.json)
        return 1
    _emit(
        {"ok": True, "db": str(path), "schema_version": version, **counts},
        args.json,
        f"已同步 {counts['packs']} 个内容包到 {path}",
    )
    return 0


def cmd_serve(args: argparse.Namespace) -> int:
    import uvicorn

    uvicorn.run(
        "app.main:app",
        host=args.host,
        port=args.port,
        reload=args.reload,
        app_dir=str(ROOT / "apps" / "api"),
    )
    return 0


def cmd_doctor(args: argparse.Namespace) -> int:
    db_file = Path(args.db) if args.db else paths.db_path()
    info: dict[str, Any] = {
        "content_dir": str(paths.content_dir()),
        "data_dir": str(paths.data_dir()),
        "db": str(db_file),
        "db_exists": db_file.is_file(),
    }
    try:
        info["packs"] = _content_rows()
    except Exception as exc:  # noqa: BLE001
        info["packs"] = []
        info["content_error"] = str(exc)

    if db_file.is_file():
        conn = sqlite3.connect(db_file)
        conn.row_factory = sqlite3.Row
        try:
            info["schema_version"] = conn.execute("PRAGMA user_version").fetchone()[0]
            info["expected_schema"] = database.SCHEMA_VERSION
            try:
                info["content_packs"] = [
                    dict(row) for row in conn.execute(
                        "SELECT id, name, version, schema, synced_at FROM content_pack "
                        "ORDER BY id"
                    )
                ]
            except sqlite3.Error:
                info["content_packs"] = []
        finally:
            conn.close()

    ok = bool(info.get("db_exists")) and all(
        pack.get("ok") for pack in info.get("packs", [])
    ) and info.get("schema_version") == database.SCHEMA_VERSION
    info["ok"] = ok
    text = "\n".join([
        f"内容目录  {info['content_dir']}",
        f"数据目录  {info['data_dir']}",
        f"数据库    {info['db']}",
        f"schema    {info.get('schema_version', '-')} / {database.SCHEMA_VERSION}",
        f"内容包    {len(info.get('packs', []))}",
    ])
    _emit(info, args.json, text)
    return 0 if ok else 1


def cmd_backup(args: argparse.Namespace) -> int:
    source = Path(args.db) if args.db else paths.db_path()
    if not source.is_file():
        _emit({"ok": False, "error": f"数据库不存在：{source}"}, args.json)
        return 2
    if args.out:
        target = Path(args.out).expanduser()
        if target.is_dir():
            target = target / f"kaodian-{datetime.now():%Y%m%d-%H%M%S}.db"
    else:
        exports = paths.data_dir() / "exports"
        exports.mkdir(parents=True, exist_ok=True)
        target = exports / f"kaodian-{datetime.now():%Y%m%d-%H%M%S}.db"
    target.parent.mkdir(parents=True, exist_ok=True)

    src = sqlite3.connect(source)
    dst = sqlite3.connect(target)
    try:
        src.backup(dst)
    finally:
        dst.close()
        src.close()
    _emit(
        {"ok": True, "source": str(source), "path": str(target)},
        args.json,
        f"已备份到 {target}",
    )
    return 0


def cmd_mcp_config(args: argparse.Namespace) -> int:
    python = ROOT / ".venv" / "bin" / "python"
    payload = {
        "mcpServers": {
            "kaodian": {
                "command": str(python),
                "args": [str(ROOT / "apps" / "mcp" / "server.py")],
                "env": {
                    "KAODIAN_API": args.api,
                    "KAODIAN_WEB": args.web,
                },
            }
        }
    }
    _emit(payload, args.json)
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="kaodian", description="考点命令行")
    sub = parser.add_subparsers(dest="command", required=True)

    serve = sub.add_parser("serve", help="启动 API + Web")
    serve.add_argument("--host", default="127.0.0.1")
    serve.add_argument("--port", type=int, default=8010)
    serve.add_argument("--reload", action="store_true")
    serve.add_argument("--json", action="store_true")
    serve.set_defaults(func=cmd_serve)

    content_parser = sub.add_parser("content", help="内容包操作")
    content_sub = content_parser.add_subparsers(dest="content_command", required=True)
    for name, func, help_text in (
        ("list", cmd_content_list, "列出内容包"),
        ("validate", cmd_content_validate, "校验内容包"),
        ("sync", cmd_content_sync, "同步内容到数据库"),
    ):
        child = content_sub.add_parser(name, help=help_text)
        child.add_argument("--json", action="store_true")
        if name == "sync":
            child.add_argument("--db", help="覆盖数据库路径")
        child.set_defaults(func=func)

    doctor = sub.add_parser("doctor", help="检查路径、数据库与内容包")
    doctor.add_argument("--json", action="store_true")
    doctor.add_argument("--db", help="覆盖数据库路径")
    doctor.set_defaults(func=cmd_doctor)

    backup = sub.add_parser("backup", help="SQLite 备份")
    backup.add_argument("--json", action="store_true")
    backup.add_argument("--db", help="覆盖数据库路径")
    backup.add_argument("--out", help="输出文件或目录")
    backup.set_defaults(func=cmd_backup)

    mcp = sub.add_parser("mcp-config", help="输出 IDE 可用的 MCP JSON")
    mcp.add_argument("--json", action="store_true")
    mcp.add_argument("--api", default="http://127.0.0.1:8010")
    mcp.add_argument("--web", default="http://127.0.0.1:8010")
    mcp.set_defaults(func=cmd_mcp_config)

    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    try:
        return int(args.func(args))
    except KeyboardInterrupt:
        return 130
    except Exception as exc:  # noqa: BLE001 - CLI 失败必须非 0
        _emit({"ok": False, "error": str(exc)}, getattr(args, "json", False))
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
