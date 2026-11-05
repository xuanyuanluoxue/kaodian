# AGENTS.md — AI 工作手册

> **这是 AI / 协作者进入本仓库的唯一入口。**
> `README.md` 面向人类用户，只讲产品与安装；工程约定、代码地图、命令、边界全部记在这里。
> 两处不重复：遇到冲突，以本文件为准；改动接口或路径时，同步更新本文件和相关 `docs/`。

## 0. 项目一句话

考点（Kaodian）是本地学习终端：FastAPI + SQLite + React；IDE 里的 Agent 通过 MCP
出题、审题、组卷、改讲义、判主观题；浏览器负责阅读、作答、计时；**API 是唯一写库路径**。

## 1. 先判断改哪一层

| 任务 | 主目录 | 先读 |
|---|---|---|
| 前端 / 后端 / MCP / CLI | `apps/`、`bin/` | `docs/dev/architecture.md`、`docs/dev/api.md` |
| 讲义 / 题库 / 素材 / 考纲 | `content/`（或 `starter-content/` 的源） | `docs/dev/content-packs.md`、`docs/content/format.md` |
| 讲义版式 / 交互块 | `apps/web/src/components/blocks/` | `docs/dev/blocks.md` |
| 学习画像 / 目标 / 阶段 | `apps/api/app/profile.py`、`apps/web/src/pages/Profile.tsx` | `docs/dev/profile.md` |
| 复习算法 / 判分 | `apps/api/app/review.py`、`grading.py` | `docs/dev/architecture.md` |
| 数据库 / 迁移 | `apps/api/app/schema.sql`、`db.py` | `docs/dev/architecture.md` |
| IDE / MCP 接入 | `apps/mcp/server.py` | `docs/ai/integration.md`、`docs/ai/pipelines.md` |
| 产品 / 路线 | `docs/product/` | `docs/product/overview.md`、`final-state.md` |
| 随框架分发的起始内容 | `scripts/export-starter-content.py` | 本文件 §6、§7 |

## 2. 仓库地图

```
kaodian/
├── apps/
│   ├── web/                  React + Vite + TS；页面、组件、API 客户端
│   ├── api/                  FastAPI + SQLite；唯一写库入口
│   ├── cli/                  `kaodian` 命令实现
│   └── mcp/                  MCP 服务（stdio / HTTP），只调 API
├── bin/kaodian               CLI shell 入口
├── config/question_types.json 题型注册表（single/multiple/judge/fill/short/calc/code）
├── starter-content/          公开的起始内容（12 页 / 71 题 / 6 素材）
├── examples/demo-content/    测试专用最小内容包
├── content/                  完整内容仓库（可选，独立 git，被 .gitignore 排除）
├── data/                     运行时数据（被 .gitignore 排除，仅 README 入库）
├── docs/                     产品 / 开发 / AI / 内容文档
├── scripts/                  导出 starter-content 等维护脚本
├── kaodian.example.toml      本机路径配置示例；kaodian.toml 不入库
├── Makefile                  setup / test / lint / build / check / docker
└── .github/workflows/ci.yml  后端 pytest + 前端 lint/build
```

关键入口：

| 文件 | 作用 |
|---|---|
| `apps/api/app/main.py` | 全部 HTTP 路由、Pydantic 入参、SPA 托管、`/media` |
| `apps/api/app/paths.py` | 内容 / 数据 / 数据库路径解析，默认 `starter-content` + `data/` |
| `apps/api/app/content.py` | pack 读取、校验、UPSERT 同步 |
| `apps/api/app/db.py` | 连接、v2→v9 迁移、配置目录 |
| `apps/api/app/schema.sql` | 当前表结构（幂等执行） |
| `apps/api/app/grading.py` | 自动判分、题目校验 |
| `apps/api/app/review.py` | 掌握度与复习间隔 |
| `apps/api/app/profile.py` | 画像读写、完整度、阶段计算 |
| `apps/cli/__main__.py` | `serve/content/doctor/backup/mcp/profile/mcp-config` |
| `apps/mcp/server.py` | 27 个 MCP 工具，全部转发到 API |
| `apps/web/src/api.ts` | 前端唯一 API 客户端 |

前端页面：

