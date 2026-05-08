# 项目指南 — AI 知识库助手

## 项目概述

本目录是一个 **AI 技术知识库采集与分析系统**，自动从 GitHub Trending、Hacker News 等渠道采集技术动态，经深度分析、评分、标签化后存入结构化知识库。

## 目录结构

```
week1/
├── .opencode/          # opencode 配置
│   ├── agents/         # Agent 定义（collector、analyzer、organizer）
│   └── skills/         # 技能定义（github-trending、tech-summary、prd-to-plan）
├── knowledge/          # 知识库数据
│   ├── raw/            # 采集 Agent 产出的原始数据（JSON）
│   ├── analyzed/       # 分析 Agent 产出的分析结果（JSON）
│   ├── analysis/       # 深度技术分析报告（Markdown/JSON）
│   ├── articles/       # 最终入库的标准化知识条目（JSON）
│   └── entries/        # 历史知识条目（JSON）
├── AGENTS.md           # 本文件 — 项目级 Agent 指南
└── LICENSE
```

## 数据流水线

```
采集(collector) → 分析(analyzer) → 整理入库(organizer)
    ↓                  ↓                  ↓
knowledge/raw/    knowledge/analyzed/  knowledge/articles/
```

### 1. 采集阶段（collector Agent）

- 使用联网搜索、网页读取、GitHub 仓库分析等工具采集技术动态
- 输出到 `knowledge/raw/`，文件命名：`{主题}-{日期}.json`
- 质量要求：条目 >= 15 条，字段完整，URL 真实，中文摘要

### 2. 分析阶段（analyzer Agent）

- 读取原始数据，通过 WebFetch 访问原始链接进行深度分析
- 输出到 `knowledge/analyzed/`，文件命名：`{主题}-{日期}-analysis.json`
- 包含评分（1-10）、亮点、标签，评分标准：
  - 9-10：改变格局
  - 7-8：直接有帮助
  - 5-6：值得了解
  - 1-4：可略过

### 3. 整理入库阶段（organizer Agent）

- 去重、格式化、分类存入 `knowledge/articles/`
- 文件命名：`{date}-{source}-{slug}.json`
- 维护 `knowledge/articles/index.json` 索引（日期倒序）

## 可用技能（Skills）

| 技能 | 用途 |
|------|------|
| `github-trending` | 采集 GitHub 热门开源项目 |
| `tech-summary` | 对采集内容进行深度分析总结 |
| `prd-to-plan` | 将 PRD 拆解为分阶段实施计划 |

## 编码规范

- 所有知识条目文件为 JSON 格式，UTF-8 编码
- 日期统一使用 ISO 格式：`YYYY-MM-DD`
- 标签统一小写，去除前后空格
- 摘要使用中文撰写，客观准确
- slug 使用 kebab-case，纯小写英文与连字符，不超过 40 字符
- 同日期同主题重复运行时，文件名追加序号（`-2`、`-3`）避免覆盖

## 重要约束

- **绝不编造 URL**：所有链接必须来自实际采集页面
- **绝不编造分析内容**：评分与分析基于实际内容
- **各 Agent 权限隔离**：采集 Agent 不可写文件，分析 Agent 不可写文件，整理 Agent 不可访问网络
- **写入前先检查**：使用 Glob 检查目标目录已有文件，避免覆盖

## 语言要求

- 始终使用简体中文进行思考和输出
- 代码标识符遵循项目原有命名规范
- Git 提交注释使用中文
