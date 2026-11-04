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

BLOCK_LESSON = {
    "lesson_key": "D-02-BLOCK",
    "title": "块页 · 发布测试",
    "summary": "JSON 文件写回测试。",
    "kind": "lesson",
    "status": "published",
    "sort_order": 12,
    "outline_codes": ["D-02"],
    "layout": "wide",
    "theme": {"accent": "math", "density": "comfortable"},
    "blocks": [{"type": "markdown", "text": "# 原块页"}],
}


def make_content(tmp_path: Path) -> Path:
    root = tmp_path / "content"
    shutil.copytree(DEMO, root)
    (root / "packs" / "demo" / "lessons" / "d-02-block.json").write_text(
        json.dumps(BLOCK_LESSON, ensure_ascii=False), encoding="utf-8",
    )
    return root


@pytest.fixture()
def edit_env(tmp_path, monkeypatch):
    root = make_content(tmp_path)
    monkeypatch.setenv("KAODIAN_CONTENT_DIR", str(root))
    monkeypatch.setenv("KAODIAN_DATA_DIR", str(tmp_path / "data"))
    monkeypatch.setenv("KAODIAN_DB", str(tmp_path / "test.db"))
    app = create_app(tmp_path / "test.db")
    with TestClient(app) as client:
        yield client, root


def page_by_key(client: TestClient, key: str) -> dict:
    pages = client.get("/api/pages?subject_id=demo&limit=200").json()
    return next(page for page in pages if page["lesson_key"] == key)


def test_page_file_is_synced(edit_env):
    client, _ = edit_env
    page = page_by_key(client, "D-01")
    assert page["file"] == "packs/demo/lessons/d-01-content-pack.md"

    block_page = page_by_key(client, "D-02-BLOCK")
    assert block_page["file"] == "packs/demo/lessons/d-02-block.json"


def test_draft_save_read_delete(edit_env):
    client, _ = edit_env
    page = page_by_key(client, "D-01")

    empty = client.get(f"/api/pages/{page['id']}/draft").json()
    assert empty["draft"] is None
    assert empty["page"]["id"] == page["id"]

    saved = client.put(
        f"/api/pages/{page['id']}/draft", json={"body": "# 草稿正文"},
    )
    assert saved.status_code == 200, saved.text
    draft = saved.json()["draft"]
    assert draft["body"] == "# 草稿正文"
    assert draft["version"] == 1
    assert draft["layout"] == "article"

    read = client.get(f"/api/pages/{page['id']}/draft").json()
    assert read["draft"]["version"] == 1
    assert read["draft"]["body"] == "# 草稿正文"

    dropped = client.delete(f"/api/pages/{page['id']}/draft")
    assert dropped.status_code == 200
    assert dropped.json()["ok"] is True
    assert client.get(f"/api/pages/{page['id']}/draft").json()["draft"] is None


def test_draft_base_version_conflict(edit_env):
    client, _ = edit_env
    page = page_by_key(client, "D-01")
    url = f"/api/pages/{page['id']}/draft"

    assert client.put(url, json={"body": "一", "base_version": 0}).status_code == 200
    conflict = client.put(url, json={"body": "冲突", "base_version": 99})
    assert conflict.status_code == 409

    updated = client.put(url, json={"body": "二", "base_version": 1})
    assert updated.status_code == 200
    assert updated.json()["draft"]["version"] == 2
    assert updated.json()["draft"]["body"] == "二"


def test_draft_rejects_invalid_blocks(edit_env):
    client, _ = edit_env
    page = page_by_key(client, "D-01")
    res = client.put(
        f"/api/pages/{page['id']}/draft",
        json={"blocks": [{"type": "carousel"}]},
    )
    assert res.status_code == 422


def test_publish_markdown_writes_file_validates_and_syncs(edit_env):
    client, root = edit_env
    page = page_by_key(client, "D-01")
    target = root / "packs" / "demo" / "lessons" / "d-01-content-pack.md"
    body = "# 发布后的正文\n\n这是网页编辑写回的内容。\n"

    client.put(
        f"/api/pages/{page['id']}/draft",
        json={"body": body, "layout": "wide", "theme": {"accent": "math"}},
    )
    published = client.post(
        f"/api/pages/{page['id']}/publish", json={"message": "测试发布"},
    )
    assert published.status_code == 200, published.text
    payload = published.json()
    assert payload["file"] == "packs/demo/lessons/d-01-content-pack.md"
    assert payload["committed"] is False
    assert payload["page"]["layout"] == "wide"
    assert payload["page"]["theme"] == {"accent": "math"}

    meta, written = content.parse_frontmatter(target.read_text(encoding="utf-8"))
    assert meta["lesson_key"] == "D-01"
    assert meta["kind"] == "lesson"
    assert meta["layout"] == "wide"
    assert json.loads(meta["theme"]) == {"accent": "math"}
    assert written == body

    detail = client.get(f"/api/pages/{page['id']}").json()
    assert detail["body"] == body
    assert detail["layout"] == "wide"
    assert client.get(f"/api/pages/{page['id']}/draft").json()["draft"] is None

    validated = client.post("/api/content/validate").json()
    assert validated["ok"] is True


