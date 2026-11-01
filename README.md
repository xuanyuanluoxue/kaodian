# 考点 · Kaodian

> 面向**有明确考纲**的考生：AI 按考点编号出题，刷完自动计时、自动排复习。
> 本地优先、无账号、数据在你自己机器上。

**状态：v0.1 纵向切片。** 已跑通「AI/接口出题 → 组卷 → 作答计时 → 判分 → 回写复习」的完整链路。
讲解板块是独立模块，暂未并入本仓库。

---

## 为什么做这个

市面上的刷题工具大多假设两件事：题是你自己找的，考试没有考纲。

但专升本、自考、考公这类考试恰好相反——**范围是固定的，题目是海量的，遗忘是必然的**。
所以真正需要的不是「又一个题库」，而是：

1. 每道题都挂在**考纲编号**上，学没学完一目了然；
2. 题目可以由 **AI 按规范接口**生成，不用手工录；
3. 刷完自动记**时长、对错、每题耗时**；
4. 错题按**掌握度**排下次出现的时间，而不是堆在收藏夹里。

## 现在能做什么

| 模块 | v0.1 |
|---|---|
| 大纲 | 4 科 / 161 条考点 / 1236 h，从 Markdown 生成 JSON |
| 题库 | 23 道示例题（C 语言，含单选/判断/填空/简答/编程） |
| 组卷 | 科目、考点编号、题型、题量、时限、练习/考试模式 |
| 作答 | 单题一屏、键盘操作、题号网格、标记 |
| 计时 | 切走自动暂停、90 秒无操作暂停、15 秒心跳、每题独立计时 |
| 判分 | 客观题自动；主观题按评分点自评 |
| 复习 | 连对 3 次掌握度 +1，答错 −1；间隔 1/3/7/15/30 天 |
| 数据 | SQLite 单文件，无账号，无联网依赖 |

### 界面

- `/` 今天：今日时长、到期复习、四科入口
- `/build` 组卷：左侧选范围，右侧看可用题数与时限
- `/quiz/:id` 作答：左侧题目，右侧计时/进度/题号/交卷
- `/result/:id` 结果：得分、客观题正确率、薄弱考点、逐题解析
- `/review` 复习队列：按到期日与掌握度排序

## 快速开始

### Docker（推荐）

```bash
docker compose up --build
# 打开 http://localhost:8010
```

数据落在仓库下的 `data/kaodian.db`，删掉即重置。

### 本地开发

需要 Python 3.10+、Node 20+。

```bash
# 后端
python3 -m venv .venv
.venv/bin/pip install -r apps/api/requirements-dev.txt
cd apps/api && ../../.venv/bin/uvicorn app.main:app --reload --port 8000

# 前端（另开一个终端）
cd apps/web
npm install
npm run dev        # http://localhost:5173，/api 已代理到 8000
```

生产模式由 FastAPI 直接托管构建产物：

```bash
cd apps/web && npm run build
cd apps/api && ../../.venv/bin/uvicorn app.main:app --port 8000
# http://localhost:8000
```

环境变量：

| 变量 | 默认 | 说明 |
|---|---|---|
| `KAODIAN_DB` | `data/kaodian.db` | SQLite 路径 |

## AI 出题接口

设计原则：**AI 只能按规范写，服务端负责校验。** 一次批量提交，要么全进，要么全退。

```bash
# 1. 拿合法考点编号（不要自己编）
curl http://localhost:8000/api/outline?subject_id=computer

# 2. 先校验，不入库
curl -X POST http://localhost:8000/api/questions/validate \
  -H 'Content-Type: application/json' \
  -d @questions.json

# 3. 通过后入库
curl -X POST http://localhost:8000/api/questions/batch \
  -H 'Content-Type: application/json' \
  -d @questions.json

# 4. 组卷
curl -X POST http://localhost:8000/api/quizzes \
  -H 'Content-Type: application/json' \
  -d '{"mode":"practice","count":10,
       "filters":{"subject_id":"computer","codes":["C-08"],"types":["single","judge"]}}'
```

题目 JSON 示例：

