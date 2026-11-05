# data/（运行时数据，不进 Git）

这个目录只放运行时数据，按 `apps/` 的模块镜像：

```
data/
├── api/
│   ├── kaodian.db          # SQLite：用户进度 + 内容索引
│   ├── backups/            # 迁移前备份 / 手动备份
│   └── exports/            # JSON 导出
├── profile.json            # 学习画像私有种子（kaodian profile export/import）
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
- `profile.json` 是**私有种子**：`bin/kaodian profile export` 导出静态画像
  （`{version: 3, exported_at, static}`，不含动态学情），`profile import` 恢复；
  内容只进 `data/api/kaodian.db` 与 `data/profile.json`，不进内容仓库，也不进 Git。
- 备份、迁移、导出都只动这里。
- 删除 `data/api/kaodian.db` 会丢用户进度；内容可以重新 `content sync`。
