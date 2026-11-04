# 本地开发与测试

## 环境

- Python 3.11+（当前 3.12，见 `.python-version`）
- Node 20.19+（当前 24，见 `.nvmrc`）
- 可选：gcc + bubblewrap（代码练习终端）

## 一次性安装

```bash
make setup
```

等价于：

```bash
python3 -m venv .venv
.venv/bin/pip install -r apps/api/requirements-dev.txt -c apps/api/constraints.txt
.venv/bin/pip install -r apps/mcp/requirements.txt -c apps/api/constraints.txt
cd apps/web && npm ci
```

`constraints.txt` 锁住传递依赖；`npm ci` 严格按 `package-lock.json` 安装。

## 日常开发（两个终端）

先准备内容路径。默认会读 `examples/demo-content`，把数据写到 `data/`；
接入本机真实内容时复制示例配置：

```bash
cp kaodian.example.toml kaodian.toml
# 编辑 [paths] content / data，或改用环境变量
```

```bash
# 终端 1：后端
cd apps/api
../../.venv/bin/uvicorn app.main:app --reload --port 8000

# 终端 2：前端（/api 自动代理到 8000）
cd apps/web
npm run dev            # http://localhost:5173
```

也可以直接用 CLI：

```bash
bin/kaodian content validate    # 校验内容包
bin/kaodian content sync        # 文件 → DB
bin/kaodian serve --reload      # API + Web，默认 :8010
bin/kaodian doctor              # 路径、DB 版本、pack 状态
```

## 生产模式（单端口）

```bash
bin/kaodian serve --host 127.0.0.1 --port 8010
# 或先 make build，再起 uvicorn
```

FastAPI 直接托管 `apps/web/dist`，同时提供 API。

## 测试

```bash
make test     # .venv/bin/python -m pytest
make lint     # 前端 oxlint
make check    # test + lint + build
```

当前 48 项：示例内容包、校验、组卷、判分、复习、Agent 事件、代码沙箱、时长统计、
题型注册表、内容同步幂等/自然键、v3→v4 迁移、媒体防穿越、CLI 冒烟。

CI：`.github/workflows/ci.yml`，push / PR 跑后端测试 + 前端 lint + build。

## Docker

```bash
make docker     # 自动传当前 UID/GID，http://127.0.0.1:8010
```

- 非 root 运行；`user: "${KAODIAN_UID:-1000}:${KAODIAN_GID:-1000}"`
- 内容只读挂载：`${KAODIAN_CONTENT_HOST:-./content}:/content:ro`
- 数据卷：`${KAODIAN_DATA_HOST:-./data}:/data`
- 容器内 `KAODIAN_CONTENT_DIR=/content`、`KAODIAN_DATA_DIR=/data`
- `HEALTHCHECK` 打 `/api/health`；`cap_drop: ALL` + `no-new-privileges`
- 默认镜像**不装** gcc/bubblewrap；需要代码沙箱用 `make docker-sandbox`
- 容器内 `bwrap` 仍受用户命名空间限制，失败时优先用本地 uvicorn
- 想用示例内容而不挂载：`KAODIAN_CONTENT_DIR=/app/examples/demo-content`

## 环境变量

| 变量 | 默认 | 说明 |
|---|---|---|
| `KAODIAN_CONTENT_DIR` | `examples/demo-content` | 内容仓库根目录（含 `registry.json`） |
| `KAODIAN_DATA_DIR` | `data/` | 数据库、备份、导出、日志；自动创建 |
| `KAODIAN_DB` | `data_dir()/kaodian.db` | SQLite 路径，优先级最高 |
| `KAODIAN_DAILY_GOAL_MINUTES` | `30` | 每日目标分钟数 |
| `KAODIAN_ALLOW_CODE_RUN` | `0` | 设为 `1` 才启用代码练习终端 |
| `KAODIAN_CORS_ORIGINS` | 本地 5173 | 逗号分隔的允许来源 |
| `KAODIAN_CONFIG_DIR` | `config/` | 框架题型注册表目录（测试可覆盖） |
| `TZ` | `Asia/Shanghai`（Docker） | 影响「今天」与连续天数 |

路径优先级：环境变量 → 仓库根 `kaodian.toml` → 默认值。`kaodian.toml` 不提交。

## 代码沙箱

- 编译：`gcc -std=c11`
- 隔离：`bubblewrap`，断网、只读系统、独立临时目录
- 限制：CPU 3 秒、内存 256 MB、进程 64、输出 64 KB
- **默认关闭**；启用后不要暴露到公网

## 常用命令

```bash
make test        # pytest
make lint        # 前端 lint
make build       # 前端构建
make check       # 以上三项
make dev-api     # 后端热重载
make dev-web     # 前端开发服务器
bin/kaodian content validate  # 校验内容包（--json 供 Agent 读）
bin/kaodian content sync      # 内容 → DB
bin/kaodian backup            # SQLite 备份到 data_dir/exports/
bin/kaodian mcp-config        # 输出 IDE MCP JSON
make docker      # compose 启动（非 root）
make docker-sandbox  # 带 gcc/bubblewrap 的镜像 + 开启代码沙箱
```

## 数据

- 运行数据默认在 `data/api/kaodian.db`，不进 Git；可用 `KAODIAN_DATA_DIR` 改位置
- 备份：`bin/kaodian backup`，或停服务后复制 SQLite 文件
- 内容来自内容仓库，首次启动/`content sync` 自动同步；框架只带 `examples/demo-content`
- 迁移真实库：先停服务并备份，再启动让 v3→v4 迁移，最后 `content sync` 回填 `pack_id`
