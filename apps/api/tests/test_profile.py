from __future__ import annotations

import sqlite3
from datetime import date, timedelta
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from apps.api.app import db as database
from apps.api.app.main import create_app

ROOT = Path(__file__).resolve().parents[3]
DEMO = ROOT / "examples" / "demo-content"


@pytest.fixture()
def client(tmp_path, monkeypatch):
    monkeypatch.setenv("KAODIAN_CONTENT_DIR", str(DEMO))
    monkeypatch.setenv("KAODIAN_DATA_DIR", str(tmp_path / "data"))
    monkeypatch.setenv("KAODIAN_DB", str(tmp_path / "test.db"))
    app = create_app(tmp_path / "test.db")
    with TestClient(app) as c:
        yield c


def answer_of(question: dict):
    if question["type"] == "judge":
        return ["true" if question["answer"][0] == "true" else "false"]
    if question["type"] in {"single", "multiple"}:
        return question["answer"]
    if question["type"] == "fill":
        return question["answer"][0]
    return None


def wrong_of(question: dict):
    if question["type"] == "judge":
        return ["maybe"]
    if question["type"] == "fill":
        return "__wrong__"
    return ["__wrong__"]


def test_new_database_has_default_profile(client):
    payload = client.get("/api/profile").json()
    static = payload["static"]
    assert static == {
        "target_exam": None,
        "target_date": None,
        "target_score": None,
        "target_school": None,
        "target_major": None,
        "target_region": None,
        "backup_school": None,
        "backup_major": None,
        "exam_type": None,
        "current_education": None,
        "graduation_year": None,
        "daily_minutes": 30,
        "subjects": ["demo"],
        "study_window": None,
        "constraints": None,
        "strengths": None,
        "weaknesses": None,
        "motivation": None,
        "notes": "",
        "ai_summary": "",
        "preferred_tone": "",
        "preferred_examples": "",
        "updated_by": "user",
    }

    assert payload["completeness"] == 0.25
    assert payload["missing"] == [
        "target_exam", "target_date", "target_score",
        "target_school", "target_major", "motivation",
    ]
    assert [q["field"] for q in payload["next_questions"]] == payload["missing"]
    assert len(payload["next_questions"]) == 6
    assert all(q["question"] for q in payload["next_questions"])

    dynamic = payload["dynamic"]
    assert dynamic["days_to_exam"] is None
    assert dynamic["today_minutes"] == 0
    assert dynamic["streak"] == 0
    assert dynamic["xp"] == 0
    assert dynamic["completed_pages"] == 0
    assert dynamic["answered"] == 0
    assert dynamic["correct"] == 0
    assert dynamic["accuracy"] is None
    assert dynamic["due_reviews"] == 0
    assert dynamic["weak_codes"] == []
    assert dynamic["subjects"] == [{
        "id": "demo",
        "name": "演示科目",
        "short": "演示",
        "color": "#2f5d8a",
        "answered": 0,
        "correct": 0,
        "accuracy": None,
        "seconds": 0,
    }]

    recent = dynamic["recent"]
    assert len(recent) == 7
    assert recent[-1]["date"] == date.today().isoformat()
    assert [item["date"] for item in recent] == sorted(item["date"] for item in recent)
    assert all(item["seconds"] == 0 and item["answered"] == 0 for item in recent)


def test_put_then_get_roundtrip(client):
    body = {
        "target_exam": "2028 广东专升本",
        "target_date": "2028-03-28",
        "target_score": 425,
        "target_school": "广东技术师范大学",
        "target_major": "计算机科学与技术",
        "target_region": "广州",
        "backup_school": "广东白云学院",
        "backup_major": "软件工程",
        "exam_type": "专升本",
        "current_education": "专科",
        "graduation_year": 2028,
        "daily_minutes": 120,
        "subjects": ["demo"],
        "study_window": "工作日晚上 2h + 周末 4h",
        "constraints": "白天上班",
        "strengths": "英语单词记得快",
        "weaknesses": "数学基础弱",
        "motivation": "想换到计算机相关岗位",
        "notes": "数学基础弱",
        "ai_summary": "目标是 2028 广东专升本。",
        "preferred_tone": "直接",
        "preferred_examples": "先具体再一般",
    }
    response = client.put("/api/profile", json=body)
    assert response.status_code == 200, response.text
    assert response.json()["static"]["daily_minutes"] == 120

    fetched = client.get("/api/profile").json()
    assert fetched["static"] == {**body, "updated_by": "user"}
    expected = (date.fromisoformat(body["target_date"]) - date.today()).days
    assert fetched["dynamic"]["days_to_exam"] == expected
    assert fetched["completeness"] == 1
    assert fetched["missing"] == []


