# MyAutoAIKnowledge

> AI 驱动的知识管理和自动化处理系统

## 项目简介

MyAutoAIKnowledge 是一个智能知识库管理系统，提供完整的工具链用于验证、评分和管理 AI 相关的知识条目。系统集成了多个 LLM 提供商，支持自动化质量检查和数据处理。

## 主要功能

### 1. LLM 客户端 (`pipeline/model_client.py`)

统一的多提供商 LLM 调用接口，支持：
- ✅ **DeepSeek** - 高性能中文模型
- ✅ **Qwen** - 阿里云通义千问
- ✅ **OpenAI** - GPT 系列
- ✅ **GLM** - 智谱 AI GLM-4

**核心特性：**
- 重试机制（3 次，指数退避）
- Token 用量统计
- 成本计算（USD 计价）
- 60 秒超时保护
- 便捷的 `quick_chat()` 函数

### 2. JSON 验证工具 (`hooks/validate_json.py`)

自动验证知识条目 JSON 文件的完整性和格式：
- ✅ JSON 解析检查
- ✅ 必填字段验证（id, title, source_url, summary, tags, status）
- ✅ ID 格式验证（{source}-{YYYYMMDD}-{NNN}）
- ✅ URL 格式验证
- ✅ 状态值检查（draft/review/published/archived）
- ✅ 摘要长度检查（最少 20 字）
- ✅ 标签数量验证（至少 1 个）
- ✅ 可选字段验证（score, audience）

### 3. 质量评分工具 (`hooks/check_quality.py`)

5 维度质量评分系统（总分 100 分）：

| 维度 | 满分 | 评分标准 |
|------|--------|----------|
| 摘要质量 | 25 分 | ≥50 字满分，≥20 字基本分，含技术关键词有奖励 |
| 技术深度 | 25 分 | 基于 score 字段（1-10 映射到 0-25） |
| 格式规范 | 20 分 | id、title、source_url、status、timestamp 五项各 4 分 |
| 标签精度 | 15 分 | 1-3 个合法标签最佳 |
| 空洞词检测 | 15 分 | 不含"赋能""抓手""闭环"等空洞词 |

**评分等级：**
- **A 级**：≥80 分
- **B 级**：≥60 分
- **C 级**：<60 分

### 4. 空洞词检测

自动检测中英文空洞词汇：

**中文黑名单：**
- 赋能、抓手、闭环、打通、全链路
- 底层逻辑、颗粒度、对齐、拉通、沉淀
- 强大的、革命性的

**英文黑名单：**
- groundbreaking、revolutionary、game-changing
- cutting-edge、disruptive、innovative
- next-generation、state-of-the-art

## 安装步骤

### 1. 克隆仓库

```bash
git clone <repository-url>
cd MyAutoAIKnowledge
```

### 2. 安装依赖

```bash
pip install httpx python-dotenv
```

### 3. 配置环境变量

复制配置模板并填入 API Keys：

```bash
cp .env.example .env
```

编辑 `.env` 文件：

```bash
# 选择提供商：deepseek、qwen、openai、glm
LLM_PROVIDER=deepseek

# 填入对应的 API Key
DEEPSEEK_API_KEY=your_actual_deepseek_api_key_here
QWEN_API_KEY=your_actual_qwen_api_key_here
OPENAI_API_KEY=your_actual_openai_api_key_here
GLM_API_KEY=your_actual_glm_api_key_here
```

### 4. 获取 API Keys

| 提供商 | 获取地址 |
|---------|----------|
| DeepSeek | https://platform.deepseek.com/api_keys |
| Qwen | https://dashscope.console.aliyun.com/apiKey |
| OpenAI | https://platform.openai.com/api-keys |
| GLM | https://open.bigmodel.cn/usercenter/apikeys |

## 使用方法

### 1. JSON 验证

**单文件验证：**
```bash
python hooks/validate_json.py data/entry_001.json
```

**多文件验证（通配符）：**
```bash
python hooks/validate_json.py data/*.json
```

