# 用户数据（user-data）

这个目录放**运行时的用户侧数据**，与源码分离，默认不进 Git。

| 文件 | 内容 |
|---|---|
| `kaodian.db` | SQLite：作答记录、答题时长、复习状态、页面进度、题库、讲义 |
| `kaodian.db-wal` / `-shm` | SQLite WAL 临时文件，随数据库一起备份 |
| `exports/` | 每日 JSON 导出（可选，未自动创建） |

## 备份

```bash
mkdir -p user-data/exports
cp user-data/kaodian.db "user-data/exports/kaodian-$(date +%F).db"
```

SQLite 有 WAL 时，最稳的是先停服务再复制；或者用：

```bash
sqlite3 user-data/kaodian.db ".backup user-data/exports/kaodian-$(date +%F).db"
```

## 重置

停服务后删掉 `kaodian.db*`，下次启动会重新建表并从 `config/` 导入种子数据。

## 边界

- 这个目录只放**数据**，不放代码。
- 学习内容（讲义 Markdown、计划）在私有工作区 `~/资料/学习`，不在本仓库。
- `apps/web` / `apps/api` / `apps/mcp` 是开发源码；`config/` 是课程配置。
