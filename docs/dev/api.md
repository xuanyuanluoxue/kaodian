# API

Base：`http://127.0.0.1:8010/api`（本地）  
所有写操作只经过 API；MCP 和浏览器都调这里。

## 健康检查与媒体

| 方法 | 路径 | 作用 |
|---|---|---|
| GET | `/api/health` | 版本与 `schema_version` |
| GET | `/media/{pack}/{path}` | 内容包素材（只读） |

`/media` 的根目录是 `content_dir()/packs/<pack>/assets/`：

- `resolve()` 后必须仍在根目录内，`../` 一律 404；
- 只返回文件；pack 或文件不存在返回 404；
- 响应头 `Cache-Control: public, max-age=31536000, immutable`；
- 正文与题目里的媒体引用统一写 `/media/<pack>/<file>`。

## 科目与大纲

| 方法 | 路径 | 作用 |
|---|---|---|
| GET | `/subjects` | 科目列表（含 `color/icon/sort/code_language` 与题量） |
| GET | `/outline?subject_id=` | 考点树（含 `parent_code/depth`） |
| GET | `/question-types` | 题型注册表：`input/grading/answer_schema` |
| GET | `/stats/library` | 题库状态（approved/pending/rejected） |

## 题目

| 方法 | 路径 | 作用 |
|---|---|---|
| GET | `/questions?subject_id=&code=&type=&status=` | 查题，默认只返回 approved；`code` 会命中任一关联考点 |
| POST | `/questions/validate` | 只校验，不入库 |
| POST | `/questions/batch` | 批量入库，默认 `pending`，按题干去重 |
| POST | `/questions/review` | `{ids, decision: approve/reject, note}` |

题目字段补充（v2.1）：

- `outline_codes`：一题多考点；包含主考点 `outline_code`，返回时按主考点优先。
- `group_id` / `group_position`：挂到材料组，位置从 0/1 开始。
- `media`：`[{type,url,alt,license,source}]`，`type` 为 image/audio/video，
  `url` 只允许 `/` 开头站内路径或 `https://`。

## 材料组（材料题 / 一拖多）

| 方法 | 路径 | 作用 |
|---|---|---|
| POST | `/question-groups` | `{subject_id,title,material,media}` 新建 |
| GET | `/question-groups?subject_id=` | 材料组列表（带 `question_count`） |
| GET | `/question-groups/{id}` | 组详情，`questions` 按 `group_position` 排序 |
| PATCH | `/question-groups/{id}` | 更新标题/材料/媒体/科目 |
| DELETE | `/question-groups/{id}` | 删除；组内题目保留并解绑（`group_id=null`） |

组卷详情额外返回 `groups: [{id,title,material,media,question_ids}]`。

## 讲义

| 方法 | 路径 | 作用 |
|---|---|---|
| GET | `/pages?subject_id=&status=` | 页面列表（不含正文，含块字段） |
| GET | `/pages/{id}` | 页面全文 |
| GET | `/pages/{id}/question-count` | 这一页挂的考点有多少道 approved 题（去重） |
| POST | `/pages` | 发布页面（`status` 可为 draft/archived，支持 `sort_order`） |
| PATCH | `/pages/{id}` | 更新标题/正文/块/版式/状态 |
| DELETE | `/pages/{id}` | 删除 |
| POST | `/pages/{id}/complete` | 标记完成，+10 XP |
| GET | `/pages/{id}/draft` | 读 `{page, draft}`；没有草稿时 `draft=null` |
| PUT | `/pages/{id}/draft` | 保存草稿（`body/blocks/layout/theme` 任意字段，可带 `base_version`） |
| DELETE | `/pages/{id}/draft` | 丢弃草稿 |
| GET | `/pages/{id}/draft/stream` | SSE：草稿版本变化时推送 `{version, updated_at}` |
| POST | `/pages/{id}/publish` | 草稿写回内容文件/本地页，校验并同步；`{message, commit}` |
| POST | `/content/validate` | 校验全部 pack，返回 `{ok, packs:[{id, ok, errors}]}` |

