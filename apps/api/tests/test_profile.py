from __future__ import annotations

import json
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
        "targets": [],
        "exam_total": 500,
        "target_school": None,
        "target_major": None,
        "target_region": None,
        "backup_school": None,
        "backup_major": None,
        "exam_type": None,
        "current_education": None,
        "graduation_year": None,
        "hard_lines": None,
        "daily_minutes": 30,
        "subjects": ["demo"],
        "subject_targets": {},
        "study_window": None,
        "constraints": None,
        "strengths": None,
        "weaknesses": None,
        "motivation": None,
        "notes": "",
        "ai_summary": "",
        "preferred_tone": "",
        "preferred_examples": "",
        "plan_phase": None,
        "phase_start": None,
        "phase_end": None,
        "phase_daily_minutes": None,
        "phase_goal": None,
        "total_hours": None,
        "updated_by": "user",
    }

    assert payload["completeness"] == 0.25
    assert payload["missing"] == [
        "target_exam", "target_date", "target_score",
        "targets", "target_major", "motivation",
    ]
    assert [q["field"] for q in payload["next_questions"]] == payload["missing"]
    assert len(payload["next_questions"]) == 6
    assert all(q["question"] for q in payload["next_questions"])
    assert payload["phase"] is None

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
        "targets": [
            {"tier": "冲", "school": "广东技术师范大学", "major": "计算机科学与技术",
             "score": 424, "rank": 120, "location": "广州", "note": ""},
            {"tier": "兜底", "school": "广东白云学院", "major": "软件工程",
             "score": 300, "rank": 3000, "location": "广州", "note": ""},
        ],
        "exam_total": 500,
        "subject_targets": {"demo": 190},
        "hard_lines": "三科 105 / 专业综合课 60",
        "plan_phase": "P1",
        "phase_start": "2026-11-01",
        "phase_end": "2027-03-31",
        "phase_daily_minutes": 120,
        "phase_goal": "打基础",
        "total_hours": 800,
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
    # 已有 daily_minutes/subjects，再补志愿表（兼容首选院校）+ 专业。
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

    # 只缺一个必填项时，它必须排在第一条；target_school 被清除后 targets 变空。
    partial = client.put("/api/profile", json={"target_school": None}).json()
    assert partial["completeness"] == 0.875
    assert partial["missing"] == ["targets"]
    assert partial["next_questions"][0]["field"] == "targets"


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
        assert conn.execute("PRAGMA user_version").fetchone()[0] == database.SCHEMA_VERSION == 9
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


def test_v7_profile_upgrades_to_v9_keeps_existing_fields(tmp_path, monkeypatch):
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
        assert conn.execute("PRAGMA user_version").fetchone()[0] == 9
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


# ---------------------------------------------------------------- profile v3

TARGETS = [
    {"tier": "冲", "school": "韩山师范学院", "major": "计算机科学与技术",
     "score": 424, "rank": 120, "location": "珠海（协同培养）", "note": ""},
    {"tier": "稳", "school": "嘉应学院", "major": "计算机科学与技术",
     "score": 413, "rank": 200, "location": "梅州", "note": ""},
    {"tier": "保", "school": "惠州学院", "major": "软件工程",
     "score": 404, "rank": 308, "location": "惠州（联合培养）", "note": ""},
    {"tier": "兜底", "school": "广州科技职业技术大学", "major": "计算机应用工程",
     "score": 182, "rank": 7599, "location": "广州（民办）", "note": ""},
]


def test_targets_write_syncs_schools_and_explicit_values_win(client):
    payload = client.put("/api/profile", json={"targets": TARGETS}).json()
    static = payload["static"]
    assert static["targets"] == TARGETS
    assert static["target_school"] == "韩山师范学院"
    assert static["backup_school"] == "广州科技职业技术大学"
    assert static["backup_major"] == "计算机应用工程"

    # 同一次请求显式传 target_school / backup_school 时以显式值为准。
    overridden = client.put("/api/profile", json={
        "targets": TARGETS,
        "target_school": "自定义首选",
        "backup_school": "自定义兜底",
    }).json()
    assert overridden["static"]["target_school"] == "自定义首选"
    assert overridden["static"]["backup_school"] == "自定义兜底"

    # 没有「兜底」档时，backup 取最后一条。
    no_backup = client.put("/api/profile", json={"targets": TARGETS[:3]}).json()["static"]
    assert no_backup["backup_school"] == "惠州学院"
    assert no_backup["backup_major"] == "软件工程"


