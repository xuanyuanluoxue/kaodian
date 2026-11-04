# 讲义块结构（blocks v1）

> Markdown 仍然是默认格式；需要版式/组件时用 JSON 块页。两种格式可以共存。

## 1. 两种讲义文件

### Markdown（默认）

`lessons/M02-1.md`：frontmatter + 正文。正文整体渲染为一个 Markdown 块。
可选 frontmatter：

```yaml
layout: "article"   # article | wide | split
theme: '{"accent":"math","density":"comfortable"}'
```

### JSON 块页（需要版式时）

`lessons/M02-1.json`：

```json
{
  "lesson_key": "M02-1",
  "title": "导数 1/7 · 定义与切线",
  "summary": "一句话",
  "kind": "lesson",
  "status": "draft",
  "sort_order": 201,
  "outline_codes": ["M-09"],
  "layout": "wide",
  "theme": {"accent": "math", "density": "comfortable"},
  "blocks": []
}
```

同一个 pack 里 `lesson_key` 不能重复；`.md` 与 `.json` 二选一。

## 2. 版式

| layout | 用途 |
|---|---|
| `article` | 默认单栏，最大宽度 |
| `wide` | 宽屏，图表/表格更大 |
| `split` | 左文右图/代码（窄屏自动单栏） |
| `slides` | 一屏一屏（v1 先按纵向卡片渲染） |
| `dashboard` | 多卡片网格（v1 先按两栏渲染） |

`theme`：

```json
{"accent": "math", "density": "comfortable", "font": "sans"}
```

- `accent`：`math` / `computer` / `english` / `politics`，或 `#hex`
- `density`：`compact` / `comfortable`
- `font`：`sans` / `serif`

不允许任意 CSS。

## 3. 块类型

所有块都是对象，`type` 必填。

| type | 字段 | 说明 |
|---|---|---|
| `markdown` | `text` | 正文；支持 KaTeX/Mermaid/图片 |
| `callout` | `tone`(`info/warn/danger/success`), `title?`, `text` | 提示卡 |
| `columns` | `cols: Block[][]`（2–3 列） | 分栏 |
| `tabs` | `items: [{label, blocks: Block[]}]` | 标签页 |
| `steps` | `items: [{title, text}]` | 步骤条 |
| `cards` | `items: [{title, text, link?}]` | 卡片网格 |
| `timeline` | `items: [{time, title, text}]` | 时间线 |
| `image` | `url`, `alt?`, `caption?`, `license?` | 图片 |
| `video` | `url`, `poster?` | 视频 |
| `audio` | `url`, `title?` | 音频 |
| `code` | `language`, `code`, `title?` | 代码块 |
| `mermaid` | `code` | 结构图 |
| `math-graph` | `spec` | JSXGraph 交互图 |
| `sandbox` | `html`, `height?`, `title?` | 隔离 iframe，实验用 |
| `divider` | — | 分隔线 |

嵌套最多 3 层。`columns/tabs` 里可以放任意块（除 `sandbox`，sandbox 只能顶层）。

## 4. 安全

- `sandbox` 渲染为 `<iframe sandbox="allow-scripts">`，不加 `allow-same-origin`，不能读应用 localStorage/API。
- `sandbox.html` 上限 200 KB；只允许顶层，不允许嵌套。
- 其他块不允许原始 HTML/CSS/JS。
- 媒体 URL 只允许 `/media/<pack>/...` 或 `https://`。
- `content validate` 校验块 schema、嵌套深度、媒体存在、sandbox 限制。

## 5. API

`page` 增加：

- `blocks: Block[] | null`
- `layout: string`
- `theme: object | null`
- `format: "markdown" | "blocks"`

`GET /api/pages/{id}` 返回以上字段。前端优先渲染 `blocks`，否则渲染 `body`。

## 6. 前端

- `BlockRenderer` 按 `type` 分发；未知类型显示降级提示，不白屏。
- `LessonBody` 统一处理 layout/theme。
- 块组件只使用全局 CSS token，不读取任意样式。
- `sandbox` 高度默认 420，最大 900；默认显示“实验页”标识。

## 7. 验收

- 现有 56 页 Markdown 不受影响。
- 新建一个 JSON 块页，包含 callout/columns/tabs/steps/code/math-graph/sandbox。
- 手机 390px 下 columns 自动单栏。
- 暗色主题正常。
- `make check` 全绿。
