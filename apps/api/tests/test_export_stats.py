from __future__ import annotations

import copy
from datetime import date

import pytest
from fastapi.testclient import TestClient

from apps.api.app.main import create_app

CONTENT_KEYS = [
    "subjects", "outline", "groups", "questions", "question_outline", "pages",
]
PROGRESS_KEYS = ["page_progress", "review", "study_time"]


@pytest.fixture()
def client(tmp_path):
    app = create_app(tmp_path / "test.db")
    with TestClient(app) as c:
        yield c


def make_page(client: TestClient, subject_id: str, title: str,
              outline_codes: list[str] | None = None) -> dict:
    r = client.post("/api/pages", json={
        "subject_id": subject_id,
        "title": title,
        "body": f"# {title}\n\n正文内容。",
        "outline_codes": outline_codes or [],
    })
    assert r.status_code == 201, r.text
    return r.json()


def fresh_client(tmp_path, monkeypatch) -> TestClient:
    """没有 config 内容的空库，用来验证导入确实写入了数据。"""
    config = tmp_path / "empty-config"
    (config / "subjects").mkdir(parents=True)
    monkeypatch.setenv("KAODIAN_CONFIG_DIR", str(config))
    return TestClient(create_app(tmp_path / "fresh.db"))


def import_body(payload: dict, overwrite: bool = False,
                data: dict | None = None) -> dict:
    return {
        "format": payload["format"],
        "version": payload["version"],
        "scope": payload["scope"],
        "overwrite": overwrite,
        "data": payload["data"] if data is None else data,
    }


def answer_of(question: dict):
    if question["type"] == "judge":
        return ["true" if question["answer"][0] == "true" else "false"]
    if question["type"] in {"single", "multiple"}:
        return question["answer"]
    if question["type"] == "fill":
        return question["answer"][0]
    return None


def test_export_content_import_into_empty_db(client, tmp_path, monkeypatch):
    make_page(client, "computer", "导出测试页", ["C-01"])
    r = client.get("/api/export?scope=content")
    assert r.status_code == 200
    assert "kaodian-export-" in r.headers["content-disposition"]
    payload = r.json()
    assert payload["format"] == "kaodian-export"
    assert payload["version"] == 3
    assert payload["scope"] == "content"
    assert set(payload["data"]) == set(CONTENT_KEYS)
    assert payload["data"]["questions"]
    # 本地备份不脱敏，题目必须带答案与解析。
    question = payload["data"]["questions"][0]
    assert {"answer", "explanation", "reference_answer", "rubric"} <= set(question)

    expected = {
        key: len(payload["data"][key])
        for key in CONTENT_KEYS
        if key != "question_outline"
    }
    with fresh_client(tmp_path, monkeypatch) as fresh:
        imported = fresh.post("/api/import", json=import_body(payload))
        assert imported.status_code == 200, imported.text
        result = imported.json()["imported"]
        for key, count in expected.items():
            assert result[key] == count

        exported = fresh.get("/api/export?scope=content").json()["data"]
        for key, count in expected.items():
            assert len(exported[key]) == count, key

        # 题目答案、页面正文与题目多考点关联都完整落库。
        ids = {q["id"] for q in exported["questions"]}
        assert {q["id"] for q in payload["data"]["questions"]} == ids
        assert all((q.get("explanation") or "") ==
                   next(x["explanation"] for x in payload["data"]["questions"]
                        if x["id"] == q["id"])
                   for q in exported["questions"])
        page = next(p for p in exported["pages"] if p["lesson_key"] is None)
        assert page["body"].startswith("# 导出测试页")


def test_repeat_import_without_overwrite_skips_everything(client, tmp_path, monkeypatch):
    payload = client.get("/api/export?scope=content").json()
    expected = {key: len(payload["data"][key]) for key in CONTENT_KEYS}

    with fresh_client(tmp_path, monkeypatch) as fresh:
        first = fresh.post("/api/import", json=import_body(payload)).json()
        second = fresh.post("/api/import", json=import_body(payload)).json()

        assert second["imported"] == {key: 0 for key in CONTENT_KEYS}
        assert second["skipped"] == first["imported"]

        exported = fresh.get("/api/export?scope=content").json()["data"]
        for key, count in expected.items():
            assert len(exported[key]) == count, key


def test_overwrite_restores_modified_page(client, tmp_path, monkeypatch):
    page = make_page(client, "computer", "原始标题", ["C-01"])
    payload = client.get("/api/export?scope=content").json()

    with fresh_client(tmp_path, monkeypatch) as fresh:
        assert fresh.post("/api/import", json=import_body(payload)).status_code == 200
        changed = fresh.patch(f"/api/pages/{page['id']}", json={"title": "被改掉了"})
        assert changed.status_code == 200
        assert changed.json()["title"] == "被改掉了"

        restored = fresh.post(
            "/api/import", json=import_body(payload, overwrite=True)
        )
        assert restored.status_code == 200
        assert restored.json()["imported"]["pages"] == 1
        assert fresh.get(f"/api/pages/{page['id']}").json()["title"] == "原始标题"