def test_partial_update_keeps_other_fields(client):
    client.put("/api/profile", json={"target_exam": "专升本", "daily_minutes": 60})
    client.put("/api/profile", json={"notes": "只改备注"})
    static = client.get("/api/profile").json()["static"]
    assert static["target_exam"] == "专升本"
    assert static["daily_minutes"] == 60
    assert static["notes"] == "只改备注"


def test_v2_fields_partial_update_and_questions(client):
    first = client.put("/api/profile", json={
        "target_school": "广东技术师范大学",
        "target_major": "计算机科学与技术",
        "graduation_year": 2028,
        "study_window": "工作日晚上",
        "source": "agent",
    }).json()
    assert first["static"]["target_school"] == "广东技术师范大学"
    assert first["static"]["target_major"] == "计算机科学与技术"
    assert first["static"]["graduation_year"] == 2028
    assert first["static"]["study_window"] == "工作日晚上"
    assert first["static"]["updated_by"] == "agent"
    # 只补了 2 个必填项：学校 + 专业。
    assert first["completeness"] == 0.5

    second = client.put("/api/profile", json={"weaknesses": "数学基础弱"}).json()
    assert second["static"]["target_school"] == "广东技术师范大学"
    assert second["static"]["weaknesses"] == "数学基础弱"
    assert second["static"]["updated_by"] == "user"
    assert second["completeness"] == 0.5


def test_completeness_and_next_questions_order(client):
    # 补齐全部必填后，完整度为 1，问题转向选填。
    payload = client.put("/api/profile", json={
        "target_exam": "2028 广东专升本",
        "target_date": "2028-03-28",
        "target_score": 425,
        "target_school": "广东技术师范大学",
        "target_major": "计算机科学与技术",
        "daily_minutes": 120,
        "subjects": ["demo"],
        "motivation": "想换到计算机相关岗位",
    }).json()
    assert payload["completeness"] == 1
    assert payload["missing"] == []
    fields = [q["field"] for q in payload["next_questions"]]
    assert len(fields) == 6
    assert fields[0] == "target_region"
    assert "target_exam" not in fields

    # 只缺一个必填项时，它必须排在第一条。
    partial = client.put("/api/profile", json={"target_school": None}).json()
    assert partial["completeness"] == 0.875
    assert partial["missing"] == ["target_school"]
    assert partial["next_questions"][0]["field"] == "target_school"


def test_profile_is_not_overwritten_on_reinit(tmp_path, monkeypatch):
    monkeypatch.setenv("KAODIAN_CONTENT_DIR", str(DEMO))
    monkeypatch.setenv("KAODIAN_DATA_DIR", str(tmp_path / "data"))
    path = tmp_path / "profile.db"
    database.init_db(path)
    with database.session(path) as conn:
        conn.execute("UPDATE profile SET daily_minutes = 90, notes = '保留' WHERE id = 1")
    database.init_db(path)
    with database.session(path) as conn:
        row = conn.execute("SELECT * FROM profile WHERE id = 1").fetchone()
        assert row["daily_minutes"] == 90
        assert row["notes"] == "保留"


