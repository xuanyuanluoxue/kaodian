# 本地开发与测试

## 环境

- Python 3.10+（当前 3.12）
- Node 20+（当前 24）
- 可选：gcc + bubblewrap（代码练习终端）

## 一次性安装

```bash
python3 -m venv .venv
.venv/bin/pip install -r apps/api/requirements-dev.txt
cd apps/web && npm install
```

MCP 需要额外依赖：

```bash
.venv/bin/pip install -r apps/mcp/requirements.txt
```

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
.venv/bin/python -m pytest apps/api/tests -q
```

当前 15 项：种子、校验、组卷、判分、复习、Agent 事件、代码沙箱、时长统计。

## Docker

```bash
docker compose up --build     # http://127.0.0.1:8010
```

- 数据卷：`./user-data:/data`
- 容器内 `KAODIAN_DB=/data/kaodian.db`
- 代码沙箱在容器里需要允许用户命名空间；若 `bwrap` 失败，优先用本地 uvicorn 跑

## 环境变量

| 变量 | 默认 | 说明 |
|---|---|---|
| `KAODIAN_DB` | `user-data/kaodian.db` | SQLite 路径 |
| `KAODIAN_DAILY_GOAL_MINUTES` | `30` | 每日目标分钟数 |
| `KAODIAN_ALLOW_CODE_RUN` | `0` | 设为 `1` 才启用代码练习终端 |

## 代码沙箱

- 编译：`gcc -std=c11`
- 隔离：`bubblewrap`，断网、只读系统、独立临时目录
- 限制：CPU 3 秒、内存 256 MB、进程 64、输出 64 KB
- **默认关闭**；启用后不要暴露到公网

## 常用命令

```bash
make test       # pytest
make build      # 前端构建
make dev-api    # 后端热重载
make dev-web    # 前端开发服务器
make docker     # compose 启动
```

## 数据

- 开发/运行数据都在 `user-data/kaodian.db`，不进 Git
- 备份与重置见 `user-data/README.md`
- 种子数据来自 `config/`，首次启动自动导入
