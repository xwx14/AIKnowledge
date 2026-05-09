"""知识库交互模块.

提供基于规则匹配的知识库检索、订阅管理和权限控制功能。
支持关键词搜索、标签过滤、日期范围查询以及用户订阅管理。
"""

from __future__ import annotations

import json
import logging
import re
from dataclasses import dataclass, field
from datetime import date, datetime
from enum import Enum, auto
from pathlib import Path
from typing import Any, Dict, List, Optional, Set, Tuple

logger = logging.getLogger(__name__)


class Intent(Enum):
    """用户意图枚举.

    定义知识库交互支持的所有意图类型。
    """

    SEARCH = auto()  # 搜索知识库
    TODAY = auto()  # 今日简报
    TOP = auto()  # 热门文章
    SUBSCRIBE = auto()  # 订阅管理
    UNSUBSCRIBE = auto()  # 取消订阅
    LIST_SUBS = auto()  # 查看订阅列表
    HELP = auto()  # 帮助信息
    UNKNOWN = auto()  # 未知意图


class Permission(Enum):
    """权限级别枚举.

    定义三级权限控制体系。
    """

    READ = auto()  # 只读权限：搜索、查看简报
    WRITE = auto()  # 写入权限：订阅、取消订阅
    DELETE = auto()  # 删除权限：删除订阅（高级用户）
    ADMIN = auto()  # 管理员权限：所有操作


@dataclass
class SearchQuery:
    """搜索查询参数.

    Attributes:
        keywords: 关键词列表,用于全文匹配.
        tags: 标签列表,用于标签过滤.
        date_from: 起始日期(YYYY-MM-DD),可选.
        date_to: 结束日期(YYYY-MM-DD),可选.
        min_score: 最低相关性评分(0-1),默认0.0.
        limit: 返回结果数量限制,默认10.
    """

    keywords: List[str] = field(default_factory=list)
    tags: List[str] = field(default_factory=list)
    date_from: Optional[str] = None
    date_to: Optional[str] = None
    min_score: float = 0.0
    limit: int = 10


@dataclass
class SearchResult:
    """搜索结果.

    Attributes:
        articles: 匹配的文章列表.
        total: 总匹配数量.
        query: 原始查询参数.
    """

    articles: List[Dict[str, Any]]
    total: int
    query: SearchQuery


class PermissionManager:
    """权限管理器.

    管理用户权限级别,支持基于角色的访问控制(RBAC)。
    默认所有用户拥有 READ 权限,可通过 grant_promission 提升。
    """

    def __init__(self, storage_path: str = "data/permissions.json"):
        """初始化权限管理器.

        Args:
            storage_path: 权限数据存储路径.
        """
        self._storage_path = Path(storage_path)
        self._permissions: Dict[str, Set[Permission]] = {}
        self._load()

    def _load(self) -> None:
        """从文件加载权限数据."""
        if self._storage_path.exists():
            try:
                with open(self._storage_path, "r", encoding="utf-8") as f:
                    data = json.load(f)
                for user_id, perms in data.items():
                    self._permissions[user_id] = {
                        Permission[perm] for perm in perms
                    }
            except (json.JSONDecodeError, KeyError, ValueError) as e:
                logger.warning("加载权限数据失败: %s", e)

    def _save(self) -> None:
        """保存权限数据到文件."""
        self._storage_path.parent.mkdir(parents=True, exist_ok=True)
        data = {
            user_id: [perm.name for perm in perms]
            for user_id, perms in self._permissions.items()
        }
        with open(self._storage_path, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)

    def get_permissions(self, user_id: str) -> Set[Permission]:
        """获取用户权限集合.

        Args:
            user_id: 用户唯一标识.

        Returns:
            用户拥有的权限集合,默认为 {Permission.READ}.
            如果用户权限集为空,也返回默认的 READ 权限.
        """
        perms = self._permissions.get(user_id)
        if not perms:
            return {Permission.READ}
        return perms

    def has_permission(
        self,
        user_id: str,
        required_permission: Permission,
    ) -> bool:
        """检查用户是否拥有指定权限.

        Args:
            user_id: 用户唯一标识.
            required_permission: 需要的权限级别.

        Returns:
            是否拥有权限,ADMIN用户拥有所有权限.
        """
        user_perms = self.get_permissions(user_id)
        if Permission.ADMIN in user_perms:
            return True
        return required_permission in user_perms

    def grant_permission(
        self,
        user_id: str,
        permission: Permission,
    ) -> bool:
        """授予用户权限.

        Args:
            user_id: 用户唯一标识.
            permission: 要授予的权限.

        Returns:
            是否成功授予.
        """
        if user_id not in self._permissions:
            self._permissions[user_id] = set()
        if permission not in self._permissions[user_id]:
            self._permissions[user_id].add(permission)
            self._save()
            return True
        return False

    def revoke_permission(
        self,
        user_id: str,
        permission: Permission,
    ) -> bool:
        """撤销用户权限.

        Args:
            user_id: 用户唯一标识.
            permission: 要撤销的权限.

        Returns:
            是否成功撤销,READ权限不可撤销.
        """
        if permission == Permission.READ:
            return False
        if user_id in self._permissions:
            if permission in self._permissions[user_id]:
                self._permissions[user_id].discard(permission)
                self._save()
                return True
        return False


