from __future__ import annotations

import shutil
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


def test_subjective_goes_to_agent_grading(client):
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
            "answers": [{
                "question_id": short["id"],
                "response": "字符数组是 char 数组；输入用 scanf，输出用 printf。",
                "time_spent": 100,
            }],
        },
    ).json()
    assert result["grading_status"] == "pending"
    assert result["score"] == 0
    assert result["results"][0]["score"] is None

    queue = client.get("/api/grading/queue").json()
    assert any(x["question_id"] == short["id"] for x in queue)

    graded = client.post(
        f"/api/grading/{attempt['id']}/{short['id']}",
        json={"score": 10, "feedback": "定义与输入输出都写到了。"},
    ).json()
    assert graded["grading_status"] == "done"
    assert graded["correct"] is True

    fetched = client.get(f"/api/attempts/{attempt['id']}").json()
    assert fetched["score"] == 10
    assert fetched["grading_status"] == "done"


def test_generated_question_needs_review(client):
    item = {
        "outline_code": "C-04",
        "type": "single",
        "stem": "十进制数 12 转换成二进制是（ ）",
        "options": ["1010", "1100", "1001", "1110"],
        "answer": ["B"],
        "explanation": "12 = 8 + 4，对应二进制 1100。",
        "difficulty": 1,
        "score": 3,
    }
    created = client.post("/api/questions/batch", json={"questions": [item]}).json()
    qid = created["ids"][0]

    pending = client.get("/api/questions?status=pending&code=C-04").json()
    assert any(q["id"] == qid for q in pending)

    before = client.post("/api/quizzes", json={"mode": "practice", "question_ids": [qid]})
    assert before.status_code == 422

    client.post("/api/questions/review", json={"ids": [qid], "decision": "approve", "note": "答案正确"})
    after = client.post("/api/quizzes", json={"mode": "practice", "question_ids": [qid]})
    assert after.status_code == 201
    assert after.json()["question_count"] == 1

    rejected = client.post("/api/questions/batch", json={"questions": [{
        **item, "stem": "十进制数 13 转换成二进制是（ ）", "answer": ["B"],
        "explanation": "13 = 8 + 4 + 1，对应二进制 1101。",
        "options": ["1101", "1100", "1011", "1110"],
    }]}).json()["ids"][0]
    client.post("/api/questions/review", json={"ids": [rejected], "decision": "reject"})
    assert client.post("/api/quizzes", json={"mode": "practice", "question_ids": [rejected]}).status_code == 422


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

def test_agent_session_flow(client):
    session = client.post("/api/agent/sessions", json={"title": "C 语言 · 循环"}).json()

    quiz = client.post(
        "/api/quizzes",
        json={
            "mode": "practice",
            "count": 1,
            "agent_session_id": session["id"],
            "filters": {"subject_id": "computer", "codes": ["C-08"], "types": ["single"]},
        },
    ).json()
    assert quiz["agent_session_id"] == session["id"]

    attempt = client.post("/api/attempts", json={"quiz_id": quiz["id"]}).json()

    note = client.post(
        "/api/agent/events",
        json={"session_id": session["id"], "body": "先做这题，卡住就点「卡住了」。"},
    )
    assert note.status_code == 201

    q = quiz["questions"][0]
    help_res = client.post(
        "/api/agent/help",
        json={"attempt_id": attempt["id"], "question_id": q["id"], "body": "while 和 do-while 分不清"},
    )
    assert help_res.status_code == 201

    feed = client.get(f"/api/agent/feed?session_id={session['id']}").json()
    kinds = [e["kind"] for e in feed]
    assert "started" in kinds
    assert "note" in kinds
    assert "help" in kinds

    client.post(
        f"/api/attempts/{attempt['id']}/submit",
        json={
            "active_seconds": 30,
            "answers": [{"question_id": q["id"], "response": answer_of(q), "time_spent": 25}],
        },
    )

    inbox = client.get("/api/agent/inbox").json()
    assert any(e["kind"] == "submitted" for e in inbox)


def test_help_requires_agent_session(client):
    quiz = client.post(
        "/api/quizzes",
        json={"mode": "practice", "count": 1, "filters": {"subject_id": "computer", "types": ["single"]}},
    ).json()
    attempt = client.post("/api/attempts", json={"quiz_id": quiz["id"]}).json()
    q = quiz["questions"][0]
    res = client.post(
        "/api/agent/help",
        json={"attempt_id": attempt["id"], "question_id": q["id"], "body": "卡住了"},
    )
    assert res.status_code == 409


def test_study_time_counts(client):
    res = client.post("/api/activity", json={"page_id": "p_lesson", "seconds": 120, "source": "page"})
    assert res.status_code == 200
    assert res.json()["ok"] is True
    assert res.json()["today_seconds"] >= 120

    stats = client.get("/api/stats/today").json()
    assert stats["active_seconds"] >= 120

    progress = client.get("/api/progress").json()
    assert progress["today_minutes"] >= 2
    assert progress["today_done"] is True


def test_active_attempt_counts_in_stats(client):
    quiz = client.post(
        "/api/quizzes",
        json={
            "mode": "practice",
            "count": 1,
            "filters": {"subject_id": "computer", "types": ["single"]},
        },
    ).json()
    attempt = client.post("/api/attempts", json={"quiz_id": quiz["id"]}).json()
    client.patch(f"/api/attempts/{attempt['id']}", json={"active_seconds": 60})

    # 还没交卷，但进行中的作答时间也要算进今日投入
    stats = client.get("/api/stats/today").json()
    assert stats["active_seconds"] >= 60
    assert stats["attempts"] >= 1


def test_code_run_disabled_by_default(client, monkeypatch):
    monkeypatch.delenv("KAODIAN_ALLOW_CODE_RUN", raising=False)
    assert client.get("/api/code/status").json()["enabled"] is False
    res = client.post("/api/code/run", json={"code": "int main(){return 0;}"})
    assert res.status_code == 403


def test_code_run_in_sandbox(client, monkeypatch):
    if not shutil.which("gcc") or not shutil.which("bwrap"):
        pytest.skip("需要 gcc 和 bubblewrap")
    monkeypatch.setenv("KAODIAN_ALLOW_CODE_RUN", "1")
    res = client.post(
        "/api/code/run",
        json={"code": '#include <stdio.h>\nint main(){printf("hi\\n");return 0;}', "stdin": ""},
    )
    assert res.status_code == 200
    data = res.json()
    assert data["ok"] is True
    assert "hi" in data["output"]


def test_code_run_explains_typo(client, monkeypatch):
    if not shutil.which("gcc") or not shutil.which("bwrap"):
        pytest.skip("需要 gcc 和 bubblewrap")
    monkeypatch.setenv("KAODIAN_ALLOW_CODE_RUN", "1")
    res = client.post(
        "/api/code/run",
        json={"code": '#inclaude <stdio.h>\n\nint main(){printf("hi");return 0;}', "stdin": ""},
    )
    assert res.status_code == 200
    data = res.json()
    assert data["ok"] is False
    hints = data["hints"]
    assert hints
    first = hints[0]
    assert first["line"] == 1
    assert "#inclaude" in first["reason"]
    assert "#include" in first["reason"]
    assert "#include" in first["fix"]
