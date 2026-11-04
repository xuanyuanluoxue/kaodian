#!/usr/bin/env python3
"""考点 Kaodian 的 MCP 服务：把 HTTP API 包装成对话里可调用的工具。

运行：
    KAODIAN_API=http://127.0.0.1:8010 \
    KAODIAN_WEB=http://127.0.0.1:8010 \
    .venv/bin/python apps/mcp/server.py

OpenCode 配置见 README 的「MCP」一节。
"""
from __future__ import annotations

import json
import os
from typing import Any

import httpx
from mcp.server.mcpserver import MCPServer

API = os.environ.get("KAODIAN_API", "http://127.0.0.1:8010").rstrip("/")
WEB = os.environ.get("KAODIAN_WEB", API).rstrip("/")

_client = httpx.Client(timeout=20.0)

mcp = MCPServer(
    "kaodian",
    version="0.1.0",
    instructions=(
        "考点是 Agent 的作答终端。先用 list_outline 确认考点编号，"
        "题库是实时生成的：create_questions 入库存为 pending，review_questions 审查后才可组卷；"
        "用 build_quiz 组卷并把 url 发给用户；用 publish_page 写讲解页，用户在控制台阅读；"
        "用户答题时可以用 send_hint 推提示；read_inbox 读取求助和交卷结果；"
        "主观题交卷后进 get_grading_queue，读答案后用 grade_answer 写回分数。"
    ),
)


def _call(method: str, path: str, **kwargs: Any) -> Any:
    try:
        res = _client.request(method, f"{API}{path}", **kwargs)
        res.raise_for_status()
        return res.json()
    except httpx.HTTPStatusError as exc:
        detail: Any = exc.response.text
        try:
            detail = exc.response.json().get("detail", detail)
        except Exception:
            pass
        raise RuntimeError(f"Kaodian API {exc.response.status_code}: {detail}") from exc
    except httpx.RequestError as exc:
        raise RuntimeError(f"连不上 Kaodian API（{API}）：{exc}") from exc


@mcp.tool()
def list_subjects() -> list[dict]:
    """列出全部科目：id、名称、题量、考点数。组卷前先看这个。"""
    return [
        {
            "id": s["id"],
            "name": s["name"],
            "short": s["short"],
            "exam_score": s["exam_score"],
            "node_count": s["node_count"],
            "question_count": s["question_count"],
        }
        for s in _call("GET", "/api/subjects")
    ]


@mcp.tool()
def list_outline(subject_id: str = "") -> list[dict]:
    """列出考点编号与标题。组卷时 codes 必须从这里取，不能自己编。

    Args:
        subject_id: 科目 id，来自 list_subjects；留空返回全部。
    """
    path = "/api/outline" + (f"?subject_id={subject_id}" if subject_id else "")
    return [
        {
            "code": n["code"],
            "title": n["title"],
            "section": n["section"],
            "hours": n["hours"],
            "stage": n["stage"],
            "question_count": n["question_count"],
        }
        for n in _call("GET", path)
    ]


@mcp.tool()
def create_agent_session(title: str) -> dict:
    """新建一个 Agent 学习会话。build_quiz 不传 session_id 时会自动建。"""
    return _call("POST", "/api/agent/sessions", json={"title": title})




@mcp.tool()
def create_questions(questions: list[dict]) -> dict:
    """批量生成题目并入库为「待审」。生成后必须用 review_questions 审查才能组卷。

    每道题至少包含：outline_code、type、stem、explanation、difficulty、score；
    客观题还要 options 和 answer，主观题还要 reference_answer 和 rubric。
        """
    return _call("POST", "/api/questions/batch", json={"questions": questions})


@mcp.tool()
def list_pending_questions(subject_id: str = "", code: str = "", limit: int = 20) -> list[dict]:
    """列出待审题目，带完整题干、答案、解析和评分点，供审查。"""
    params = [f"status=pending", f"limit={limit}"]
    if subject_id:
        params.append(f"subject_id={subject_id}")
    if code:
        params.append(f"code={code}")
    items = _call("GET", "/api/questions?" + "&".join(params))
    return [
        {
            "id": q["id"],
            "outline_code": q["outline_code"],
            "type": q["type"],
            "stem": q["stem"],
            "options": q.get("options"),
            "answer": q.get("answer"),
            "explanation": q.get("explanation"),
            "reference_answer": q.get("reference_answer"),
            "rubric": q.get("rubric"),
            "difficulty": q["difficulty"],
            "score": q["score"],
        }
        for q in items
    ]


