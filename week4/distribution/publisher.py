"""AI 知识简报推送模块.

通过 Telegram Bot API 和飞书机器人应用异步发送知识简报。
基于 ABC 抽象基类实现可扩展的 Publisher 架构。
"""

from __future__ import annotations

import asyncio
import json
import logging
import os
from abc import ABC, abstractmethod
from dataclasses import dataclass
from datetime import date
from typing import Any, Dict, List, Optional

import aiohttp
from dotenv import load_dotenv

from distribution.formatter import generate_daily_digest

logger = logging.getLogger(__name__)

load_dotenv()


@dataclass
class PublishResult:
    """单次推送的结果记录.

    Attributes:
        channel: 推送渠道名称 (telegram / feishu).
        success: 是否推送成功.
        message_id: 成功时返回的消息 ID.
        error: 失败时的错误信息.
    """

    channel: str
    success: bool
    message_id: Optional[str] = None
    error: Optional[str] = None

    def __str__(self) -> str:
        if self.success:
            return f"[{self.channel}] OK message_id={self.message_id}"
        return f"[{self.channel}] FAIL error={self.error}"


class BasePublisher(ABC):
    """推送渠道的抽象基类.

    所有推送渠道必须实现 ``send_message`` 和 ``send_digest`` 两个接口。
    """

    @property
    @abstractmethod
    def channel_name(self) -> str:
        """渠道标识名称."""

    @abstractmethod
    async def send_message(self, text: str) -> PublishResult:
        """发送纯文本消息.

        Args:
            text: 消息文本内容.

        Returns:
            推送结果.
        """

    @abstractmethod
    async def send_digest(
        self,
        knowledge_dir: str = "knowledge/articles",
        target_date: Optional[date] = None,
        top_n: int = 5,
    ) -> PublishResult:
        """生成并推送当日知识简报.

        Args:
            knowledge_dir: 知识条目目录路径.
            target_date: 目标日期, 默认今天.
            top_n: 返回的 Top N 篇文章数.

        Returns:
            推送结果.
        """


class TelegramPublisher(BasePublisher):
    """通过 Telegram Bot API 发送 MarkdownV2 消息.

    使用 aiohttp 异步请求, 超时 30 秒。
    从 .env 读取 TELEGRAM_BOT_TOKEN 和 TELEGRAM_CHAT_ID。

    Args:
        bot_token: Telegram Bot Token, 默认从环境变量读取.
        chat_id: Telegram Chat ID, 默认从环境变量读取.
        timeout: 请求超时秒数, 默认 30.
    """

    API_BASE = "https://api.telegram.org/bot{token}"

    def __init__(
        self,
        bot_token: Optional[str] = None,
        chat_id: Optional[str] = None,
        timeout: int = 30,
    ) -> None:
        self._bot_token = bot_token or os.getenv("TELEGRAM_BOT_TOKEN", "")
        self._chat_id = chat_id or os.getenv("TELEGRAM_CHAT_ID", "")
        self._timeout = timeout

    @property
    def channel_name(self) -> str:
        return "telegram"

    async def send_message(self, text: str) -> PublishResult:
        """发送 Telegram MarkdownV2 文本消息.

        Args:
            text: 消息文本 (应已转义 MarkdownV2 特殊字符).

        Returns:
            推送结果.
        """
        if not self._bot_token or not self._chat_id:
            return PublishResult(
                channel=self.channel_name,
                success=False,
                error="TELEGRAM_BOT_TOKEN 或 TELEGRAM_CHAT_ID 未配置",
            )


        url = f"{self.API_BASE.format(token=self._bot_token)}/sendMessage"
        payload: Dict[str, Any] = {
            "chat_id": self._chat_id,
            "text": text,
            "parse_mode": "MarkdownV2",
        }

        try:
            timeout = aiohttp.ClientTimeout(total=self._timeout)
            async with aiohttp.ClientSession(timeout=timeout) as session:
                async with session.post(url, json=payload) as resp:
                    body = await resp.json()
                    if resp.status == 200 and body.get("ok"):
                        result = body.get("result", {})
                        message_id = str(result.get("message_id", ""))
                        logger.info(
                            "Telegram 消息发送成功, message_id=%s", message_id
                        )
                        return PublishResult(
                            channel=self.channel_name,
                            success=True,
                            message_id=message_id,
                        )
                    description = body.get("description", "未知错误")
                    logger.warning("Telegram API 返回错误: %s", description)
                    return PublishResult(
                        channel=self.channel_name,
                        success=False,
                        error=description,
                    )
        except Exception as exc:
            logger.error("Telegram 请求异常: %s", exc)
            return PublishResult(
                channel=self.channel_name,
                success=False,
                error=str(exc),
            )

    async def send_digest(
        self,
        knowledge_dir: str = "knowledge/articles",
        target_date: Optional[date] = None,
        top_n: int = 5,
    ) -> PublishResult:
        """生成当日简报并以 Telegram MarkdownV2 格式推送.

        Args:
            knowledge_dir: 知识条目目录路径.
            target_date: 目标日期, 默认今天.
            top_n: Top N 篇文章.

        Returns:
            推送结果.
        """
        digest = generate_daily_digest(
            knowledge_dir=knowledge_dir,
            target_date=target_date,
            top_n=top_n,
        )
        return await self.send_message(digest["telegram"])