class SubscriptionManager:
    """订阅管理器.

    管理用户的知识条目标签订阅,支持按标签过滤推送。
    """

    def __init__(self, storage_path: str = "data/subscriptions.json"):
        """初始化订阅管理器.

        Args:
            storage_path: 订阅数据存储路径.
        """
        self._storage_path = Path(storage_path)
        self._subscriptions: Dict[str, Set[str]] = {}
        self._load()

    def _load(self) -> None:
        """从文件加载订阅数据."""
        if self._storage_path.exists():
            try:
                with open(self._storage_path, "r", encoding="utf-8") as f:
                    self._subscriptions = json.load(f)
                for user_id, tags in self._subscriptions.items():
                    self._subscriptions[user_id] = set(tags)
            except (json.JSONDecodeError, ValueError) as e:
                logger.warning("加载订阅数据失败: %s", e)

    def _save(self) -> None:
        """保存订阅数据到文件."""
        self._storage_path.parent.mkdir(parents=True, exist_ok=True)
        data = {
            user_id: list(tags)
            for user_id, tags in self._subscriptions.items()
        }
        with open(self._storage_path, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)

    def get_subscriptions(self, user_id: str) -> Set[str]:
        """获取用户订阅的标签集合.

        Args:
            user_id: 用户唯一标识.

        Returns:
            用户订阅的标签集合.
        """
        return self._subscriptions.get(user_id, set())

    def add_subscription(
        self,
        user_id: str,
        tag: str,
    ) -> bool:
        """添加标签订阅.

        Args:
            user_id: 用户唯一标识.
            tag: 要订阅的标签.

        Returns:
            是否是新订阅.
        """
        if user_id not in self._subscriptions:
            self._subscriptions[user_id] = set()
        if tag not in self._subscriptions[user_id]:
            self._subscriptions[user_id].add(tag)
            self._save()
            return True
        return False

    def remove_subscription(
        self,
        user_id: str,
        tag: str,
    ) -> bool:
        """取消标签订阅.

        Args:
            user_id: 用户唯一标识.
            tag: 要取消的标签.

        Returns:
            是否成功取消.
        """
        if user_id in self._subscriptions and tag in self._subscriptions[user_id]:
            self._subscriptions[user_id].discard(tag)
            self._save()
            return True
        return False

    def clear_subscriptions(self, user_id: str) -> bool:
        """清空用户所有订阅.

        Args:
            user_id: 用户唯一标识.

        Returns:
            是否成功清空.
        """
        if user_id in self._subscriptions and self._subscriptions[user_id]:
            self._subscriptions[user_id].clear()
            self._save()
            return True
        return False

    def get_subscribers_for_tag(self, tag: str) -> List[str]:
        """获取订阅了指定标签的所有用户.

        Args:
            tag: 标签名称.

        Returns:
            用户ID列表.
        """
        return [
            user_id
            for user_id, tags in self._subscriptions.items()
            if tag in tags
        ]


