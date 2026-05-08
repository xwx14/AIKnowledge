# AGENTS.md — OpenClaw Agent 配置

> OpenClaw 网关的 Agent 路由与协作配置。
> 每个 Agent 对应一种用户意图，由 openclaw.json5 中的 bindings 进行消息分发。

## Agent 列表

### knowledge-query（知识检索）

**触发条件**：用户消息包含"知识""搜索""查询"等关键词，或使用 `/search` 命令

**职责**：

- 解析用户查询意图（关键词、标签、时间范围）
- 在 `knowledge/articles/` 中检索匹配条目
- 按相关性评分排序，返回 Top 5 结果
- 格式化输出，包含标题、摘要、来源链接

**可用工具**：

- Read — 读取知识库 JSON 文件
- Glob — 按文件名模式匹配
- Grep — 全文搜索

### daily-briefing（每日简报）

**触发条件**：用户消息包含"简报""摘要""今日"等关键词，或使用 `/today` 命令

**职责**：

- 汇总当天采集的所有知识条目
- 按 relevance_score 排序取 Top 5
- 生成结构化简报（标题 + 一句话摘要 + 标签）
- 支持 Markdown 和 Feishu 卡片两种输出格式

**可用工具**：

- Read — 读取文章 JSON
- Glob — 扫描当日文件

### subscription-manager（订阅管理）

**触发条件**：用户消息包含"订阅""取消订阅"等关键词，或使用 `/subscribe` 命令

**职责**：

- 管理用户的标签订阅列表
- 新文章匹配订阅标签时主动推送
- 存储订阅数据到 `data/subscriptions.json`

### general-chat（通用对话）

**触发条件**：其他所有未匹配的消息（兜底 Agent）

**职责**：

- 回答关于知识库使用方式的问题
- 引导用户使用正确的命令
- 闲聊时友善回应，但引导回技术话题

## 协作规则

1. **单一入口**：所有消息经 OpenClaw 网关统一接入，不允许 Agent 直接接收消息
2. **无跨 Agent 调用**：Agent 之间不互相调用，由网关负责路由
3. **共享知识库**：所有 Agent 只读访问 `knowledge/` 目录
4. **状态隔离**：每个 Agent 的会话状态独立，不共享上下文