class FeishuPublisher(BasePublisher):
    """通过飞书机器人应用发送 Interactive Card 消息.

    从 .env 读取 FEISHU_APP_ID / FEISHU_APP_SECRET / FEISHU_CHAT_ID。
    先通过 App ID + Secret 获取 tenant_access_token, 再发送卡片消息。

    Args:
        app_id: 飞书应用 ID, 默认从环境变量读取.
        app_secret: 飞书应用 Secret, 默认从环境变量读取.
        chat_id: 飞书群聊/用户 ID, 默认从环境变量读取.
        timeout: 请求超时秒数, 默认 30.
    """

    TOKEN_URL = "https://open.feishu.cn/open-apis/auth/v3/tenant_access_token/internal"
    MESSAGE_URL = "https://open.feishu.cn/open-apis/im/v1/messages?receive_id_type={id_type}"

    def __init__(
        self,
        app_id: Optional[str] = None,
        app_secret: Optional[str] = None,
        chat_id: Optional[str] = None,
        timeout: int = 30,
    ) -> None:

        self._app_id = app_id or os.getenv("FEISHU_APP_ID", "")
        self._app_secret = app_secret or os.getenv("FEISHU_APP_SECRET", "")
        self._timeout = timeout
        raw_chat_id = chat_id or os.getenv("FEISHU_CHAT_ID", "")
        self._chat_id = raw_chat_id
        if raw_chat_id.startswith("ou_"):
            self._id_type = "open_id"
        elif raw_chat_id.startswith("oc_"):
            self._id_type = "chat_id"
        else:
            self._id_type = "chat_id"

    @property
    def channel_name(self) -> str:
        return "feishu"

    async def _get_tenant_access_token(self, session: Any) -> str:
        """获取飞书 tenant_access_token.

        Args:
            session: aiohttp ClientSession 实例.

        Returns:
            access_token 字符串.

        Raises:
            RuntimeError: 获取 token 失败.
        """
        payload = {
            "app_id": self._app_id,
            "app_secret": self._app_secret,
        }
        async with session.post(self.TOKEN_URL, json=payload) as resp:
            body = await resp.json()
            if body.get("code") == 0:
                token = body.get("tenant_access_token", "")
                logger.info("飞书 tenant_access_token 获取成功")
                return token
            msg = body.get("msg", "未知错误")
            raise RuntimeError(f"获取飞书 token 失败: {msg}")

    async def send_message(self, text: str) -> PublishResult:
        """发送飞书文本消息.

        Args:
            text: 消息文本内容.

        Returns:
            推送结果.
        """
        if not self._app_id or not self._app_secret or not self._chat_id:
            return PublishResult(
                channel=self.channel_name,
                success=False,
                error="FEISHU_APP_ID / FEISHU_APP_SECRET / FEISHU_CHAT_ID 未配置",
            )


        card: Dict[str, Any] = {
            "msg_type": "interactive",
            "card": {
                "elements": [
                    {
                        "tag": "div",
                        "text": {"tag": "lark_md", "content": text},
                    }
                ]
            },
        }
        return await self._send_card(card)

    async def _send_card(self, card: Dict[str, Any]) -> PublishResult:
        """发送飞书 Interactive Card.

        Args:
            card: 飞书卡片字典 (需包含 msg_type 和 card 字段).

        Returns:
            推送结果.
        """

        timeout = aiohttp.ClientTimeout(total=self._timeout)
        try:
            async with aiohttp.ClientSession(timeout=timeout) as session:
                token = await self._get_tenant_access_token(session)
                url = self.MESSAGE_URL.format(id_type=self._id_type)
                payload: Dict[str, Any] = {
                    "receive_id": self._chat_id,
                    "msg_type": card.get("msg_type", "interactive"),
                    "content": json.dumps(card.get("card", card), ensure_ascii=False),
                }
                headers = {"Authorization": f"Bearer {token}"}

                async with session.post(url, json=payload, headers=headers) as resp:
                    body = await resp.json()
                    if body.get("code") == 0:
                        message_id = body.get("data", {}).get("message_id", "")
                        logger.info(
                            "飞书消息发送成功, message_id=%s", message_id
                        )
                        return PublishResult(
                            channel=self.channel_name,
                            success=True,
                            message_id=message_id,
                        )
                    msg = body.get("msg", "未知错误")
                    logger.warning("飞书 API 返回错误: %s", msg)
                    return PublishResult(
                        channel=self.channel_name,
                        success=False,
                        error=msg,
                    )
        except Exception as exc:
            logger.error("飞书请求异常: %s", exc)
            return PublishResult(
                channel=self.channel_name,
                success=False,
                error=str(exc),
            )

    async def send_digest(
        self,
        knowledge_dir: str = "knowledge/articles",
        target_date: Optional[date] = None,
        top_n: int = 5,
    ) -> PublishResult:
        """生成当日简报并以飞书 Interactive Card 格式推送.

        Args:
            knowledge_dir: 知识条目目录路径.
            target_date: 目标日期, 默认今天.
            top_n: Top N 篇文章.

        Returns:
            推送结果.
        """
        digest = generate_daily_digest(
            knowledge_dir=knowledge_dir,
            target_date=target_date,
            top_n=top_n,
        )
        try:
            card = json.loads(digest["feishu"])
        except (json.JSONDecodeError, TypeError):
            card = {
                "msg_type": "interactive",
                "card": {
                    "elements": [
                        {
                            "tag": "div",
                            "text": {
                                "tag": "lark_md",
                                "content": digest["feishu"],
                            },
                        }
                    ]
                },
            }
        return await self._send_card(card)


