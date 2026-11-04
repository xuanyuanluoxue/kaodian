from __future__ import annotations

import json
import shutil
import sqlite3
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from apps.api.app import content
from apps.api.app import db as database
from apps.api.app.main import create_app

ROOT = Path(__file__).resolve().parents[3]
DEMO = ROOT / "examples" / "demo-content"

BLOCK_PAGE = {
    "lesson_key": "D-02-BLOCK",
    "title": "块页 · 版式演示",
    "summary": "JSON 块页同步与接口返回。",
    "kind": "lesson",
    "status": "published",
    "sort_order": 11,
    "outline_codes": ["D-02"],
    "layout": "wide",
    "theme": {"accent": "math", "density": "comfortable"},
    "blocks": [
        {"type": "markdown", "text": "# 块页"},
        {"type": "callout", "tone": "info", "title": "提示", "text": "内容"},
        {"type": "columns", "cols": [
            [{"type": "markdown", "text": "左栏"}],
            [{"type": "image", "url": "/media/demo/demo.svg", "alt": "演示"}],
        ]},
        {"type": "sandbox", "html": "<p>实验</p>", "height": 420},
    ],
}


def make_content(tmp_path: Path) -> Path:
    root = tmp_path / "content"
    shutil.copytree(DEMO, root)
    lessons = root / "packs" / "demo" / "lessons"
    (lessons / "d-02-block.json").write_text(
        json.dumps(BLOCK_PAGE, ensure_ascii=False), encoding="utf-8",
    )
    return root


@pytest.fixture()
def block_client(tmp_path, monkeypatch):
    root = make_content(tmp_path)
    monkeypatch.setenv("KAODIAN_CONTENT_DIR", str(root))
    monkeypatch.setenv("KAODIAN_DATA_DIR", str(tmp_path / "data"))
    monkeypatch.setenv("KAODIAN_DB", str(tmp_path / "test.db"))
    app = create_app(tmp_path / "test.db")
    with TestClient(app) as client:
        yield client


def test_json_block_page_loads_and_validates(monkeypatch, tmp_path):
    root = make_content(tmp_path)
    monkeypatch.setenv("KAODIAN_CONTENT_DIR", str(root))
    pack = content.load_all()[0]
    assert content.validate_pack(pack) == []
    lesson = next(item for item in pack["lessons"] if item.get("lesson_key") == "D-02-BLOCK")
    assert lesson["format"] == "blocks"
    assert lesson["layout"] == "wide"
    assert lesson["theme"] == {"accent": "math", "density": "comfortable"}
    assert lesson["blocks"] == BLOCK_PAGE["blocks"]


def test_sync_keeps_markdown_pages_and_returns_block_fields(block_client):
    pages = block_client.get("/api/pages?subject_id=demo&limit=200").json()
    assert len(pages) == 3
    markdown_pages = [page for page in pages if page["format"] == "markdown"]
    assert len(markdown_pages) == 2
    for page in markdown_pages:
        assert page["blocks"] is None
        assert page["layout"] == "article"
        assert page["theme"] is None
        detail = block_client.get(f"/api/pages/{page['id']}").json()
        assert detail["body"]
        assert detail["format"] == "markdown"

    block_page = next(page for page in pages if page["format"] == "blocks")
    assert block_page["lesson_key"] == "D-02-BLOCK"
    assert block_page["layout"] == "wide"
    assert block_page["theme"] == {"accent": "math", "density": "comfortable"}
    detail = block_client.get(f"/api/pages/{block_page['id']}").json()
    assert detail["blocks"] == BLOCK_PAGE["blocks"]
    assert detail["format"] == "blocks"


def test_page_api_accepts_and_validates_blocks(block_client):
    created = block_client.post("/api/pages", json={
        "subject_id": "demo",
        "title": "API 块页",
        "blocks": [{"type": "markdown", "text": "正文"}],
        "layout": "split",
        "theme": {"accent": "#2f5d8a"},
    })
    assert created.status_code == 201, created.text
    page = created.json()
    assert page["format"] == "blocks"
    assert page["blocks"] == [{"type": "markdown", "text": "正文"}]
    assert page["layout"] == "split"
    assert page["theme"] == {"accent": "#2f5d8a"}
    assert page["body"] == ""

    patched = block_client.patch(f"/api/pages/{page['id']}", json={
        "blocks": [{"type": "callout", "tone": "warn", "text": "改过"}],
    }).json()
    assert patched["format"] == "blocks"
    assert patched["blocks"][0]["type"] == "callout"

    unknown = block_client.patch(f"/api/pages/{page['id']}", json={
        "blocks": [{"type": "carousel"}],
    })
    assert unknown.status_code == 422

    bad_columns = block_client.post("/api/pages", json={
        "subject_id": "demo", "title": "坏块页",
        "blocks": [{"type": "columns", "cols": [[{"type": "markdown", "text": "一"}]]}],
    })
    assert bad_columns.status_code == 422

    back_to_markdown = block_client.patch(f"/api/pages/{page['id']}", json={
        "blocks": None,
    }).json()
    assert back_to_markdown["format"] == "markdown"
    assert back_to_markdown["blocks"] is None