| 路由 | 页面 | 作用 |
|---|---|---|
| `/` | `pages/Today.tsx` | 今日路径、到期复习、快捷入口 |
| `/console` | `pages/Console.tsx` + `console/` | 讲义阅读、目录、阅读计时 |
| `/edit/:pageId` | `pages/PageEditor.tsx` + `editor/` | 块编辑器、草稿保存与发布 |
| `/build` | `pages/Build.tsx` | 组卷、选题、材料题 |
| `/quiz/:quizId` | `pages/Quiz.tsx` + `quiz/` | 答题、计时、提示 |
| `/result/:attemptId` | `pages/Result.tsx` | 交卷结果与逐题解析 |
| `/review` | `pages/Review.tsx` | 到期复习 |
| `/stats` | `pages/Stats.tsx` | 分科、热力图、题型统计 |
| `/profile` | `pages/Profile.tsx` | 画像、志愿表、阶段计划 |

## 3. 硬边界（不要破坏）

- **框架仓库不放完整学科内容**；完整内容在 `content/`，独立 Git，被框架 `.gitignore` 排除。
- **`starter-content/` 是导出的公开子集**，不要手改；改完整内容后运行
  `python3 scripts/export-starter-content.py --source content --dest starter-content`。
- **`examples/demo-content/` 只服务测试**，不要拿它当正式内容。
- **`data/` 不进 Git**：数据库、备份、导出、日志、画像种子都在里面，只有 `data/README.md` 入库。
- **`kaodian.toml` 是本机配置**，不入库；示例放 `kaodian.example.toml`。
- **MCP 不直接连库**：它只调 API；浏览器也只调 API；迁移与写入都在 API 内完成。
- **同步不删本地数据**：`content sync` 只 UPSERT 内容包命中的行；`pack_id IS NULL`
  的本地页面 / 题目保留。pack 内下线内容用 frontmatter `status: archived`，不要删库。
- **不把 `data/` 内容读进上下文**，除非用户明确要求排查某条作答记录。

## 4. 环境与命令

需要 Python 3.11+（当前 3.12，见 `.python-version`）、Node 20.19+（当前 24，见 `.nvmrc`）。

```bash
make setup          # venv + 后端依赖 + 前端 npm ci
make dev-api        # API :8000（开发）
make dev-web        # Vite :5173，/api 代理到 :8000
make check          # pytest + 前端 lint + build（提交前必跑）
bin/kaodian serve --port 8010   # 生产式启动：API + 托管 apps/web/dist
```

CLI：

```bash
bin/kaodian content list
bin/kaodian content validate
bin/kaodian content sync
bin/kaodian doctor --json
bin/kaodian backup
bin/kaodian profile show --json
bin/kaodian profile export [--output data/profile.json]
bin/kaodian profile import <file>
bin/kaodian mcp --transport stdio|http|sse
bin/kaodian mcp-config
```

路径优先级：**环境变量 → `kaodian.toml` → 默认 `starter-content/` + `data/`**。

| 变量 | 默认 | 说明 |
|---|---|---|
| `KAODIAN_CONTENT_DIR` | `starter-content/` | 内容根目录（含 `registry.json`） |
| `KAODIAN_DATA_DIR` | `data/` | 数据库、备份、日志根目录 |
| `KAODIAN_DB` | `<data>/api/kaodian.db` | SQLite 路径，优先级最高 |
| `KAODIAN_CONFIG_DIR` | `config/` | 题型注册表目录 |
| `KAODIAN_API` / `KAODIAN_WEB` | `http://127.0.0.1:8010` | MCP 访问的 API / 页面地址 |
| `KAODIAN_MCP_TRANSPORT` | `stdio` | `stdio` / `http` / `sse` |
| `KAODIAN_MCP_HOST` / `PORT` | `127.0.0.1` / `8020` | HTTP 模式监听地址 |
| `KAODIAN_ALLOW_CODE_RUN` | `0` | `1` 才启用代码沙箱 |
| `KAODIAN_DAILY_GOAL_MINUTES` | `30` | 仅在画像没有 `daily_minutes` 时兜底 |
| `KAODIAN_CORS_ORIGINS` | 仅本机开发源 | 逗号分隔 |

Docker：

```bash
make docker           # compose，默认挂载 ./starter-content 与 ./data
make docker-sandbox   # INSTALL_SANDBOX=1 + KAODIAN_ALLOW_CODE_RUN=1
```

容器内 `/content`、`/data`；宿主机非 1000 用户需传 `KAODIAN_UID/GID`。

## 5. 代码与数据地图

### API 路由（按用途）

- 内容：`/api/subjects`、`/api/outline`、`/api/questions`、`/api/questions/batch`、
  `/api/questions/review`、`/api/question-groups*`、`/api/content/validate`
