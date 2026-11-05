# 文档索引

> 根目录的 `README.md` 面向使用者，只做产品入口；根目录的 `AGENTS.md` 面向 AI / 开发者，
> 记录仓库地图、命令、边界与验收清单。细节按任务读对应文档，避免一次性把整个项目塞进上下文。

## 按任务找文档

| 我要做什么 | 先读 | 再读 |
|---|---|---|
| 了解项目定位与功能 | [`product/overview.md`](product/overview.md) | [`product/roadmap.md`](product/roadmap.md) |
| 改代码 / 看模块划分 | [`dev/architecture.md`](dev/architecture.md) | [`dev/content-packs.md`](dev/content-packs.md) |
| 本地跑起来 / 跑测试 | [`dev/development.md`](dev/development.md) | [`dev/tech-stack.md`](dev/tech-stack.md) |
| 调 API | [`dev/api.md`](dev/api.md) | [`ai/pipelines.md`](ai/pipelines.md) |
| 让 AI / IDE 接进来 | [`ai/integration.md`](ai/integration.md) | [`ai/ide-workflow.md`](ai/ide-workflow.md) |
| 让 AI 出题、审题、评分 | [`ai/pipelines.md`](ai/pipelines.md) | [`content/format.md`](content/format.md) |
| 写讲义 / 加图 / 加交互图 | [`content/format.md`](content/format.md) | [`dev/blocks.md`](dev/blocks.md) |
| 网页编辑 / 草稿 / 发布 | [`dev/editing.md`](dev/editing.md) | [`dev/blocks.md`](dev/blocks.md) |
| 学习画像 / 目标 / 学情 | [`dev/profile.md`](dev/profile.md) | [`dev/api.md`](dev/api.md) |

## 分区

```
docs/
├── product/     项目定位、功能、路线图
├── dev/         架构、技术栈、开发、API
├── ai/          AI 如何运行、MCP、出题/评分流水线
│   └── protocols/agent.md   事件流与协作协议
└── content/     讲义格式、图表、交互图规范
```

## 维护约定

- 根 `README.md` ≤100 行，只放产品入口和快速开始，不写工程细节
- 根 `AGENTS.md` 是本仓库 AI 的唯一入口，命令 / 路径 / 约定以它为准；两处不重复维护
- 一个主题一个文件，单文件 ≤200 行
- 文档里的代码路径写相对仓库根的路径，不写本机绝对路径
- 改结构时同步更新本索引和根 `AGENTS.md`
