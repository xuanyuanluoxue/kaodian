# 考点 · Kaodian

> **Agent 的作答终端。** 你在对话里让 Agent 出题、给提示，在网页上作答；
> 计时和结果自动回传，Agent 接着安排下一组或讲解。
> 本地优先、无账号、数据在你自己机器上。

**状态：v0.1 纵向切片 + MCP。** 已跑通「Agent 建会话 → 组卷 → 作答计时 → 卡住求助 → 交卷回传」的完整链路，
并提供了可被 OpenCode / Claude Desktop 直接调用的 MCP 服务。
不接 Agent 也能手动组卷，但默认按「对话 + 网页」双屏使用设计。

讲解内容由「控制台」承载：Agent 写入 Markdown 页面，用户在控制台阅读，并可一键「练这一课」。

---

## 为什么是「配合 Agent」而不是又一个刷题网站

刷题时真正打断你的，不是题目，是**切换**：在聊天里问完，去题库里找题，做完再回来描述结果。

所以这个项目把职责拆开：

- **Agent 负责「学什么」**：按考纲编号出题、看你的卡点、给提示、决定下一组；
- **网页负责「怎么答」**：一题一屏、计时、标记、自评、把状态写回去。

两边通过一条事件流连起来：Agent 写的 `note` 会出现在答题页顶部，你点「卡住了」会把题目编号和本题用时发给 Agent，交卷后 `submitted` 事件直接进它的收件箱。**不需要复制粘贴，也不需要在对话里复述成绩。**

当然，考纲编号、自动判分、间隔复习这些底座仍然在：

1. 每道题挂在**考纲编号**上，学没学完一目了然；
2. 题目由 **Agent 按规范接口**生成，不用手工录；
3. 自动记**时长、对错、每题耗时**；
4. 错题按**掌握度**排下次出现的时间。

## 现在能做什么

| 模块 | v0.1 |
|---|---|
| Agent 协作 | 会话、事件流、答题页提示条、卡住求助、交卷自动回传 |
| 控制台 | 多邻国式学习路径：节点、连续天数、每日目标、XP；Agent 写入的 Markdown 讲义（含 Mermaid 流程图/时序图）；一键配套练习 |
| 可视化 | `/visuals/hello-anatomy.html` 代码解剖台；`/visuals/c-basics.html` 程序生命周期、变量盒子、整数除法 |
| 大纲 | 4 科 / 161 条考点 / 1236 h，从 Markdown 生成 JSON |
| 题库 | 24 道示例题；AI 生成先入库待审，审查通过才上架 |
| 评分 | 客观题自动判；主观题交卷后由 Agent 读库评分并写回 |
| 组卷 | 科目、考点编号、题型、题量、时限、练习/考试模式 |
| 作答 | 单题一屏、键盘操作、题号网格、标记 |
| 计时 | 切走自动暂停、90 秒无操作暂停、15 秒心跳、每题独立计时 |
| 判分 | 客观题自动；主观题按评分点自评 |
| 复习 | 连对 3 次掌握度 +1，答错 −1；间隔 1/3/7/15/30 天 |
| 主题 | 亮/暗两套配色，默认跟随系统，可手动切换 |
| 数据 | SQLite 单文件，无账号，无联网依赖 |

### 界面

- `/` 今天：今日时长、到期复习、四科入口
- `/console` 学习路径：节点式课程、连续天数、每日目标进度环；点节点进入阅读
- `/console?page=…` 阅读页：Markdown 讲义 + 「完成本课 +10 XP」+「练这一课」
- `/visuals/hello-anatomy.html` hello.c 解剖台：点代码、拨开关、看编译/运行结果
- `/visuals/c-basics.html` C 基础实验室：三个可动手的小实验
- `/build` 组卷：左侧选范围，右侧看可用题数与时限
- `/quiz/:id` 作答：左侧题目，右侧计时/进度/题号/交卷
- `/result/:id` 结果：得分、客观题正确率、薄弱考点、逐题解析
- `/review` 复习队列：按到期日与掌握度排序

