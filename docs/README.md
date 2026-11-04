# 文档索引

> 根目录的 `README.md` 只做入口。细节按任务读对应文档，避免一次性把整个项目塞进上下文。

## 按任务找文档

| 我要做什么 | 先读 | 再读 |
|---|---|---|
| 了解项目定位与功能 | [`product/overview.md`](product/overview.md) | [`product/roadmap.md`](product/roadmap.md) |
| 改代码 / 看模块划分 | [`dev/architecture.md`](dev/architecture.md) | [`dev/content-packs.md`](dev/content-packs.md) |
| 本地跑起来 / 跑测试 | [`dev/development.md`](dev/development.md) | [`dev/tech-stack.md`](dev/tech-stack.md) |
| 调 API | [`dev/api.md`](dev/api.md) | [`ai/pipelines.md`](ai/pipelines.md) |
| 让 AI / IDE 接进来 | [`ai/integration.md`](ai/integration.md) | [`ai/ide-workflow.md`](ai/ide-workflow.md) |
| 让 AI 出题、审题、评分 | [`ai/pipelines.md`](ai/pipelines.md) | [`content/format.md`](content/format.md) |
| 写讲义 / 加图 / 加交互图 | [`content/format.md`](content/format.md) | [`dev/content-packs.md`](dev/content-packs.md) |

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

- 根 `README.md` ≤100 行，只放入口和快速开始
- 一个主题一个文件，单文件 ≤200 行
- 文档里的代码路径写相对仓库根的路径，不写本机绝对路径
- 改结构时同步更新本索引和根 `AGENTS.md`
