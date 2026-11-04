from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

from apps.api.app import content, paths

ROOT = Path(__file__).resolve().parents[3]
DEMO = ROOT / "examples" / "demo-content"


def test_parse_frontmatter_basic():
    text = (
        "---\n"
        'title: "第一课"\n'
        "sort_order: 12\n"
        'kind: "lesson"\n'
        "outline_codes: [\"D-01\", \"D-02\"]\n"
        "status: published\n"
        "draft: false\n"
        "---\n\n"
        "# 正文\n"
    )
    meta, body = content.parse_frontmatter(text)
    assert meta == {
        "title": "第一课",
        "sort_order": 12,
        "kind": "lesson",
        "outline_codes": ["D-01", "D-02"],
        "status": "published",
        "draft": False,
    }
    assert body == "# 正文\n"


def test_parse_frontmatter_rejects_nested():
    with pytest.raises(content.PackError):
        content.parse_frontmatter("---\ntags:\n  - a\n---\n")
    with pytest.raises(content.PackError):
        content.parse_frontmatter("---\ntitle: x\n")


def test_demo_pack_validates(monkeypatch):
    monkeypatch.setenv("KAODIAN_CONTENT_DIR", str(DEMO))
    packs = content.load_all()
    assert [pack["id"] for pack in packs] == ["demo"]
    assert content.validate_pack(packs[0]) == []
    assert packs[0]["assets"] == ["demo.svg"]


def test_validate_pack_reports_duplicate_key_and_missing_asset(tmp_path, monkeypatch):
    root = tmp_path / "content"
    shutil.copytree(DEMO, root)
    lesson_dir = root / "packs" / "demo" / "lessons"
    (lesson_dir / "99-重复.md").write_text(
        "---\n"
        'lesson_key: "D-01"\n'
        'title: "重复 key"\n'
        'kind: "lesson"\n'
        'status: "published"\n'
        "sort_order: 99\n"
        'outline_codes: ["D-99"]\n'
        "---\n\n"
        "![缺失](/media/demo/missing.svg)\n",
        encoding="utf-8",
    )
    monkeypatch.setenv("KAODIAN_CONTENT_DIR", str(root))
    pack = content.load_all()[0]
    errors = content.validate_pack(pack)
    assert any("lesson_key 重复" in error for error in errors)
    assert any("D-99" in error for error in errors)
    assert any("missing.svg" in error for error in errors)


def test_paths_env_overrides_and_data_dir(tmp_path, monkeypatch):
    target = tmp_path / "content"
    target.mkdir()
    data = tmp_path / "runtime"
    monkeypatch.setenv("KAODIAN_CONTENT_DIR", str(target))
    monkeypatch.setenv("KAODIAN_DATA_DIR", str(data))
    monkeypatch.delenv("KAODIAN_DB", raising=False)
    assert paths.content_dir() == target
    assert paths.data_dir() == data
    assert data.is_dir()
    assert paths.db_path() == data / "api" / "kaodian.db"
    assert paths.config_file("registry.json") == target / "registry.json"


def _run_cli(*args: str, content_dir: Path = DEMO) -> subprocess.CompletedProcess:
    env = os.environ.copy()
    env["KAODIAN_CONTENT_DIR"] = str(content_dir)
    env["KAODIAN_DATA_DIR"] = str(ROOT / "runtime-test")
    env["PYTHONPATH"] = str(ROOT)
    return subprocess.run(
        [sys.executable, "-m", "apps.cli", *args],
        cwd=ROOT,
        env=env,
        capture_output=True,
        text=True,
    )


def test_cli_content_validate_and_list():
    validated = _run_cli("content", "validate", "--json")
    assert validated.returncode == 0, validated.stderr
    payload = json.loads(validated.stdout)
    assert payload["ok"] is True
    assert payload["packs"][0]["id"] == "demo"

    listed = _run_cli("content", "list", "--json")
    assert listed.returncode == 0, listed.stderr
    body = json.loads(listed.stdout)
    assert body["ok"] is True
    assert body["packs"][0]["questions"] == 3
    assert body["packs"][0]["lessons"] == 2


def test_cli_content_validate_exits_nonzero_on_broken_pack(tmp_path):
    root = tmp_path / "content"
    shutil.copytree(DEMO, root)
    (root / "packs" / "demo" / "pack.json").write_text(
        json.dumps({
            "id": "demo", "name": "坏包", "version": "1.0.0", "schema": 99,
            "subject": {"id": "demo", "name": "坏包", "short": "坏"},
        }, ensure_ascii=False),
        encoding="utf-8",
    )
    result = _run_cli("content", "validate", "--json", content_dir=root)
    assert result.returncode == 1
    payload = json.loads(result.stdout)
    assert payload["ok"] is False
    assert any("schema" in error for error in payload["packs"][0]["errors"])
