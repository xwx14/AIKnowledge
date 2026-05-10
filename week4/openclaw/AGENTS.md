# AGENTS.md — OpenClaw Agent 配置

> OpenClaw 网关的 Agent 路由与协作配置。
> 每个 Agent 对应一种用户意图，由 `openclaw.json5` 中的 bindings 进行消息分发。

## Agent 列表

### knowledge-query（知识检索）

| 属性 | 值 |
|------|-----|
| Skill | `./skills/knowledge-query/SKILL.md` |
| 超时 | 30s |
| 路由 pattern | `知识\|搜索\|查询\|search\|find` |
| 命令 | `/search <关键词>` |

**职责**：

- 解析用户查询意图（关键词、标签、时间范围）
- 在 `knowledge/articles/` 中检索匹配条目
- 按相关性评分排序，返回 Top 5 结果
- 格式化输出，包含标题、摘要、来源链接

**可用工具**：Read、Glob、Grep

---

### daily-briefing（每日简报）

| 属性 | 值 |
|------|-----|
| Skill | `./skills/daily-digest/SKILL.md` |
| Script | `../distribution/formatter.py` |
| 超时 | 60s |
| 路由 pattern | `简报\|摘要\|今日\|daily\|digest` |
| 命令 | `/today` |

**职责**：

- 汇总当天采集的所有知识条目
- 按 relevance_score 排序取 Top 5
- 生成结构化简报（标题 + 一句话摘要 + 标签）
- 支持 Markdown 和 Feishu 卡片两种输出格式

**可用工具**：Read、Glob

---

### subscription-manager（订阅管理）

| 属性 | 值 |
|------|-----|
| 超时 | 10s |
| 路由 pattern | `订阅\|subscribe\|取消订阅\|unsubscribe` |
| 命令 | `/subscribe <标签>` |

**职责**：

- 管理用户的标签订阅列表
- 新文章匹配订阅标签时主动推送
- 存储订阅数据到 `data/subscriptions.json`

---

### top-rated（最高评分搜索）

| 属性 | 值 |
|------|-----|
| Skill | `./skills/top-rated/SKILL.md` |
| Script | `./skills/top-rated/top-rated.py` |
| 超时 | 15s |
| 路由 pattern | `最高评分\|最高分\|top.rated\|评分最高\|best` |
| 命令 | `/toprated <关键词>` |

**职责**：

- 解析用户输入的关键字
- 在 `knowledge/articles/` 中搜索 title / summary / description / tags 匹配的条目
- 按 score 降序排序，返回评分最高的 Top N 项目（默认 5）
- 格式化输出，包含标题、评分、摘要、来源链接、标签

**脚本调用**：

```bash
python skills/top-rated/top-rated.py "<keyword>" [--top N]
```

输出 JSON 数组到 stdout，退出码 0 成功，1 无匹配。

**可用工具**：top-rated.py 脚本、Read、Glob、Grep

---

### general-chat（通用对话）

| 属性 | 值 |
|------|-----|
| 超时 | 15s |
| 路由 pattern | `*`（兜底） |
| 命令 | `/help` |

**职责**：

- 回答关于知识库使用方式的问题
- 引导用户使用正确的命令
- 闲聊时友善回应，但引导回技术话题

---

## 协作规则

1. **单一入口**：所有消息经 OpenClaw 网关统一接入，不允许 Agent 直接接收消息
2. **无跨 Agent 调用**：Agent 之间不互相调用，由网关负责路由
3. **共享知识库**：所有 Agent 只读访问 `knowledge/` 目录
4. **状态隔离**：每个 Agent 的会话状态独立，不共享上下文

## 命令速查

| 命令 | Agent | 说明 |
|------|-------|------|
| `/search <关键词>` | knowledge-query | 搜索知识库 |
| `/today` | daily-briefing | 今日简报 |
| `/top` | daily-briefing | 本周热门 Top 5 |
| `/subscribe <标签>` | subscription-manager | 订阅特定主题 |
| `/toprated <关键词>` | top-rated | 按关键字搜索评分最高的项目 |
| `/help` | general-chat | 显示帮助信息 |
