# 框架 v2 契约

> 边界：**任意科目、单一考试形态、单机单用户、题型注册表**。
> 内容（题库/讲义）不在本期范围；这里只定义框架层。
> v2.1 追加：材料题 / 一拖多、一题多考点、媒体引用。

## 1. 配置

### 科目 `config/subjects/*.json`

```json
{
  "id": "computer",
  "name": "计算机基础与程序设计",
  "short": "计算机",
  "color": "#1d6b5c",
  "icon": "cpu",
  "sort": 1,
  "code_language": "c",
  "exam": { "score": 200, "minutes": 150 },
  "nodes": [
    { "code": "C-01", "title": "…", "parent": null }
  ]
}
```

| 字段 | 必填 | 说明 |
|---|---|---|
| `id` / `name` / `short` | 是 | 科目身份与显示名 |
| `color` | 否 | 主题色，前端用 CSS 变量渲染 |
| `icon` | 否 | 图标名（`cpu` / `sigma` / `languages` / `landmark`） |
| `sort` | 否 | 科目顺序，默认 0 |
| `code_language` | 否 | 有值才显示代码终端（当前仅 `c`） |
| `nodes[].parent` | 否 | 父节点 code，用于层级；无则 depth=0 |

### 题型 `config/question_types.json`

```json
{
  "id": "single",
  "label": "单选",
  "input": "choice",
  "grading": "auto",
  "answer_schema": "letters",
  "min_options": 2,
  "max_options": 8,
  "sort": 10
}
```

| 字段 | 说明 |
|---|---|
| `input` | `choice` / `judge` / `text` / `code`，决定前端控件 |
| `grading` | `auto`（服务端判分）/ `agent`（进评分队列） |
| `answer_schema` | `letters` / `boolean` / `blanks` / `rubric` / `code` / `text` |
| `requires_rubric` | 是否强制 `reference_answer` + `rubric` |
| `allow_partial` | 多空填空是否按空给分 |
| `language` | 代码题默认语言 |

新增题型只改这个文件；服务端校验、判分、评分队列和前端筛选都读它。

### 题库 `config/questions/*.json`

仍支持纯数组，也支持带材料组的对象格式：

```json
{
  "groups": [
    {"key": "g1", "title": "阅读材料", "material": "…", "media": []}
  ],
  "questions": [
    {"outline_code": "M-01", "group_key": "g1", "group_position": 1, "…": "…"}
  ]
}
```

`groups[].key` 会存为 `question_group.source_key`，按 `(subject_id, source_key)`
幂等 upsert；`group_key` 在同步时映射为 `group_id`。`subject_id` 可省略，由组内题目的
考点反推。

### 媒体引用

`media` 是 JSON 数组，元素：

```json
{"type": "image|audio|video", "url": "/images/x.svg", "alt": "图注", "license": "CC0", "source": "…"}
```

`type` / `url` 必填；`url` 只允许 `/` 开头的站内路径或 `https://` 外链。题目和材料都支持。

## 2. 数据库

版本号 `PRAGMA user_version = 3`。启动时：

1. 旧库先备份为 `*.bak-v{old}-{timestamp}`（SQLite backup API，包含 WAL）；
2. `migrate()` 增量加列/建表（不重建表）；
3. 再执行 `schema.sql` 补齐新表/索引（幂等）；
4. `config/` 全量同步：科目/大纲/材料组 UPSERT，题库只补新题；
5. 同步不删除库里已有、但配置里没有的节点/题目。

新增列：

| 表 | 列 |
|---|---|
| `subject` | `color` `icon` `sort` `code_language` |
| `outline_node` | `parent_code` `depth` |
| `question` | `language` `group_id` `group_position` `media` |
| `page` | `sort_order`（默认 1000） |
| `question_group` | `source_key`（按 `subject_id + source_key` 唯一） |

新增表：

| 表 | 用途 |
|---|---|
| `question_group` | 材料 / 一拖多；`material` + `media` |
| `question_outline` | 一题多考点；主考点仍写 `question.outline_code`，这里保存全部关联 |

v2 升级时会把每道老题的 `outline_code` 回填进 `question_outline`。

## 3. API

| 方法 | 路径 | 变化 |
|---|---|---|
| GET | `/api/question-types` | 新增，返回题型注册表 |
| GET | `/api/subjects` | 多返回 `color/icon/sort/code_language`，按 `sort` 排序 |
| GET | `/api/outline` | 多返回 `parent_code/depth` |
| GET | `/api/pages` | 按 `sort_order, lesson_key, created_at` 排序 |
| POST/PATCH | `/api/pages` | 接受 `sort_order`，`status` 支持 `archived` |
| POST/GET | `/api/question-groups` | 新建 / 列出材料组 |
| GET/PATCH/DELETE | `/api/question-groups/{id}` | 组详情返回 `questions`（按 `group_position`） |
| POST | `/api/code/run` | 接受 `language`，当前仅 `c` |
| GET | `/api/health` | 多返回 `schema_version` |

`POST /api/questions/batch` 的每道题接受：`outline_codes`（一题多考点）、
`group_id` / `group_position`（挂材料组）、`media`。`get_quiz` 额外返回
`groups: [{id,title,material,media,question_ids}]`，每道题仍带 `group_id`。

题型相关行为不再写死：

- 判分按 `answer_schema`；
- 主观题 = `grading == "agent"`；
- 评分队列按注册表动态取题型；
- 组卷 `types` 由注册表提供。

## 4. 前端要求

1. 页面不再出现 `"computer"` 兜底；默认科目 = `subjects[0]`。
2. 科目色用 `style={{ "--subject": s.color }}` 或内联 `background`，不再用 `.dot-computer` 等四个类。
3. 题型列表、标签、主观题判断全部来自 `/api/question-types`。
4. `input=choice` 渲染选项；`judge` 渲染对/错；`text` 渲染文本框；`code` 渲染代码框；未知类型回退文本框并提示。
5. 代码终端只在 `subject.code_language` 有值时显示，不再判断 `subject === "computer"`。
6. 加载失败要复位 busy，不能用 `String(e)` 直接显示对象。

## 5. 验收

```bash
.venv/bin/python -m pytest apps/api/tests -q   # ≥30 passed
cd apps/web && npm run build
```

再造一个临时科目（只加 `config/subjects/test.json`）验证：路径出现、组卷可选、无需改代码。
