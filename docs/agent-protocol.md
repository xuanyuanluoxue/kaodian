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

## 5. MCP 工具映射（下一步）

| MCP 工具 | 对应 |
|---|---|
| `create_agent_session` | `POST /api/agent/sessions` |
| `build_quiz` | `POST /api/quizzes` |
| `send_hint` | `POST /api/agent/events` |
| `read_inbox` | `GET /api/agent/inbox` |
| `get_attempt` | `GET /api/attempts/{id}` |

## 6. 边界

- 练习单**没有** `agent_session_id` 时，网页不显示协作条，`/api/agent/help` 返回 409。
- 网页只轮询**新**事件（`after_id`），不做已读回执；v0.1 够用。
- Agent 的 `note` 不区分「提示」和「讲解」，由 Agent 自己在正文里组织。
- 事件不存敏感信息：只有题目编号、用时、用户自己写的描述。