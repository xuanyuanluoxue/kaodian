# 学习画像（profile v3）

> v1：目标考试 / 分数 / 每日时长。v2：升学目标、学习条件、自我评估、AI 补全。
> v3：志愿表、分科目标分、阶段计划、CLI 导入导出，让画像能承载「已经定下来的升学方案」。

## 1. 字段

### 升学目标

| 字段 | 说明 |
|---|---|
| `target_exam` | 考试名称，如 `2028 广东专升本` |
| `target_date` | 考试日期 `YYYY-MM-DD` |
| `target_score` | 目标总分 |
| `exam_total` | 满分，默认 500 |
| `hard_lines` | 硬线说明，如「三科 105 / 专业综合课 60」 |
| `targets` | 志愿表 JSON，见下 |
| `target_school` | 首选院校（由 `targets` 同步，兼容旧数据） |
| `target_major` | 目标专业 |
| `target_region` | 目标地区 |
| `backup_school` | 兜底院校（由 `targets` 同步） |
| `backup_major` | 兜底专业（由 `targets` 同步） |
| `exam_type` | 升学类型 |
| `current_education` | 当前学历 |
| `graduation_year` | 毕业年份 |

`targets` 是数组，按志愿顺序：

```json
[
  {"tier": "冲", "school": "韩山师范学院", "major": "计算机科学与技术",
   "score": 424, "rank": 120, "location": "珠海（协同培养）", "note": ""},
  {"tier": "稳", "school": "嘉应学院", "major": "计算机科学与技术",
   "score": 413, "rank": 200, "location": "梅州", "note": ""},
  {"tier": "保", "school": "惠州学院", "major": "软件工程",
   "score": 404, "rank": 308, "location": "惠州（联合培养）", "note": ""},
  {"tier": "兜底", "school": "广州科技职业技术大学", "major": "计算机应用工程",
   "score": 182, "rank": 7599, "location": "广州（民办）", "note": ""}
]
```

- `tier` 只能是 `冲` / `稳` / `保` / `兜底`；
- `score` / `rank` 可为 `null`；
- 最多 8 条；
- 写入后同步 `target_school` = 第一条 `school`，`backup_school` = `兜底` 条（无则最后一条）；
  若同一次请求显式传了 `target_school` / `backup_school`，以显式值为准；
- `targets: []` 会一并清空派生的 `target_school` / `backup_school` / `backup_major`。

### 分科目标

| 字段 | 说明 |
|---|---|
| `subject_targets` | JSON 对象，`{subject_id: 目标分}`，如 `{"computer":190,"math":85,"english":55,"politics":80}` |

键必须是已存在科目；分数 0–`exam_total`。

### 阶段计划

| 字段 | 说明 |
|---|---|
| `plan_phase` | `P1` / `P2` / `P3` |
| `phase_start` | `YYYY-MM-DD` |
| `phase_end` | `YYYY-MM-DD`，不早于 start |
| `phase_daily_minutes` | 阶段日均分钟，1–600 |
| `phase_goal` | 阶段目标，≤500 字 |
| `total_hours` | 全程预算小时，0–100000 |

阶段只是**当前执行档位**，不是历史记录；换阶段时覆盖。

### 学习条件 / 自我评估 / 教学偏好

沿用 v2：`daily_minutes`、`subjects`、`study_window`、`constraints`、
`strengths`、`weaknesses`、`motivation`、`notes`、`ai_summary`、
`preferred_tone`、`preferred_examples`、`updated_by`。

## 2. Schema v9

`profile` 增加：

```sql
targets TEXT,
subject_targets TEXT,
exam_total INTEGER,
hard_lines TEXT,
plan_phase TEXT,
phase_start TEXT,
phase_end TEXT,
phase_daily_minutes INTEGER,
phase_goal TEXT,
total_hours INTEGER
```

旧库启动时备份后只加列，已有行保留。

## 3. 完整度

必填 8 项：

`target_exam`、`target_date`、`target_score`、`targets`、`target_major`、
`daily_minutes`、`subjects`、`motivation`

`targets` 为空但 `target_school` 有值时视为已填（兼容 v2 数据）。

`GET /api/profile` 返回：

