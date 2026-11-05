# 考点 · Kaodian

> **在 IDE 里让 AI 出题、改讲义、给提示；在浏览器里阅读、作答、计时。**
> 本地优先、无账号，代码、内容、用户数据三层彻底分开。

考点是一个跑在自己电脑上的学习终端：内容是可版本化的 Markdown / JSON，
进度存在本地 SQLite，AI 通过 MCP 读写同一套内容与数据。适合需要长期备考、
又不想把学习记录交给第三方平台的人。

## 能做什么

- **IDE 是控制面**：Agent 通过 MCP 查考纲、出题、审题、组卷、推提示、改讲义、判主观题。
- **网页是学习面**：今日路径、讲义阅读、计时答题、错题复习、分科统计、学习画像。
- **内容即文件**：一课一个 Markdown，题目按考点分 JSON，素材放 `assets/`；Git 可审、可回滚。
- **本地优先**：FastAPI + SQLite + React，默认只绑 `127.0.0.1`，不需要账号。
- **AI 可补全画像**：目标院校、分科目标分、阶段计划都能在对话里补齐，再落到本地。

## 三层边界

```
kaodian/
├── apps/                 框架：web / api / mcp / cli（公开）
├── starter-content/      起始内容：四科各 3 页讲义 + 71 题（公开）
├── content/              完整内容仓库（可选，独立 git，不进框架仓库）
└── data/                 运行时数据：数据库、备份、导出（不进 Git）
```

| 层 | 放什么 | 怎么重建 |
|---|---|---|
| 框架 | 代码、CLI、文档 | Git 版本化 |
| 内容 | 讲义、题库、素材 | 文件是源，数据库只是索引 |
| 数据 | 作答、复习、画像、统计 | 只能备份，删库即丢进度 |

## 快速开始

需要 Python 3.11+、Node 20.19+。

```bash
git clone https://github.com/xuanyuanluoxue/kaodian.git kaodian
cd kaodian
make setup
bin/kaodian content validate
bin/kaodian serve --port 8010
# 打开 http://127.0.0.1:8010
```

仓库自带 `starter-content/`，clone 完就能阅读、作答、看统计，不需要再找题库。

### 接自己的完整内容

把内容仓库放到项目根的 `./content`，再指定路径：

```bash
git clone <你的内容仓库> content
cp kaodian.example.toml kaodian.toml     # [paths] content = "./content"
bin/kaodian content sync
```

`content/` 与 `kaodian.toml` 都不进框架仓库；`data/` 始终不进 Git。

### 接到 IDE

```bash
bin/kaodian mcp-config
```

把输出的 JSON 加到 IDE 的 MCP 配置即可。运行中的服务默认是
`KAODIAN_API=http://127.0.0.1:8010`，MCP 只调 API，不直接碰数据库。

## 内容长什么样

一页讲义 = 一个 Markdown 文件 + frontmatter；题目按考点分成 JSON；图片放
`assets/`，正文用 `/media/<pack>/...` 引用。新增一科只加一个 pack，新增一页
只加一个 Markdown，不用改框架代码。

格式细节（frontmatter、块类型、图表规范）见 `docs/content/format.md` 与
`docs/dev/blocks.md`。

> `starter-content/` 由 `scripts/export-starter-content.py` 从完整内容仓库导出，
> 不要手改；更新完整内容后重新导出即可。

## 文档

- **开发者 / AI 协作者**：先读 [`AGENTS.md`](AGENTS.md)，里面有仓库地图、命令、边界和验收清单。
- 产品与路线：`docs/product/`
- 开发契约：`docs/dev/`
- IDE / MCP 接入：`docs/ai/`
- 内容格式：`docs/content/format.md`、`docs/dev/blocks.md`

README 面向使用者；工程约定集中在 `AGENTS.md`，两处不重复维护。
改完代码跑 `make check`（pytest + 前端 lint + build）。

## 安全与许可

- 默认只绑 `127.0.0.1`，没有账号体系，不要直接暴露公网。
- 代码沙箱默认关闭；需要时用 `KAODIAN_ALLOW_CODE_RUN=1`。
- 代码 MIT；`starter-content/` 与各 pack 的素材许可见对应 `LICENSES.md`。
- 真题只用改编版，不收录原卷。