页面响应在原有字段外增加：

| 字段 | 类型 | 说明 |
|---|---|---|
| `blocks` | `Block[] \| null` | JSON 块数组；Markdown 页为 `null` |
| `layout` | `string` | 默认 `article`；取值见 `blocks.md` |
| `theme` | `object \| null` | 主题对象；无则 `null` |
| `format` | `"markdown" \| "blocks"` | 有 `blocks` 即为 `blocks`，否则沿用存储值 |
| `file` | `string \| null` | 内容文件相对 `content/` 的路径；本地页为 `null` |

`POST /api/pages` 与 `PATCH /api/pages/{id}` 接受 `blocks/layout/theme`：

- `body` 对块页可为空；`blocks` 存在（含空数组）时 `format` 推导为 `blocks`，
  `blocks: null` 时回到 `markdown`；
- `blocks` 按 `blocks.md` 校验，未知类型、列数/嵌套/沙箱/媒体地址不合法返回 422；
- `layout` 与 `theme` 同样校验，不接受任意 CSS。

网页编辑流程见 [`editing.md`](editing.md)：保存草稿只写 `page_draft`；发布时先校验，
失败返回 422 且不改文件；`commit=true` 时在内容仓库执行 git 提交。

页面可练题量（`/pages/{id}/question-count`）：

- 取页面 `outline_codes`，统计 `status=approved` 且主考点 `outline_code` 或
  `question_outline` 命中任一 code 的**去重题数**；
- 返回 `{count, codes}`；页面不存在 404，`outline_codes` 为空返回 `{count:0,codes:[]}`。

## 组卷与作答

| 方法 | 路径 | 作用 |
|---|---|---|
| POST | `/quizzes` | 组卷（filters / question_ids） |
| GET | `/quizzes` | 最近练习单 |
| GET | `/quizzes/{id}` | 练习单详情（考试模式隐藏答案） |
| POST | `/attempts` | 开始作答 |
| PATCH | `/attempts/{id}` | 心跳 / 保存单题答案 |
| POST | `/attempts/{id}/submit` | 交卷 |
| GET | `/attempts/{id}` | 结果与逐题详情 |

## 主观题评分

| 方法 | 路径 | 作用 |
|---|---|---|
| GET | `/grading/queue` | 待评分队列 |
| POST | `/grading/{attempt_id}/{question_id}` | `{score, feedback}` 写回 |

## Agent 协作

| 方法 | 路径 | 作用 |
|---|---|---|
| POST | `/agent/sessions` | 新建会话 |
| POST | `/agent/events` | Agent 写提示（note） |
| GET | `/agent/feed?session_id=&after_id=` | 网页拉新事件（轮询） |
| GET | `/agent/stream?session_id=&after_id=` | 网页订阅事件（SSE，先补历史再推新事件） |
| GET | `/agent/inbox?after_id=` | Agent 拉求助/交卷 |
| POST | `/agent/help` | 网页求助 |

### SSE 事件流

`GET /agent/stream?session_id=&after_id=0`：`text/event-stream`，
响应头 `Cache-Control: no-cache`、`X-Accel-Buffering: no`。

- 连接后先补发 `after_id` 之后的历史事件，再每 1 秒查一次库推送新事件；
- 15 秒无新事件发注释心跳 `: ping`；
- 每条事件以空行结尾：

```
id: 42
event: note
data: {"id":42,"session_id":"s_x","kind":"note","role":"agent","body":"...","ref":null,"created_at":"...","read_at":null}

```

- `event` 取 `agent_event.kind`，`data` 是该行的完整 JSON；
- 客户端断开时生成器退出；仅本地单用户，不做鉴权。

## 统计

| 方法 | 路径 | 作用 |
|---|---|---|
| GET | `/stats/today` | 今日时长、作答、正确率 |
| GET | `/stats/subjects?days=30` | 分科目作答/正确/时长/练习次数 |
| GET | `/stats/heatmap?days=90` | 每日时长与作答数，缺失日期补 0 |
| GET | `/stats/types?days=30` | 分题型作答/正确数 |
| GET | `/progress` | 连续天数、目标、XP、完成课数 |
| GET | `/reviews/due` | 到期复习 |
| POST | `/activity` | 阅读/练习时长增量 |

