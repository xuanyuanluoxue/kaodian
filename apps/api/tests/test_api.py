from __future__ import annotations

import json
import shutil
import sqlite3
from pathlib import Path

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


def test_spa_blocks_path_traversal(client):
    for path in (
        "/../../../README.md",
        "/%2e%2e/%2e%2e/%2e%2e/user-data/kaodian.db",
    ):
        r = client.get(path)
        assert r.status_code == 200
        assert r.content.startswith(b"<!doctype html>")
        assert b"SQLite format" not in r.content


def test_answer_must_belong_to_quiz(client):
    quiz = client.post(
        "/api/quizzes",
        json={
            "mode": "practice",
            "count": 1,
            "filters": {"subject_id": "computer", "types": ["single"]},
        },
    ).json()
    attempt = client.post("/api/attempts", json={"quiz_id": quiz["id"]}).json()
    in_quiz = {q["id"] for q in quiz["questions"]}

    outsider = next(
        q
        for q in client.get("/api/questions?subject_id=computer&limit=50").json()
        if q["id"] not in in_quiz
    )
    r = client.patch(
        f"/api/attempts/{attempt['id']}",
        json={"answers": [{"question_id": outsider["id"], "response": "A"}]},
    )
    assert r.status_code == 422


def test_question_type_registry(client):
    types = client.get("/api/question-types").json()
    by_id = {t["id"]: t for t in types}
    assert by_id["single"]["grading"] == "auto"
    assert by_id["single"]["input"] == "choice"
    assert by_id["essay"]["grading"] == "agent"
    assert by_id["code"]["input"] == "code"
    assert by_id["fill"]["answer_schema"] == "blanks"


def test_subject_display_fields(client):
    subjects = client.get("/api/subjects").json()
    computer = next(s for s in subjects if s["id"] == "computer")
    assert computer["color"].startswith("#")
    assert computer["icon"]
    assert computer["sort"] == 1
    assert computer["code_language"] == "c"
    assert [s["sort"] for s in subjects] == sorted(s["sort"] for s in subjects)


def test_content_sync_is_idempotent(tmp_path):
    from apps.api.app import db as database

    path = tmp_path / "sync.db"
    database.init_db(path)
    database.init_db(path)
    with database.session(path) as conn:
        assert conn.execute("SELECT COUNT(*) FROM subject").fetchone()[0] == 4
        assert conn.execute("SELECT COUNT(*) FROM outline_node").fetchone()[0] == 161
        assert conn.execute("PRAGMA user_version").fetchone()[0] == database.SCHEMA_VERSION


def test_multi_blank_fill_grading():
    from apps.api.app.grading import grade

    q = {
        "type": "fill",
        "score": 4,
        "answer": [["2", "二"], ["3", "三"]],
    }
    assert grade(q, ["2", "3"])["score"] == 4
    assert grade(q, ["2", "4"])["score"] == 0
    assert grade(q, "2")["score"] == 0


def test_page_sort_order(client):
    def make(title, order):
        return client.post("/api/pages", json={
            "subject_id": "math",
            "title": title,
            "body": "正文内容",
            "kind": "lesson",
            "status": "published",
            "sort_order": order,
        }).json()

    make("后", 20)
    make("前", 10)
    titles = [p["title"] for p in client.get("/api/pages?subject_id=math").json()]
    assert titles.index("前") < titles.index("后")


def test_new_subject_only_needs_config(tmp_path, monkeypatch):
    cfg = tmp_path / "config"
    shutil.copytree(Path(__file__).resolve().parents[3] / "config", cfg)
    (cfg / "subjects" / "physics.json").write_text(
        json.dumps({
            "id": "physics",
            "name": "物理",
            "short": "物理",
            "color": "#336699",
            "icon": "atom",
            "sort": 9,
            "exam": {"score": 100, "minutes": 90},
            "nodes": [{"code": "PH-01", "title": "质点运动"}],
        }, ensure_ascii=False),
        encoding="utf-8",
    )
    monkeypatch.setenv("KAODIAN_CONFIG_DIR", str(cfg))
    app = create_app(tmp_path / "physics.db")
    with TestClient(app) as c:
        subjects = c.get("/api/subjects").json()
        assert any(s["id"] == "physics" for s in subjects)
        assert subjects[-1]["id"] == "physics"
        nodes = c.get("/api/outline?subject_id=physics").json()
        assert nodes[0]["code"] == "PH-01"
        res = c.post("/api/questions/batch", json={"questions": [{
            "outline_code": "PH-01",
            "type": "single",
            "stem": "一个质点做匀速直线运动，下列说法正确的是（ ）",
            "options": ["速度不变", "加速度变大", "位移不变", "速率变小"],
            "answer": ["A"],
            "explanation": "匀速直线运动速度大小和方向都不变。",
            "difficulty": 1,
            "score": 2,
        }]})
        assert res.status_code == 201
        assert res.json()["created"] == 1