**输出示例：**
```
data/entry_001.json:
  - Invalid ID format: 'invalid-id'. Expected format: {source}-{YYYYMMDD}-{NNN}
  - Summary too short: 15 characters. Minimum: 20 characters

Summary: 2 error(s) in 1/3 file(s)
```

### 2. 质量评分

**单文件评分：**
```bash
python hooks/check_quality.py data/entry_001.json
```

**批量评分：**
```bash
python hooks/check_quality.py data/*.json
```

**输出示例：**
```
Checking 3 file(s)...
[########################################] 100% (3/3)

======================================================================
File: data/entry_001.json
ID: github-20260310-001
----------------------------------------------------------------------
[+] Summary Quality     : [####################] 25/25
[+] Technical Depth     : [################----] 20/25
[+] Format Compliance   : [####################] 20/20
[+] Tag Precision       : [####################] 15/15
[+] Empty Words Check   : [####################] 15/15
----------------------------------------------------------------------
Total Score: 95/100  Grade: [A]
======================================================================

Summary: 3 file(s) processed
Average Score: 85.0/100
Grade Distribution: A=2  B=1  C=0
======================================================================
```

### 3. LLM 客户端

**基础使用：**
```python
from pipeline.model_client import get_provider, quick_chat
import asyncio

# 获取提供商
provider = get_provider()

# 快速对话
response = await quick_chat("帮我总结一下这个项目的功能")
print(response)
```

**高级使用：**
```python
from pipeline.model_client import chat_with_retry, calculate_cost
import asyncio

# 自定义消息
messages = [
    {"role": "system", "content": "你是一个专业的技术助手"},
    {"role": "user", "content": "解释一下 RESTful API 的设计原则"}
]

# 带重试的聊天
response = await chat_with_retry(
    messages=messages,
    temperature=0.7,
    max_tokens=500
)

# 查看用量和成本
print(f"Content: {response.content}")
print(f"Usage: {response.usage}")
print(f"Cost: ${calculate_cost(response):.6f}")
```

## 项目结构

```
MyAutoAIKnowledge/
├── hooks/                    # 验证和质量检查工具
│   ├── validate_json.py       # JSON 格式验证
│   └── check_quality.py       # 质量评分
├── pipeline/                 # LLM 客户端模块
│   ├── __init__.py
│   └── model_client.py       # 统一 LLM 调用接口
├── openclaw/                # OpenClaw 网关配置
│   ├── cron/                # 定时任务定义
│   │   ├── jobs.json        # 定时任务配置（cron 表达式、执行动作、投递渠道）
│   │   └── jobs-state.json  # 定时任务状态跟踪（下次执行时间等）
│   ├── skills/              # Agent 技能目录
│   ├── openclaw.json5       # 网关主配置
│   ├── AGENTS.md            # Agent 路由与协作配置
│   ├── IDENTITY.md          # 身份定义
│   ├── SOUL.md              # 人格设定
│   ├── MEMORY.md            # 长期记忆
│   ├── HEARTBEAT.md         # 心跳检测
│   ├── TOOLS.md             # 工具声明
│   └── USER.md              # 用户信息
├── .env.example             # 环境变量配置模板
├── .gitignore              # Git 忽略规则
├── README.md               # 项目说明（本文件）
├── ENV_SETUP.md            # 环境配置详细指南
└── GLM_PROVIDER.md         # GLM 提供商集成文档
```

## 知识条目 JSON 格式

```json
{
  "id": "github-20260310-001",
  "title": "项目标题",
  "source_url": "https://example.com/article",
  "summary": "文章摘要，至少 20 个字符",
  "tags": ["python", "machine-learning"],
  "status": "published",
  "score": 8,
  "audience": "intermediate",
  "timestamp": "2026-03-10T10:00:00Z"
}
```

### 必填字段

| 字段 | 类型 | 说明 | 验证规则 |
|------|------|------|----------|
| `id` | string | 唯一标识符 | 格式：{source}-{YYYYMMDD}-{NNN} |
| `title` | string | 知识条目标题 | 非空字符串 |
| `source_url` | string | 来源链接 | 必须以 http:// 或 https:// 开头 |
| `summary` | string | 内容摘要 | 最少 20 个字符 |
| `tags` | array | 标签列表 | 至少包含 1 个标签 |
| `status` | string | 状态 | draft/review/published/archived |