def test_targets_completeness_and_clear(client):
    # v2 数据兼容：只有首选院校、没有志愿表，也算填了 targets。
    payload = client.put("/api/profile", json={"target_school": "广东技术师范大学"}).json()
    assert "targets" not in payload["missing"]
    assert payload["missing"] == [
        "target_exam", "target_date", "target_score", "target_major", "motivation",
    ]

    cleared = client.put("/api/profile", json={"targets": None}).json()
    assert cleared["static"]["targets"] == []
    assert "targets" not in cleared["missing"]  # target_school 还有值


def test_empty_targets_clears_derived_schools(client):
    client.put("/api/profile", json={"targets": TARGETS})
    payload = client.put("/api/profile", json={"targets": []}).json()["static"]
    assert payload["targets"] == []
    assert payload["target_school"] is None
    assert payload["backup_school"] is None
    assert payload["backup_major"] is None

    # 显式传值仍然优先于清空。
    explicit = client.put("/api/profile", json={
        "targets": [], "target_school": "自定义首选",
    }).json()["static"]
    assert explicit["target_school"] == "自定义首选"


@pytest.mark.parametrize("body", [
    {"targets": [{"tier": "冲", "school": ""}]},
    {"targets": [{"school": "韩山师范学院"}]},
    {"targets": [{"tier": "梦", "school": "韩山师范学院"}]},
    {"targets": [{"tier": "冲", "school": "x" * 101}]},
    {"targets": [{"tier": "冲", "school": "A", "major": "x" * 101}]},
    {"targets": [{"tier": "冲", "school": "A", "location": "x" * 101}]},
    {"targets": [{"tier": "冲", "school": "A", "note": "x" * 201}]},
    {"targets": [{"tier": "冲", "school": "A", "score": -1}]},
    {"targets": [{"tier": "冲", "school": "A", "score": 501}]},
    {"targets": [{"tier": "冲", "school": "A", "rank": -1}]},
    {"targets": [{"tier": "冲", "school": "A", "rank": 1000001}]},
    {"targets": "not-a-list"},
    {"targets": [{"tier": "冲", "school": f"S{index}"} for index in range(9)]},
    {"targets": [{"tier": "冲", "school": "A", "score": 424}], "exam_total": 400},
])
def test_invalid_targets_return_422(client, body):
    response = client.put("/api/profile", json=body)
    assert response.status_code == 422, response.text
    assert client.get("/api/profile").json()["static"]["targets"] == []


def test_subject_targets_validation_and_roundtrip(client):
    payload = client.put("/api/profile", json={
        "exam_total": 500,
        "subject_targets": {"demo": 190},
    }).json()
    assert payload["static"]["subject_targets"] == {"demo": 190}
    assert payload["static"]["exam_total"] == 500

    # 分数上限跟着 exam_total 走。
    assert client.put("/api/profile", json={
        "subject_targets": {"demo": 401}, "exam_total": 400,
    }).status_code == 422
    assert client.put("/api/profile", json={"exam_total": 400}).status_code == 200
    assert client.put("/api/profile", json={
        "subject_targets": {"demo": 401},
    }).status_code == 422
    assert client.put("/api/profile", json={
        "subject_targets": {"demo": 400},
    }).status_code == 200
    unknown = client.put("/api/profile", json={"subject_targets": {"nope": 10}})
    assert unknown.status_code == 422
    assert "nope" in unknown.json()["detail"]
    assert client.put("/api/profile", json={"subject_targets": [1, 2]}).status_code == 422


def test_phase_object_days_left_and_progress(client):
    assert client.get("/api/profile").json()["phase"] is None

    start = (date.today() - timedelta(days=10)).isoformat()
    end = (date.today() + timedelta(days=20)).isoformat()
    payload = client.put("/api/profile", json={
        "plan_phase": "P2",
        "phase_start": start,
        "phase_end": end,
        "phase_daily_minutes": 150,
        "phase_goal": "高数第二轮 + 真题",
        "total_hours": 600,
    }).json()
    phase = payload["phase"]
    assert phase["name"] == "P2"
    assert phase["goal"] == "高数第二轮 + 真题"
    assert phase["start"] == start
    assert phase["end"] == end
    assert phase["daily_minutes"] == 150
    assert phase["days_left"] == 20
    assert phase["progress"] == pytest.approx(10 / 30, abs=0.001)
    assert payload["static"]["total_hours"] == 600

    # 阶段结束日期可以早于今天，days_left 为负，progress 封顶 1。
    past = client.put("/api/profile", json={
        "phase_start": "2020-01-01",
        "phase_end": "2020-01-31",
    }).json()["phase"]
    assert past["days_left"] < 0
    assert past["progress"] == 1.0

    # 只清掉阶段名与起止，phase 回到 null。
    cleared = client.put("/api/profile", json={
        "plan_phase": None, "phase_start": None, "phase_end": None,
    }).json()
    assert cleared["phase"] is None