@pytest.mark.parametrize("body", [
    {"target_date": "2028/03/28"},
    {"target_date": "2028-13-01"},
    {"target_date": "2028-02-30"},
    {"graduation_year": 1949},
    {"graduation_year": 2101},
    {"daily_minutes": 0},
    {"daily_minutes": 601},
    {"subjects": ["nope"]},
    {"subjects": ["demo", "nope"]},
    {"notes": "x" * 2001},
    {"ai_summary": "x" * 2001},
    {"target_school": "x" * 101},
    {"target_major": "x" * 101},
    {"backup_school": "x" * 101},
    {"backup_major": "x" * 101},
    {"target_region": "x" * 51},
    {"study_window": "x" * 201},
    {"constraints": "x" * 1001},
    {"strengths": "x" * 1001},
    {"weaknesses": "x" * 1001},
    {"motivation": "x" * 1001},
    {"preferred_tone": "x" * 201},
    {"preferred_examples": "x" * 201},
    {"source": "system"},
])
def test_invalid_profile_returns_422(client, body):
    response = client.put("/api/profile", json=body)
    assert response.status_code == 422, response.text
    # 失败不能写库。
    assert client.get("/api/profile").json()["static"]["daily_minutes"] == 30


def test_agent_source_keeps_ai_summary_and_user_save_does_not_clear_it(client):
    agent = client.put("/api/profile", json={
        "ai_summary": "目标是 2028 广东专升本，数学偏弱。",
        "motivation": "想换到计算机相关岗位",
        "source": "agent",
    }).json()
    assert agent["static"]["ai_summary"] == "目标是 2028 广东专升本，数学偏弱。"
    assert agent["static"]["updated_by"] == "agent"

    user = client.put("/api/profile", json={"notes": "用户自己的备注"}).json()
    assert user["static"]["notes"] == "用户自己的备注"
    assert user["static"]["ai_summary"] == "目标是 2028 广东专升本，数学偏弱。"
    assert user["static"]["updated_by"] == "user"

    cleared = client.put("/api/profile", json={"ai_summary": ""}).json()
    assert cleared["static"]["ai_summary"] == ""
    assert cleared["static"]["notes"] == "用户自己的备注"


def test_dynamic_fields_with_activity(client, tmp_path):
    questions = client.get("/api/questions?subject_id=demo&limit=50").json()
    objective = [
        q for q in questions
        if q["type"] in {"single", "multiple", "judge", "fill"}
    ]
    assert len(objective) >= 2

    quiz = client.post("/api/quizzes", json={
        "mode": "practice",
        "question_ids": [q["id"] for q in questions],
    }).json()
    attempt = client.post("/api/attempts", json={"quiz_id": quiz["id"]}).json()

    answers = [
        {"question_id": objective[0]["id"], "response": answer_of(objective[0]), "time_spent": 5},
        {"question_id": objective[1]["id"], "response": wrong_of(objective[1]), "time_spent": 5},
    ]
    submitted = client.post(
        f"/api/attempts/{attempt['id']}/submit",
        json={"active_seconds": 90, "answers": answers},
    )
    assert submitted.status_code == 200, submitted.text

    page = client.post("/api/pages", json={
        "subject_id": "demo",
        "title": "画像测试页",
        "body": "正文",
    }).json()
    assert client.post("/api/activity", json={
        "page_id": page["id"], "seconds": 30, "source": "page",
    }).status_code == 200
    assert client.post(f"/api/pages/{page['id']}/complete").status_code == 200

    # 把复习到期日改到今天，验证 due_reviews 的口径。
    with database.session(tmp_path / "test.db") as conn:
        conn.execute("UPDATE review SET due_date = date('now','localtime')")
        due = conn.execute("SELECT COUNT(*) AS n FROM review").fetchone()["n"]

    dynamic = client.get("/api/profile").json()["dynamic"]
    assert dynamic["answered"] == 2
    assert dynamic["correct"] == 1
    assert dynamic["accuracy"] == 0.5
    assert dynamic["today_minutes"] == 2
    assert dynamic["streak"] == 1
    assert dynamic["xp"] == 12
    assert dynamic["completed_pages"] == 1
    assert dynamic["due_reviews"] == due

    subject = dynamic["subjects"][0]
    assert subject["id"] == "demo"
    assert subject["answered"] == 2
    assert subject["correct"] == 1
    assert subject["accuracy"] == 0.5
    assert subject["seconds"] == 120  # 90 秒作答 + 30 秒阅读

    assert len(dynamic["weak_codes"]) == 1
    assert dynamic["weak_codes"][0]["wrong"] == 1
    assert dynamic["weak_codes"][0]["code"] == objective[1]["outline_code"]
    assert dynamic["weak_codes"][0]["title"]

    assert dynamic["recent"][-1] == {
        "date": date.today().isoformat(),
        "seconds": 120,
        "answered": 2,
    }
    assert dynamic["recent"][-2]["seconds"] == 0