### 可选字段

| 字段 | 类型 | 说明 | 验证规则 |
|------|------|------|----------|
| `score` | number | 技术深度评分 | 1-10 之间的数值 |
| `audience` | string | 目标受众 | beginner/intermediate/advanced |
| `timestamp` | string | 时间戳 | ISO 8601 格式 |

## 配置说明

### 提供商配置

| 提供商 | 模型 | 输入价格 | 输出价格 |
|---------|------|----------|----------|
| DeepSeek | deepseek-chat | $0.14/1M | $0.28/1M |
| Qwen | qwen-turbo | $0.0008/1K | $0.002/1K |
| OpenAI | gpt-3.5-turbo | $0.5/1M | $1.5/1M |
| GLM | glm-4 | $0.1/1M | $0.1/1M |

### 环境变量

```bash
# 提供商选择
LLM_PROVIDER=deepseek          # 或 qwen、openai、glm

# API Keys
DEEPSEEK_API_KEY=sk-xxx
QWEN_API_KEY=sk-xxx
OPENAI_API_KEY=sk-xxx
GLM_API_KEY=sk-xxx
```

## 开发指南

### 添加新的验证规则

编辑 `hooks/validate_json.py`：

```python
def validate_custom_field(value: str) -> list[str]:
    errors = []
    # 添加你的验证逻辑
    if not value:
        errors.append("Field cannot be empty")
    return errors
```

### 添加新的质量维度

编辑 `hooks/check_quality.py`：

```python
def check_new_dimension(data: dict) -> int:
    score = 0
    # 添加你的评分逻辑
    if data.get("custom_field"):
        score = 15
    return score
```

### 添加新的 LLM 提供商

编辑 `pipeline/model_client.py`：

```python
PROVIDER_CONFIG = {
    # ... 现有配置 ...
    "new_provider": {
        "base_url": "https://api.newprovider.com/v1",
        "model": "new-model",
        "input_price": 0.1,
        "output_price": 0.2,
    },
}
```

## 常见问题

### Q: 如何切换 LLM 提供商？

编辑 `.env` 文件，修改 `LLM_PROVIDER` 变量：

```bash
# 切换到 GLM
LLM_PROVIDER=glm
GLM_API_KEY=your_glm_api_key
```

### Q: 质量评分如何计算？

评分基于 5 个维度，每维度有特定满分：
- 摘要质量：25 分（长度 + 技术关键词）
- 技术深度：25 分（score 字段映射）
- 格式规范：20 分（5 个必填字段）
- 标签精度：15 分（1-3 个标准标签）
- 空洞词检测：15 分（无空洞词汇）

### Q: 如何处理 C 级条目？

C 级条目（<60 分）通常需要：
- 扩充摘要内容
- 添加技术细节
- 补充缺失字段
- 修正空洞词汇
- 优化标签组合

### Q: 验证失败的退出码是什么？

- **0**：所有文件验证通过
- **1**：存在验证错误或 C 级条目

## 技术栈

- **Python 3.9+** - 主要开发语言
- **httpx** - 异步 HTTP 客户端
- **python-dotenv** - 环境变量管理
- **dataclass** - 数据结构定义
- **logging** - 日志记录

## 贡献指南

欢迎贡献！请遵循以下步骤：

1. Fork 本仓库
2. 创建特性分支 (`git checkout -b feature/AmazingFeature`)
3. 提交更改 (`git commit -m 'feat: Add some AmazingFeature'`)
4. 推送到分支 (`git push origin feature/AmazingFeature`)
5. 开启 Pull Request

## 许可证

MIT License - 详见 LICENSE 文件

## 联系方式

- 项目主页：[GitHub Repository]
- 问题反馈：[Issues]

---

**Made with ❤️ for AI-driven knowledge management**
