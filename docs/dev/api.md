# API

Base：`http://127.0.0.1:8010/api`（本地）  
所有写操作只经过 API；MCP 和浏览器都调这里。

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
| GET | `/pages?subject_id=&status=` | 页面列表（不含正文） |
| GET | `/pages/{id}` | 页面全文 |
| POST | `/pages` | 发布页面（`status` 可为 draft/archived，支持 `sort_order`） |
| PATCH | `/pages/{id}` | 更新标题/正文/状态 |
| DELETE | `/pages/{id}` | 删除 |
| POST | `/pages/{id}/complete` | 标记完成，+10 XP |

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
| GET | `/agent/feed?session_id=&after_id=` | 网页拉新事件 |
| GET | `/agent/inbox?after_id=` | Agent 拉求助/交卷 |
| POST | `/agent/help` | 网页求助 |

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
  "version": 3,
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
- 响应头带 `Content-Disposition: attachment; filename="kaodian-export-YYYYMMDD.json"`。
- 导入只接收 JSON body，不接受文件路径或上传文件。

导入 body：

```json
{"format":"kaodian-export","version":3,"scope":"content","overwrite":false,"data":{}}
```

规则：

- `format` 必须为 `kaodian-export`；`version` 高于当前 `SCHEMA_VERSION` 返回 422；
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
