# data/（运行时数据，不进 Git）

这个目录只放运行时数据，按 `apps/` 的模块镜像：

```
data/
├── api/
│   ├── kaodian.db          # SQLite：用户进度 + 内容索引
│   ├── backups/            # 迁移前备份 / 手动备份
│   └── exports/            # JSON 导出
├── web/
│   └── uploads/            # 预留：用户上传
├── mcp/
│   └── logs/               # 预留：MCP 日志
├── cli/
│   └── cache/              # 预留：CLI 缓存
└── shared/
    ├── logs/               # API / 服务日志
    └── sandbox/            # 代码沙箱临时目录
```

- 整个 `data/` 被 `.gitignore` 排除，只有本 README 入库。
- 备份、迁移、导出都只动这里。
- 删除 `data/api/kaodian.db` 会丢用户进度；内容可以重新 `content sync`。
