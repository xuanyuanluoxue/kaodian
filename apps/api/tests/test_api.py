from __future__ import annotations

import sqlite3

import pytest
from fastapi.testclient import TestClient

from apps.api.app.main import create_app


@pytest.fixture()
def client(tmp_path):
    app = create_app(tmp_path / "test.db")
    with TestClient(app) as c:
        yield c


def answer_of(q: dict):
    if q["type"] == "judge":
        return [
            "true" if q["answer"][0] == "true" else "false"
        ]
    if q["type"] in {"single", "multiple"}:
        return q["answer"]
    if q["type"] == "fill":
        return q["answer"][0]
    return None


def test_seed(client):
    subjects = client.get("/api/subjects").json()
    assert {s["id"] for s in subjects} == {"computer", "math", "english", "politics"}
    computer = next(s for s in subjects if s["id"] == "computer")
    assert computer["node_count"] == 50
    assert computer["question_count"] >= 20
    assert len(client.get("/api/outline?subject_id=math").json()) == 54


def test_validate_rejects_unknown_code(client):
    bad = {
        "outline_code": "C-99",
        "type": "single",
        "stem": "这是一道测试题，选项至少两个。",
        "options": ["甲", "乙"],
        "answer": ["A"],
        "explanation": "这是解析，长度足够通过校验。",
        "difficulty": 2,
        "score": 3,
    }
    r = client.post("/api/questions/validate", json={"questions": [bad]})
    assert r.status_code == 200
    assert r.json()["ok"] is False
    assert any("不在大纲里" in e for e in r.json()["results"][0]["errors"])


def test_batch_create_and_dedupe(client):
    item = {
        "outline_code": "C-02",
        "type": "single",
        "stem": "测试标识符规则：下列哪个是合法标识符？",
        "options": ["1a", "a1", "int", "-a"],
        "answer": ["B"],
        "explanation": "标识符不能以数字开头，也不能是关键字，所以 a1 合法。",
        "difficulty": 2,
        "score": 3,
    }
    first = client.post("/api/questions/batch", json={"questions": [item]})
    assert first.status_code == 201
    assert first.json()["created"] == 1
    second = client.post("/api/questions/batch", json={"questions": [item]})
    assert second.status_code == 201
    assert second.json()["created"] == 0
    assert second.json()["skipped"] == 1


def test_practice_flow(client):
    quiz = client.post(
        "/api/quizzes",
        json={
            "mode": "practice",
            "count": 2,
            "filters": {"subject_id": "computer", "codes": ["C-08"], "types": ["single"]},
        },
    ).json()
    assert quiz["question_count"] == 2
    assert all("answer" in q for q in quiz["questions"])

    attempt = client.post("/api/attempts", json={"quiz_id": quiz["id"]}).json()
    answers = [
        {"question_id": q["id"], "response": answer_of(q), "time_spent": 10}
        for q in quiz["questions"]
    ]
    result = client.post(
        f"/api/attempts/{attempt['id']}/submit",
        json={"active_seconds": 60, "answers": answers},
    ).json()
    assert result["status"] == "submitted"
    assert result["score"] == 6
    assert len(result["results"]) == 2
    assert result["weak"] == []

    fetched = client.get(f"/api/attempts/{attempt['id']}").json()
    assert len(fetched["results"]) == 2


def test_exam_hides_answers(client):
    quiz = client.post(
        "/api/quizzes",
        json={"mode": "exam", "count": 2, "filters": {"subject_id": "computer", "types": ["single"]}},
    ).json()
    assert quiz["time_limit"] == 180
    assert all("answer" not in q for q in quiz["questions"])
    attempt = client.post("/api/attempts", json={"quiz_id": quiz["id"]}).json()
    assert all("answer" not in q for q in attempt["quiz"]["questions"])


def test_subjective_self_grade(client):
    q = client.get("/api/questions?code=C-11&limit=50").json()
    short = next(x for x in q if x["type"] == "short")
    quiz = client.post(
        "/api/quizzes",
        json={"mode": "practice", "question_ids": [short["id"]]},
    ).json()
    attempt = client.post("/api/attempts", json={"quiz_id": quiz["id"]}).json()
    result = client.post(
        f"/api/attempts/{attempt['id']}/submit",
        json={
            "active_seconds": 120,
            "answers": [{"question_id": short["id"], "self_grade": [0, 1, 2], "time_spent": 100}],
        },
    ).json()
    assert result["score"] == 10
    assert result["results"][0]["correct"] is True


def test_review_mastery_after_three_correct(client, tmp_path):
    q = client.get("/api/questions?code=C-08&type=fill&limit=1").json()[0]
    quiz = client.post("/api/quizzes", json={"mode": "practice", "question_ids": [q["id"]]}).json()
    for _ in range(3):
        attempt = client.post("/api/attempts", json={"quiz_id": quiz["id"]}).json()
        client.post(
            f"/api/attempts/{attempt['id']}/submit",
            json={
                "active_seconds": 20,
                "answers": [{"question_id": q["id"], "response": q["answer"][0], "time_spent": 15}],
            },
        )
    db = sqlite3.connect(tmp_path / "test.db")
    db.row_factory = sqlite3.Row
    row = db.execute("SELECT * FROM review WHERE question_id = ?", (q["id"],)).fetchone()
    db.close()
    assert row is not None
    assert row["mastery"] == 1
    assert row["streak"] == 0
    assert row["interval_days"] == 1