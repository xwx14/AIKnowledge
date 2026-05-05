# AGENTS.md

## 项目概述

AI 知识库自动采集 pipeline：从 GitHub Search API 和 RSS 源采集 AI 相关内容，可选调用 LLM 做摘要/评分/标签，经去重/标准化/校验后以独立 JSON 文件存入 `knowledge/articles/`。

## 目录结构

```
week2/
├── pipeline/                 # 核心 pipeline 模块
│   ├── pipeline.py           # 入口，编排四步流程
│   ├── collector.py          # Step 1: 采集（GitHub + RSS）
│   ├── analyzer.py           # Step 2: LLM 分析
│   ├── organizer.py          # Step 3: 去重/标准化/校验
│   ├── saver.py              # Step 4: 逐条保存 JSON
│   ├── model_client.py       # 统一 LLM 客户端 + CostTracker
│   ├── config.py             # RAW_DIR / ARTICLES_DIR 路径常量
│   ├── rss_sources.yaml      # RSS 源配置（enabled 控制启停）
│   └── __init__.py           # 导出 model_client 公共 API
├── hooks/                    # 数据质量守卫
│   ├── validate_json.py      # JSON 结构/字段校验
│   └── check_quality.py      # 五维质量评分（C 级 exit 1）
├── mcp/                      # MCP Server
│   └── mcp_knowledge_server.py  # JSON-RPC 2.0 over stdio
├── knowledge/                # 数据目录
│   ├── raw/                  # 采集原始 JSON（按时间戳命名）
│   └── articles/             # 最终知识条目（按标题/ID 命名）
├── test/                     # hooks fixture
│   ├── good.json             # 合法样本
│   └── wrong.json            # 非法样本
├── .github/workflows/        # CI
│   └── daily-collect.yml     # 每日 08:00 UTC 采集
├── verify_model_client.py    # model_client 离线验证（不调 API）
├── requirements.txt          # httpx, pyyaml, python-dotenv
├── .env.example              # 环境变量模板
└── .gitignore
```

## 常用命令（CWD 必须是 week2/）

```bash
pip install -r requirements.txt

# 仅采集（不调 LLM）
python pipeline/pipeline.py --sources github,rss --limit 20

# 含 LLM 分析
python pipeline/pipeline.py --sources github,rss --limit 20 --analyze --provider deepseek

# Dry run（不写文件）
python pipeline/pipeline.py --dry-run --verbose

# JSON 验证
python hooks/validate_json.py knowledge/articles/*.json

# 质量评分（C 级 exit 1）
python hooks/check_quality.py knowledge/articles/*.json

# LLM 客户端离线验证（不调 API）
python verify_model_client.py
```

## 关键约定

### CWD 必须是 week2/

pipeline 内部使用裸导入（`from config import RAW_DIR`、`from model_client import ...`），`pipeline.py` 把 `pipeline/` 加入 `sys.path` 才能解析；hooks 命令的 glob 路径（`knowledge/articles/*.json`）也依赖 CWD。

### Pipeline 四步流程

1. **Collect** — 始终执行，从 GitHub Search API + RSS 采集，原始数据存入 `knowledge/raw/`
2. **Analyze** — 仅 `--analyze` 时执行，调用 LLM 做中文摘要/评分(1-10)/标签
3. **Organize** — 去重（URL + ID）、标准化（统一字段）、校验（过滤无标题/无ID条目）
4. **Save** — 逐条写入 `knowledge/articles/{filename}.json`，同名同 URL 覆盖，同名不同 URL 追加数字后缀

### Provider 配置

CLI `--provider` 与 `model_client.py` 的 `PROVIDER_CONFIG`/`COST_TABLE` 均支持 `deepseek/qwen/glm/kimi`，四者统一。

### 知识条目文件命名

- 有标题：标题清洗后作为文件名（替换非法字符为下划线，截断 80 字符）
- 无标题：回退到 `id` 或 URL 哈希前 12 位
- ID 格式：`github_{repo_id}` 或 `rss_{md5_hash[:12]}`

### RSS 源管理

配置在 `pipeline/rss_sources.yaml`，`enabled: false` 跳过。当前启用：Hacker News Best、Lobsters AI/ML、OpenAI Blog、Anthropic Research、Hugging Face Blog、GitHub Blog AI。

### 环境变量

```bash
cp .env.example .env
```

| 变量 | 说明 | 默认值 |
|------|------|--------|
| `LLM_PROVIDER` | LLM 提供商 | `deepseek` |
| `DEEPSEEK_API_KEY` | DeepSeek API Key | - |
| `QWEN_API_KEY` | 通义千问 API Key | - |
| `KIMI_API_KEY` | Kimi (Moonshot) API Key | - |
| `GLM_API_KEY` | 智谱 GLM API Key | - |

