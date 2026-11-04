---
lesson_key: "D-01"
title: "第 1 课 · 内容包怎么工作"
summary: "从 registry.json 到数据库：自然键、pack_id 与媒体路径。"
kind: "lesson"
status: "published"
sort_order: 10
outline_codes: ["D-01"]
---

# 第 1 课 · 内容包怎么工作

内容仓库只有 Markdown、JSON 和素材；框架启动时把它们同步进 SQLite。

![演示素材](/media/demo/demo.svg)

## 三个自然键

| 内容 | 自然键 |
|---|---|
| 科目 | `subject.id` |
| 考点 | `outline_node.code` |
| 题目 | `question.id`，没有则用题干指纹 |
| 页面 | `subject_id + lesson_key`；大纲页用 `subject_id + kind='outline'` |

同步只 upsert，不删除本地运行时创建的内容。