def test_export_import_keeps_block_fields(block_client, tmp_path, monkeypatch):
    payload = block_client.get("/api/export?scope=content").json()
    page = next(item for item in payload["data"]["pages"]
                if item.get("lesson_key") == "D-02-BLOCK")
    assert page["format"] == "blocks"
    assert page["layout"] == "wide"
    assert page["theme"] == {"accent": "math", "density": "comfortable"}
    assert page["blocks"] == BLOCK_PAGE["blocks"]

    empty = tmp_path / "empty-content"
    empty.mkdir()
    (empty / "registry.json").write_text(
        json.dumps({"schema": 1, "packs": []}), encoding="utf-8",
    )
    monkeypatch.setenv("KAODIAN_CONTENT_DIR", str(empty))
    monkeypatch.setenv("KAODIAN_DATA_DIR", str(tmp_path / "fresh-data"))
    fresh = create_app(tmp_path / "fresh.db")
    with TestClient(fresh) as client:
        imported = client.post("/api/import", json={
            "format": payload["format"],
            "version": payload["version"],
            "scope": "content",
            "overwrite": False,
            "data": payload["data"],
        })
        assert imported.status_code == 200, imported.text
        restored = client.get(f"/api/pages/{page['id']}").json()
        assert restored["format"] == "blocks"
        assert restored["layout"] == "wide"
        assert restored["theme"] == {"accent": "math", "density": "comfortable"}
        assert restored["blocks"] == BLOCK_PAGE["blocks"]


def test_v4_database_upgrades_to_v5_without_data_loss(tmp_path, monkeypatch):
    monkeypatch.setenv("KAODIAN_CONTENT_DIR", str(DEMO))
    monkeypatch.setenv("KAODIAN_DATA_DIR", str(tmp_path / "data"))

    path = tmp_path / "v4.db"
    database.init_db(path)
    with database.session(path) as conn:
        before = conn.execute("SELECT COUNT(*) FROM page").fetchone()[0]

    raw = sqlite3.connect(path)
    try:
        for column in ("blocks", "layout", "theme", "format"):
            raw.execute(f"ALTER TABLE page DROP COLUMN {column}")
        raw.execute("PRAGMA user_version = 4")
        raw.commit()
    finally:
        raw.close()

    database.init_db(path)

    with database.session(path) as conn:
        assert conn.execute("PRAGMA user_version").fetchone()[0] == database.SCHEMA_VERSION
        assert conn.execute("SELECT COUNT(*) FROM page").fetchone()[0] == before
        rows = conn.execute(
            "SELECT title, body, layout, theme, format, blocks FROM page"
        ).fetchall()
        assert all(row["body"] for row in rows)
        assert all(row["layout"] == "article" for row in rows)
        assert all(row["theme"] is None for row in rows)
        assert all(row["format"] == "markdown" for row in rows)
        assert all(row["blocks"] is None for row in rows)

    assert list((tmp_path / "backups").glob("v4.db.bak-v4-*"))


def test_sandbox_route_serves_isolated_html(block_client):
    client = block_client
    page = client.post("/api/pages", json={
        "subject_id": "demo",
        "title": "沙箱验证",
        "kind": "note",
        "status": "published",
        "blocks": [
            {"type": "markdown", "text": "正文"},
            {"type": "sandbox", "html": "<p id='x'>ok</p><script>1+1</script>", "height": 300},
        ],
    })
    assert page.status_code == 201, page.text
    pid = page.json()["id"]

    res = client.get(f"/sandbox/{pid}/1")
    assert res.status_code == 200
    assert "unsafe-inline" in res.headers["content-security-policy"]
    assert res.headers["x-frame-options"] == "SAMEORIGIN"
    assert "<p id='x'>ok</p>" in res.text

    assert client.get(f"/sandbox/{pid}/0").status_code == 404
    assert client.get(f"/sandbox/{pid}/9").status_code == 404