@mcp.tool()
def review_questions(ids: list[str], decision: str, note: str = "") -> dict:
    """审查题目：decision=approve 上架，decision=reject 拒绝。

    审查要点：编号是否匹配、答案是否正确、解析是否支持答案、主观题评分点是否可操作。
    """
    if decision not in {"approve", "reject"}:
        raise RuntimeError("decision 只能是 approve 或 reject")
    return _call("POST", "/api/questions/review",
                 json={"ids": ids, "decision": decision, "note": note or None})


@mcp.tool()
def get_grading_queue(limit: int = 20) -> list[dict]:
    """主观题待评分队列：用户已交卷、答案已入库、等待 Agent 评分。"""
    return _call("GET", f"/api/grading/queue?limit={limit}")


@mcp.tool()
def grade_answer(attempt_id: str, question_id: str, score: float, feedback: str = "") -> dict:
    """给一道主观题打分并写回数据库。

    评分依据：题目 rubric、reference_answer 和用户 response；feedback 会显示在结果页。
    """
    return _call("POST", f"/api/grading/{attempt_id}/{question_id}",
                 json={"score": score, "feedback": feedback})

@mcp.tool()
def build_quiz(
    subject_id: str = "",
    codes: list[str] | None = None,
    types: list[str] | None = None,
    count: int = 10,
    mode: str = "practice",
    time_limit_minutes: int | None = None,
    title: str = "",
    session_id: str = "",
) -> dict:
    """组一套题，返回可以直接发给用户的链接。

    Args:
        subject_id: 科目 id，来自 list_subjects；留空表示跨科目。
        codes: 考点编号，如 ["C-08"]；留空表示全科目。
        types: single/multiple/judge/fill/short/calc/code/essay；留空表示不限。
        count: 题量 1-100。
        mode: practice（即时看解析）或 exam（交卷后统一批）。
        time_limit_minutes: 限时分钟数；考试模式留空则按每题 1.5 分钟。
        title: 练习单标题，留空自动生成。
        session_id: 关联的 Agent 会话；留空会自动新建一个。
    """
    sid = session_id
    if not sid:
        sid = create_agent_session(title or f"练习 · {count} 题")["id"]

    body: dict[str, Any] = {
        "mode": mode,
        "count": count,
        "agent_session_id": sid,
        "filters": {
            "codes": codes or [],
            "types": types or [],
        },
    }
    if subject_id:
        body["filters"]["subject_id"] = subject_id
    if title:
        body["title"] = title
    if time_limit_minutes:
        body["time_limit"] = int(time_limit_minutes) * 60

    quiz = _call("POST", "/api/quizzes", json=body)
    return {
        "quiz_id": quiz["id"],
        "url": f"{WEB}/quiz/{quiz['id']}",
        "session_id": sid,
        "title": quiz["title"],
        "question_count": quiz["question_count"],
        "mode": quiz["mode"],
        "time_limit_seconds": quiz["time_limit"],
    }


@mcp.tool()
def send_hint(session_id: str, body: str) -> dict:
    """给正在答题的用户推一条提示。网页会在 5 秒内显示在答题页顶部。"""
    return _call("POST", "/api/agent/events", json={"session_id": session_id, "body": body})


@mcp.tool()
def read_inbox(after_id: int = 0, session_id: str = "") -> list[dict]:
    """读取用户的求助（help）和交卷结果（submitted），按时间正序。

    Args:
        after_id: 只返回 id 大于它的事件；第一次传 0。
        session_id: 只读某个 Agent 会话的事件；留空表示全部。
    """
    query = f"/api/agent/inbox?after_id={after_id}"
    if session_id:
        query += f"&session_id={session_id}"
    events = _call("GET", query)
    for event in events:
        if event["kind"] == "submitted" and event.get("body"):
            try:
                event["data"] = json.loads(event["body"])
            except json.JSONDecodeError:
                pass
    return events


@mcp.tool()
def get_attempt(attempt_id: str) -> dict:
    """看某次作答的详情：得分、薄弱考点、逐题对错与用时。"""
    a = _call("GET", f"/api/attempts/{attempt_id}")
    results = a.get("results") or []
    return {
        "attempt_id": a["id"],
        "status": a["status"],
        "score": a["score"],
        "max_score": a["max_score"],
        "active_seconds": a["active_seconds"],
        "weak": a.get("weak", []),
        "questions": [
            {
                "code": r["question"]["outline_code"],
                "type": r["question"]["type"],
                "stem": r["question"]["stem"][:120],
                "correct": r["correct"],
                "score": r["score"],
                "max_score": r["max_score"],
                "time_spent": r.get("time_spent", 0),
            }
            for r in results
        ],
    }


