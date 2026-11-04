# 考点 · Kaodian

> **Agent 的作答终端。** 在 IDE 里让 Agent 出题、改讲义、给提示；在网页上阅读、作答、计时；结果通过 MCP 回传。
> 本地优先、无账号、内容与用户数据彻底分开。

## 一个项目根，三层边界

```
kaodian/
├── apps/                 框架仓库（公开）：web / api / mcp / cli
├── content/              内容仓库（公开，独立 git）：讲义 / 题库 / 素材
└── data/                 运行时数据（不进 Git）
    ├── api/              kaodian.db、backups、exports
    ├── web/              uploads
    ├── mcp/              logs
    ├── cli/              cache
    └── shared/           logs、sandbox
```

| 层 | 内容 | 能否重建 |
|---|---|---|
| 框架 | `apps/{web,api,mcp,cli}` | 代码，Git 版本化 |
| 内容 | `content/packs/<科目>/` | 文件是源，DB 只是索引 |
| 数据 | `data/api/kaodian.db`、备份、导出 | 用户数据，只能备份 |

## 快速开始

需要 Python 3.11+、Node 20.19+。

```bash
git clone <framework> kaodian
cd kaodian
git clone <content> content
make setup
bin/kaodian content validate
bin/kaodian serve --port 8010
# http://127.0.0.1:8010
```

`content/` 是独立 git 仓库，被框架的 `.gitignore` 排除；`data/` 整个目录也不进 Git。
不克隆内容时，默认加载 `examples/demo-content`，数据写到 `./data/`，用于试跑。

## IDE 是控制面

```bash
bin/kaodian content list          # 看有哪些 pack
bin/kaodian content validate      # 校验讲义/题库/素材
bin/kaodian content sync          # 文件 -> DB 索引
bin/kaodian doctor --json         # 路径、DB 版本、pack 状态
bin/kaodian mcp-config            # 输出 IDE 的 MCP 配置
```

AI 在 IDE 里改内容文件、跑上面命令；运行时通过 MCP 调 API：

```bash
opencode mcp add kaodian --global \
  --env KAODIAN_API=http://127.0.0.1:8010 \
  -- -- /path/to/kaodian/.venv/bin/python /path/to/kaodian/apps/mcp/server.py
```

## 内容包

```
content/
├── registry.json
└── packs/math/
    ├── pack.json          # 科目、版本、考试参数
    ├── outline.json       # 考纲节点
    ├── lessons/*.md       # frontmatter + Markdown
    ├── questions/*.json
    ├── assets/*           # /media/math/xxx.svg
    └── LICENSES.md
```

新增一科只加一个 pack；新增一页只加一个 Markdown；不用改框架代码。

## 目录

```
apps/web/      前端（React + Vite + TS）
apps/api/      后端（FastAPI + SQLite）
apps/mcp/      AI 桥（stdio MCP）
apps/cli/      kaodian 命令
bin/kaodian    CLI 入口
config/        框架默认配置（题型注册表）
docs/          产品 / 开发 / AI / 内容
examples/      演示内容包（测试与首次启动）
```

## 验证

```bash
make check     # pytest + 前端 lint + build
```

## 安全与许可

- 默认只绑 `127.0.0.1`，无账号体系，不要暴露公网。
- 代码沙箱默认关闭，`KAODIAN_ALLOW_CODE_RUN=1` 才启用。
- 代码 MIT；内容与素材许可见内容仓库的 `LICENSES.md` 和各 pack 的 `LICENSES.md`。
- 真题只用改编版，不收录原卷。
