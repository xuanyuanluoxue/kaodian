"""讲义 JSON 块校验。契约见 ``docs/dev/blocks.md``。

这里只做结构校验，不执行任何块内容。返回错误列表，空列表表示通过。
"""

from __future__ import annotations

import re
from typing import Any, Iterator

BLOCK_TYPES = frozenset({
    "markdown", "callout", "columns", "tabs", "steps", "cards", "timeline",
    "image", "video", "audio", "code", "mermaid", "math-graph", "sandbox",
    "divider",
})

LAYOUTS = frozenset({"article", "wide", "split", "slides", "dashboard"})
THEME_ACCENTS = frozenset({"math", "computer", "english", "politics"})
THEME_DENSITIES = frozenset({"compact", "comfortable"})
THEME_FONTS = frozenset({"sans", "serif"})

CALLOUT_TONES = frozenset({"info", "warn", "danger", "success"})

MAX_DEPTH = 3
SANDBOX_MAX_BYTES = 200 * 1024
SANDBOX_MIN_HEIGHT = 200
SANDBOX_MAX_HEIGHT = 900

_MEDIA_LOCAL_RE = re.compile(r"^/media/[A-Za-z0-9._-]+/[^\s]+$")
_HEX_COLOR_RE = re.compile(r"^#[0-9A-Fa-f]{3,8}$")


def validate_blocks(blocks: Any, *, label: str = "blocks") -> list[str]:
    """校验一个块数组；``label`` 用于错误定位。"""
    errors: list[str] = []
    _validate_list(blocks, label, 0, errors)
    return errors


def _validate_list(blocks: Any, label: str, depth: int, errors: list[str]) -> None:
    if not isinstance(blocks, list):
        errors.append(f"{label} 必须是数组")
        return
    for index, block in enumerate(blocks):
        _validate_block(block, f"{label}[{index}]", depth, errors)


def _validate_block(block: Any, label: str, depth: int, errors: list[str]) -> None:
    if not isinstance(block, dict):
        errors.append(f"{label} 必须是对象")
        return
    block_type = block.get("type")
    if not isinstance(block_type, str) or not block_type:
        errors.append(f"{label} 缺少 type")
        return
    if block_type not in BLOCK_TYPES:
        errors.append(f"{label} 未知块类型：{block_type}")
        return
    if depth > MAX_DEPTH:
        errors.append(f"{label} 嵌套超过 {MAX_DEPTH} 层")
        return

    if block_type == "markdown":
        _require_str(block, "text", label, errors)
    elif block_type == "callout":
        if block.get("tone") not in CALLOUT_TONES:
            errors.append(
                f"{label}.tone 必须是 {'/'.join(sorted(CALLOUT_TONES))}"
            )
        _require_str(block, "text", label, errors)
        _optional_str(block, "title", label, errors)
    elif block_type == "columns":
        cols = block.get("cols")
        if not isinstance(cols, list) or not 2 <= len(cols) <= 3:
            errors.append(f"{label}.cols 必须是 2–3 列的数组")
            cols = cols if isinstance(cols, list) else []
        for index, col in enumerate(cols):
            _validate_list(col, f"{label}.cols[{index}]", depth + 1, errors)
    elif block_type == "tabs":
        items = block.get("items")
        if not isinstance(items, list) or not items:
            errors.append(f"{label}.items 至少要有 1 项")
            items = items if isinstance(items, list) else []
        for index, item in enumerate(items):
            item_label = f"{label}.items[{index}]"
            if not isinstance(item, dict):
                errors.append(f"{item_label} 必须是对象")
                continue
            _require_str(item, "label", item_label, errors)
            _validate_list(item.get("blocks"), f"{item_label}.blocks", depth + 1, errors)
    elif block_type == "steps":
        _validate_items(block, label, errors, ("title", "text"))
    elif block_type == "cards":
        items = _validate_items(block, label, errors, ("title", "text"))
        for index, item in enumerate(items):
            if isinstance(item, dict):
                _optional_str(item, "link", f"{label}.items[{index}]", errors)
    elif block_type == "timeline":
        _validate_items(block, label, errors, ("time", "title", "text"))
    elif block_type == "image":
        _media_url(block.get("url"), f"{label}.url", errors)
        for key in ("alt", "caption", "license"):
            _optional_str(block, key, label, errors)
    elif block_type == "video":
        _media_url(block.get("url"), f"{label}.url", errors)
        if block.get("poster") is not None:
            _media_url(block.get("poster"), f"{label}.poster", errors)
    elif block_type == "audio":
        _media_url(block.get("url"), f"{label}.url", errors)
        _optional_str(block, "title", label, errors)
    elif block_type == "code":
        _require_str(block, "language", label, errors)
        _require_str(block, "code", label, errors)
        _optional_str(block, "title", label, errors)
    elif block_type == "mermaid":
        _require_str(block, "code", label, errors)
    elif block_type == "math-graph":
        spec = block.get("spec")
        if not isinstance(spec, (str, dict)) or (isinstance(spec, str) and not spec.strip()):
            errors.append(f"{label}.spec 必须是字符串或对象")
    elif block_type == "sandbox":
        if depth != 0:
            errors.append(f"{label} sandbox 只能放在顶层")
        html = block.get("html")
        if not isinstance(html, str) or not html.strip():
            errors.append(f"{label}.html 不能为空")
        elif len(html.encode("utf-8")) > SANDBOX_MAX_BYTES:
            errors.append(
                f"{label}.html 超过 {SANDBOX_MAX_BYTES // 1024}KB"
            )
        height = block.get("height")
        if height is not None and (
            not isinstance(height, int) or isinstance(height, bool)
            or not SANDBOX_MIN_HEIGHT <= height <= SANDBOX_MAX_HEIGHT
        ):
            errors.append(
                f"{label}.height 必须是 {SANDBOX_MIN_HEIGHT}–{SANDBOX_MAX_HEIGHT} 的整数"
            )
        _optional_str(block, "title", label, errors)
    # divider 没有必填字段


