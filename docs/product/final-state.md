# 最终形态 v1.0

> 目标不是“又一个刷题网站”，而是**一个能长期用的本地学习终端**：
> 内容可换、科目可加、AI 在 IDE 里指挥，网页只负责读、答、计时、回传。

## 一、用户看到的样子

### 1. 今天

打开 `/`：

- 今日已投入时长 / 每日目标
- 到期复习题（按掌握度排好）
- 四科（或任意科目）进度与入口
- 最近练习单、连续天数、XP

### 2. 学习路径

`/console?subject=…`：

- 科目 → 章节 → 单概念课，节点显示完成状态
- 一页只讲一个概念，10–15 分钟
- 每页：一句话 → 考频 → 直觉/定义 → 3 个递进例子 → 图/表 → 2 个易错点 → 3 道自测 → 一句话

### 3. 讲义阅读

- Markdown 正文，KaTeX 公式、Mermaid、SVG 动图
- `math-graph` 可拖滑块 / 切点 / 切线
- 有 `code_language` 的科目显示代码终端（gcc + bubblewrap，默认关闭）
- 阅读自动计时，切走暂停
- 一键「练这一课」→ Agent 组卷

### 4. 组卷与作答

- 按科目、考点、题型、题量、时限组卷
- 材料题：一段材料 / 一张图 / 一段音频带多道小题
- 一题可挂多个考点
- 题型由 `config/question_types.json` 决定，不写死在 UI 里
- 单题一屏、键盘操作、标记、草稿自动保存
- 主观题有 rubric，可自评；代码题有语言标记
- 「卡住了」把题目、用时、描述发给 Agent，Agent 回提示
- 交卷后客观题即时判分，主观题进评分队列

### 5. 结果与复习

- 得分、逐题解析、薄弱考点
- 主观题 Agent 评分 + 评语回写
- 错题按掌握度进入复习队列：1/3/7/15/30 天
- 连对 3 次掌握度 +1，答错 −1

### 6. AI 在 IDE 里做什么

| 能力 | 工具 |
|---|---|
| 看科目 / 考纲 | `list_subjects` `list_outline` |
| 出题 / 审题 | `create_questions` `list_pending_questions` `review_questions` |
| 组卷 | `create_agent_session` `build_quiz` |
| 讲义 | `publish_page` `update_page` `list_pages` |
| 协作 | `send_hint` `read_inbox` |
| 评分 | `get_grading_queue` `grade_answer` |
| 看结果 | `get_attempt` `get_due_reviews` `get_stats_today` `get_progress` |

### 7. 学习画像

- 静态目标：考试、日期、分数、每日时长、科目、备注
- 动态学情：正确率、时长、连续天数、薄弱考点、到期复习、近 7 天
- Agent 通过 `get_profile` 读取，用于安排当天内容

### 8. 数据与运维

- SQLite 单文件，`data/api/kaodian.db`
- 启动自动迁移 + 备份
- 支持导出 / 导入（JSON）
- Docker 非 root、健康检查、TZ 可配
- CI：pytest + lint + build
- 加科目只加内容仓库的 `packs/<id>/`
- 加题型只改框架的 `config/question_types.json`

## 二、必须做到的验收

### 内容模型

- [x] 材料题 / 一拖多：一个 group 带多道题
- [x] 题目可挂多个考点（“不属于具体考点”仍待做）
- [x] 题目 / 材料支持图片、音频、视频引用（带 alt / license）
- [x] 复合题：多小问用 group 承载，不另造一套模型

### 作答体验

- [x] 刷新 / 断网 / 崩溃后恢复答案、标记、自评、单题用时
- [x] 考试模式到时自动交卷
- [x] 键盘与移动端可用：Tab、数字键、空格不误触、题号可跳转
- [x] 交卷失败可重试，不重复计分
- [x] 大组件拆分：Quiz 181 行 / Console 159 行

### 数据

- [x] `GET /api/export` 导出科目、考纲、题库、讲义、进度
- [x] `POST /api/import` 合并导入（按 id / fingerprint 去重）
- [x] 迁移有版本、有备份、有回滚说明

### 工程

- [x] `make check` 通过
- [x] `docker compose up` 非 root 可跑
- [x] CI 配置完成（需推送到 GitHub 后实际跑）
- [x] 文档与代码一致

## 三、非目标

- 多用户 / 班级 / 教师后台
- 排行榜、生命值、内购
- 云端同步
- 多考试 / 多考纲版本（保持单一考试形态）

## 四、实施顺序

| 阶段 | 内容 | 状态 |
|---|---|---|
| v2 | 科目/题型配置化、迁移、同步、CI、Docker | ✅ |
| v2.1 | 材料题、多考点、媒体、复合题 | ✅ |
| v2.2 | 答题草稿、自动交卷、可访问性、组件拆分 | ✅ |
| v2.3 | 导出/导入、统计页、SSE | ✅ |
| v3 | 高数 15、计算机 17、英语 12、政治 12 页；题库 227 题 | 进行中 |

## 五、验收命令

```bash
make check
docker compose build
```

内容验收以控制台实际页面为准，不以“接口返回 200”为准。