@pytest.mark.parametrize("body", [
    {"plan_phase": "P4"},
    {"phase_start": "2026/01/01"},
    {"phase_end": "2026-02-30"},
    {"phase_start": "2026-05-01", "phase_end": "2026-04-01"},
    {"phase_daily_minutes": 0},
    {"phase_daily_minutes": 601},
    {"phase_goal": "x" * 501},
    {"total_hours": -1},
    {"total_hours": 100001},
    {"exam_total": 0},
    {"exam_total": 1001},
    {"hard_lines": "x" * 201},
])
def test_invalid_plan_fields_return_422(client, body):
    response = client.put("/api/profile", json=body)
    assert response.status_code == 422, response.text
    assert client.get("/api/profile").json()["static"]["plan_phase"] is None


def test_v8_profile_upgrades_to_v9_keeps_existing_fields(tmp_path, monkeypatch):
    monkeypatch.setenv("KAODIAN_CONTENT_DIR", str(DEMO))
    monkeypatch.setenv("KAODIAN_DATA_DIR", str(tmp_path / "data"))

    path = tmp_path / "v8.db"
    database.init_db(path)

    # 还原成 v8 的 profile 表：没有 v9 新列，user_version=8。
    with database.session(path) as conn:
        conn.execute("DROP TABLE profile")
        conn.execute(
            """CREATE TABLE profile (
                   id                 INTEGER PRIMARY KEY CHECK (id = 1),
                   target_exam        TEXT,
                   target_date        TEXT,
                   target_score       REAL,
                   target_school      TEXT,
                   target_major       TEXT,
                   target_region      TEXT,
                   backup_school      TEXT,
                   backup_major       TEXT,
                   exam_type          TEXT,
                   current_education  TEXT,
                   graduation_year    INTEGER,
                   daily_minutes      INTEGER NOT NULL DEFAULT 30,
                   subjects           TEXT NOT NULL DEFAULT '[]',
                   study_window       TEXT,
                   constraints        TEXT,
                   strengths          TEXT,
                   weaknesses         TEXT,
                   motivation         TEXT,
                   notes              TEXT NOT NULL DEFAULT '',
                   ai_summary         TEXT,
                   preferred_tone     TEXT NOT NULL DEFAULT '',
                   preferred_examples TEXT NOT NULL DEFAULT '',
                   updated_by         TEXT NOT NULL DEFAULT 'user',
                   updated_at         TEXT
               )"""
        )
        conn.execute(
            """INSERT INTO profile(id, target_exam, target_date, target_score,
                                   target_school, target_major, daily_minutes,
                                   subjects, notes, ai_summary, updated_by, updated_at)
               VALUES (1, '2028 广东专升本', '2028-03-28', 425,
                       '广东技术师范大学', '计算机科学与技术', 90,
                       '["demo"]', '旧备注', '旧摘要', 'agent', '2026-01-01T00:00:00')"""
        )
        conn.execute("PRAGMA user_version = 8")

    database.init_db(path)

    with database.session(path) as conn:
        assert conn.execute("PRAGMA user_version").fetchone()[0] == 9
        row = conn.execute("SELECT * FROM profile WHERE id = 1").fetchone()
        # 旧字段原样保留。
        assert row["target_exam"] == "2028 广东专升本"
        assert row["target_date"] == "2028-03-28"
        assert row["target_score"] == 425
        assert row["target_school"] == "广东技术师范大学"
        assert row["target_major"] == "计算机科学与技术"
        assert row["daily_minutes"] == 90
        assert row["notes"] == "旧备注"
        assert row["ai_summary"] == "旧摘要"
        assert row["updated_by"] == "agent"
        # v9 新列存在且默认 NULL。
        for name in ("targets", "subject_targets", "exam_total", "hard_lines",
                     "plan_phase", "phase_start", "phase_end",
                     "phase_daily_minutes", "phase_goal", "total_hours"):
            assert row[name] is None

    assert list(tmp_path.glob("backups/v8.db.bak-v8-*"))