class KnowledgeSearchEngine:
    """知识库搜索引擎.

    支持关键词、标签、日期范围等多种过滤条件。
    """

    def __init__(self, knowledge_dir: str = "knowledge/articles"):
        """初始化搜索引擎.

        Args:
            knowledge_dir: 知识库文章目录路径.
        """
        self._knowledge_dir = Path(knowledge_dir)
        self._articles: List[Dict[str, Any]] = []
        self._load_articles()

    def _load_articles(self) -> None:
        """加载所有知识库文章."""
        if not self._knowledge_dir.exists():
            logger.warning("知识库目录不存在: %s", self._knowledge_dir)
            return

        for json_file in self._knowledge_dir.glob("*.json"):
            try:
                with open(json_file, "r", encoding="utf-8") as f:
                    data = json.load(f)
                if isinstance(data, dict):
                    self._articles.append(data)
            except (json.JSONDecodeError, OSError) as e:
                logger.warning("加载文章失败 %s: %s", json_file, e)

        logger.info("已加载 %d 篇知识库文章", len(self._articles))

    def reload(self) -> None:
        """重新加载知识库文章."""
        self._articles.clear()
        self._load_articles()

    def search(self, query: SearchQuery) -> SearchResult:
        """执行搜索查询.

        Args:
            query: 搜索查询参数.

        Returns:
            搜索结果对象.
        """
        results: List[Dict[str, Any]] = []

        for article in self._articles:
            if self._matches_query(article, query):
                results.append(article)

        results.sort(
            key=lambda a: float(a.get("score", 0)),
            reverse=True,
        )
        total = len(results)
        limited_results = results[: query.limit]

        return SearchResult(
            articles=limited_results,
            total=total,
            query=query,
        )

    def _matches_query(
        self,
        article: Dict[str, Any],
        query: SearchQuery,
    ) -> bool:
        """检查文章是否匹配查询条件.

        Args:
            article: 文章数据.
            query: 搜索查询参数.

        Returns:
            是否匹配.
        """
        score = float(article.get("score", 0))
        if score < query.min_score:
            return False

        if query.date_from or query.date_to:
            collected_at = article.get("collected_at", "")
            if not collected_at:
                return False
            article_date = datetime.fromisoformat(collected_at).date()

            if query.date_from:
                try:
                    from_date = date.fromisoformat(query.date_from)
                    if article_date < from_date:
                        return False
                except ValueError:
                    pass

            if query.date_to:
                try:
                    to_date = date.fromisoformat(query.date_to)
                    if article_date > to_date:
                        return False
                except ValueError:
                    pass

        if query.tags:
            article_tags = set(article.get("tags", []))
            if not any(tag in article_tags for tag in query.tags):
                return False

        if query.keywords:
            text = (
                article.get("title", "") +
                " " +
                article.get("summary", "") +
                " " +
                " ".join(article.get("tags", []))
            ).lower()
            if not any(kw.lower() in text for kw in query.keywords):
                return False

        return True

    def get_today_articles(
        self,
        target_date: Optional[date] = None,
        limit: int = 10,
    ) -> List[Dict[str, Any]]:
        """获取指定日期的文章.

        Args:
            target_date: 目标日期,默认今天.
            limit: 返回数量限制.

        Returns:
            文章列表,按评分降序排列.
        """
        if target_date is None:
            target_date = date.today()

        date_str = target_date.isoformat()
        results: List[Dict[str, Any]] = []

        for article in self._articles:
            collected_at = article.get("collected_at", "")
            if collected_at and collected_at[:10] == date_str:
                results.append(article)

        results.sort(
            key=lambda a: float(a.get("score", 0)),
            reverse=True,
        )
        return results[:limit]

    def get_top_articles(self, top_n: int = 10) -> List[Dict[str, Any]]:
        """获取评分最高的文章.

        Args:
            top_n: 返回数量.

        Returns:
            文章列表,按评分降序排列.
        """
        sorted_articles = sorted(
            self._articles,
            key=lambda a: float(a.get("score", 0)),
            reverse=True,
        )
        return sorted_articles[:top_n]

    def get_all_tags(self) -> List[str]:
        """获取知识库中所有标签.

        Returns:
            标签列表,按使用频率降序排列.
        """
        tag_counts: Dict[str, int] = {}
        for article in self._articles:
            for tag in article.get("tags", []):
                tag_counts[tag] = tag_counts.get(tag, 0) + 1

        sorted_tags = sorted(
            tag_counts.items(),
            key=lambda x: x[1],
            reverse=True,
        )
        return [tag for tag, _ in sorted_tags]


