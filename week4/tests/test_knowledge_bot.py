"""知识库机器人模块测试.

验证意图识别、搜索、权限和订阅功能。
"""

import os
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from bot.knowledge_bot import (
    Intent,
    KnowledgeBot,
    KnowledgeSearchEngine,
    Permission,
    PermissionManager,
    SearchQuery,
    SubscriptionManager,
)


def test_intent_recognition():
    """测试意图识别功能."""
    bot = KnowledgeBot()

    test_cases = [
        ("/search 机器学习", Intent.SEARCH, "机器学习"),
        ("搜索 Python 教程", Intent.SEARCH, "搜索 Python 教程"),
        ("/today", Intent.TODAY, ""),
        ("今日简报", Intent.TODAY, ""),
        ("/top", Intent.TOP, ""),
        ("/top 20", Intent.TOP, "20"),
        ("/subscribe 人工智能", Intent.SUBSCRIBE, "人工智能"),
        ("订阅 LLM", Intent.SUBSCRIBE, "订阅 LLM"),
        ("/unsubscribe 机器学习", Intent.UNSUBSCRIBE, "机器学习"),
        ("/list", Intent.LIST_SUBS, ""),
        ("/help", Intent.HELP, ""),
        ("随便说说", Intent.UNKNOWN, "随便说说"),
    ]

    print("🔍 测试意图识别:")
    for text, expected_intent, expected_params in test_cases:
        intent, params = bot.recognize_intent(text)
        status = "✅" if intent == expected_intent else "❌"
        print(
            f"  {status} '{text}' -> {intent.name} "
            f"(期望: {expected_intent.name})"
        )
        assert intent == expected_intent, f"意图不匹配: {text}"


def test_search_engine():
    """测试搜索引擎功能."""
    knowledge_dir = Path(__file__).parent.parent / "knowledge/articles"
    engine = KnowledgeSearchEngine(str(knowledge_dir))

    print(f"\n📚 测试搜索引擎 (已加载 {len(engine._articles)} 篇文章):")

    # 测试关键词搜索
    query = SearchQuery(keywords=["AI"], limit=5)
    result = engine.search(query)
    print(f"  🔍 关键词 'AI' 搜索结果: {result.total} 篇")
    for article in result.articles[:2]:
        print(f"     - {article.get('title', '无标题')[:50]}")

    # 测试标签搜索
    query = SearchQuery(tags=["人工智能"], limit=3)
    result = engine.search(query)
    print(f"  🏷️ 标签 '人工智能' 搜索结果: {result.total} 篇")

    # 测试今日文章
    today_articles = engine.get_today_articles(limit=5)
    print(f"  📰 今日文章: {len(today_articles)} 篇")

    # 测试热门文章
    top_articles = engine.get_top_articles(3)
    print(f"  🏆 热门文章 Top 3:")
    for i, article in enumerate(top_articles, 1):
        print(f"     {i}. {article.get('title', '无标题')[:40]}... "
              f"({article.get('score', 0)})")


def test_permission_manager():
    """测试权限管理功能."""
    with tempfile.TemporaryDirectory() as tmpdir:
        storage_path = Path(tmpdir) / "permissions.json"
        pm = PermissionManager(str(storage_path))

        print("\n🔐 测试权限管理:")

        # 测试默认权限
        assert pm.has_permission("user1", Permission.READ)
        print("  ✅ 新用户默认拥有 READ 权限")

        # 测试授予权限
        assert pm.grant_permission("user1", Permission.WRITE)
        assert pm.has_permission("user1", Permission.WRITE)
        print("  ✅ 成功授予 WRITE 权限")

        # 测试撤销权限
        assert pm.revoke_permission("user1", Permission.WRITE)
        assert not pm.has_permission("user1", Permission.WRITE)
        print("  ✅ 成功撤销 WRITE 权限")

        # 测试 READ 不可撤销
        assert not pm.revoke_permission("user1", Permission.READ)
        assert pm.has_permission("user1", Permission.READ)
        print("  ✅ READ 权限不可撤销")


def test_subscription_manager():
    """测试订阅管理功能."""
    with tempfile.TemporaryDirectory() as tmpdir:
        storage_path = Path(tmpdir) / "subscriptions.json"
        sm = SubscriptionManager(str(storage_path))

        print("\n📌 测试订阅管理:")

        # 测试添加订阅
        assert sm.add_subscription("user1", "人工智能")
        assert sm.add_subscription("user1", "机器学习")
        assert not sm.add_subscription("user1", "人工智能")
        print("  ✅ 添加订阅成功")

        # 测试获取订阅
        subs = sm.get_subscriptions("user1")
        assert "人工智能" in subs and "机器学习" in subs
        print(f"  ✅ 获取订阅: {subs}")

        # 测试删除订阅
        assert sm.remove_subscription("user1", "人工智能")
        assert "人工智能" not in sm.get_subscriptions("user1")
        print("  ✅ 删除订阅成功")

        # 测试清空订阅
        assert sm.clear_subscriptions("user1")
        assert not sm.get_subscriptions("user1")
        print("  ✅ 清空订阅成功")


def test_bot_message_handling():
    """测试机器人消息处理."""
    knowledge_dir = Path(__file__).parent.parent / "knowledge/articles"
    bot = KnowledgeBot(str(knowledge_dir))

    print("\n🤖 测试机器人消息处理:")

    # 测试搜索消息
    response = bot.handle_message("user1", "/search AI")
    print(f"  🔍 搜索响应: {response[:100]}...")

    # 测试今日简报
    response = bot.handle_message("user1", "/today")
    print(f"  📰 今日简报: {response[:100]}...")

    # 测试订阅功能(需要 WRITE 权限)
    response = bot.handle_message("user1", "/subscribe 人工智能")
    print(f"  📌 订阅响应: {response[:100]}...")

    # 提升 user1 权限后再试
    bot.permission_manager.grant_permission("user1", Permission.WRITE)
    response = bot.handle_message("user1", "/subscribe 人工智能")
    assert "订阅成功" in response or "已订阅过" in response
    print(f"  📌 授权后订阅响应: {response}")

    # 测试帮助
    response = bot.handle_message("user1", "/help")
    assert "使用指南" in response
    print("  ✅ 帮助信息正常")


def test_search_query_parsing():
    """测试搜索查询解析."""
    bot = KnowledgeBot()

    print("\n🔧 测试搜索查询解析:")

    test_cases = [
        ("机器学习 深度学习", {"keywords": ["机器学习", "深度学习"]}),
        ("tag:Python tag:AI", {"tags": ["Python", "AI"]}),
        ("date:2026-05-01~2026-05-07", {"date_from": "2026-05-01",
                                         "date_to": "2026-05-07"}),
        ("机器学习 tag:Python limit:5", {"keywords": ["机器学习"],
                                         "tags": ["Python"],
                                         "limit": 5}),
    ]

    for params, expected in test_cases:
        query = bot._parse_search_query(params)
        for key, value in expected.items():
            actual = getattr(query, key)
            if isinstance(actual, list):
                assert set(actual) == set(value), \
                    f"{params}: {key} 不匹配 {actual} != {value}"
            else:
                assert actual == value, \
                    f"{params}: {key} 不匹配 {actual} != {value}"
        print(f"  ✅ '{params}' 解析正确")


if __name__ == "__main__":
    test_intent_recognition()
    test_search_engine()
    test_permission_manager()
    test_subscription_manager()
    test_search_query_parsing()
    test_bot_message_handling()

    print("\n" + "="*50)
    print("✅ 所有测试通过!")
    print("="*50)