`.env` 在 `.gitignore` 中，切勿提交。

## 核心模块说明

### pipeline/model_client.py

统一 LLM 客户端，所有 provider 走 OpenAI 兼容 API 格式。

- **CostTracker** (`pipeline/model_client.py:81`): 累计 token 用量和成本（人民币），全局单例 `tracker` 在 `pipeline.py:111` 调用 `tracker.report()` 输出报告
- **OpenAICompatibleProvider** (`pipeline/model_client.py:220`): 统一 HTTP 客户端，60s 超时
- **chat_with_retry** (`pipeline/model_client.py:354`): 指数退避重试（最多 3 次），注意内部 `time.sleep()` 为同步等待
- **quick_chat** (`pipeline/model_client.py:439`): 便捷封装，system + user 两轮对话

### pipeline/collector.py

- **collect_github** (`collector.py:44`): GitHub Search API，查询 `AI OR artificial intelligence OR machine learning`，按更新时间倒序
- **collect_rss** (`collector.py:77`): 正则解析 RSS XML（`<title>/<link>/<description>`），跳过第一条（频道标题）
- **save_raw** (`collector.py:133`): 按时间戳保存原始 JSON 到 `knowledge/raw/`

### pipeline/analyzer.py

- **analyze_item** (`analyzer.py:28`): `async def`，构造中文 prompt 要求 LLM 返回 `{summary, score, tags}` JSON，用正则提取 JSON
- **analyze_all** (`analyzer.py:67`): `async def`，循环 `await analyze_item` 并原地更新；`pipeline.py` 中通过 `asyncio.run()` 一次调用
- dry_run 或 provider 不可用时返回占位数据

### pipeline/organizer.py

- **deduplicate** (`organizer.py:15`): 基于 URL 和 ID 双重去重
- **standardize** (`organizer.py:39`): 统一字段名和类型
- **validate** (`organizer.py:59`): 过滤无 title 或无 id 的条目

### pipeline/saver.py

- **_sanitizeFilename** (`saver.py:18`): 标题 → 安全文件名（Windows 兼容）
- **_resolveFilename** (`saver.py:54`): 同名同 URL 覆盖，同名不同 URL 追加数字后缀
- **save_articles** (`saver.py:104`): 逐条写入，同名文件先删后写

## Hooks

### hooks/validate_json.py

结构校验：必填字段（`id/title/url/summary/tags/status`）、ID 格式（`{source}-{YYYYMMDD}-{NNN}`）、status 枚举、URL 格式、summary 最少 20 字符、至少 1 个标签。

### hooks/check_quality.py

五维评分（满分 100）：

| 维度 | 满分 | 评判依据 |
|------|------|----------|
| Summary Quality | 25 | 摘要长度 + 技术关键词命中 |
| Technical Depth | 25 | score 字段值（1-10 映射） |
| Format Compliance | 20 | id/title/url/status/timestamp 五字段完整性 |
| Tag Precision | 15 | 标签是否在 STANDARD_TAGS 集合中 |
| Empty Words Check | 15 | 摘要不含空话套话 |

等级：A ≥ 80, B ≥ 60, C < 60。**C 级 exit 1**。

## MCP Server

`mcp/mcp_knowledge_server.py`：纯标准库 MCP 服务（JSON-RPC 2.0 over stdio），提供三个工具：

| 工具 | 说明 |
|------|------|
| `search_articles` | 按关键词搜索标题/摘要/描述 |
| `get_article` | 按 ID 获取完整文章 |
| `knowledge_stats` | 统计文章总数/来源分布/热门标签 |

启动方式：`python mcp/mcp_knowledge_server.py`（从 stdin 读取 JSON-RPC 行）。

## CI

`.github/workflows/daily-collect.yml`：每日 08:00 UTC 自动执行。

**注意**：CI 不加 `--analyze`，仅采集不做 LLM 分析。

需要 GitHub Secrets：`LLM_PROVIDER`、`DEEPSEEK_API_KEY`、`QWEN_API_KEY`、`KIMI_API_KEY`。

## 测试

无正式测试框架。验证方式：

- `verify_model_client.py` — 检查导入/配置/数据类（不调 API），须从 week2/ 运行
- `test/good.json` / `test/wrong.json` — hooks 脚本 fixture
- 手动运行 `hooks/validate_json.py` 和 `hooks/check_quality.py`

## 已知问题

（无）
