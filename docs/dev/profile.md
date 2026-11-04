# 学习画像（profile v1）

> 静态目标存表，动态学情实时算。画像属于用户数据，只进 `data/api/kaodian.db`，不进内容仓库。

## 1. Schema v7

`profile` 单行表：

| 列 | 类型 | 说明 |
|---|---|---|
| `id` | INTEGER PK | 固定 1 |
| `target_exam` | TEXT | 如 `2028 广东专升本` |
| `target_date` | TEXT | `YYYY-MM-DD`，可为空 |
| `target_score` | REAL | 目标分，可为空 |
| `daily_minutes` | INTEGER | 每日目标分钟，1–600，默认 30 |
| `subjects` | TEXT | JSON 数组，默认全部科目 id |
| `notes` | TEXT | 备注，≤2000 字 |
| `preferred_tone` | TEXT | 讲解语气，≤200 字 |
| `preferred_examples` | TEXT | 例子偏好，≤200 字 |
| `updated_at` | TEXT | 最后修改时间 |

旧库迁移前备份；v6→v7 只建表。

## 2. API

### `GET /api/profile`

```json
{
  "static": {
    "target_exam": "2028 广东专升本",
    "target_date": "2028-03-28",
    "target_score": 425,
    "daily_minutes": 120,
    "subjects": ["computer", "math", "english", "politics"],
    "notes": "",
    "preferred_tone": "",
    "preferred_examples": ""
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
      {"id":"math","name":"高等数学","short":"高数","color":"#2f5d8a",
       "answered":50,"correct":35,"accuracy":0.7,"seconds":3600}
    ],
    "weak_codes": [
      {"code":"M-09","title":"导数定义","wrong":4}
    ],
    "recent": [
      {"date":"2026-11-04","seconds":2700,"answered":12}
    ]
  }
}
```

- `days_to_exam`：`target_date - today`，空目标为 null
- `accuracy`：0–1，小数 3 位；无作答为 null
- `weak_codes`：按答错次数 Top 5
- `recent`：近 7 天，缺失日期补 0
- 动态部分全部实时查询，不落库

### `PUT /api/profile`

Body 任意静态字段：

```json
{
  "target_exam": "2028 广东专升本",
  "target_date": "2028-03-28",
  "target_score": 425,
  "daily_minutes": 120,
  "subjects": ["computer","math"],
  "notes": "数学基础弱",
  "preferred_tone": "直接",
  "preferred_examples": "先具体再一般"
}
```

校验：

- `target_date` 必须是 `YYYY-MM-DD`
- `daily_minutes` 1–600
- `subjects` 必须是已存在科目
- 文本长度限制
- 返回更新后的 `GET /api/profile` 同结构

## 3. MCP

新增：

| 工具 | 作用 |
|---|---|
| `get_profile()` | 读静态 + 动态 |
| `update_profile(...)` | 改静态字段 |

MCP instructions 加一句：每次开工先 `get_profile`，再决定学什么。

## 4. 前端

路由 `/profile`，导航加「画像」：

- 顶部：目标考试、倒计时、目标分、每日目标
- 静态表单可编辑：考试/日期/分数/每日分钟/科目/备注/语气/例子偏好
- 动态区：
  - 总正确率、作答数、连续天数、XP、完成课数、到期复习
  - 四科卡片：正确率条 + 时长 + 作答数
  - 薄弱考点 Top 5
  - 近 7 天柱状图（纯 CSS）
- 空目标显示「设置目标」引导，不显示 NaN

## 5. 安全

- 画像只在本地 DB，不写内容仓库、不进导出 content scope。
- 不存身份证、学校、真实姓名等敏感信息；`notes` 只放学习相关。
- 后续 HTTP MCP 暴露时需 token。

## 6. 验收

- 新库有默认 profile，`daily_minutes=30`，`subjects` 为当前科目
- PUT 后 GET 一致；日期/分钟/科目非法 422
- 有作答数据时动态字段正确；无数据不报错
- `/profile` 可保存、刷新后保留
- `make check` 全绿
