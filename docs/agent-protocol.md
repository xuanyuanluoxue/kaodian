# Agent 协作协议

> 这个项目的定位是 **Agent 的作答终端**，不是独立的刷题网站。
> Agent 负责决定学什么、出题、给提示、读结果；网页负责作答、计时、回传。

## 1. 一次完整循环

```
用户                    Agent（对话）                    网页
 │                          │                              │
 │  "按 C-08 出 10 道"      │                              │
 ├─────────────────────────→│                              │
 │                          │ POST /api/agent/sessions     │
 │                          │ POST /api/quizzes            │
 │                          │   { agent_session_id }       │
 │  ←──── 链接 ─────────────┤                              │
 │                          │                              │
 │  打开链接 ─────────────────────────────────────────────→│ POST /api/attempts
 │                          │                              │ 计时 / 作答
 │                          │                              │
 │  "卡住了" ─────────────────────────────────────────────→│ POST /api/agent/help
 │                          │ GET /api/agent/inbox ←───────┤
 │  ←──── 讲解/提示 ────────┤ POST /api/agent/events       │
 │                          │        （note）              │
 │                          │                              │ GET /api/agent/feed（5s 轮询）
 │                          │                              │ 顶部显示提示
 │                          │                              │
 │                          │                              │ 交卷
 │                          │ ←── GET /api/agent/inbox ────┤ POST .../submit
 │  ←──── 复盘/下一组 ──────┤      （submitted 事件）      │
```

## 2. 会话与事件

- **一个 Agent 会话**对应一段学习上下文，可以有多个练习单和多次作答。
- 所有协作都写进一条**只追加的事件流**：

| kind | 谁写 | 含义 |
|---|---|---|
| `started` | 服务端 | 用户开始作答 |
| `help` | 网页 | 用户点「卡住了」，附题目编号与描述 |
| `note` | Agent | 提示、讲解、让他跳过的指令 |
| `submitted` | 服务端 | 交卷，附得分与题量 |

事件字段：

```json
{
  "id": 12,
  "session_id": "s_ab12cd34ef56",
  "kind": "help",
  "role": "user",
  "body": "while 和 do-while 分不清\n\n[C-08 · 单选 · 本题已用 48s]",
  "ref": "q_xxx",
  "created_at": "2026-11-01T20:14:03"
}
```

## 3. 端点

| 方法 | 路径 | 谁调用 | 作用 |
|---|---|---|---|
| POST | `/api/agent/sessions` | Agent | 新建会话，返回 `session_id` |
| POST | `/api/quizzes` | Agent | 组卷，传 `agent_session_id` |
| GET | `/api/agent/feed?session_id=&after_id=` | 网页 | 拉新事件（5 秒轮询） |
| GET | `/api/agent/inbox?after_id=` | Agent | 拉取 `help` / `submitted` |
| POST | `/api/agent/events` | Agent | 写一条 `note` 提示 |
| POST | `/api/agent/help` | 网页 | 用户求助 |
| POST | `/api/attempts/{id}/submit` | 网页 | 交卷（服务端自动写 `submitted`） |
| POST | `/api/pages` | Agent | 发布一页 Markdown 讲义/大纲 |
| GET | `/api/pages` | 控制台 | 页面列表 |
| GET/PATCH/DELETE | `/api/pages/{id}` | Agent/控制台 | 读取 / 更新 / 删除 |
| POST | `/api/pages/{id}/complete` | 控制台 | 标记一课完成（+10 XP） |
| GET | `/api/progress` | 控制台/Agent | 连续天数、目标、XP |

## 4. 最小示例