def test_code_run_output_is_capped(client, monkeypatch):
    if not shutil.which("gcc") or not shutil.which("bwrap"):
        pytest.skip("需要 gcc 和 bubblewrap")
    monkeypatch.setenv("KAODIAN_ALLOW_CODE_RUN", "1")
    code = (
        '#include <stdio.h>\n'
        'int main(){for(int i=0;i<20000;i++)printf("0123456789");return 0;}'
    )
    res = client.post("/api/code/run", json={"code": code})
    assert res.status_code == 200
    assert len(res.json()["output"]) <= 65536


def test_code_run_rejects_unknown_language(client, monkeypatch):
    monkeypatch.setenv("KAODIAN_ALLOW_CODE_RUN", "1")
    res = client.post("/api/code/run", json={"code": "print(1)", "language": "python"})
    assert res.status_code == 422


def _single(outline_code, stem, **extra):
    return {
        "outline_code": outline_code,
        "type": "single",
        "stem": stem,
        "options": ["甲", "乙", "丙", "丁"],
        "answer": ["A"],
        "explanation": "这是解析，长度足够通过校验。",
        "difficulty": 2,
        "score": 3,
        **extra,
    }


def test_question_group_quiz_detail(client):
    group = client.post("/api/question-groups", json={
        "subject_id": "computer",
        "title": "阅读下面材料",
        "material": "一个 C 程序由若干函数组成。",
        "media": [{"type": "image", "url": "/images/x.svg", "alt": "程序结构"}],
    }).json()
    assert group["id"].startswith("g_")

    created = client.post("/api/questions/batch", json={"questions": [
        _single("C-01", "材料题小题一：程序的基本单位是（ ）",
                group_id=group["id"], group_position=1),
        _single("C-01", "材料题小题二：函数入口是（ ）",
                group_id=group["id"], group_position=2),
    ]}).json()
    assert created["created"] == 2
    client.post("/api/questions/review",
                json={"ids": created["ids"], "decision": "approve"})

    detail = client.get(f"/api/question-groups/{group['id']}").json()
    assert [q["id"] for q in detail["questions"]] == created["ids"]
    assert all(q["group_id"] == group["id"] for q in detail["questions"])

    quiz = client.post("/api/quizzes", json={
        "mode": "practice", "question_ids": created["ids"],
    }).json()
    assert len(quiz["groups"]) == 1
    assert quiz["groups"][0]["id"] == group["id"]
    assert quiz["groups"][0]["question_ids"] == created["ids"]
    assert quiz["groups"][0]["material"] == "一个 C 程序由若干函数组成。"
    assert all(q["group_id"] == group["id"] for q in quiz["questions"])


def test_question_with_secondary_outline_code_can_be_drawn(client):
    created = client.post("/api/questions/batch", json={"questions": [
        _single("C-02", "多考点测试：下列哪个是合法标识符（ ）",
                outline_codes=["C-02", "C-05"]),
    ]}).json()
    qid = created["ids"][0]
    client.post("/api/questions/review", json={"ids": [qid], "decision": "approve"})

    found = client.get("/api/questions?code=C-05&limit=200").json()
    assert any(q["id"] == qid for q in found)
    assert set(next(q for q in found if q["id"] == qid)["outline_codes"]) == {"C-02", "C-05"}

    quiz = client.post("/api/quizzes", json={
        "mode": "practice", "count": 100,
        "filters": {"subject_id": "computer", "codes": ["C-05"], "types": ["single"]},
    }).json()
    assert qid in {q["id"] for q in quiz["questions"]}