```json
{
  "static": {},
  "dynamic": {},
  "completeness": 1.0,
  "missing": [],
  "next_questions": [],
  "phase": {
    "name": "P1",
    "goal": "C 语言基础 + 高数第一轮；2027 报名考试拿真实排位",
    "start": "2026-11-01",
    "end": "2027-03-31",
    "daily_minutes": 120,
    "days_left": 146,
    "progress": 0.02
  }
}
```

- `phase` 为 `null`（无阶段）或对象；
- `days_left` = `phase_end - today`，可为负；
- `progress` = 已过天数 / 总天数，0–1；无起止为 `null`。

## 4. API

- `GET /api/profile` → `{static, dynamic, completeness, missing, next_questions, phase}`
- `PUT /api/profile` 局部更新；新增字段校验：

| 字段 | 校验 |
|---|---|
| `targets` | 数组 ≤8；`tier` 枚举；`school` 必填 ≤100；`major` ≤100；`location` ≤100；`note` ≤200；`score` 0–`exam_total`；`rank` 0–1000000 |
| `subject_targets` | 科目必须存在；分数 0–`exam_total` |
| `plan_phase` | `P1` / `P2` / `P3` / 空 |
| `phase_start` / `phase_end` | `YYYY-MM-DD`；end ≥ start |
| `phase_daily_minutes` | 1–600 |
| `phase_goal` | ≤500 |
| `total_hours` | 0–100000 |
| `exam_total` | 1–1000 |
| `hard_lines` | ≤200 |

非法值返回 422，消息为中文，指明字段。

## 5. CLI

画像要能离开数据库备份、迁移、重建：

```bash
bin/kaodian profile show --json
bin/kaodian profile export --output data/profile.json
bin/kaodian profile import data/profile.json
```

- `export` 写 `{static, version, exported_at}`，不含动态学情；
- `import` 接受 `{static: {...}}` 或扁平静态对象，走同一套校验；
- `import` 默认 `source="user"`，文件里有 `source` 时以其为准；
- 导入后打印完整度与缺失项。

`data/profile.json` 是私有种子文件，不进 Git；`data/README.md` 说明其用途。

## 6. MCP

`get_profile()` 返回完整结构（含 `completeness` / `missing` / `next_questions` / `phase`）。

`update_profile(...)` 增加 `targets`、`subject_targets`、`exam_total`、`hard_lines`、
`plan_phase`、`phase_start`、`phase_end`、`phase_daily_minutes`、`phase_goal`、`total_hours`。

推荐流程：

```
get_profile
→ 看 missing / next_questions / phase
→ 一次问 2–3 个问题
→ update_profile(..., source="agent", ai_summary="...")
→ 再 get_profile 确认完整度
```

`targets` 用 JSON 数组传，不拆成多个参数。

## 7. 前端

`/profile`：

- 目标卡：考试、倒计时、目标总分 / 满分、每日目标、今日已学
- 阶段卡：阶段名、目标、起止、日均、剩余天数、进度条
- 志愿表：冲 / 稳 / 保 / 兜底四行，可增删改；显示 2026 线、排位、地点
- 分数模型：四科目标分 vs 当前正确率
- 完整度、missing、AI 补全、AI 摘要沿用 v2
- 分组表单：升学目标 / 学习条件 / 自我评估 / 教学偏好
- 空值显示 `—`，不出现 `NaN` / `undefined`

## 8. 数据边界

- 画像只进 `data/api/kaodian.db` 与 `data/profile.json`，不进内容仓库；
- 外部决策档案（择校笔记、分数线）是**只读依据**，画像是**当前执行状态（可改）**；
  改目标先改决策记录，再更新画像；
- 不写身份证、学号、联系方式、家庭财务细节。

## 9. 验收

- v8 → v9 迁移保留原有字段，新增列默认 `NULL`
- `targets` 写入后 `target_school` / `backup_school` 同步；显式传值优先
- `completeness` / `missing` / `phase` 随字段变化
- 非法 tier / 日期 / 分数 / 科目 → 422
- CLI export → import 往返一致
- `/profile` 志愿表增删改保存后刷新保留
- `make check` 全绿