统计口径与 `/stats/today` 一致：

- 作答数只统计 `answer.correct IS NOT NULL` 的记录，按 `attempt.started_at` 的本地日期归档；
- 时长 = `attempt.active_seconds` + `study_time.seconds`；
- 分科目时长把整次作答的 `active_seconds` 按该练习单内各科目的题目数分摊，
  阅读时长按 `page.subject_id` 归属；无法归属的 `study_time`（如页面已删）不计入科目，
  但仍计入 heatmap；
- 时间一律用本地朴素时间，`days` 为闭区间（今天往前 `days-1` 天）。

`/stats/subjects` 返回全部科目（无数据补 0）：
`{subject_id,name,short,color,icon,answered,correct,seconds,attempts}`。  
`/stats/heatmap` 返回按日期升序的 `{date,seconds,answered}`，长度恒等于 `days`。  
`/stats/types` 返回有作答的题型：`{type,label,answered,correct}`。

## 学习画像

| 方法 | 路径 | 作用 |
|---|---|---|
| GET | `/profile` | 静态目标 + 实时学情 |
| PUT | `/profile` | 更新静态字段，返回与 GET 相同结构 |

Schema v9 的 `profile` 是单行表（`id=1`）。新库或缺少该行时自动插入默认画像：
`daily_minutes=30`、`exam_total` 默认 500、`subjects` 为当前全部科目 id，其余为空、
`updated_by='user'`；已有画像不会被覆盖。静态字段只存库，动态字段全部实时查询、不落库。

`GET /api/profile` 返回 `{static, dynamic, completeness, missing, next_questions, phase}`：

```json
{
  "static": {
    "target_exam": "2028 广东专升本",
    "target_date": "2028-03-28",
    "target_score": 425,
    "targets": [
      {"tier": "冲", "school": "韩山师范学院", "major": "计算机科学与技术",
       "score": 424, "rank": 120, "location": "珠海（协同培养）", "note": ""},
      {"tier": "兜底", "school": "广州科技职业技术大学", "major": "计算机应用工程",
       "score": 182, "rank": 7599, "location": "广州（民办）", "note": ""}
    ],
    "exam_total": 500,
    "target_school": "韩山师范学院",
    "target_major": "计算机科学与技术",
    "target_region": "珠海",
    "backup_school": "广州科技职业技术大学",
    "backup_major": "计算机应用工程",
    "exam_type": "专升本",
    "current_education": "专科",
    "graduation_year": 2028,
    "hard_lines": "三科 105 / 专业综合课 60",
    "daily_minutes": 120,
    "subjects": ["computer", "math"],
    "subject_targets": {"computer": 190, "math": 85},
    "study_window": "工作日晚上 2h + 周末 4h",
    "constraints": "白天上班",
    "strengths": "英语单词记得快",
    "weaknesses": "数学基础弱",
    "motivation": "想换到计算机相关岗位",
    "notes": "",
    "ai_summary": "目标是 2028 广东专升本……",
    "preferred_tone": "",
    "preferred_examples": "",
    "plan_phase": "P1",
    "phase_start": "2026-11-01",
    "phase_end": "2027-03-31",
    "phase_daily_minutes": 120,
    "phase_goal": "C 语言基础 + 高数第一轮",
    "total_hours": 800,
    "updated_by": "agent"
  },
  "dynamic": {
    "days_to_exam": 508,
    "today_minutes": 44,
    "streak": 3,
    "xp": 120,
    "completed_pages": 7,
    "answered": 180,
    "correct": 120,
    "accuracy": 0.667,
    "due_reviews": 6,
    "subjects": [
      {"id": "math", "name": "高等数学", "short": "高数", "color": "#2f5d8a",
       "answered": 50, "correct": 35, "accuracy": 0.7, "seconds": 3600}
    ],
    "weak_codes": [{"code": "M-09", "title": "导数定义", "wrong": 4}],
    "recent": [{"date": "2026-11-04", "seconds": 2700, "answered": 12}]
  },
  "completeness": 1,
  "missing": [],
  "next_questions": [
    {"field": "target_region", "question": "目标院校在哪个地区？"}
  ],
  "phase": {
    "name": "P1",
    "goal": "C 语言基础 + 高数第一轮",
    "start": "2026-11-01",
    "end": "2027-03-31",
    "daily_minutes": 120,
    "days_left": 146,
    "progress": 0.027
  }
}
```