## 和 Agent 一起用

```
你在对话里                        网页上
──────────────                   ──────────────────
"按 C-08 出 10 道"  ──→  组卷，返回 /quiz/xxx
                                      │
打开链接 ────────────────────────────→│ 作答、计时
                                      │
"卡住了" ────────────────────────────→│ 顶部协作条
                                      │   POST /api/agent/help
Agent 看到求助 ───────────────────────┤
"先跳过第 3 题"  ──→ POST note ──────→│ 5 秒内出现在顶部
                                      │
交卷 ────────────────────────────────→│ POST submit
Agent 读 inbox ←──────────────────────┤ submitted + 得分
```

协议细节、事件字段与 curl 示例见 [`docs/agent-protocol.md`](docs/agent-protocol.md)。

### 在 OpenCode 里接入 MCP

先装依赖：

```bash
.venv/bin/pip install -r apps/mcp/requirements.txt
```

注册服务（把路径换成你的仓库位置）：

```bash
opencode mcp add kaodian --global \
  --env KAODIAN_API=http://127.0.0.1:8010 \
  --env KAODIAN_WEB=http://127.0.0.1:8010 \
  -- /path/to/kaodian/.venv/bin/python /path/to/kaodian/apps/mcp/server.py
```

接好之后，在对话里说「按 C-08 出 6 道，练习模式」，Agent 会：

1. `list_outline` 确认编号；
2. `build_quiz` 建会话、组卷；
3. 把 `http://…/quiz/xxx` 发给你；
4. 你在网页上答，卡住点「卡住了」；
5. Agent 用 `read_inbox` 读到求助，用 `send_hint` 推提示；
6. 交卷后 Agent 用 `get_attempt` 读结果，安排下一组。

可用工具：`list_subjects` / `list_outline` / `create_agent_session` / `build_quiz` /
`send_hint` / `read_inbox` / `get_attempt` / `get_due_reviews` / `get_stats_today` /
`get_progress` / `publish_page` / `update_page` / `list_pages` / `list_quizzes` /
`create_questions` / `list_pending_questions` / `review_questions` /
`get_grading_queue` / `grade_answer`。

在对话里说「把今天这一节写成讲义并发布」，页面会出现在控制台；说「练这一课」，会按页面关联的考点编号组卷。

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
| `KAODIAN_DAILY_GOAL_MINUTES` | `30` | 每日目标分钟数 |

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

### 提前缓存下几章（子 Agent 流水线）

课程不需要等学到才写。主 Agent 可以提前派子 Agent 生成后面几章：

```text
主 Agent 派发子 Agent（每章一个）
  → 子 Agent 写讲义 .md
  → POST /api/pages   status=draft, lesson_key=L05
  → POST /api/questions/batch   status=pending（8–10 题）
  → 子 Agent 报告 page_id + question ids

主 Agent 验收
  → 读讲义，校对概念与例题
  → list_pending_questions 逐题验算
  → review_questions approve/reject
  → PATCH /api/pages/{id}  status=published
  → 控制台路径出现新节点
```

两条纪律：

1. **子 Agent 不许发布、不许审题、不许组卷**——它们只产出草稿和待审题。
2. **主 Agent 必须逐题验算**，不能把「格式校验通过」当成「内容正确」。

`lesson_key` 决定路径顺序（L01…L12），与创建时间无关。

### 题库流水线：生成 → 审查 → 上架

AI 生成的题**不会直接进入组卷**：

```text
create_questions / POST /api/questions/batch
        ↓  status = pending（格式已校验）
list_pending_questions / GET /api/questions?status=pending
        ↓  Agent 逐题审查：编号、答案、解析、评分点
review_questions / POST /api/questions/review  {approve | reject}
        ↓  只有 status = approved 的题
build_quiz / POST /api/quizzes
```

审查要点：答案是否唯一且正确、解析是否真的支持答案、主观题评分点是否可操作、题干是否和已有题重复。`reject` 的题留在库里但永不组卷。