class KnowledgeBot:
    """知识库交互机器人主入口.

    整合搜索引擎、订阅管理和权限控制,提供统一的消息处理接口。
    """

    def __init__(
        self,
        knowledge_dir: str = "knowledge/articles",
        permission_storage: str = "data/permissions.json",
        subscription_storage: str = "data/subscriptions.json",
    ):
        """初始化知识库机器人.

        Args:
            knowledge_dir: 知识库文章目录路径.
            permission_storage: 权限数据存储路径.
            subscription_storage: 订阅数据存储路径.
        """
        self.search_engine = KnowledgeSearchEngine(knowledge_dir)
        self.permission_manager = PermissionManager(permission_storage)
        self.subscription_manager = SubscriptionManager(subscription_storage)

    @staticmethod
    def recognize_intent(text: str) -> Tuple[Intent, str]:
        """识别用户消息意图.

        优先匹配命令前缀,再匹配自然语言关键词。
        规则匹配实现,不依赖 LLM。

        Args:
            text: 用户输入文本.

        Returns:
            (意图类型, 参数字符串) 元组.
        """
        text = text.strip()
        if not text:
            return Intent.UNKNOWN, ""

        text_lower = text.lower()

        # 命令前缀匹配 (注意: len("/search ") = 8, len("/subscribe ") = 12)
        if text_lower.startswith("/search "):
            return Intent.SEARCH, text[8:].strip()
        if text_lower.startswith("/today"):
            return Intent.TODAY, ""
        if text_lower.startswith("/top"):
            return Intent.TOP, text[5:].strip()
        if text_lower.startswith("/subscribe "):
            return Intent.SUBSCRIBE, text[11:].strip()
        if text_lower.startswith("/unsubscribe "):
            return Intent.UNSUBSCRIBE, text[13:].strip()
        if text_lower.startswith("/list") or text_lower.startswith("/mysubs"):
            return Intent.LIST_SUBS, ""
        if text_lower in ("/help", "/h", "/?"):
            return Intent.HELP, ""

        # 自然语言关键词匹配
        search_keywords = [
            "搜索", "查询", "查找", "找", "search", "find", "look for",
            "关于", "想知道",
        ]
        if any(kw in text_lower for kw in search_keywords):
            return Intent.SEARCH, text

        today_keywords = [
            "今天", "今日", "简报", "摘要", "daily", "today", "briefing",
        ]
        if any(kw in text_lower for kw in today_keywords):
            return Intent.TODAY, ""

        top_keywords = [
            "热门", "top", "排名", "最佳", "最好", "推荐",
        ]
        if any(kw in text_lower for kw in top_keywords):
            return Intent.TOP, ""

        subscribe_keywords = [
            "订阅", "关注", "subscribe", "follow",
        ]
        if any(kw in text_lower for kw in subscribe_keywords):
            return Intent.SUBSCRIBE, text

        unsubscribe_keywords = [
            "取消订阅", "unsubscribe", "unfollow",
        ]
        if any(kw in text_lower for kw in unsubscribe_keywords):
            return Intent.UNSUBSCRIBE, text

        list_keywords = [
            "我的订阅", "订阅列表", "list", "my subscriptions",
        ]
        if any(kw in text_lower for kw in list_keywords):
            return Intent.LIST_SUBS, ""

        help_keywords = [
            "帮助", "怎么用", "如何使用", "help", "how to",
        ]
        if any(kw in text_lower for kw in help_keywords):
            return Intent.HELP, ""

        return Intent.UNKNOWN, text

    def handle_message(
        self,
        user_id: str,
        text: str,
    ) -> str:
        """处理用户消息的统一入口.

        根据意图识别结果分发到对应处理器。

        Args:
            user_id: 用户唯一标识.
            text: 用户输入文本.

        Returns:
            机器人回复文本.
        """
        intent, params = self.recognize_intent(text)

        match intent:
            case Intent.SEARCH:
                return self._handle_search(user_id, params)
            case Intent.TODAY:
                return self._handle_today(user_id)
            case Intent.TOP:
                return self._handle_top(user_id, params)
            case Intent.SUBSCRIBE:
                return self._handle_subscribe(user_id, params)
            case Intent.UNSUBSCRIBE:
                return self._handle_unsubscribe(user_id, params)
            case Intent.LIST_SUBS:
                return self._handle_list_subs(user_id)
            case Intent.HELP:
                return self._handle_help()
            case _:
                return self._handle_unknown(params)

    def _handle_search(self, user_id: str, params: str) -> str:
        """处理搜索请求.

        Args:
            user_id: 用户唯一标识.
            params: 搜索参数字符串.

        Returns:
            搜索结果文本.
        """
        if not self.permission_manager.has_permission(user_id, Permission.READ):
            return "❌ 您没有搜索权限,请联系管理员。"

        query = self._parse_search_query(params)
        result = self.search_engine.search(query)

        if not result.articles:
            return f"📭 未找到匹配的文章,共检索了 {self.search_engine._articles} 篇。"

        lines = [
            f"🔍 搜索结果: 共 {result.total} 篇匹配",
            f"显示前 {len(result.articles)} 篇:\n",
        ]
        for i, article in enumerate(result.articles, 1):
            title = article.get("title", "无标题")
            score = article.get("score", 0)
            tags = article.get("tags", [])
            summary = article.get("summary", "")[:100]
            url = article.get("url", "")

            tag_str = ", ".join(f"`{t}`" for t in tags[:3]) if tags else "无标签"
            lines.append(
                f"{i}. **{title}**\n"
                f"   评分: {score} | 标签: {tag_str}\n"
                f"   {summary}..."
            )
            if url:
                lines.append(f"   🔗 {url}")
            lines.append("")

        return "\n".join(lines)

    def _parse_search_query(self, params: str) -> SearchQuery:
        """解析搜索参数字符串为 SearchQuery 对象.

        支持以下格式:
        - 纯关键词: "机器学习 深度学习"
        - 标签过滤: "tag:人工智能 tag:LLM"
        - 日期范围: "date:2026-05-01~2026-05-07"
        - 混合使用: "机器学习 tag:Python date:2026-05-01~"

        Args:
            params: 参数字符串.

        Returns:
            SearchQuery 对象.
        """
        query = SearchQuery()

        tag_pattern = re.compile(r"tag:(\S+)")
        date_pattern = re.compile(r"date:(\d{4}-\d{2}-\d{2})(?:~(\d{4}-\d{2}-\d{2}))?")
        limit_pattern = re.compile(r"limit:(\d+)")

        for match in tag_pattern.finditer(params):
            query.tags.append(match.group(1))

        for match in date_pattern.finditer(params):
            query.date_from = match.group(1)
            if match.group(2):
                query.date_to = match.group(2)
            else:
                query.date_to = match.group(1)

        for match in limit_pattern.finditer(params):
            try:
                query.limit = int(match.group(1))
            except ValueError:
                pass

        cleaned = params
        for pattern in [tag_pattern, date_pattern, limit_pattern]:
            cleaned = pattern.sub("", cleaned)

        keywords = [kw.strip() for kw in cleaned.split() if kw.strip()]
        query.keywords = keywords

        return query

    def _handle_today(self, user_id: str) -> str:
        """处理今日简报请求.

        Args:
            user_id: 用户唯一标识.

        Returns:
            今日简报文本.
        """
        if not self.permission_manager.has_permission(user_id, Permission.READ):
            return "❌ 您没有查看简报权限,请联系管理员。"

        articles = self.search_engine.get_today_articles()

        if not articles:
            today = date.today().isoformat()
            return f"📭 {today} 暂无新增知识条目。"

        lines = [
            f"📰 今日知识简报 ({date.today().isoformat()})",
            f"共 {len(articles)} 篇:\n",
        ]
        for i, article in enumerate(articles, 1):
            title = article.get("title", "无标题")
            score = article.get("score", 0)
            tags = article.get("tags", [])[:3]
            summary = article.get("summary", "")[:80]

            tag_str = " ".join(f"#{t}" for t in tags) if tags else ""
            lines.append(
                f"{i}. {title}\n"
                f"   ⭐ {score} {tag_str}\n"
                f"   {summary}..."
            )
            lines.append("")

        return "\n".join(lines)

    def _handle_top(self, user_id: str, params: str) -> str:
        """处理热门文章请求.

        Args:
            user_id: 用户唯一标识.
            params: 参数字符串,可能包含数量限制.

        Returns:
            热门文章文本.
        """
        if not self.permission_manager.has_permission(user_id, Permission.READ):
            return "❌ 您没有查看热门文章权限,请联系管理员。"

        limit = 10
        if params:
            match = re.search(r"\d+", params)
            if match:
                try:
                    limit = int(match.group())
                except ValueError:
                    pass

        articles = self.search_engine.get_top_articles(limit)

        lines = [
            f"🏆 热门文章 Top {len(articles)}",
            "",
        ]
        for i, article in enumerate(articles, 1):
            title = article.get("title", "无标题")
            score = article.get("score", 0)
            source = article.get("source", "unknown")

            lines.append(f"{i}. **{title}** ({source}) - ⭐ {score}")

        return "\n".join(lines)

    def _handle_subscribe(self, user_id: str, params: str) -> str:
        """处理订阅请求.

        Args:
            user_id: 用户唯一标识.
            params: 参数字符串,包含要订阅的标签.

        Returns:
            订阅结果文本.
        """
        if not self.permission_manager.has_permission(user_id, Permission.WRITE):
            return "❌ 订阅功能需要 WRITE 权限,请联系管理员提升权限。"

        tags = [tag.strip() for tag in params.split() if tag.strip()]
        if not tags:
            all_tags = self.search_engine.get_all_tags()[:20]
            return (
                "❓ 请指定要订阅的标签。\n"
                f"示例: `/subscribe 机器学习 LLM`\n\n"
                f"📋 热门标签: {', '.join(all_tags[:10])}"
            )

        new_subs = []
        for tag in tags:
            if self.subscription_manager.add_subscription(user_id, tag):
                new_subs.append(tag)

        if new_subs:
            return f"✅ 订阅成功: {', '.join(new_subs)}"
        return f"ℹ️ 您已订阅过这些标签: {', '.join(tags)}"

    def _handle_unsubscribe(self, user_id: str, params: str) -> str:
        """处理取消订阅请求.

        Args:
            user_id: 用户唯一标识.
            params: 参数字符串,包含要取消的标签.

        Returns:
            取消订阅结果文本.
        """
        if not self.permission_manager.has_permission(user_id, Permission.WRITE):
            return "❌ 取消订阅需要 WRITE 权限,请联系管理员。"

        tags = [tag.strip() for tag in params.split() if tag.strip()]
        if not tags:
            subs = self.subscription_manager.get_subscriptions(user_id)
            return (
                "❓ 请指定要取消的标签,或使用 `/unsubscribe all` 清空所有订阅。\n"
                f"当前订阅: {', '.join(subs) or '无'}"
            )

        if "all" in [t.lower() for t in tags]:
            if self.subscription_manager.clear_subscriptions(user_id):
                return "✅ 已清空所有订阅"
            return "ℹ️ 您暂无订阅"

        removed = []
        for tag in tags:
            if self.subscription_manager.remove_subscription(user_id, tag):
                removed.append(tag)

        if removed:
            return f"✅ 已取消订阅: {', '.join(removed)}"
        unsub = [t for t in tags if t not in removed]
        return f"ℹ️ 您未订阅这些标签: {', '.join(unsub)}"

    def _handle_list_subs(self, user_id: str) -> str:
        """处理查看订阅列表请求.

        Args:
            user_id: 用户唯一标识.

        Returns:
            订阅列表文本.
        """
        subs = self.subscription_manager.get_subscriptions(user_id)
        if not subs:
            return "📭 您暂无订阅,使用 `/subscribe <标签>` 添加订阅。"

        return (
            f"📋 您的订阅列表 ({len(subs)} 个):\n"
            f"{'  '.join(f'`{tag}`' for tag in sorted(subs))}"
        )

    def _handle_help(self) -> str:
        """生成帮助信息.

        Returns:
            帮助文本.
        """
        return """🤖 **知识库机器人使用指南**

🔍 **搜索知识库**
- `/search <关键词>` - 搜索文章
- 支持标签过滤: `tag:人工智能`
- 支持日期范围: `date:2026-05-01~2026-05-07`
- 示例: `/search 机器学习 tag:Python`

📰 **今日简报**
- `/today` - 查看今日新增文章

🏆 **热门文章**
- `/top` - 查看评分最高的文章
- `/top 20` - 查看 Top 20

📌 **订阅管理**
- `/subscribe <标签>` - 订阅标签
- `/unsubscribe <标签>` - 取消订阅
- `/unsubscribe all` - 清空所有订阅
- `/list` - 查看我的订阅

❓ **帮助**
- `/help` - 显示此帮助信息

💡 **权限说明**
- READ: 搜索、查看简报(默认)
- WRITE: 订阅管理
- DELETE: 高级操作
- ADMIN: 管理员权限
"""

    def _handle_unknown(self, text: str) -> str:
        """处理未知意图.

        Args:
            text: 用户输入文本.

        Returns:
            提示文本.
        """
        return (
            f"❓ 未理解您的请求: '{text[:50]}...'\n"
            f"发送 `/help` 查看使用说明。"
        )