`static` 字段：

| 分组 | 字段 |
|---|---|
| 升学目标 | `target_exam` `target_date` `target_score` `exam_total` `hard_lines` `targets` `target_school` `target_major` `target_region` `backup_school` `backup_major` `exam_type` `current_education` `graduation_year` |
| 学习条件 | `daily_minutes` `subjects` `subject_targets` `study_window` `constraints` |
| 阶段计划 | `plan_phase` `phase_start` `phase_end` `phase_daily_minutes` `phase_goal` `total_hours` |
| 自我评估 | `strengths` `weaknesses` `motivation` `notes` `ai_summary` |
| 教学偏好 | `preferred_tone` `preferred_examples` |
| 来源 | `updated_by`（`user` / `agent`） |

- `targets` 按志愿顺序存 JSON 数组，`tier` 只能是 `冲` / `稳` / `保` / `兜底`，最多 8 条；
  写入后 `target_school` = 第一条 `school`，`backup_school` = `兜底` 条（无则最后一条），
  `backup_major` 同步该条 `major`；同一次请求显式传值时以显式值为准。
- `subject_targets` 是 `{科目 id: 目标分}`，键必须是已有科目，分数 0–`exam_total`。
- `exam_total` 未设置时按 500 返回。

完整度：

- 必填 8 项：`target_exam` `target_date` `target_score` `targets`
  `target_major` `daily_minutes` `subjects` `motivation`；
- `targets` 为空但 `target_school` 有值时视为已填（兼容 v2 数据）；
- `completeness` = 已填必填 / 8（0–1，三位小数）；
- `missing` 按上面的必填顺序列出未填字段；
- `next_questions` 先列必填、再列选填，每条形如 `{field, question}`，最多 6 条。

`phase` 是**当前执行档位**，不是历史：

- 没有 `plan_phase` / `phase_start` / `phase_end` 时返回 `null`；
- `days_left` = `phase_end - today`，可为负，无结束日期为 `null`；
- `progress` = 已过天数 / 总天数（0–1，三位小数），缺起止日期为 `null`。

动态字段口径：

- `days_to_exam` = `target_date - today`，未设置目标为 `null`；
- `today_minutes` / `streak` / `xp` / `completed_pages` 与 `/api/progress` 一致；
- `answered` / `correct` / `accuracy` 统计全库 `answer.correct IS NOT NULL`，
  `accuracy` 为 0–1 的三位小数，无作答为 `null`；
- `due_reviews` = `review.due_date <= today` 的数量；
- `subjects` 返回全部科目，`seconds` 含 `attempt.active_seconds` 与 `study_time`，
  归属规则同 `/api/stats/subjects`；
- `weak_codes` 按答错次数取 Top 5；
- `recent` 为近 7 天（含今天）`{date,seconds,answered}`，缺失日期补 0。

`PUT /api/profile` 只更新传入的静态字段，不传的字段不动；传 `null`（或空字符串）
表示清除：

- `target_date` 必须是有效 `YYYY-MM-DD`；
- `graduation_year` 1950–2100；`daily_minutes` 1–600；
- `exam_total` 1–1000；`total_hours` 0–100000；`phase_daily_minutes` 1–600；
- `targets`：数组 ≤8；`tier` 枚举；`school` 必填 ≤100 字；`major` / `location`
  ≤100 字；`note` ≤200 字；`score` 0–`exam_total`；`rank` 0–1000000；
