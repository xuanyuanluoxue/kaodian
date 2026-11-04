# 学习画像（profile v2）

> v1 只有目标考试/分数/每日时长；v2 补升学目标、学习条件、自我评估，并让 AI 在对话后补全。

## 1. 字段

### 升学目标

| 字段 | 说明 |
|---|---|
| `target_exam` | 考试名称，如 `2028 广东专升本` |
| `target_date` | 考试日期 `YYYY-MM-DD` |
| `target_score` | 目标分 |
| `target_school` | 目标院校 |
| `target_major` | 目标专业 |
| `target_region` | 目标地区 |
| `backup_school` | 保底院校 |
| `backup_major` | 保底专业 |
| `exam_type` | 升学类型，如 专升本/自考/考研 |
| `current_education` | 当前学历 |
| `graduation_year` | 毕业年份 |

### 学习条件

| 字段 | 说明 |
|---|---|
| `daily_minutes` | 每日目标分钟 |
| `subjects` | 本次准备的科目 id 数组 |
| `study_window` | 可学习时段，如“工作日晚上 + 周末” |
| `constraints` | 时间/工作/家庭等限制 |

### 自我评估

| 字段 | 说明 |
|---|---|
| `strengths` | 自认为的优势 |
| `weaknesses` | 自认为的薄弱点 |
| `motivation` | 为什么考 |
| `notes` | 用户备注（用户手写） |
| `ai_summary` | AI 在对话后整理的摘要（AI 维护，不覆盖 notes） |

### 教学偏好

`preferred_tone`、`preferred_examples`。

## 2. Schema v8

`profile` 增加：

```sql
target_school TEXT,
target_major TEXT,
target_region TEXT,
backup_school TEXT,
backup_major TEXT,
exam_type TEXT,
current_education TEXT,
graduation_year INTEGER,
study_window TEXT,
constraints TEXT,
strengths TEXT,
weaknesses TEXT,
motivation TEXT,
ai_summary TEXT,
updated_by TEXT NOT NULL DEFAULT 'user'
```

旧库备份后只加列。已有行保留。

## 3. 完整度

必填 8 项：

`target_exam`、`target_date`、`target_score`、`target_school`、`target_major`、`daily_minutes`、`subjects`、`motivation`

`GET /api/profile` 增加：

```json
{
  "completeness": 0.75,
  "missing": ["target_school", "motivation"],
  "next_questions": [
    {"field": "target_school", "question": "你想冲哪所学校？有保底吗？"},
    {"field": "motivation", "question": "你为什么要考这个本科？"}
  ]
}
```

- `completeness` = 已填必填 / 8
- `missing` 按必填顺序
- `next_questions` 先必填、后选填，最多 6 条

## 4. API

`GET /api/profile` → `{static, dynamic, completeness, missing, next_questions}`

`PUT /api/profile`：

```json
{
  "target_school": "广东技术师范大学",
  "target_major": "计算机科学与技术",
  "target_region": "广州",
  "backup_school": "广东白云学院",
  "exam_type": "专升本",
  "current_education": "专科",
  "graduation_year": 2028,
  "study_window": "工作日晚上 2h + 周末 4h",
  "constraints": "白天上班",
  "strengths": "英语单词记得快",
  "weaknesses": "数学基础弱",
  "motivation": "想换到计算机相关岗位",
  "ai_summary": "目标是 2028 广东专升本……",
  "source": "agent"
}
```

- 局部更新，不传的字段不动
- `source`：`user` / `agent`，默认 `user`，写入 `updated_by`
- `ai_summary` 只由 AI 写；`notes` 只由用户写
- 校验：年份 1950–2100；文本长度；科目存在；日期格式

## 5. MCP

`get_profile()` 返回完整结构（含完整度、missing、next_questions）。

`update_profile(...)` 增加新字段和 `ai_summary`、`source="agent"`。

推荐对话流程：

```
get_profile
→ 看 missing / next_questions
→ 一次问 2–3 个问题
→ update_profile(..., source="agent", ai_summary="...")
→ 再 get_profile 确认完整度
```

MCP instructions 写明：不要一次问完所有问题；先问目标院校/专业/动机，再问时间限制和薄弱点。

## 6. 前端

`/profile` 增加：

- 完整度条：`75% · 还差 2 项`
- 升学目标分组：考试/日期/分数/院校/专业/地区/保底/类型/学历/毕业年
- 学习条件分组：每日分钟/科目/学习时段/限制
- 自我评估分组：优势/薄弱/动机/备注
- AI 摘要卡：显示 `ai_summary`，标注“AI 整理”
- “让 AI 完善画像”按钮：复制提示词，包含 missing 和当前画像摘要
- 保存后显示“由你更新 / 由 AI 更新”

## 7. 验收

- 老库 v7→v8 保留原目标/科目/备注
- 完整度随字段变化
- AI 通过 `update_profile(source="agent", ai_summary=...)` 更新后，页面显示 AI 摘要和 `updated_by=agent`
- 用户保存不会清空 `ai_summary`
- 非法年份/日期/科目 422
- `make check` 全绿
