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

```bash
# 终端 1：后端
cd apps/api
../../.venv/bin/uvicorn app.main:app --reload --port 8000

# 终端 2：前端（/api 自动代理到 8000）
cd apps/web
npm run dev            # http://localhost:5173
```

## 生产模式（单端口）

```bash
cd apps/web && npm run build
cd apps/api && ../../.venv/bin/uvicorn app.main:app --host 127.0.0.1 --port 8010
# http://127.0.0.1:8010
```

FastAPI 直接托管 `apps/web/dist`，同时提供 API。

## 测试

```bash
make test     # .venv/bin/python -m pytest
make lint     # 前端 oxlint
make check    # test + lint + build
```

当前 25 项：种子、校验、组卷、判分、复习、Agent 事件、代码沙箱、时长统计、
题型注册表、内容同步幂等、页面排序、新增科目仅靠配置。

CI：`.github/workflows/ci.yml`，push / PR 跑后端测试 + 前端 lint + build。

## Docker

```bash
make docker     # 自动传当前 UID/GID，http://127.0.0.1:8010
```

- 非 root 运行；`user: "${KAODIAN_UID:-1000}:${KAODIAN_GID:-1000}"`
- 数据卷：`./user-data:/data`；宿主机 UID 不是 1000 时用 `make docker`
- 容器内 `KAODIAN_DB=/data/kaodian.db`，`TZ` 默认 `Asia/Shanghai`
- `HEALTHCHECK` 打 `/api/health`；`cap_drop: ALL` + `no-new-privileges`
- 默认镜像**不装** gcc/bubblewrap；需要代码沙箱用 `make docker-sandbox`
- 容器内 `bwrap` 仍受用户命名空间限制，失败时优先用本地 uvicorn

## 环境变量

| 变量 | 默认 | 说明 |
|---|---|---|
| `KAODIAN_DB` | `user-data/kaodian.db` | SQLite 路径 |
| `KAODIAN_DAILY_GOAL_MINUTES` | `30` | 每日目标分钟数 |
| `KAODIAN_ALLOW_CODE_RUN` | `0` | 设为 `1` 才启用代码练习终端 |
| `KAODIAN_CORS_ORIGINS` | 本地 5173 | 逗号分隔的允许来源 |
| `KAODIAN_CONFIG_DIR` | `config/` | 科目/题型配置目录（测试可覆盖） |
| `TZ` | `Asia/Shanghai`（Docker） | 影响「今天」与连续天数 |

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
make docker      # compose 启动（非 root）
make docker-sandbox  # 带 gcc/bubblewrap 的镜像 + 开启代码沙箱
```

## 数据

- 开发/运行数据都在 `user-data/kaodian.db`，不进 Git
- 备份与重置见 `user-data/README.md`
- 种子数据来自 `config/`，首次启动自动导入
