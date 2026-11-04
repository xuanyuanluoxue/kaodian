# IDE 工作流：内容、MCP 与浏览器

> 目标：在 IDE 终端里改内容包，校验/同步后，让同一台机器上的 MCP 客户端和浏览器
> 立刻看到结果。框架、内容、运行时数据三层分开。

## 三层位置

| 层 | 默认 | 说明 |
|---|---|---|
| 框架 | 本仓库 | 代码、CLI、示例内容，不含真实学科内容 |
| 内容 | `KAODIAN_CONTENT_DIR` / `kaodian.toml` | Markdown、题目 JSON、素材 |
| 数据 | `KAODIAN_DATA_DIR` | SQLite、导出、日志 |

优先级：环境变量 → 仓库根 `kaodian.toml` → `examples/demo-content` + `runtime/`。

```bash
cp kaodian.example.toml kaodian.toml
# [paths]
# content = "../kaodian-content"
# data = "../../kaodian-runtime"
```

## 0. 三根工作区

用 IDE 打开 `kaodian.code-workspace`，同时看到：

- `framework/`：代码、CLI、文档
- `content/`：讲义、题库、素材
- `runtime/`：数据库、导出（只读查看）

`.vscode/tasks.json` 提供 `validate / sync / serve / check` 四个任务，直接跑不用记路径。

## 1. 终端里改内容

```bash
cd /path/to/kaodian

bin/kaodian content list          # 有哪些 pack、版本、页数、题数
bin/kaodian content validate      # frontmatter、考点、题型、答案、素材
bin/kaodian content validate --json
bin/kaodian content sync          # 文件 → SQLite（自然键 UPSERT）
```

失败时退出码非 0，Agent 可以直接读 `--json` 的 `{ok, packs:[{id, errors}]}`。

改内容的常见循环：

1. 改 `packs/<id>/lessons/*.md` 或 `questions/*.json`；
2. `bin/kaodian content validate`；
3. `bin/kaodian content sync`；
4. 浏览器刷新对应页面/题库。

`content sync` 不写内容仓库，也不删除本地创建的页面/题目。要下线内容，把
frontmatter 改成 `status: archived`，不要从库里硬删。

## 2. 起服务

```bash
bin/kaodian serve                 # 默认 127.0.0.1:8010，API + 前端构建产物
bin/kaodian serve --reload        # 开发时热重载
bin/kaodian doctor --json         # 路径、DB 版本、pack 状态
```

如果只调后端/前端，仍可用 `make dev-api` + `make dev-web`。

## 3. IDE 接 MCP

```bash
bin/kaodian mcp-config            # 输出可直接粘贴的 JSON
```

典型配置：

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

MCP 只调 HTTP API，不直接读 SQLite。浏览器和 MCP 看到的是同一份运行时数据。

## 4. 浏览器里学

1. 在 IDE 里让 Agent 组卷（MCP `build_quiz`）；
2. 打开返回的 `url`，在浏览器答题；
3. 交卷后 Agent 通过 `read_inbox` 收到结果；
4. 主观题用 `get_grading_queue` / `grade_answer` 回写分数；
5. 讲义页在控制台阅读，素材走 `/media/<pack>/<file>`。

## 5. 迁移真实数据

```bash
# 1. 停服务
# 2. 备份旧库（路径按实际）
bin/kaodian backup --db /path/to/old/kaodian.db --out /path/to/backup.db
# 3. 指到 runtime 后启动；v3→v4 会自动再备份并迁移
KAODIAN_DB=/path/to/runtime/kaodian.db bin/kaodian serve
# 4. 回填 pack_id / source_key，确认没有重复页/题
bin/kaodian content sync
bin/kaodian doctor --json
```

迁移只加列/建表，不重建表；备份文件是 `*.bak-v{old}-{时间}`。
