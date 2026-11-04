"""路径解析：内容包、运行时数据与数据库。

优先级（从高到低）：

1. 环境变量 ``KAODIAN_CONTENT_DIR`` / ``KAODIAN_DATA_DIR`` / ``KAODIAN_DB``
2. 仓库根目录的 ``kaodian.toml``
3. 默认 ``examples/demo-content`` + ``data/``
"""

from __future__ import annotations

import json
import os
import tomllib
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[3]
DEFAULT_CONTENT = ROOT / "examples" / "demo-content"
DEFAULT_DATA = ROOT / "data"


def _root_config() -> dict[str, Any]:
    """读取仓库根的 kaodian.toml；不存在或格式错误时返回空配置。"""
    file = ROOT / "kaodian.toml"
    if not file.is_file():
        return {}
    try:
        with file.open("rb") as handle:
            data = tomllib.load(handle)
    except (OSError, tomllib.TOMLDecodeError) as exc:
        raise RuntimeError(f"无法读取 {file}：{exc}") from exc
    return data if isinstance(data, dict) else {}


def _resolve(value: str, base: Path = ROOT) -> Path:
    path = Path(value).expanduser()
    return path if path.is_absolute() else (base / path).resolve()


def _toml_path(key: str) -> Path | None:
    value = (_root_config().get("paths") or {}).get(key)
    if not value:
        return None
    if not isinstance(value, str):
        raise RuntimeError(f"kaodian.toml 的 paths.{key} 必须是字符串")
    return _resolve(value)


def content_dir() -> Path:
    """内容仓库根目录（包含 registry.json 与 packs/）。"""
    env = os.environ.get("KAODIAN_CONTENT_DIR")
    if env:
        return _resolve(env, Path.cwd())
    configured = _toml_path("content")
    return configured or DEFAULT_CONTENT


def data_dir() -> Path:
    """运行时数据目录：数据库、导出、日志。自动创建。"""
    env = os.environ.get("KAODIAN_DATA_DIR")
    if env:
        path = _resolve(env, Path.cwd())
    else:
        path = _toml_path("data") or DEFAULT_DATA
    path.mkdir(parents=True, exist_ok=True)
    return path


def db_path() -> Path:
    """SQLite 路径；KAODIAN_DB 最高优先。"""
    env = os.environ.get("KAODIAN_DB")
    if env:
        return _resolve(env, Path.cwd())
    configured = _toml_path("db")
    if configured:
        return configured
    return data_dir() / "api" / "kaodian.db"


def api_data_dir() -> Path:
    path = data_dir() / "api"
    path.mkdir(parents=True, exist_ok=True)
    return path


def backups_dir() -> Path:
    path = api_data_dir() / "backups"
    path.mkdir(parents=True, exist_ok=True)
    return path


def exports_dir() -> Path:
    path = api_data_dir() / "exports"
    path.mkdir(parents=True, exist_ok=True)
    return path


def sandbox_dir() -> Path:
    path = data_dir() / "shared" / "sandbox"
    path.mkdir(parents=True, exist_ok=True)
    return path


def logs_dir() -> Path:
    path = data_dir() / "shared" / "logs"
    path.mkdir(parents=True, exist_ok=True)
    return path


def config_file(name: str) -> Path:
    """内容仓库根目录下的文件，例如 ``registry.json``。"""
    return content_dir() / name


def framework_config(name: str) -> Path:
    """框架自身的配置（题型注册表等），与内容包分开。"""
    return ROOT / "config" / name


def packs() -> list[dict[str, Any]]:
    """读取 registry.json，返回 ``[{id, path, entry}]``。

    ``path`` 已解析为绝对路径；registry 缺失或结构不合法时抛 RuntimeError。
    """
    registry_file = config_file("registry.json")
    if not registry_file.is_file():
        raise RuntimeError(f"找不到内容注册表：{registry_file}")
    try:
        data = json.loads(registry_file.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise RuntimeError(f"无法读取 {registry_file}：{exc}") from exc
    if not isinstance(data, dict):
        raise RuntimeError(f"{registry_file} 必须是对象")
    if data.get("schema") != 1:
        raise RuntimeError(f"{registry_file} 的 schema 必须是 1")
    entries = data.get("packs")
    if not isinstance(entries, list):
        raise RuntimeError(f"{registry_file} 缺少 packs 数组")

    base = content_dir()
    out: list[dict[str, Any]] = []
    seen: set[str] = set()
    for index, entry in enumerate(entries):
        if not isinstance(entry, dict) or not entry.get("id"):
            raise RuntimeError(f"{registry_file} packs[{index}] 缺少 id")
        pack_id = str(entry["id"])
        if pack_id in seen:
            raise RuntimeError(f"{registry_file} 的 pack id 重复：{pack_id}")
        seen.add(pack_id)
        raw_path = entry.get("path") or f"packs/{pack_id}"
        if not isinstance(raw_path, str):
            raise RuntimeError(f"{registry_file} packs[{index}].path 必须是字符串")
        out.append({
            "id": pack_id,
            "path": _resolve(raw_path, base),
            "entry": entry,
        })
    return out
