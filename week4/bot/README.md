# 知识库机器人模块 (bot/knowledge_bot.py)

已完成 OOP 架构的知识库交互模块，支持搜索、订阅管理和权限控制。

## 模块结构

```
bot/
├── __init__.py           # 模块导出
├── knowledge_bot.py      # 主模块 (700+ 行)
└── README.md            # 本文档
```

## 核心类

### Intent (枚举)
定义用户意图类型：
- `SEARCH` - 搜索知识库
- `TODAY` - 今日简报
- `TOP` - 热门文章
- `SUBSCRIBE` - 订阅标签
- `UNSUBSCRIBE` - 取消订阅
- `LIST_SUBS` - 查看订阅列表
- `HELP` - 帮助信息
- `UNKNOWN` - 未知意图

### Permission (枚举)
三级权限控制：
- `READ` - 只读权限（搜索、查看简报）
- `WRITE` - 写入权限（订阅管理）
- `DELETE` - 删除权限（高级操作）
- `ADMIN` - 管理员权限（所有操作）

### KnowledgeSearchEngine
知识库搜索引擎，支持：
- 关键词全文搜索
- 标签过滤
- 日期范围查询
- 最低评分过滤
- 结果数量限制

### SubscriptionManager
订阅管理器，支持：
- 添加/删除标签订阅
- 查看用户订阅列表
- 获取某标签的所有订阅者
- 清空用户所有订阅

### PermissionManager
权限管理器，支持：
- 检查用户权限
- 授予/撤销权限
- 新用户默认 READ 权限
- READ 权限不可撤销

### KnowledgeBot
主入口类，整合以上模块：
- `recognize_intent(text)` - 意图识别
- `handle_message(user_id, text)` - 统一消息处理

## 使用示例

```python
from bot import KnowledgeBot, Permission

# 初始化机器人
bot = KnowledgeBot(knowledge_dir="knowledge/articles")

# 提升用户权限（订阅需要 WRITE 权限）
bot.permission_manager.grant_permission("user123", Permission.WRITE)

# 处理用户消息
response = bot.handle_message("user123", "/search AI")
print(response)

response = bot.handle_message("user123", "/subscribe 机器学习")
print(response)

response = bot.handle_message("user123", "/today")
print(response)
```

## 支持的命令

| 命令 | 说明 | 权限 |
|------|------|------|
| `/search <关键词>` | 搜索文章 | READ |
| `tag:<标签>` | 标签过滤 | READ |
| `date:YYYY-MM-DD~` | 日期范围 | READ |
| `/today` | 今日简报 | READ |
| `/top [N]` | 热门文章 Top N | READ |
| `/subscribe <标签>` | 订阅标签 | WRITE |
| `/unsubscribe <标签>` | 取消订阅 | WRITE |
| `/list` | 查看订阅 | READ |
| `/help` | 帮助信息 | READ |

## 测试

```bash
# 运行完整测试
python3 tests/test_knowledge_bot.py

# 或使用虚拟环境（需先安装 python3-venv）
source venv/bin/activate
python tests/test_knowledge_bot.py
```

## 编码规范

- PEP 8 风格
- Google 风格 docstring
- 类型注解 (typing)
- 使用 dataclass 简化数据结构
- 使用 Enum 定义枚举类型