def test_publish_block_page_writes_json(edit_env):
    client, root = edit_env
    page = page_by_key(client, "D-02-BLOCK")
    blocks = [
        {"type": "markdown", "text": "# 改过的块页"},
        {"type": "callout", "tone": "info", "text": "提示"},
    ]
    saved = client.put(
        f"/api/pages/{page['id']}/draft",
        json={
            "blocks": blocks,
            "layout": "split",
            "theme": {"accent": "#2f5d8a", "density": "compact"},
        },
    )
    assert saved.status_code == 200, saved.text

    published = client.post(f"/api/pages/{page['id']}/publish", json={})
    assert published.status_code == 200, published.text

    data = json.loads(
        (root / "packs" / "demo" / "lessons" / "d-02-block.json").read_text(encoding="utf-8")
    )
    assert data["lesson_key"] == "D-02-BLOCK"
    assert data["layout"] == "split"
    assert data["theme"] == {"accent": "#2f5d8a", "density": "compact"}
    assert data["blocks"] == blocks
    assert data.get("format") is None
    assert data.get("body") is None

    detail = client.get(f"/api/pages/{page['id']}").json()
    assert detail["format"] == "blocks"
    assert detail["blocks"] == blocks


def test_publish_validation_failure_keeps_file(edit_env):
    client, root = edit_env
    page = page_by_key(client, "D-01")
    target = root / "packs" / "demo" / "lessons" / "d-01-content-pack.md"
    before = target.read_text(encoding="utf-8")

    client.put(
        f"/api/pages/{page['id']}/draft",
        json={"body": "![缺失](/media/demo/missing.svg)\n"},
    )
    res = client.post(f"/api/pages/{page['id']}/publish", json={})
    assert res.status_code == 422
    assert target.read_text(encoding="utf-8") == before
    # 草稿保留，用户可以继续修
    assert client.get(f"/api/pages/{page['id']}/draft").json()["draft"] is not None


def test_publish_requires_draft(edit_env):
    client, _ = edit_env
    page = page_by_key(client, "D-01")
    assert client.post(f"/api/pages/{page['id']}/publish", json={}).status_code == 422


def test_publish_commit_failure_keeps_file_and_db(edit_env):
    client, root = edit_env
    page = page_by_key(client, "D-01")
    target = root / "packs" / "demo" / "lessons" / "d-01-content-pack.md"
    body = "# git 提交失败也要保留文件\n"

    client.put(f"/api/pages/{page['id']}/draft", json={"body": body})
    res = client.post(
        f"/api/pages/{page['id']}/publish",
        json={"message": "测试提交失败", "commit": True},
    )
    assert res.status_code == 500
    assert "文件已写入" in res.text
    assert body in target.read_text(encoding="utf-8")
    assert client.get(f"/api/pages/{page['id']}").json()["body"] == body
    assert client.get(f"/api/pages/{page['id']}/draft").json()["draft"] is None


def test_publish_local_page_updates_db_only(edit_env):
    client, root = edit_env
    created = client.post("/api/pages", json={
        "subject_id": "demo",
        "title": "本地页",
        "body": "原始正文",
        "kind": "note",
    })
    assert created.status_code == 201, created.text
    page = created.json()
    assert page["file"] is None

    before = sorted(path.name for path in (root / "packs" / "demo" / "lessons").iterdir())
    client.put(f"/api/pages/{page['id']}/draft", json={"body": "本地页改过"})
    published = client.post(f"/api/pages/{page['id']}/publish", json={})
    assert published.status_code == 200, published.text
    assert published.json()["file"] is None
    assert published.json()["page"]["body"] == "本地页改过"
    assert sorted(path.name for path in (root / "packs" / "demo" / "lessons").iterdir()) == before


def test_draft_stream_sends_first_event(edit_env):
    client, _ = edit_env
    page = page_by_key(client, "D-01")
    client.put(f"/api/pages/{page['id']}/draft", json={"body": "流式版本"})

    with client.stream("GET", f"/api/pages/{page['id']}/draft/stream") as response:
        assert response.status_code == 200
        assert response.headers["content-type"].startswith("text/event-stream")
        assert response.headers["cache-control"] == "no-cache"
        line = next(response.iter_lines())

    assert line.startswith("data: ")
    payload = json.loads(line[len("data: "):])
    assert payload["version"] == 1
    assert payload["updated_at"]


def test_draft_stream_404_for_missing_page(edit_env):
    client, _ = edit_env
    assert client.get("/api/pages/nope/draft/stream").status_code == 404


def test_v5_database_upgrades_to_v6_without_data_loss(tmp_path, monkeypatch):
    monkeypatch.setenv("KAODIAN_CONTENT_DIR", str(DEMO))
    monkeypatch.setenv("KAODIAN_DATA_DIR", str(tmp_path / "data"))

    path = tmp_path / "v5.db"
    database.init_db(path)
    with database.session(path) as conn:
        before = [tuple(row) for row in conn.execute(
            "SELECT id, title, body FROM page ORDER BY id"
        )]
        conn.execute("DROP TABLE page_draft")

    raw = sqlite3.connect(path)
    try:
        raw.execute("ALTER TABLE page DROP COLUMN file")
        raw.execute("PRAGMA user_version = 5")
        raw.commit()
    finally:
        raw.close()

    database.init_db(path)

    with database.session(path) as conn:
        assert conn.execute("PRAGMA user_version").fetchone()[0] == 6
        after = [tuple(row) for row in conn.execute(
            "SELECT id, title, body FROM page ORDER BY id"
        )]
        assert after == before
        columns = {row["name"] for row in conn.execute("PRAGMA table_info(page)")}
        assert "file" in columns
        tables = {row["name"] for row in conn.execute(
            "SELECT name FROM sqlite_master WHERE type = 'table'"
        )}
        assert "page_draft" in tables
        files = [row["file"] for row in conn.execute("SELECT file FROM page")]
        assert any(value and value.startswith("packs/demo/lessons/") for value in files)

    assert list((tmp_path / "backups").glob("v5.db.bak-v5-*"))
