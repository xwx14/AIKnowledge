"""知识库机器人模块.

提供知识库检索、订阅管理和权限控制功能。
"""

from bot.knowledge_bot import (
    Intent,
    KnowledgeBot,
    KnowledgeSearchEngine,
    Permission,
    PermissionManager,
    SearchQuery,
    SearchResult,
    SubscriptionManager,
)

__all__ = [
    "Intent",
    "KnowledgeBot",
    "KnowledgeSearchEngine",
    "Permission",
    "PermissionManager",
    "SearchQuery",
    "SearchResult",
    "SubscriptionManager",
]