@mcp.tool()
def get_due_reviews(subject_id: str = "") -> list[dict]:
    """今日到期复习的题目。安排下一组之前先看这里。"""
    path = "/api/reviews/due" + (f"?subject_id={subject_id}" if subject_id else "")
    return [
        {
            "id": q["id"],
            "code": q["outline_code"],
            "type": q["type"],
            "stem": q["stem"][:120],
            "mastery": q["mastery"],
            "due_date": q["due_date"],
        }
        for q in _call("GET", path)
    ]


@mcp.tool()
def publish_page(
    title: str,
    body: str,
    subject_id: str = "",
    summary: str = "",
    outline_codes: list[str] | None = None,
    kind: str = "lesson",
    lesson_key: str = "",
    status: str = "published",
) -> dict:
    """在控制台发布一页学习内容（Markdown），返回可直接发给用户的链接。

    Args:
        title: 页面标题。
        body: Markdown 正文，支持 `代码`、$公式$、表格、列表、details。
        subject_id: 科目 id，来自 list_subjects；留空表示不属于具体科目。
        summary: 一句话摘要，显示在列表里。
        outline_codes: 关联的考点编号，如 ["C-01","C-02"]。
        kind: outline（大纲）/ lesson（讲义）/ daily（每日任务）/ note（笔记）。
        lesson_key: 章节号，如 L03；用来把草稿和课程路径绑定。
        status: published（直接发布）或 draft（缓存待审）。
    """
    payload: dict[str, Any] = {
        "title": title,
        "body": body,
        "summary": summary or None,
        "outline_codes": outline_codes or [],
        "kind": kind,
        "lesson_key": lesson_key or None,
        "status": status,
    }
    if subject_id:
        payload["subject_id"] = subject_id
    page = _call("POST", "/api/pages", json=payload)
    return {
        "page_id": page["id"],
        "url": f"{WEB}/console?page={page['id']}",
        "title": page["title"],
        "kind": page["kind"],
    }


@mcp.tool()
def update_page(
    page_id: str,
    title: str = "",
    body: str = "",
    summary: str = "",
    outline_codes: list[str] | None = None,
    status: str = "",
) -> dict:
    """更新一页已发布的内容。只传要改的字段，空字符串表示不改。"""
    payload: dict[str, Any] = {}
    if title:
        payload["title"] = title
    if body:
        payload["body"] = body
    if summary:
        payload["summary"] = summary
    if outline_codes is not None:
        payload["outline_codes"] = outline_codes
    if status:
        payload["status"] = status
    if not payload:
        raise RuntimeError("没有要更新的字段")
    page = _call("PATCH", f"/api/pages/{page_id}", json=payload)
    return {"page_id": page["id"], "url": f"{WEB}/console?page={page['id']}", "title": page["title"]}


@mcp.tool()
def list_pages(subject_id: str = "") -> list[dict]:
    """列出控制台里已发布的学习页，按时间倒序。"""
    path = "/api/pages" + (f"?subject_id={subject_id}" if subject_id else "")
    return [
        {
            "page_id": p["id"],
            "title": p["title"],
            "summary": p["summary"],
            "kind": p["kind"],
            "lesson_key": p.get("lesson_key"),
            "status": p["status"],
            "codes": p["outline_codes"],
            "created_at": p["created_at"],
            "url": f"{WEB}/console?page={p['id']}",
        }
        for p in _call("GET", path)
    ]


@mcp.tool()
def list_quizzes(limit: int = 10) -> list[dict]:
    """列出最近生成的练习单，带链接。"""
    return [
        {
            "quiz_id": q["id"],
            "title": q["title"],
            "mode": q["mode"],
            "question_count": q["question_count"],
            "time_limit_seconds": q["time_limit"],
            "created_at": q["created_at"],
            "url": f"{WEB}/quiz/{q['id']}",
        }
        for q in _call("GET", f"/api/quizzes?limit={limit}")
    ]


@mcp.tool()
def get_stats_today() -> dict:
    """今日学习时长、作答数、正确率。"""
    return _call("GET", "/api/stats/today")


@mcp.tool()
def get_progress() -> dict:
    """学习路径进度：连续天数、今日目标、XP、完成课数、最近 7 天。"""
    return _call("GET", "/api/progress")


if __name__ == "__main__":
    mcp.run("stdio")