from __future__ import annotations

from apps.api.app import blocks


def nested_columns(level: int) -> list[dict]:
    leaf = [{"type": "markdown", "text": "叶子"}]
    if level == 0:
        return leaf
    return [{
        "type": "columns",
        "cols": [nested_columns(level - 1), [{"type": "markdown", "text": "旁栏"}]],
    }]


def test_valid_blocks_pass():
    content = [
        {"type": "markdown", "text": "# 标题"},
        {"type": "callout", "tone": "warn", "title": "注意", "text": "内容"},
        {"type": "columns", "cols": [
            [{"type": "markdown", "text": "左"}],
            [{"type": "code", "language": "python", "code": "print(1)"}],
        ]},
        {"type": "tabs", "items": [
            {"label": "一", "blocks": [{"type": "markdown", "text": "A"}]},
            {"label": "二", "blocks": [{"type": "divider"}]},
        ]},
        {"type": "steps", "items": [{"title": "第一步", "text": "做"}]},
        {"type": "cards", "items": [{"title": "卡片", "text": "说明", "link": "https://example.com"}]},
        {"type": "timeline", "items": [{"time": "2026", "title": "节点", "text": "事件"}]},
        {"type": "image", "url": "/media/demo/demo.svg", "alt": "图"},
        {"type": "video", "url": "https://example.com/v.mp4", "poster": "/media/demo/demo.svg"},
        {"type": "audio", "url": "https://example.com/a.mp3", "title": "音频"},
        {"type": "mermaid", "code": "graph TD; A-->B"},
        {"type": "math-graph", "spec": {"fn": "x^2"}},
        {"type": "sandbox", "html": "<p>hi</p>", "height": 420},
        {"type": "divider"},
    ]
    assert blocks.validate_blocks(content) == []


def test_unknown_type():
    errors = blocks.validate_blocks([{"type": "carousel", "items": []}])
    assert any("未知块类型" in error for error in errors)


def test_columns_requires_two_or_three():
    errors = blocks.validate_blocks([{
        "type": "columns", "cols": [[{"type": "markdown", "text": "唯一"}]],
    }])
    assert any("2–3 列" in error for error in errors)


def test_nesting_more_than_three_layers():
    errors = blocks.validate_blocks(nested_columns(4))
    assert any("嵌套超过 3 层" in error for error in errors)
    assert blocks.validate_blocks(nested_columns(3)) == []


def test_sandbox_must_be_top_level():
    errors = blocks.validate_blocks([{
        "type": "columns",
        "cols": [
            [{"type": "sandbox", "html": "<p>x</p>"}],
            [{"type": "markdown", "text": "右"}],
        ],
    }])
    assert any("sandbox 只能放在顶层" in error for error in errors)


def test_sandbox_html_size_limit():
    errors = blocks.validate_blocks([{
        "type": "sandbox",
        "html": "x" * (blocks.SANDBOX_MAX_BYTES + 1),
    }])
    assert any("超过 200KB" in error for error in errors)


def test_sandbox_height_range():
    errors = blocks.validate_blocks([{"type": "sandbox", "html": "x", "height": 120}])
    assert any("height" in error for error in errors)


def test_media_url_scheme():
    errors = blocks.validate_blocks([
        {"type": "image", "url": "http://example.com/a.png"},
        {"type": "audio", "url": "/other/a.mp3"},
    ])
    assert len([e for e in errors if "只允许 /media" in e]) == 2
    assert blocks.validate_blocks([
        {"type": "image", "url": "/media/demo/a.png"},
        {"type": "video", "url": "https://example.com/v.mp4"},
    ]) == []


def test_layout_and_theme():
    assert blocks.validate_layout("wide") == []
    assert any("layout" in e for e in blocks.validate_layout("fancy"))
    assert blocks.validate_theme({"accent": "math", "density": "compact", "font": "serif"}) == []
    assert blocks.validate_theme({"accent": "#2f5d8a"}) == []
    assert any("density" in e for e in blocks.validate_theme({"density": "loose"}))
    assert any("不支持" in e for e in blocks.validate_theme({"css": "red"}))