async def publish_daily_digest(
    knowledge_dir: str = "knowledge/articles",
    target_date: Optional[date] = None,
    top_n: int = 5,
    publishers: Optional[List[BasePublisher]] = None,
) -> List[PublishResult]:
    """统一异步入口: 生成简报并并发推送到所有渠道.

    如果未提供 publishers, 默认创建 TelegramPublisher + FeishuPublisher。

    Args:
        knowledge_dir: 知识条目目录路径.
        target_date: 目标日期, 默认今天.
        top_n: Top N 篇文章.
        publishers: 推送渠道列表, 默认 [TelegramPublisher, FeishuPublisher].

    Returns:
        各渠道推送结果列表.
    """
    if publishers is None:
        publishers = [TelegramPublisher(), FeishuPublisher()]


    tasks = [
        pub.send_digest(
            knowledge_dir=knowledge_dir,
            target_date=target_date,
            top_n=top_n,
        )
        for pub in publishers
    ]
    results = await asyncio.gather(*tasks, return_exceptions=True)

    final_results: List[PublishResult] = []
    for pub, result in zip(publishers, results):
        if isinstance(result, Exception):
            final_results.append(
                PublishResult(
                    channel=pub.channel_name,
                    success=False,
                    error=str(result),
                )
            )
        else:
            final_results.append(result)

    return final_results