def _validate_items(
    block: dict[str, Any], label: str, errors: list[str],
    fields: tuple[str, ...],
) -> list[Any]:
    items = block.get("items")
    if not isinstance(items, list) or not items:
        errors.append(f"{label}.items 至少要有 1 项")
        return items if isinstance(items, list) else []
    for index, item in enumerate(items):
        item_label = f"{label}.items[{index}]"
        if not isinstance(item, dict):
            errors.append(f"{item_label} 必须是对象")
            continue
        for field in fields:
            _require_str(item, field, item_label, errors)
    return items


def _require_str(
    data: dict[str, Any], key: str, label: str, errors: list[str],
) -> None:
    value = data.get(key)
    if not isinstance(value, str) or not value.strip():
        errors.append(f"{label}.{key} 不能为空")


def _optional_str(
    data: dict[str, Any], key: str, label: str, errors: list[str],
) -> None:
    value = data.get(key)
    if value is not None and not isinstance(value, str):
        errors.append(f"{label}.{key} 必须是字符串")


def _media_url(value: Any, label: str, errors: list[str]) -> None:
    if not isinstance(value, str) or not value:
        errors.append(f"{label} 不能为空")
        return
    if value.startswith("https://") and len(value) > len("https://"):
        return
    if _MEDIA_LOCAL_RE.match(value) and ".." not in value:
        return
    errors.append(f"{label} 只允许 /media/<pack>/... 或 https:// 地址：{value}")


def validate_layout(layout: Any) -> list[str]:
    if layout in LAYOUTS:
        return []
    return [f"layout 必须是 {'/'.join(sorted(LAYOUTS))}"]


def validate_theme(theme: Any) -> list[str]:
    if theme is None:
        return []
    if not isinstance(theme, dict):
        return ["theme 必须是对象"]
    errors: list[str] = []
    unknown = set(theme) - {"accent", "density", "font"}
    if unknown:
        errors.append(f"theme 含不支持的字段：{', '.join(sorted(unknown))}")
    accent = theme.get("accent")
    if accent is not None and not (
        (isinstance(accent, str) and accent in THEME_ACCENTS)
        or (isinstance(accent, str) and _HEX_COLOR_RE.match(accent))
    ):
        errors.append(
            f"theme.accent 必须是 {'/'.join(sorted(THEME_ACCENTS))} 或 #hex"
        )
    density = theme.get("density")
    if density is not None and density not in THEME_DENSITIES:
        errors.append(
            f"theme.density 必须是 {'/'.join(sorted(THEME_DENSITIES))}"
        )
    font = theme.get("font")
    if font is not None and font not in THEME_FONTS:
        errors.append(f"theme.font 必须是 {'/'.join(sorted(THEME_FONTS))}")
    return errors


def iter_media_urls(blocks: Any) -> Iterator[str]:
    """递归产出块里需要检查的媒体地址（image/video/audio）。"""
    if not isinstance(blocks, list):
        return
    for block in blocks:
        if not isinstance(block, dict):
            continue
        block_type = block.get("type")
        if block_type in {"image", "video", "audio"}:
            url = block.get("url")
            if isinstance(url, str) and url:
                yield url
        if block_type == "video":
            poster = block.get("poster")
            if isinstance(poster, str) and poster:
                yield poster
        if block_type == "columns":
            for col in block.get("cols") or []:
                yield from iter_media_urls(col)
        elif block_type == "tabs":
            for item in block.get("items") or []:
                if isinstance(item, dict):
                    yield from iter_media_urls(item.get("blocks"))