def test_question_media_roundtrip(client):
    media = [
        {"type": "image", "url": "/images/tree.svg", "alt": "二叉树",
         "license": "CC0", "source": "local"},
        {"type": "audio", "url": "https://example.com/a.mp3", "alt": "朗读"},
    ]
    created = client.post("/api/questions/batch", json={"questions": [
        _single("C-03", "媒体测试：二叉树的中序遍历是（ ）", media=media),
    ]}).json()
    qid = created["ids"][0]
    items = client.get("/api/questions?status=pending&code=C-03&limit=200").json()
    item = next(q for q in items if q["id"] == qid)
    assert item["media"] == media

    bad = client.post("/api/questions/batch", json={"questions": [
        _single("C-03", "媒体校验：非法外链应当被拒绝（ ）",
                media=[{"type": "image", "url": "http://example.com/x.png"}]),
    ]})
    assert bad.status_code == 422


def test_group_config_sync_is_idempotent(tmp_path, monkeypatch):
    from apps.api.app import db as database

    cfg = tmp_path / "config"
    shutil.copytree(Path(__file__).resolve().parents[3] / "config", cfg)
    (cfg / "questions" / "grouped.seed.json").write_text(json.dumps({
        "groups": [{
            "key": "g1",
            "title": "材料组一",
            "material": "阅读材料正文。",
            "media": [{"type": "image", "url": "/images/x.svg", "alt": "图"}],
        }],
        "questions": [
            {**_single("M-01", "对象格式测试：函数极限的定义是（ ）",
                       outline_codes=["M-01", "M-02"]),
             "group_key": "g1", "group_position": 1},
        ],
    }, ensure_ascii=False), encoding="utf-8")

    monkeypatch.setenv("KAODIAN_CONFIG_DIR", str(cfg))
    path = tmp_path / "sync-group.db"
    database.init_db(path)
    database.init_db(path)

    with database.session(path) as conn:
        groups = conn.execute(
            "SELECT * FROM question_group WHERE source_key = 'g1'"
        ).fetchall()
        assert len(groups) == 1
        q = conn.execute(
            "SELECT * FROM question WHERE stem = ?",
            ("对象格式测试：函数极限的定义是（ ）",),
        ).fetchone()
        assert q is not None
        assert q["group_id"] == groups[0]["id"]
        assert q["group_position"] == 1
        linked = {
            r["outline_code"] for r in conn.execute(
                "SELECT outline_code FROM question_outline WHERE question_id = ?",
                (q["id"],),
            )
        }
        assert {"M-01", "M-02"} <= linked


def test_v2_database_upgrades_without_data_loss(tmp_path):
    from apps.api.app import db as database

    path = tmp_path / "v2.db"
    database.init_db(path)
    with database.session(path) as conn:
        before = {
            table: conn.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0]
            for table in ("subject", "outline_node", "question")
        }
        now = database.now_iso()
        conn.execute(
            """INSERT INTO page(id, subject_id, title, summary, body, lesson_key,
                                outline_codes, kind, status, sort_order, created_at, updated_at)
               VALUES ('p_migrate', 'computer', '迁移测试页', NULL, '正文', 'L99',
                       '[]', 'lesson', 'published', 1, ?, ?)""",
            (now, now),
        )
        qid = conn.execute("SELECT id FROM question LIMIT 1").fetchone()["id"]

    # 退回 v2：删掉 v2.1 新增的表和列。
    raw = sqlite3.connect(path)
    try:
        raw.execute("DROP TABLE question_outline")
        raw.execute("DROP TABLE question_group")
        raw.execute("DROP INDEX IF EXISTS idx_question_group")
        raw.execute("ALTER TABLE question DROP COLUMN group_id")
        raw.execute("ALTER TABLE question DROP COLUMN group_position")
        raw.execute("ALTER TABLE question DROP COLUMN media")
        raw.execute("PRAGMA user_version = 2")
        raw.commit()
    finally:
        raw.close()

    database.init_db(path)

    with database.session(path) as conn:
        for table in before:
            assert conn.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0] >= before[table]
        assert conn.execute("PRAGMA user_version").fetchone()[0] == 3
        tables = {
            r["name"] for r in conn.execute(
                "SELECT name FROM sqlite_master WHERE type = 'table'"
            )
        }
        assert {"question_group", "question_outline"} <= tables
        columns = {r["name"] for r in conn.execute("PRAGMA table_info(question)")}
        assert {"group_id", "group_position", "media"} <= columns
        assert conn.execute(
            "SELECT 1 FROM page WHERE id = 'p_migrate'"
        ).fetchone() is not None
        assert conn.execute(
            "SELECT 1 FROM question_outline WHERE question_id = ?", (qid,)
        ).fetchone() is not None

    assert list(tmp_path.glob("v2.db.bak-v2-*"))