- 练习：`/api/quizzes*`、`/api/attempts*`、`/api/reviews/due`
- 判分：`/api/grading/queue`、`/api/grading/{attempt_id}/{question_id}`
- 讲义：`/api/pages*`（含 `/draft`、`/draft/stream`、`/publish`、`/complete`）
- 统计：`/api/stats/{today,subjects,heatmap,types,library}`、`/api/export`、`/api/import`
- 画像：`GET/PUT /api/profile`
- 进度：`/api/progress`、`/api/activity`
- Agent：`/api/agent/{sessions,events,feed,stream,inbox,help}`
- 静态：`/media/{pack_id}/{path}`、`/sandbox/{page_id}/{index}`、SPA 兜底

### 数据表（schema v9）

`content_pack`、`subject`、`outline_node`、`question`、`question_group`、
`question_outline`、`quiz`、`quiz_item`、`attempt`、`answer`、`review`、
`page`、`page_progress`、`page_draft`、`study_time`、`profile`、
`agent_session`、`agent_event`。

- `question.status`：`pending / approved / rejected`；MCP 出的题先入库为 pending，
  `review_questions` 审查后才能组卷。
- `page` 存内容索引与 `file` 相对路径；网页编辑先写 `page_draft`，发布时才写文件。
- 迁移顺序：启动时备份旧库 → 增量迁移 → 幂等执行 `schema.sql` → 内容同步。

### MCP 工具（27 个）

- 读：`list_subjects`、`list_outline`、`list_pending_questions`、`get_grading_queue`、
  `list_pages`、`list_quizzes`、`get_stats_today`、`get_progress`、`get_profile`、
  `get_due_reviews`、`get_attempt`、`get_question_group`、`read_inbox`、`get_page_draft`
- 出题：`create_agent_session`、`create_questions`、`create_question_group`、
  `review_questions`、`build_quiz`
- 辅导：`send_hint`
- 内容：`publish_page`、`update_page`、`save_page_draft`、`publish_page_draft`、
  `validate_content`
- 判分 / 画像：`grade_answer`、`update_profile`

材料题先 `create_question_group` 建组，再用 `create_questions` 传
`group_id` / `group_position` 挂题。组卷用 `build_quiz`，把返回的 `url` 交给用户。

## 6. 内容格式

命名：目录与文件名一律英文小写 kebab-case；中文只出现在标题字段。

- 讲义：`packs/<id>/lessons/<lesson-key 小写>-<slug>.md`（或 `.json` 块页）
- 题目：`packs/<id>/questions/<outline-code 小写>.json`
- 素材：`packs/<id>/assets/<topic>.svg`；正文写 `/media/<pack>/<file>`

Markdown frontmatter：

```yaml
lesson_key: "M02-1"
title: "导数 1/7 · 定义与切线"
summary: "一句话"
kind: "lesson"          # lesson | outline | note | daily
status: "published"     # draft | published | archived
sort_order: 201
outline_codes: ["M-09"]
layout: "article"       # article | wide | split | slides | dashboard
theme: '{"accent":"math","density":"comfortable"}'
```

题目的核心字段（`QuestionIn`）：`outline_code`、`outline_codes`、`subject_id`、`type`、
`stem`、`options`、`answer`、`explanation`、`reference_answer`、`rubric`、`score`、
`difficulty`、`source`、`tags`、`verified`、`language`、`group_id`、`group_position`、
`media`、`client_ref`。`id` 用作稳定 key。

块页字段见 `docs/dev/blocks.md`；块类型：`markdown`、`callout`、`columns`、`tabs`、
`steps`、`cards`、`timeline`、`image`、`video`、`audio`、`code`、`mermaid`、
`math-graph`、`sandbox`、`divider`。

内容约定：

- 一课一概念，正文 ≤120 行，10–15 分钟；3 个递进例子；每页 3–5 道自测。
- 正文只用 Markdown；Mermaid 画结构，GFM 表格，SVG 放 `assets/`，`math-graph` 做交互。
- 不内嵌任意 HTML / iframe（需要实验时用 `sandbox` 块）。
- 素材必须登记许可证；真题只写改编版并注明来源。

## 7. 改内容的正确流程

1. 在 `content/packs/<id>/` 改 Markdown / JSON / 素材；不要改 `starter-content/`。
2. 跑 `bin/kaodian content validate`。
3. 需要入库时跑 `bin/kaodian content sync`（或重启服务，启动会自动同步）。
4. 若公开子集应包含这页/这些题，更新 `scripts/export-starter-content.py` 里的
   `LESSONS` 映射后重新导出，并再校验 `starter-content/`。
5. 内容仓库独立提交；框架仓库只提交导出结果与脚本变更。

