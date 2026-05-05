# AGENTS.md

## 仓库结构

按周演进的项目，各周目录独立运行，无共享包：

- **week2/** — 主工作目录，完整 pipeline + hooks + MCP server
- **week3/** — 新版模块：`patterns/router.py`（意图路由）、`workflows/model_client.py`（增强版客户端）
- **week1/** — 早期版本，仅保留 `.opencode/` 配置和知识库

## 常用命令（均在 `week2/` 下执行）

```bash
pip install -r requirements.txt

# 仅采集（不调 LLM）
python pipeline/pipeline.py --sources github,rss --limit 20

# 含 LLM 分析
python pipeline/pipeline.py --sources github,rss --limit 20 --analyze --provider deepseek

# Dry run
python pipeline/pipeline.py --dry-run --verbose

# JSON 验证 / 质量评分（C 级 exit 1）
python hooks/validate_json.py knowledge/articles/*.json
python hooks/check_quality.py knowledge/articles/*.json

# LLM 客户端验证（不调 API）
python verify_model_client.py
```

## 关键约定

- **CWD 必须是 week2/**：pipeline 内部用裸导入（`from config import RAW_DIR`、`from model_client import ...`），`python pipeline/pipeline.py` 把 `pipeline/` 加入 sys.path 才能解析；hooks 命令的 glob 路径（`knowledge/articles/*.json`）也依赖 CWD
- **week3 独立导入路径**：`patterns/router.py` 用 `from workflows.model_client import ...`，须从 `week3/` 运行，与 week2 的 `from pipeline.model_client import ...` 不同
- **Provider 列表不一致**：CLI `--provider` 支持 `deepseek/qwen/glm/kimi`，但 `model_client.py` 的 `PROVIDER_CONFIG` 只有 `deepseek/qwen/openai/glm`（kimi 未实现，openai 未暴露在 CLI choices）
- **知识条目 ID**：`{source}-{YYYYMMDD}-{NNN}`
- **Python 3.9+**：使用 `list[dict[str, Any]]` 等内置泛型语法

## Pipeline 四步流程

1. **Collect** — 始终执行，从 GitHub Search API + RSS 采集
2. **Analyze** — 仅 `--analyze` 时执行，调用 LLM 做摘要/评分/标签
3. **Organize** — 去重、标准化、校验
4. **Save** — 逐条写入 `knowledge/articles/{id}.json`

RSS 源配置在 `pipeline/rss_sources.yaml`，`enabled: false` 跳过。

## 环境变量

`cp .env.example .env` 并填入 API Key。`LLM_PROVIDER` 选提供商（deepseek/qwen/openai/glm）。`.env` 在 `.gitignore` 中，切勿提交。

## 测试

无正式测试框架。验证方式：
- `verify_model_client.py` — 检查导入/配置/数据类（不调 API）
- `test/good.json` / `test/wrong.json` — hooks 脚本 fixture
- 手动运行 `hooks/validate_json.py` 和 `hooks/check_quality.py`

## CI

`week2/.github/workflows/daily-collect.yml`：每日 08:00 UTC 采集 → 验证 → 质量检查 → 提交。**注意**：CI 不加 `--analyze`，仅采集不做 LLM 分析。需要 GitHub Secrets：`LLM_PROVIDER`、`DEEPSEEK_API_KEY` 等。

## MCP Server

`week2/mcp/mcp_knowledge_server.py`：纯标准库 MCP 服务（JSON-RPC 2.0 over stdio），提供 `search_articles`、`get_article`、`knowledge_stats`，读取 `knowledge/articles/` 下 JSON。