def test_page_question_count(client):
    page = client.post("/api/pages", json={
        "subject_id": "computer",
        "title": "循环与跳转",
        "body": "正文",
        "outline_codes": ["C-08"],
    }).json()
    res = client.get(f"/api/pages/{page['id']}/question-count")
    assert res.status_code == 200
    data = res.json()
    assert data["codes"] == ["C-08"]
    assert data["count"] > 0
    assert data["count"] == len(
        client.get("/api/questions?code=C-08&limit=200").json()
    )

    # 一题挂多个考点：C-08 是副考点，也要计入且只算一次
    first = client.post("/api/pages", json={
        "subject_id": "computer", "title": "多考点", "body": "正文",
        "outline_codes": ["C-05", "C-08"],
    }).json()
    before = client.get(f"/api/pages/{first['id']}/question-count").json()["count"]

    qid = client.post("/api/questions/batch", json={"questions": [{
        "outline_code": "C-05",
        "outline_codes": ["C-08"],
        "type": "single",
        "stem": "下列循环语句中，至少执行一次循环体的是（ ）",
        "options": ["while", "for", "do-while", "if"],
        "answer": ["C"],
        "explanation": "do-while 先执行循环体再判断条件。",
        "difficulty": 2,
        "score": 3,
    }]}).json()["ids"][0]
    # 未审的题不计入
    pending = client.get(f"/api/pages/{first['id']}/question-count").json()["count"]
    assert pending == before

    client.post("/api/questions/review", json={"ids": [qid], "decision": "approve"})
    after = client.get(f"/api/pages/{first['id']}/question-count").json()["count"]
    assert after == before + 1

    # 无考点页面返回 0；不存在的页面 404
    empty = client.post("/api/pages", json={
        "subject_id": "computer", "title": "空页", "body": "正文",
    }).json()
    assert client.get(f"/api/pages/{empty['id']}/question-count").json() == {
        "count": 0, "codes": [],
    }
    assert client.get("/api/pages/p_missing/question-count").status_code == 404


def test_agent_stream_sse(client):
    session = client.post("/api/agent/sessions", json={"title": "SSE"}).json()
    first = client.post("/api/agent/events", json={
        "session_id": session["id"], "kind": "note", "body": "先看定义",
    }).json()["id"]
    second = client.post("/api/agent/events", json={
        "session_id": session["id"], "kind": "note", "body": "想一下切线斜率",
    }).json()["id"]

    def read_event(res) -> str:
        text = ""
        for _ in range(4):
            text += next(res.iter_bytes()).decode()
            if "\n\n" in text:
                break
        return text

    url = f"/api/agent/stream?session_id={session['id']}"
    with client.stream("GET", url) as res:
        assert res.status_code == 200
        assert "text/event-stream" in res.headers["content-type"]
        assert res.headers["cache-control"] == "no-cache"
        assert res.headers["x-accel-buffering"] == "no"
        block = read_event(res)
    assert f"id: {first}" in block
    assert "event: note" in block
    data_line = next(line for line in block.splitlines() if line.startswith("data: "))
    payload = json.loads(data_line[len("data: "):])
    assert payload["id"] == first
    assert payload["body"] == "先看定义"

    # after_id 之后只补发新事件
    with client.stream("GET", f"{url}&after_id={first}") as res:
        block = read_event(res)
    payloads = [
        json.loads(line[len("data: "):])
        for line in block.splitlines()
        if line.startswith("data: ")
    ]
    assert payloads
    assert payloads[0]["id"] == second
    assert all(p["id"] > first for p in payloads)