```json
{
  "outline_code": "C-08",
  "type": "single",
  "stem": "执行 `int a=1; while(a<4) printf(\"%d\",a++);` 的输出是（ ）",
  "options": ["1", "12", "1234", "123"],
  "answer": ["D"],
  "explanation": "a 依次为 1、2、3 时打印，随后 a 变成 4，条件不成立退出。",
  "difficulty": 1,
  "score": 3,
  "source": { "kind": "ai", "model": "your-model", "date": "2026-11-01" },
  "tags": ["while", "后置自增"],
  "verified": false
}
```

主观题必须带评分点，且分数加总等于 `score`：

```json
{
  "outline_code": "D-03",
  "type": "short",
  "stem": "简述顺序表与链表的优缺点。",
  "explanation": "按「顺序表—链表—对比」三段作答。",
  "reference_answer": "……",
  "rubric": [
    { "point": "顺序表支持随机访问 O(1)", "score": 3 },
    { "point": "链表已知位置插入删除 O(1)", "score": 3 },
    { "point": "顺序表插入删除需移动元素", "score": 2 },
    { "point": "链表不支持随机访问", "score": 2 }
  ],
  "score": 10,
  "difficulty": 2
}
```

校验规则（节选）：编号必须存在且与科目匹配、单选唯一答案、多选至少两个、评分点总分一致、解析至少 10 字、题干去重。

### API 一览

| 方法 | 路径 | 作用 |
|---|---|---|
| GET | `/api/subjects` | 科目与题量 |
| GET | `/api/outline` | 考点树 |
| GET | `/api/questions` | 按科目/编号/题型查 |
| POST | `/api/questions/validate` | 只校验 |
| POST | `/api/questions/batch` | 批量入库（幂等去重） |
| POST | `/api/quizzes` | 组卷 |
| POST | `/api/attempts` | 开始作答 |
| PATCH | `/api/attempts/{id}` | 心跳 / 存答案 |
| POST | `/api/attempts/{id}/submit` | 交卷并判分 |
| GET | `/api/attempts/{id}` | 结果 |
| GET | `/api/reviews/due` | 到期复习 |
| GET | `/api/stats/today` | 今日统计 |

## 大纲配置

`config/subjects/*.json` 由 Markdown 大纲生成：

```bash
python scripts/import_outline.py --src /path/to/你的大纲目录
```

每个考点带 `code / title / section / hours / stage / frequency`。换一套考试，只换配置，不改代码。

## 目录结构

```
apps/api/app/        FastAPI + SQLite
  main.py            路由
  grading.py         判分与题目校验
  review.py         掌握度与复习间隔
  schema.sql         表结构
apps/api/tests/      pytest
apps/web/            React + Vite + TypeScript
config/subjects/     四科大纲
config/questions/    种子题库
scripts/             大纲导入
```

## 开发与测试

```bash
make test          # pytest
make build         # 前端构建
make dev-api       # 后端热重载
make dev-web       # 前端开发服务器
```

## 数据与隐私

- 默认**不联网**，没有账号、没有遥测；
- 全部数据在 `data/kaodian.db`，SQLite 单文件，可直接备份/迁移；
- 前端不把答案发给第三方；AI 出题是可选的外部调用，Key 由使用者自己配置（v0.2 接入）。

## Roadmap

- [ ] FSRS 替换当前的掌握度间隔（保留 `review` 表接口）
- [ ] AI 出题 UI + MCP 工具（`build_quiz` / `get_due_reviews`）
- [ ] 讲解板块（独立 app，与刷题通过 `outline_code` 连接）
- [ ] 真题批量导入（docx/PDF → 校验 → 入库）
- [ ] 考试模式收尾：到时强制交卷、结果快照
- [ ] 手机 PWA + 离线草稿
- [ ] 统计看板：按考点编号的正确率、每题耗时分布

## 许可证与题目版权

代码：MIT，见 `LICENSE`。

种子题库中的题目**改编自公开的广东专升本历年真题，仅用于演示**。正式分发前请替换为自编题，或确认你所在地区的使用权限。用户自行导入的题目版权归其各自所有者。

---

如果这个项目对你有用，欢迎提 Issue 或 PR。最小可贡献的入口是：新增一种题型（Schema + 渲染器 + 判分器），或补一套你所在考试的大纲配置。