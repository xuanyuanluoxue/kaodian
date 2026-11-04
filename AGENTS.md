# AGENTS.md

> 三处边界：**框架**在 `~/code/kaodian`，**内容**在 `~/code/kaodian-content`，**运行时数据**在 `~/kaodian-runtime`。
> 先确认改哪一层，再动手。

## 路由

| 任务 | 目录 | 先读 |
|---|---|---|
| 改前端/后端/MCP/CLI | 框架仓库 | `docs/dev/architecture.md`、`docs/dev/content-packs.md` |
| 改讲义/题库/素材 | 内容仓库 | 内容仓库 `README.md`、`AGENTS.md` |
| 迁移/备份/导出 | 运行时目录 + `bin/kaodian` | `docs/dev/development.md` |
| 接 IDE / MCP | 框架仓库 | `docs/ai/integration.md`、`docs/ai/ide-workflow.md` |
| 产品/路线 | 框架仓库 `docs/product/` | `final-state.md` |

## 硬边界

- 框架仓库**不放**任何一科内容、图片、题库。
- 内容仓库**不放**代码、数据库、作答记录。
- 运行时目录**不进 Git**；备份只拷它。
- 内容源是 Markdown/JSON 文件；DB 里的内容只是可重建索引。
- 本地页面/题目（`pack_id IS NULL`）不会被 `content sync` 删除或覆盖。

## 子 Agent

| 角色 | 只碰 | 不碰 |
|---|---|---|
| 框架开发 | `apps/` `bin/` `docs/dev/` `examples/` | 内容仓库、runtime |
| 内容教学 | 内容仓库 `packs/<id>/` | 代码、DB |
| 验收 | 只读 diff / 文件 | 实现 |

- 子 Agent 不 commit；主 Agent 验收后提交。
- 内容子 Agent 只写文件，不 `content sync`；主 Agent 统一同步。
- 交付只报文件、校验结果、风险；长日志留在子 Agent。

## 常用命令

```bash
make check
bin/kaodian content validate
bin/kaodian content sync
bin/kaodian doctor --json
bin/kaodian serve --port 8010
```

## 内容格式

- 一课一概念，≤120 行。
- Markdown + KaTeX + Mermaid + `/media/<pack>/...`。
- frontmatter 字段见 `docs/dev/content-packs.md`。
- 素材必须登记许可证；真题写“改编自 X 年真题”。

## 文档维护

- 根 `README.md` ≤110 行，只做入口。
- 改路径/接口时同步 `docs/dev/`、`docs/ai/` 和本文件。