```bash
# 1. 建会话
SID=$(curl -s -X POST localhost:8000/api/agent/sessions \
  -H 'Content-Type: application/json' \
  -d '{"title":"C 语言 · 循环结构"}' | python3 -c 'import sys,json;print(json.load(sys.stdin)["id"])')

# 2. 组卷
curl -s -X POST localhost:8000/api/quizzes \
  -H 'Content-Type: application/json' \
  -d "{\"mode\":\"practice\",\"count\":10,\"agent_session_id\":\"$SID\",
       \"filters\":{\"subject_id\":\"computer\",\"codes\":[\"C-08\"],\"types\":[\"single\",\"judge\"]}}"

# 3. 发一条提示
curl -s -X POST localhost:8000/api/agent/events \
  -H 'Content-Type: application/json' \
  -d "{\"session_id\":\"$SID\",\"body\":\"先做第 1 题，卡住就点「卡住了」。\"}"

# 4. 用户交卷后，Agent 读收件箱
curl -s "localhost:8000/api/agent/inbox?after_id=0"
```

## 5. MCP 工具（已实现）

`apps/mcp/server.py` 把上面的 HTTP 接口包成 stdio MCP 服务，工具名如下：

| MCP 工具 | 对应 HTTP |
|---|---|
| `list_subjects` | `GET /api/subjects` |
| `list_outline` | `GET /api/outline` |
| `create_agent_session` | `POST /api/agent/sessions` |
| `build_quiz` | `POST /api/quizzes` |
| `send_hint` | `POST /api/agent/events` |
| `read_inbox` | `GET /api/agent/inbox` |
| `get_attempt` | `GET /api/attempts/{id}` |
| `get_due_reviews` | `GET /api/reviews/due` |
| `get_stats_today` | `GET /api/stats/today` |
| `publish_page` | `POST /api/pages` |
| `update_page` | `PATCH /api/pages/{id}` |
| `list_pages` | `GET /api/pages` |
| `list_quizzes` | `GET /api/quizzes` |
| `get_progress` | `GET /api/progress` |

接入 OpenCode：

```bash
opencode mcp add kaodian --global \
  --env KAODIAN_API=http://127.0.0.1:8010 \
  --env KAODIAN_WEB=http://127.0.0.1:8010 \
  -- /path/to/kaodian/.venv/bin/python /path/to/kaodian/apps/mcp/server.py
```

接好后直接说「按 C-08 出 6 道」，Agent 会调用 `build_quiz` 并把链接发回来。

## 6. 边界

- 练习单**没有** `agent_session_id` 时，网页不显示协作条，`/api/agent/help` 返回 409。
- 网页只轮询**新**事件（`after_id`），不做已读回执；v0.1 够用。
- Agent 的 `note` 不区分「提示」和「讲解」，由 Agent 自己在正文里组织。
- 事件不存敏感信息：只有题目编号、用时、用户自己写的描述。

## 7. 题库与评分流水线

### 生成 → 审查 → 上架

```
AI 生成题目
  → POST /api/questions/batch
     入库 status = pending（格式校验已过）
  → GET /api/questions?status=pending
     交给 Agent 做语义审查
  → POST /api/questions/review { ids, decision: approve|reject, note }
     approve → status=approved，verified=1
     reject  → status=rejected，永不组卷
  → POST /api/quizzes
     只抽取 status = approved
```

审查要点：

1. `outline_code` 是否真的是这道题考的考点；
2. 客观题答案是否唯一、是否正确；
3. 解析是否能推出答案，而不是复述题干；
4. 主观题评分点是否可操作、总分是否等于满分；
5. 与已有题是否重复。

### 主观题评分

```
学生交卷
  → answer.response 写入
  → answer.score = NULL
  → attempt.grading_status = pending

Agent:
  GET  /api/grading/queue
  POST /api/grading/{attempt_id}/{question_id}
       { score, feedback }
  → answer.score / correct / graded_by='agent' / feedback 写回
  → attempt.score 重算；没有待评题时 grading_status=done
  → 结果页每 5 秒轮询刷新
```

评分依据是 `question.rubric` + `question.reference_answer` + `answer.response`。
学生自评 `self_grade` 只作为参考，不作为最终分。

### 新增 MCP 工具

| 工具 | 用途 |
|---|---|
| `create_questions` | 批量生成，入库待审 |
| `list_pending_questions` | 拉待审题（含答案/解析/评分点） |
| `review_questions` | 批量 approve / reject |
| `get_grading_queue` | 拉主观题待评分队列 |
| `grade_answer` | 写入分数与评语 |
