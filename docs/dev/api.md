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
| GET | `/questions?subject_id=&code=&type=&status=` | 查题，默认只返回 approved |
| POST | `/questions/validate` | 只校验，不入库 |
| POST | `/questions/batch` | 批量入库，默认 `pending`，按题干去重 |
| POST | `/questions/review` | `{ids, decision: approve/reject, note}` |

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
| GET | `/progress` | 连续天数、目标、XP、完成课数 |
| GET | `/reviews/due` | 到期复习 |
| POST | `/activity` | 阅读/练习时长增量 |

## 代码练习

| 方法 | 路径 | 作用 |
|---|---|---|
| GET | `/code/status` | 是否启用 |
| POST | `/code/run` | `{code, stdin, language}` → gcc + bwrap 运行（当前仅 `c`） |

## 约定

- 失败返回 `{"detail": ...}`，批量校验失败返回 422 + 逐条 errors
- 时间戳为本地朴素时间（`YYYY-MM-DDTHH:MM:SS`）
- 组卷只抽 `status=approved` 的题
- 主观题 = 题型注册表里 `grading=agent`；判分按 `answer_schema`
- 主观题交卷后 `score=null`、`grading_status=pending`，由 Agent 评分