def test_import_rejects_newer_version(client):
    payload = client.get("/api/export?scope=content").json()
    body = import_body(payload, data={"subjects": []})
    body["version"] = 99
    r = client.post("/api/import", json=body)
    assert r.status_code == 422
    assert "高于当前支持" in r.text

    body["version"] = 3
    body["format"] = "something-else"
    assert client.post("/api/import", json=body).status_code == 422


def test_stats_subjects_heatmap_and_types(client):
    created = client.post("/api/questions/batch", json={"questions": [
        {
            "outline_code": "C-01", "type": "single",
            "stem": "统计测试：计算机科目单选题，选出正确答案。",
            "options": ["甲", "乙", "丙", "丁"], "answer": ["A"],
            "explanation": "测试用解析，长度足够通过校验。",
            "score": 2,
        },
        {
            "outline_code": "M-01", "type": "single",
            "stem": "统计测试：数学科目单选题，选出正确答案。",
            "options": ["甲", "乙", "丙", "丁"], "answer": ["B"],
            "explanation": "测试用解析，长度足够通过校验。",
            "score": 2,
        },
    ]}).json()
    assert created["created"] == 2
    assert client.post("/api/questions/review", json={
        "ids": created["ids"], "decision": "approve",
    }).status_code == 200

    ids = created["ids"]
    expected = {}
    for qid, subject_id, seconds in ((ids[0], "computer", 60), (ids[1], "math", 90)):
        quiz = client.post("/api/quizzes", json={
            "mode": "practice", "question_ids": [qid],
        }).json()
        question = quiz["questions"][0]
        attempt = client.post("/api/attempts", json={"quiz_id": quiz["id"]}).json()
        result = client.post(
            f"/api/attempts/{attempt['id']}/submit",
            json={
                "active_seconds": seconds,
                "answers": [{
                    "question_id": question["id"],
                    "response": answer_of(question),
                    "time_spent": seconds,
                }],
            },
        )
        assert result.status_code == 200, result.text
        expected[subject_id] = seconds

    computer_page = make_page(client, "computer", "统计页 · 计算机")
    math_page = make_page(client, "math", "统计页 · 数学")
    client.post("/api/activity", json={
        "page_id": computer_page["id"], "seconds": 120, "source": "page",
    })
    client.post("/api/activity", json={
        "page_id": math_page["id"], "seconds": 30, "source": "page",
    })

    subjects = {s["subject_id"]: s for s in
                client.get("/api/stats/subjects?days=30").json()}
    assert subjects["computer"]["answered"] == 1
    assert subjects["computer"]["correct"] == 1
    assert subjects["computer"]["attempts"] == 1
    assert subjects["computer"]["seconds"] == expected["computer"] + 120
    assert subjects["math"]["answered"] == 1
    assert subjects["math"]["correct"] == 1
    assert subjects["math"]["attempts"] == 1
    assert subjects["math"]["seconds"] == expected["math"] + 30
    # 没有作答的科目也要返回 0，方便前端画完整列表。
    assert subjects["english"]["answered"] == 0
    assert subjects["english"]["seconds"] == 0

    heatmap = client.get("/api/stats/heatmap?days=90").json()
    assert len(heatmap) == 90
    assert heatmap[-1]["date"] == date.today().isoformat()
    assert heatmap[-1]["answered"] == 2
    assert heatmap[-1]["seconds"] == 300
    assert [x["date"] for x in heatmap] == sorted(x["date"] for x in heatmap)

    types = {t["type"]: t for t in client.get("/api/stats/types?days=30").json()}
    assert types["single"]["answered"] == 2
    assert types["single"]["correct"] == 2
    assert types["single"]["label"] == "单选"

    today = client.get("/api/stats/today").json()
    assert today["answered"] == 2
    assert today["correct"] == 2


def test_import_rejects_missing_foreign_key(client, tmp_path, monkeypatch):
    payload = client.get("/api/export?scope=content").json()
    data = copy.deepcopy(payload["data"])
    data["questions"][0]["outline_code"] = "NOPE-99"

    with fresh_client(tmp_path, monkeypatch) as fresh:
        r = fresh.post("/api/import", json=import_body(payload, data=data))
        assert r.status_code == 422
        assert "outline_code" in r.text and "NOPE-99" in r.text
        # 整个导入回滚：不能留下半份科目。
        assert fresh.get("/api/subjects").json() == []


def test_export_progress_scope_only_progress_tables(client):
    make_page(client, "computer", "进度导出页")
    client.post("/api/activity", json={
        "page_id": "p_anything", "seconds": 30, "source": "page",
    })
    payload = client.get("/api/export?scope=progress").json()
    assert set(payload["data"]) == set(PROGRESS_KEYS)
    assert payload["data"]["study_time"]

    all_payload = client.get("/api/export?scope=all").json()
    assert set(all_payload["data"]) == set(CONTENT_KEYS + PROGRESS_KEYS)