def test_v6_database_migrates_with_backup(tmp_path, monkeypatch):
    monkeypatch.setenv("KAODIAN_CONTENT_DIR", str(DEMO))
    monkeypatch.setenv("KAODIAN_DATA_DIR", str(tmp_path / "data"))

    path = tmp_path / "v6.db"
    database.init_db(path)
    with database.session(path) as conn:
        before = {
            table: conn.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0]
            for table in ("subject", "outline_node", "question", "page")
        }

    raw = sqlite3.connect(path)
    try:
        raw.execute("DROP TABLE profile")
        raw.execute("PRAGMA user_version = 6")
        raw.commit()
    finally:
        raw.close()

    database.init_db(path)

    with database.session(path) as conn:
        assert conn.execute("PRAGMA user_version").fetchone()[0] == database.SCHEMA_VERSION == 8
        for table, count in before.items():
            assert conn.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0] >= count
        tables = {
            row["name"]
            for row in conn.execute("SELECT name FROM sqlite_master WHERE type = 'table'")
        }
        assert "profile" in tables
        row = conn.execute("SELECT * FROM profile WHERE id = 1").fetchone()
        assert row["daily_minutes"] == 30
        assert row["subjects"] == '["demo"]'

    assert list(tmp_path.glob("backups/v6.db.bak-v6-*"))


def test_v7_profile_upgrades_to_v8_keeps_existing_fields(tmp_path, monkeypatch):
    monkeypatch.setenv("KAODIAN_CONTENT_DIR", str(DEMO))
    monkeypatch.setenv("KAODIAN_DATA_DIR", str(tmp_path / "data"))

    path = tmp_path / "v7.db"
    database.init_db(path)

    # 还原成 v7 的 profile 表：没有 v8 新列，user_version=7。
    with database.session(path) as conn:
        conn.execute("DROP TABLE profile")
        conn.execute(
            """CREATE TABLE profile (
                   id                 INTEGER PRIMARY KEY CHECK (id = 1),
                   target_exam        TEXT,
                   target_date        TEXT,
                   target_score       REAL,
                   daily_minutes      INTEGER NOT NULL DEFAULT 30,
                   subjects           TEXT NOT NULL DEFAULT '[]',
                   notes              TEXT NOT NULL DEFAULT '',
                   preferred_tone     TEXT NOT NULL DEFAULT '',
                   preferred_examples TEXT NOT NULL DEFAULT '',
                   updated_at         TEXT
               )"""
        )
        conn.execute(
            """INSERT INTO profile(id, target_exam, target_date, target_score,
                                   daily_minutes, subjects, notes, preferred_tone,
                                   preferred_examples, updated_at)
               VALUES (1, '2028 广东专升本', '2028-03-28', 425, 90, '["demo"]',
                       '旧备注', '直接', '先具体', '2026-01-01T00:00:00')"""
        )
        conn.execute("PRAGMA user_version = 7")

    database.init_db(path)

    with database.session(path) as conn:
        assert conn.execute("PRAGMA user_version").fetchone()[0] == 8
        row = conn.execute("SELECT * FROM profile WHERE id = 1").fetchone()
        # 旧字段原样保留。
        assert row["target_exam"] == "2028 广东专升本"
        assert row["target_date"] == "2028-03-28"
        assert row["target_score"] == 425
        assert row["daily_minutes"] == 90
        assert row["subjects"] == '["demo"]'
        assert row["notes"] == "旧备注"
        assert row["preferred_tone"] == "直接"
        assert row["preferred_examples"] == "先具体"
        # 新列存在且默认值正确。
        assert row["target_school"] is None
        assert row["graduation_year"] is None
        assert row["ai_summary"] is None
        assert row["updated_by"] == "user"

    assert list(tmp_path.glob("backups/v7.db.bak-v7-*"))