网页编辑走草稿层：`save_page_draft` / `PUT /api/pages/{id}/draft` 只写
`page_draft`；`publish_page_draft` / `POST /api/pages/{id}/publish` 才写回内容文件。
不要直接改数据库里的页面正文。

## 8. 学习画像（profile v3）

- 静态目标在 `profile` 单行表；动态学情实时从 `attempt` / `answer` / `study_time` 算，
  不落冗余字段。
- 必填：`target_exam`、`target_date`、`target_score`、`targets`、`target_major`、
  `daily_minutes`、`subjects`、`motivation`。
- 可选：地区、满分、分科目标、硬线、阶段（`P1/P2/P3`）、阶段起止与日均、总预算小时、
  升学类型、学习条件、优劣势、教学偏好等。
- `targets` 是按志愿顺序的数组，`tier` 只能是 `冲/稳/保/兜底`，最多 8 条；
  写入后同步 `target_school` / `backup_school`。
- `subject_targets` 的键必须是已存在科目；分数范围 0–`exam_total`。
- `phase_*` 只表示当前执行档位，换阶段覆盖，不保留历史。
- AI 补画像用 `update_profile(source="agent", ai_summary="...")`；一次问 2–3 个问题，
  从目标院校/专业/动机开始，再问时间与薄弱点。
- 导入导出：`bin/kaodian profile export/import`，文件默认 `data/profile.json`，不入 Git。

## 9. 测试、CI 与提交

```bash
make check                     # pytest + 前端 lint + build
.venv/bin/python -m pytest -q  # 只跑后端
```

测试文件：

| 文件 | 覆盖 |
|---|---|
| `test_api.py` | 路由、组卷、作答、导出、SPA 兜底 |
| `test_content.py` | pack 校验、路径解析、同步 |
| `test_editing.py` | 页面草稿与发布 |
| `test_block_pages.py` / `test_blocks.py` | 块页与块校验 |
| `test_profile.py` | 画像字段、完整度、阶段、迁移 |
| `test_export_stats.py` | 导出与统计 |

CI（`.github/workflows/ci.yml`）分 backend（Python 3.12 + pytest）与 frontend
（Node 24 + lint + build）两个 job。后端 job **不构建** `apps/web/dist`，涉及 SPA
兜底的测试要容忍 dist 不存在。

提交约定：

- Conventional Commits，中文描述，例如 `fix(api): 每日目标读取画像而不是环境变量`。
- 一个提交只做一件事；内容仓库与框架仓库分开提交。
- 子 Agent 不 commit；主 Agent 验收后统一提交。
- 提交前确认 `git status` 不含 `data/`、`content/`、`kaodian.toml`、`.venv/`。
- 不提交密钥、真实姓名、个人院校与绝对路径；示例用「示例大学 A/B/C/D」。

## 10. 编码约定

- Python：3.12、类型标注、`sqlite3` 直连、Pydantic 入参；不引入 ORM。
- 新依赖要克制：先看标准库与现有依赖能否解决；锁文件用 `constraints.txt` / `package-lock.json`。
- 前端：React + TypeScript + Vite，函数组件；样式写 `styles.css`，不引入 UI 框架；
  所有请求走 `src/api.ts`。
- 标识符、文件名用英文；界面文案、错误提示、文档用中文。
- 新增题型改 `config/question_types.json`，同时检查判分、前端渲染与测试。
- 改动路径、环境变量、API、MCP 工具时，同步 `docs/dev/`、`docs/ai/` 与本文件。

## 11. 禁止事项

- 不把 `data/`、数据库、作答记录、密钥提交到任何仓库。
- 不把完整题库塞回框架仓库；公开仓库只带 `starter-content/` 子集。
- 不绕过 API 直接写 SQLite（迁移与备份脚本除外）。
- 不把服务绑到 `0.0.0.0` / 公网；本项目没有账号与鉴权。
- 不在未确认时启用代码沙箱或放宽 Docker 权限。
- 不用未改编真题原卷；不伪造考频、分数线和来源。
- 不手改 `starter-content/`；不要为了让测试过而删掉安全断言。

## 12. 交付检查清单

- [ ] 改对了层：框架 / 内容 / 数据没有混。
- [ ] `make check` 通过（内容改动另跑 `content validate`）。
- [ ] 内容改动已同步；需要公开时已重新导出 `starter-content/`。
- [ ] 路径 / 接口 / 环境变量变更已同步文档。
- [ ] `git status` 干净，未带入 `data/`、`content/`、`kaodian.toml`。
- [ ] 报告写清：改了哪些文件、验证结果、剩余风险。
