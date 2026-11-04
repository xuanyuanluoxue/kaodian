# 网页编辑与草稿（editing v1）

> 内容源仍是 `content/packs/` 文件；网页编辑只改草稿，点“发布”才写回文件并同步。

## 1. 数据

`page_draft`：

| 列 | 说明 |
|---|---|
| `page_id` | 主键，关联 `page` |
| `body` | Markdown 正文（Markdown 页） |
| `blocks` | JSON 块数组（块页） |
| `layout` | article/wide/split/slides/dashboard |
| `theme` | JSON：accent/density/font |
| `updated_at` | 最后保存时间 |
| `version` | 每次保存 +1 |

`page` 增加 `file TEXT`：内容文件相对 `content/` 的路径，例如
`packs/math/lessons/M02-1-....md`。本地页（`pack_id IS NULL`）为 null。

## 2. API

| 方法 | 路径 | 作用 |
|---|---|---|
| GET | `/api/pages/{id}/draft` | 返回 `{page, draft}`；没有草稿时 draft 为 null |
| PUT | `/api/pages/{id}/draft` | 保存草稿，body：`body/blocks/layout/theme` 任意字段 |
| DELETE | `/api/pages/{id}/draft` | 丢弃草稿 |
| GET | `/api/pages/{id}/draft/stream` | SSE：草稿版本变化时推送 `{version, updated_at}` |
| POST | `/api/pages/{id}/publish` | 把草稿写回内容文件/本地页，然后 validate + sync |
| POST | `/api/content/validate` | 校验所有 pack，返回 `{ok, packs}` |

保存草稿只写 `page_draft`，**不写内容文件**，不触发 sync。

## 3. 发布

`POST /api/pages/{id}/publish`：

```json
{"message": "M02-1 调整例题", "commit": false}
```

流程：

1. 取 page + draft；没有草稿直接 422。
2. 如果 `page.pack_id` 为空：直接更新 `page`（本地页），跳过文件。
3. 如果 `page.file` 为空：422（内容来源不可写）。
4. 解析 `content_dir()/page.file`，必须仍在 `content/` 内。
5. Markdown 页：重写 frontmatter + body。
6. 块页：重写 JSON 对象（保留元信息 + blocks/layout/theme）。
7. 运行 `content.validate_pack`；失败 422，不写文件。
8. 写文件（原子替换：临时文件 + rename）。
9. `sync_content` 回填 DB。
10. 删除草稿。
11. `commit=true` 时在内容仓库执行 `git add <file> && git commit -m <message>`；
    默认 false，由主 Agent/IDE 统一提交。
12. 返回 `{page, file, committed}`。

## 4. 安全

- 只允许本地使用；后续 HTTP MCP 再加 token。
- `file` 必须 resolve 后仍在 `content/` 内。
- 发布前必须通过 `validate_pack`；不允许把坏 JSON 写进仓库。
- 草稿只影响当前 page；不创建新的 pack/lesson。
- 并发：`page_draft.version` 递增；保存时可带 `base_version`，不一致返回 409。

## 5. 前端

路由 `/edit/:pageId`：

- 左侧编辑，右侧实时预览（复用 `LessonBody`）。
- Markdown 页：textarea 编辑正文。
- 块页：JSON 编辑器（textarea）编辑 blocks；解析失败只提示，不崩。
- 布局/主题：下拉选择。
- 1.2s 防抖自动保存草稿；状态显示“已保存/保存中/有冲突”。
- 按钮：保存、发布、丢弃草稿、返回阅读。
- 阅读页右上角加“编辑”链接。
- SSE 收到新版本时，如果本地没有未保存修改，自动刷新预览。

## 6. MCP

新增：

| 工具 | 作用 |
|---|---|
| `get_page_draft(page_id)` | 读 page + draft |
| `save_page_draft(page_id, body?, blocks?, layout?, theme?)` | 存草稿 |
| `publish_page_draft(page_id, message?, commit?)` | 发布 |
| `validate_content()` | 校验内容包 |

## 7. 验收

- 改一页 Markdown → 预览实时变 → 发布 → 文件被改、`content validate` 通过、页面更新。
- 改一个块页 JSON → 预览实时变 → 发布 → 文件为 JSON。
- 非法 JSON/块 → 发布 422，文件不变。
- 两个客户端同时编辑 → 版本冲突 409。
- `make check` 全绿。