### 主观题：Agent 读库评分

```text
学生交卷
  → 客观题立即判分
  → 主观题 response 写入 answer，score = NULL
  → attempt.grading_status = pending
Agent:
  GET  /api/grading/queue
  POST /api/grading/{attempt_id}/{question_id}  { score, feedback }
  → 写回 score/correct/feedback，重算本次得分
  → 结果页 5 秒轮询，自动显示分数和评语
```

评分依据是题目的 `rubric` + `reference_answer` + 学生 `response`，不是自评。自评只作为参考。

### API 一览

| 方法 | 路径 | 作用 |
|---|---|---|
| GET | `/api/subjects` | 科目与题量 |
| GET | `/api/outline` | 考点树 |
| GET | `/api/questions` | 按科目/编号/题型查 |
| GET/POST | `/api/pages` | 列出 / 发布学习页 |
| GET/PATCH/DELETE | `/api/pages/{id}` | 读取 / 更新 / 删除 |
| GET | `/api/quizzes` | 最近的练习单 |
| GET | `/api/progress` | 连续天数、每日目标、XP、完成课数 |
| POST | `/api/pages/{id}/complete` | 标记一课完成（+10 XP） |
| POST | `/api/questions/validate` | 只校验 |
| POST | `/api/questions/batch` | 批量入库（默认 `pending`，幂等去重） |
| POST | `/api/questions/review` | 审查：approve / reject |
| GET | `/api/stats/library` | 题库状态统计 |
| POST | `/api/quizzes` | 组卷 |
| POST | `/api/attempts` | 开始作答 |
| PATCH | `/api/attempts/{id}` | 心跳 / 存答案 |
| POST | `/api/attempts/{id}/submit` | 交卷并判分 |
| GET | `/api/attempts/{id}` | 结果 |
| GET | `/api/reviews/due` | 到期复习 |
| GET | `/api/stats/today` | 今日统计 |
| POST | `/api/agent/sessions` | 新建 Agent 会话 |
| POST | `/api/agent/events` | Agent 写提示 |
| GET | `/api/agent/feed` | 网页拉新事件 |
| GET | `/api/agent/inbox` | Agent 拉求助/交卷 |
| POST | `/api/agent/help` | 网页求助 |
| GET | `/api/grading/queue` | 主观题待评分队列 |
| POST | `/api/grading/{attempt_id}/{question_id}` | 写入主观题分数与评语 |

## 大纲配置

`config/subjects/*.json` 由 Markdown 大纲生成：

```bash
python scripts/import_outline.py --src /path/to/你的大纲目录
```

每个考点带 `code / title / section / hours / stage / frequency`。换一套考试，只换配置，不改代码。

## 目录结构

```
apps/mcp/server.py   stdio MCP 服务（HTTP 的薄包装）
apps/api/app/        FastAPI + SQLite
  pages              控制台页面（Markdown）
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

- [x] MCP 工具（`create_agent_session` / `build_quiz` / `send_hint` / `read_inbox`）
- [ ] Agent 流式提示（SSE 替换 5 秒轮询）
- [ ] FSRS 替换当前的掌握度间隔（保留 `review` 表接口）
- [ ] 讲解板块（独立 app，与刷题通过 `outline_code` + 同一事件流连接）
- [ ] 真题批量导入（docx/PDF → 校验 → 入库）
- [ ] 考试模式收尾：到时强制交卷、结果快照
- [ ] 手机 PWA + 离线草稿
- [ ] 统计看板：按考点编号的正确率、每题耗时分布

## 许可证与题目版权

代码：MIT，见 `LICENSE`。

种子题库中的题目**改编自公开的广东专升本历年真题，仅用于演示**。正式分发前请替换为自编题，或确认你所在地区的使用权限。用户自行导入的题目版权归其各自所有者。

---

如果这个项目对你有用，欢迎提 Issue 或 PR。最小可贡献的入口是：新增一种题型（Schema + 渲染器 + 判分器），或补一套你所在考试的大纲配置。