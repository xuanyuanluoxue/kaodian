# 内容包与路径契约（C 方案）

> 框架、内容、运行时数据三层分离。框架仓库不包含任何一科内容；内容仓库不包含代码和用户数据。

## 1. 路径解析

优先级从高到低：

1. 环境变量 `KAODIAN_CONTENT_DIR` / `KAODIAN_DATA_DIR` / `KAODIAN_DB`
2. 框架根目录的 `kaodian.toml`
3. 默认：`examples/demo-content` + `data/`

```toml
# kaodian.toml（本机配置，不提交）
[paths]
content = "./content"
# data = "./data"   # 默认就是 ./data
```

`kaodian.example.toml` 入库，`kaodian.toml` 进 `.gitignore`。

- `data_dir` 默认 `./data`，按模块分：`api/`、`web/`、`mcp/`、`cli/`、`shared/`。
- `db_path` = `KAODIAN_DB` 或 `data/api/kaodian.db`。
- 启动时 `data_dir.mkdir(parents=True, exist_ok=True)`。

## 2. 内容仓库

```
content/
registry.json
packs/<id>/
  pack.json
  outline.json
  lessons/*.md|*.json
  questions/*.json
  assets/*
  LICENSES.md
```

`registry.json`：

```json
{"schema": 1, "packs": [{"id": "math", "path": "packs/math"}]}
```

`pack.json`：

```json
{
  "id": "math",
  "name": "高等数学",
  "version": "1.0.0",
  "schema": 1,
  "subject": {
    "id": "math", "name": "高等数学", "short": "高数",
    "color": "#2f5d8a", "icon": "sigma", "sort": 2,
    "exam": {"score": 100, "minutes": 120}
  }
}
```

`outline.json`：节点数组，字段与 `outline_node` 一致（`code/title/section/...`）。

`lessons/*.md`：frontmatter + Markdown，字段：

```yaml
---
lesson_key: "M02-1"
title: "导数 1/7 · 定义与切线"
summary: "一句话"
kind: "lesson"          # lesson | outline | note | daily
status: "published"     # draft | published | archived
sort_order: 201
outline_codes: ["M-09"]
layout: "article"       # article | wide | split | slides | dashboard（可选）
theme: '{"accent":"math","density":"comfortable"}'  # 可选，JSON 字符串或对象
---
```

`lessons/*.json`：整个文件是一个 lesson 对象，字段与 Markdown frontmatter 相同，
额外带 `blocks`（块数组）；`format` 固定为 `blocks`。同一个 pack 里 `lesson_key`
跨 `.md`/`.json` 唯一，两种文件二选一。

```json
{
  "lesson_key": "M02-2",
  "title": "导数 2/7 · 四则运算",
  "kind": "lesson",
  "status": "published",
  "sort_order": 202,
  "outline_codes": ["M-09"],
  "layout": "wide",
  "theme": {"accent": "math"},
  "blocks": [{"type": "markdown", "text": "# 块页"}]
}
```

Markdown 页同步为 `format='markdown'`、`blocks=NULL`；JSON 块页同步为
`format='blocks'`，并写入 `blocks/layout/theme`。块结构见
[`blocks.md`](blocks.md)。

`questions/*.json`：题目数组，字段与 `QuestionIn` 一致；`id` 用作稳定 key。

素材：正文写 `/media/<pack>/<file>`，文件在 `packs/<pack>/assets/`。
框架前端只保留 UI 素材（favicon、图标），不再放任何学科图片。

## 3. 数据库 v6

v4 新增：

| 表 | 列 |
|---|---|
| `subject` | `pack_id`, `source_key` |
| `outline_node` | `pack_id` |
| `question` | `pack_id`, `source_key` |
| `page` | `pack_id`, `source_key` |

新增 `content_pack(id, name, version, schema, path, synced_at)`。

v5 只给 `page` 加列，不重建表：

| 列 | 类型/默认值 | 说明 |
|---|---|---|
| `blocks` | `TEXT` | JSON 块数组；Markdown 页为 `NULL` |
| `layout` | `TEXT NOT NULL DEFAULT 'article'` | article / wide / split / slides / dashboard |
| `theme` | `TEXT` | JSON 对象；无主题为 `NULL` |
| `format` | `TEXT NOT NULL DEFAULT 'markdown'` | markdown / blocks |

v6 只给 `page` 加一列并新增草稿表，不重建表：

| 对象 | 说明 |
|---|---|
| `page.file` | `TEXT`；内容文件相对 `content/` 的路径，例如 `packs/math/lessons/M02-1.md`；本地页为 `NULL` |
| `page_draft` | `page_id, body, blocks, layout, theme, version, updated_at`；只存未发布的修改，发布后删除 |

草稿与发布契约见 [`editing.md`](editing.md)。

旧库迁移前自动备份为 `*.bak-v{old}-{时间}`。

唯一索引（partial，`pack_id IS NOT NULL`）：

- `subject(pack_id, source_key)`
- `question(pack_id, source_key)`
- `page(pack_id, source_key)`

同步时按自然键匹配旧数据，避免重复：

- subject：`id`
- outline：`code`
- question：`id`，没有则 `fingerprint`
- page：`subject_id + lesson_key`；outline 页用 `subject_id + kind='outline'`

只更新/插入带 `pack_id` 的行；本地运行时创建的页面/题目（`pack_id IS NULL`）不动、不删。
pack 里删除的内容不自动删库，改 frontmatter `status: archived`。

## 4. 媒体

`GET /media/{pack}/{path:path}`：

- 根目录 `content_dir/packs/<pack>/assets/`
- `resolve()` 后必须在根目录内，禁止 `../`
- 只返回文件
- `Cache-Control: public, max-age=31536000, immutable`

## 5. CLI

`bin/kaodian` → `.venv/bin/python -m apps.cli`

| 命令 | 作用 |
|---|---|
| `kaodian serve [--host --port --reload]` | 起 API + Web |
| `kaodian content list [--json]` | 列出 pack/版本/页数/题数 |
| `kaodian content validate [--json]` | 校验 frontmatter、考点、题型、答案、素材、重复 key、块 schema/嵌套/媒体地址 |
| `kaodian content sync [--json]` | 文件 → DB 索引 |
| `kaodian doctor [--json]` | 打印路径、DB 版本、pack 状态 |
| `kaodian backup [--out]` | SQLite backup 到 data_dir/exports |
| `kaodian mcp-config` | 输出 IDE 可用的 MCP JSON |

所有命令失败返回非 0；`--json` 输出 `{ok, ...}` 供 Agent 读取。

## 6. 安全

- 内容目录按只读处理；`content sync` 不写内容。
- 媒体路径必须防穿越。
- 不执行 pack 里的任何代码。
- 素材只按路径引用，不上传、不解析。

## 7. 迁移顺序

1. 框架实现 pack 加载、v4 迁移、`/media`、CLI，用 `examples/demo-content` 测试。
2. 本机建 `kaodian.toml` 指向 `./content` 与 `./data`。
3. 停服务，把旧库复制到 `data/api/kaodian.db`，备份后启动迁移。
4. `content sync` 按自然键回填 `pack_id`，确认无重复页/题。
5. 删除框架里的 `config/subjects`、`config/questions`、`apps/web/public/images`、`apps/web/public/素材库`。
6. 更新 Docker/README/AGENTS，跑全量测试与浏览器验收。
