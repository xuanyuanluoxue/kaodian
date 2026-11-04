# AI 如何运行在这个项目里

## 一句话

**AI 不在网页里跑。** 它是 IDE / 终端里的 MCP 客户端，通过 stdio 启动 `apps/mcp/server.py`，再由这个桥去调本地 API。网页只是它让你作答的终端。

```mermaid
flowchart LR
  Chat["IDE / 对话窗口"] -->|MCP stdio| MCP["apps/mcp/server.py"]
  MCP -->|HTTP| API["apps/api"]
  Browser["浏览器 / 手机"] -->|HTTP| API
  API --> DB[("data/api/kaodian.db")]
  API --> Sandbox["gcc + bubblewrap"]
```

## 三种角色

| 角色 | 跑在哪 | 做什么 |
|---|---|---|
| 对话 Agent | IDE 插件 / 终端 / Claude Desktop | 决定学什么、出题、给提示、读结果、评分 |
| MCP 桥 | 本机 Python 进程（由 Agent 启动） | 把 API 包装成 25 个工具 |
| 学习终端 | 浏览器 | 显示讲义、答题、计时、把事件写回 API |

## 常见 IDE / 客户端

| 宿主 | 接入方式 |
|---|---|
| **OpenCode**（当前使用） | `opencode mcp add …` |
| Claude Desktop | `claude_desktop_config.json` 里配 `mcpServers` |
| Cursor | Settings → MCP → 添加 stdio server |
| VS Code（Cline / Continue） | 在扩展的 MCP 配置里加 stdio server |
| JetBrains AI Assistant | 支持 MCP 的版本里添加 stdio server |

> 不需要为本项目写 IDE 插件。任何支持 MCP stdio 的客户端都能接。

## 接入命令（OpenCode）

```bash
opencode mcp add kaodian --global \
  --env KAODIAN_API=http://127.0.0.1:8010 \
  --env KAODIAN_WEB=http://127.0.0.1:8010 \
  -- /path/to/kaodian/.venv/bin/python /path/to/kaodian/apps/mcp/server.py
```

Claude Desktop 的等价配置：

```json
{
  "mcpServers": {
    "kaodian": {
      "command": "/path/to/kaodian/.venv/bin/python",
      "args": ["/path/to/kaodian/apps/mcp/server.py"],
      "env": {
        "KAODIAN_API": "http://127.0.0.1:8010",
        "KAODIAN_WEB": "http://127.0.0.1:8010"
      }
    }
  }
}
```

> 改完配置后 OpenCode 一般会自动重载；工具列表没更新就 `/reload` 或开新会话。

## 工具（25 个）

| 分类 | 工具 |
|---|---|
| 读 | `list_subjects` `list_outline` `list_pages` `list_quizzes` `get_attempt` `get_due_reviews` `get_stats_today` `get_progress` |
| 出题 | `create_questions` `list_pending_questions` `review_questions` |
| 组卷 | `create_agent_session` `build_quiz` |
| 协作 | `send_hint` `read_inbox` |
| 评分 | `get_grading_queue` `grade_answer` |
| 讲义 | `publish_page` `update_page` |
| 网页编辑 | `get_page_draft` `save_page_draft` `publish_page_draft` `validate_content` |

## 一次典型循环

1. 你说「按 C-08 出 6 道」；
2. Agent 调 `list_outline` 确认编号，`build_quiz` 组卷，把链接发你；
3. 你打开链接作答，卡住点「卡住了」；
4. Agent 用 `read_inbox` 读到求助，用 `send_hint` 推提示；
5. 交卷后 Agent 用 `read_inbox` / `get_attempt` 读结果；
6. 主观题进 `get_grading_queue`，Agent 用 `grade_answer` 写回分数。

## 为什么不让 AI 直接写数据库

- 网页和 AI 共用一套校验/判分/复习逻辑；
- AI 只传结构化参数，不碰 SQL；
- 出题先进 `pending`，审核后才上架；
- 代码执行走独立沙箱。

## 安全边界

- 默认只绑 `127.0.0.1`，没有账号体系，**不要暴露公网**
- `KAODIAN_ALLOW_CODE_RUN=1` 才启用代码沙箱；即使启用也是断网 + 只读系统
- MCP 的 `KAODIAN_API` 指向本地；不要让远程客户端直连
- AI 写的讲义/题目是**内容**，发布前由主 Agent 审查

协议细节（事件、字段、错误码）见 [`protocols/agent.md`](protocols/agent.md)。
