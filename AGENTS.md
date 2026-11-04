# AGENTS.md

> 面向 AI Agent 的项目入口。根 `README.md` 给人看；这里给 Agent 任务路由和边界。
> 详细文档在 `docs/`，按任务读，不要一次全读。

## 先确认三件事

1. **改哪**：源码 `apps/`，内容配置 `config/`，文档 `docs/`，用户数据 `user-data/`（只读，除非用户要求）。
2. **能不能写**：用户数据、`LICENSE`、`.git/` 不主动改；新增依赖前先问。
3. **谁来提交**：子 Agent 一律不 commit；主 Agent 验收后提交。

## 任务路由

| 任务 | 先读 | 交给 |
|---|---|---|
| 改前端 / 后端 / MCP | `docs/dev/architecture.md`、`docs/dev/tech-stack.md` | 开发子 Agent |
| 加 API / 改数据模型 | `docs/dev/api.md`、`apps/api/app/main.py` | 开发子 Agent |
| 本地跑、测试、构建 | `docs/dev/development.md` | 开发子 Agent |
| 写讲义、拆课、加图 | `docs/content/format.md` | 教学子 Agent |
| 出题、审题、评分 | `docs/ai/pipelines.md` | 教学子 Agent（审题只由主 Agent） |
| 接 IDE / MCP | `docs/ai/integration.md`、`docs/ai/protocols/agent.md` | 主 Agent |
| 排期、进度、决策 | `docs/product/roadmap.md` | 主 Agent |

## 子 Agent 规则

给子 Agent 的任务必须自带：**工作目录、目标、验收命令、禁止项**。子 Agent 只回报文件、行数与结果，长日志留在子 Agent 上下文。

| 角色 | 可以 | 不可以 |
|---|---|---|
| 开发 | 改 `apps/`、跑测试/构建 | 改讲义、动 `user-data/`、commit |
| 教学 | 写 Markdown、`create_questions`、`publish_page(draft)` | 审题、组卷、发布、改代码、commit |
| 验收 | 只读 diff、复核题目与例题 | 改实现 |

## 内容与数据边界

- 讲义源文件在本机的私有学习工作区（如 `~/资料/学习`），**不进本仓库**；控制台里是发布后的副本。
- `user-data/kaodian.db` 是用户进度，默认被 `.gitignore` 排除；不要读进上下文，不要提交。
- 题目入库只算格式合法，必须人工/主 Agent 验算后才能 `approve` 组卷。
- 素材只用可自由使用的来源并记录许可证；真题注明「改编自 X 年真题」。

## 常用命令

```bash
make test     # pytest apps/api/tests
make build    # 前端构建（tsc + vite）
make dev-api  # uvicorn :8000
make dev-web  # vite :5173
```

## 文档维护

- 根 `README.md` ≤100 行，只做入口；
- 一个主题一个文件，单文件 ≤200 行；
- 改目录或接口时，同步更新 `docs/README.md`、`docs/dev/architecture.md` 和本文件。