def test_cli_profile_export_import_roundtrip(tmp_path, monkeypatch, capsys):
    from apps.cli.__main__ import main as cli_main
    from apps.api.app import profile as profiles

    monkeypatch.setenv("KAODIAN_CONTENT_DIR", str(DEMO))
    monkeypatch.setenv("KAODIAN_DATA_DIR", str(tmp_path / "data"))
    db = tmp_path / "cli.db"
    monkeypatch.setenv("KAODIAN_DB", str(db))

    database.init_db(db)
    with database.session(db) as conn:
        profiles.update_profile(conn, {
            "target_exam": "2028 广东专升本",
            "target_date": "2028-03-28",
            "target_score": 425,
            "target_major": "计算机科学与技术",
            "motivation": "想换到计算机相关岗位",
            "targets": TARGETS,
            "exam_total": 500,
            "subject_targets": {"demo": 190},
            "hard_lines": "三科 105",
            "plan_phase": "P1",
            "phase_start": "2026-11-01",
            "phase_end": "2027-03-31",
            "phase_daily_minutes": 120,
            "phase_goal": "打基础",
            "total_hours": 800,
            "source": "agent",
        })

    out = tmp_path / "profile.json"
    assert cli_main(["profile", "export", "--output", str(out), "--json"]) == 0
    exported = json.loads(out.read_text(encoding="utf-8"))
    assert exported["version"] == 3
    assert exported["exported_at"]
    assert "dynamic" not in exported
    assert exported["static"]["targets"] == TARGETS
    assert exported["static"]["subject_targets"] == {"demo": 190}

    # 清空后导入，静态字段应完整回来。
    with database.session(db) as conn:
        conn.execute(
            "UPDATE profile SET target_exam = NULL, targets = NULL, "
            "subject_targets = NULL, plan_phase = NULL WHERE id = 1"
        )
    assert cli_main(["profile", "import", str(out)]) == 0
    printed = capsys.readouterr().out
    assert "完整度" in printed and "缺失" in printed

    with database.session(db) as conn:
        restored = profiles.get_profile(conn)
    assert restored["static"]["target_exam"] == "2028 广东专升本"
    assert restored["static"]["targets"] == TARGETS
    assert restored["static"]["subject_targets"] == {"demo": 190}
    assert restored["static"]["plan_phase"] == "P1"
    assert restored["completeness"] == 1
    assert restored["missing"] == []
    assert restored["phase"]["name"] == "P1"


def test_cli_profile_import_accepts_flat_file_and_source(tmp_path, monkeypatch):
    from apps.cli.__main__ import main as cli_main

    monkeypatch.setenv("KAODIAN_CONTENT_DIR", str(DEMO))
    monkeypatch.setenv("KAODIAN_DATA_DIR", str(tmp_path / "data"))
    db = tmp_path / "cli-flat.db"
    monkeypatch.setenv("KAODIAN_DB", str(db))
    database.init_db(db)

    flat = tmp_path / "flat.json"
    flat.write_text(json.dumps({
        "target_exam": "2028 自考", "source": "agent", "version": 3,
    }, ensure_ascii=False), encoding="utf-8")
    assert cli_main(["profile", "import", str(flat), "--json"]) == 0

    with database.session(db) as conn:
        row = conn.execute("SELECT target_exam, updated_by FROM profile WHERE id = 1").fetchone()
    assert row["target_exam"] == "2028 自考"
    assert row["updated_by"] == "agent"

    bad = tmp_path / "bad.json"
    bad.write_text(json.dumps({"targets": [{"tier": "梦", "school": "A"}]}), encoding="utf-8")
    assert cli_main(["profile", "import", str(bad), "--json"]) == 1


def test_cli_profile_show_default_paths(tmp_path, monkeypatch):
    from apps.cli.__main__ import main as cli_main

    monkeypatch.setenv("KAODIAN_CONTENT_DIR", str(DEMO))
    monkeypatch.setenv("KAODIAN_DATA_DIR", str(tmp_path / "data"))
    db = tmp_path / "cli-show.db"
    monkeypatch.setenv("KAODIAN_DB", str(db))
    database.init_db(db)

    assert cli_main(["profile", "show", "--json"]) == 0
    assert cli_main(["profile", "export"]) == 0
    assert (tmp_path / "data" / "profile.json").is_file()