- `subject_targets`：科目必须存在；分数 0–`exam_total`；
- `plan_phase` 只能是 `P1` / `P2` / `P3`；`phase_start` / `phase_end` 为
  `YYYY-MM-DD` 且 `end >= start`；`phase_goal` ≤500 字；`hard_lines` ≤200 字；
- `subjects` 必须是已存在科目 id；
- 文本长度：学校/专业 ≤100 字，地区 ≤50 字，学习时段 ≤200 字，
  限制/优势/薄弱/动机 ≤1000 字，`ai_summary` / `notes` ≤2000 字，
  `preferred_tone` / `preferred_examples` ≤200 字；
- `source`：`user` / `agent`，默认 `user`，写入 `updated_by`；
- `ai_summary` 与 `notes` 分开存：AI 写 `ai_summary`，用户保存不会清空它；
- 校验失败返回 422（中文消息，指明字段），且不写库。

## 备份：导出 / 导入

| 方法 | 路径 | 作用 |
|---|---|---|
| GET | `/export?scope=content\|progress\|all` | 下载 JSON 备份 |
| POST | `/import` | 从 JSON body 合并导入 |

`scope`：

| 值 | 内容 |
|---|---|
| `content`（默认） | `subjects` `outline` `groups` `questions` `question_outline` `pages` |
| `progress` | `page_progress` `review` `study_time` |
| `all` | 两者 |

导出结构：

```json
{
  "format": "kaodian-export",
  "version": 9,
  "exported_at": "2026-11-04T18:30:00",
  "scope": "content",
  "data": {
    "subjects": [], "outline": [], "groups": [], "questions": [],
    "question_outline": [], "pages": [],
    "page_progress": [], "review": [], "study_time": []
  }
}
```

- 题目包含 `answer/explanation/reference_answer/rubric`，是本地备份，不脱敏。
- `pages` 包含 `blocks/layout/theme/format`，导入时 `blocks` 非空则 `format` 置为 `blocks`。
- 响应头带 `Content-Disposition: attachment; filename="kaodian-export-YYYYMMDD.json"`。
- 导入只接收 JSON body，不接受文件路径或上传文件。

导入 body：

```json
{"format":"kaodian-export","version":9,"scope":"content","overwrite":false,"data":{}}
```

规则：

- `format` 必须为 `kaodian-export`；`version` 高于当前 `SCHEMA_VERSION`（当前 9） 返回 422；
- 整个导入在单个事务里，任一记录失败全部回滚；
- `overwrite=false`：按主键跳过已存在记录；题目同时按 `fingerprint` 去重；
- `overwrite=true`：UPSERT（页面标题、题目字段等以导入文件为准）；
- 写入顺序：`subjects → outline → groups → questions → question_outline → pages`，
  进度表最后；
- 外键缺失返回 422，并指出字段（如 `questions[0].outline_code: X 不存在`）；
- 返回 `{"imported":{...},"skipped":{...}}`，键与 scope 内的表名一致；
- 单独导入 `progress` 时，找不到页面/题目的进度记录计入 `skipped`，不报错。

## 代码练习

| 方法 | 路径 | 作用 |
|---|---|---|
| GET | `/code/status` | 是否启用 |
| POST | `/code/run` | `{code, stdin, language}` → gcc + bwrap 运行（当前仅 `c`） |

## 约定

- 失败返回 `{"detail": ...}`，批量校验失败返回 422 + 逐条 errors
- 时间戳为本地朴素时间（`YYYY-MM-DDTHH:MM:SS`）
- 组卷只抽 `status=approved` 的题
- 按考点组卷时同时匹配主考点 `outline_code` 和 `question_outline` 里的关联考点
- 材料题通过 `question_group` 承载，不为复合题另造模型
- 主观题 = 题型注册表里 `grading=agent`；判分按 `answer_schema`
- 主观题交卷后 `score=null`、`grading_status=pending`，由 Agent 评分
