# 技术栈

## 一览

| 层 | 技术 | 版本 | 作用 |
|---|---|---|---|
| 前端框架 | React | 19.3 | 页面与交互 |
| 构建 | Vite | 8.3 | 开发服务器与打包 |
| 语言 | TypeScript | 7.0 | 类型 |
| 路由 | React Router | 7.18 | 单页路由 |
| Markdown | react-markdown + remark-gfm | 10 / 4 | 讲义正文 |
| 公式 | KaTeX + remark-math + rehype-katex | 0.19 | 行内/块级公式 |
| 图 | Mermaid | 12.2 | 流程图/时序图 |
| 交互数学图 | JSXGraph | 1.14 | 滑块、切点、切线 |
| 后端 | FastAPI | 0.162 | REST API |
| 服务器 | Uvicorn | 0.54 | ASGI |
| 数据库 | SQLite | 3 | 单文件、WAL |
| MCP | mcp (Python SDK) | 2.3 | stdio 工具服务 |
| 代码沙箱 | gcc + bubblewrap | 13 / 0.9 | 编译、断网隔离 |
| 容器 | Docker + Compose | 29 | 单容器部署 |

## 为什么是这套

- **本地优先**：SQLite 单文件、无外部服务、无账号；备份就是复制文件。
- **Markdown 为内容格式**：AI 写讲义只产出 Markdown；表格、Mermaid、SVG、`math-graph` 都是 Markdown 代码块，不需要网页编辑器。
- **重交互用轻依赖**：Mermaid 和 JSXGraph 都按需动态加载，只有用到图的页面才付体积成本。
- **MCP 作为 AI 接口**：AI 不嵌在网页里，而是通过 stdio MCP 调 API；网页和 AI 共用同一套写库逻辑。
- **单容器**：FastAPI 同时托管前端构建产物和 API，部署只有一个端口。

## 前端依赖（要点）

- `react`, `react-dom`, `react-router-dom`
- `react-markdown`, `remark-gfm`, `remark-math`, `rehype-katex`, `katex`
- `mermaid`（懒加载）
- `jsxgraph`（懒加载，259 KB gzip）
- 没有 UI 组件库；样式是手写 CSS 变量，亮/暗两套

## 后端依赖

- `fastapi`, `uvicorn[standard]`, `pydantic`
- 标准库 `sqlite3`、`subprocess`、`tempfile`、`shutil`
- 测试：`pytest`, `httpx`

## 开发环境

- Python 3.10+（当前 3.12）
- Node 20+（当前 24）
- gcc + bubblewrap（仅代码练习需要）

## 体积与加载

| 块 | 大小 | 何时加载 |
|---|---|---|
| 主包 | ~1 MB（gzip ~260 KB） | 首屏 |
| KaTeX / Mermaid | 随主包/按需 | 有公式/图时 |
| JSXGraph | 259 KB gzip | 页面含 `math-graph` 时 |
| SVG 图 | 3–6 KB/张 | 直接 `<img>` |

> 新增重依赖前先问：能不能用 SVG / Markdown 表格 / 现有 Mermaid 解决？不能才引入，并且必须懒加载。
