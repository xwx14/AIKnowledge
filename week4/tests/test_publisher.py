"""publisher.py 推送模块测试.

使用 unittest.mock.patch 模拟 aiohttp 请求, 不发真实网络请求。
运行方式: python -m pytest tests/test_publisher.py -v
"""

import json
from datetime import date
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from distribution.publisher import (
    BasePublisher,
    FeishuPublisher,
    PublishResult,
    TelegramPublisher,
    publish_daily_digest,
)

PROJECT_ROOT = r"E:\myProject\MyProject\aiKnowledge-merged\week4"
ARTICLES_DIR = f"{PROJECT_ROOT}\\knowledge\\articles"


def _make_aiohttp_response(status, json_data):
    resp = AsyncMock()
    resp.status = status
    resp.json = AsyncMock(return_value=json_data)
    resp.__aenter__ = AsyncMock(return_value=resp)
    resp.__aexit__ = AsyncMock(return_value=False)
    return resp


class TestPublishResult:
    def test_success_str(self):
        r = PublishResult(channel="telegram", success=True, message_id="123")
        assert "OK" in str(r)
        assert "123" in str(r)

    def test_failure_str(self):
        r = PublishResult(channel="feishu", success=False, error="timeout")
        assert "FAIL" in str(r)
        assert "timeout" in str(r)

    def test_defaults(self):
        r = PublishResult(channel="test", success=True)
        assert r.message_id is None
        assert r.error is None


class TestBasePublisher:
    def test_cannot_instantiate(self):
        with pytest.raises(TypeError):
            BasePublisher()

    def test_subclass_must_implement(self):
        class IncompletePublisher(BasePublisher):
            @property
            def channel_name(self) -> str:
                return "incomplete"

            async def send_message(self, text: str) -> PublishResult:
                return PublishResult(channel=self.channel_name, success=True)

        with pytest.raises(TypeError):
            IncompletePublisher()

    def test_complete_subclass(self):
        class CompletePublisher(BasePublisher):
            @property
            def channel_name(self) -> str:
                return "complete"

            async def send_message(self, text: str) -> PublishResult:
                return PublishResult(channel=self.channel_name, success=True)

            async def send_digest(self, knowledge_dir, target_date, top_n):
                return PublishResult(channel=self.channel_name, success=True)

        pub = CompletePublisher()
        assert pub.channel_name == "complete"


class TestTelegramPublisher:
    def test_channel_name(self):
        pub = TelegramPublisher(bot_token="t", chat_id="c")
        assert pub.channel_name == "telegram"

    def test_init_from_env(self):
        pub = TelegramPublisher()
        assert pub._timeout == 30

    def test_init_custom_params(self):
        pub = TelegramPublisher(bot_token="tok", chat_id="chat", timeout=60)
        assert pub._bot_token == "tok"
        assert pub._chat_id == "chat"
        assert pub._timeout == 60

    @pytest.mark.asyncio
    async def test_send_message_no_config(self):
        pub = TelegramPublisher(bot_token="", chat_id="")
        result = await pub.send_message("hello")
        assert result.success is False
        assert "未配置" in result.error

    @pytest.mark.asyncio
    async def test_send_message_success(self):
        token = "123456:ABC-DEF"
        chat_id = "987654321"
        pub = TelegramPublisher(bot_token=token, chat_id=chat_id)
        expected_url = f"https://api.telegram.org/bot{token}/sendMessage"
        mock_resp = _make_aiohttp_response(200, {"ok": True, "result": {"message_id": 42}})

        mock_session = AsyncMock()
        mock_post = MagicMock(return_value=mock_resp)
        mock_session.post = mock_post
        mock_session.__aenter__ = AsyncMock(return_value=mock_session)
        mock_session.__aexit__ = AsyncMock(return_value=False)

        with patch("distribution.publisher.aiohttp.ClientSession", return_value=mock_session):
            result = await pub.send_message("test message")

        assert result.success is True
        assert result.message_id == "42"

    @pytest.mark.asyncio
    async def test_send_message_api_error(self):
        token = "123456:ABC-DEF"
        pub = TelegramPublisher(bot_token=token, chat_id="987654321")
        mock_resp = _make_aiohttp_response(400, {
            "ok": False,
            "description": "Bad Request: message is too long",
        })

        mock_session = AsyncMock()
        mock_session.post = MagicMock(return_value=mock_resp)
        mock_session.__aenter__ = AsyncMock(return_value=mock_session)
        mock_session.__aexit__ = AsyncMock(return_value=False)

        with patch("distribution.publisher.aiohttp.ClientSession", return_value=mock_session):
            result = await pub.send_message("x" * 10000)

        assert result.success is False
        assert "too long" in result.error

    @pytest.mark.asyncio
    async def test_send_message_network_error(self):
        token = "123456:ABC-DEF"
        pub = TelegramPublisher(bot_token=token, chat_id="987654321", timeout=1)

        mock_session = AsyncMock()
        mock_session.post = MagicMock(side_effect=TimeoutError("connection timed out"))
        mock_session.__aenter__ = AsyncMock(return_value=mock_session)
        mock_session.__aexit__ = AsyncMock(return_value=False)

        with patch("distribution.publisher.aiohttp.ClientSession", return_value=mock_session):
            result = await pub.send_message("test")

        assert result.success is False
        assert "timed out" in result.error

    @pytest.mark.asyncio
    async def test_send_message_payload_format(self):
        token = "123456:ABC-DEF"
        chat_id = "987654321"
        pub = TelegramPublisher(bot_token=token, chat_id=chat_id)
        mock_resp = _make_aiohttp_response(200, {"ok": True, "result": {"message_id": 1}})

        captured_json = {}

        def capture_post(url, **kwargs):
            captured_json.update(kwargs.get("json", {}))
            return mock_resp

        mock_session = AsyncMock()
        mock_session.post = capture_post
        mock_session.__aenter__ = AsyncMock(return_value=mock_session)
        mock_session.__aexit__ = AsyncMock(return_value=False)

        with patch("distribution.publisher.aiohttp.ClientSession", return_value=mock_session):
            await pub.send_message("hello *world*")

        assert captured_json["chat_id"] == chat_id
        assert captured_json["parse_mode"] == "MarkdownV2"
        assert captured_json["text"] == "hello *world*"

    @pytest.mark.asyncio
    async def test_send_digest_no_config(self):
        pub = TelegramPublisher(bot_token="", chat_id="")
        result = await pub.send_digest(knowledge_dir=ARTICLES_DIR)
        assert result.success is False


class TestFeishuPublisher:
    def test_channel_name(self):
        pub = FeishuPublisher(app_id="a", app_secret="s", chat_id="c")
        assert pub.channel_name == "feishu"

    def test_init_from_env(self):
        pub = FeishuPublisher()
        assert pub._timeout == 30

    def test_init_custom_params(self):
        pub = FeishuPublisher(
            app_id="aid", app_secret="asec", chat_id="och", timeout=45
        )
        assert pub._app_id == "aid"
        assert pub._app_secret == "asec"
        assert pub._chat_id == "och"
        assert pub._timeout == 45

    @pytest.mark.asyncio
    async def test_send_message_no_config(self):
        pub = FeishuPublisher(app_id="", app_secret="", chat_id="")
        result = await pub.send_message("hello")
        assert result.success is False
        assert "未配置" in result.error

    @pytest.mark.asyncio
    async def test_send_message_success(self):
        pub = FeishuPublisher(
            app_id="test_app", app_secret="test_secret", chat_id="oc_test"
        )

        token_resp = _make_aiohttp_response(200, {
            "code": 0, "tenant_access_token": "t-token-123", "expire": 7200
        })
        msg_resp = _make_aiohttp_response(200, {
            "code": 0, "msg": "success", "data": {"message_id": "om_xxx"}
        })

        call_count = 0

        def mock_post(url, **kwargs):
            nonlocal call_count
            call_count += 1
            if call_count == 1:
                return token_resp
            return msg_resp

        mock_session = AsyncMock()
        mock_session.post = mock_post
        mock_session.__aenter__ = AsyncMock(return_value=mock_session)
        mock_session.__aexit__ = AsyncMock(return_value=False)

        with patch("distribution.publisher.aiohttp.ClientSession", return_value=mock_session):
            result = await pub.send_message("test card")

        assert result.success is True
        assert result.message_id == "om_xxx"

    @pytest.mark.asyncio
    async def test_send_message_token_fail(self):
        pub = FeishuPublisher(
            app_id="bad", app_secret="bad", chat_id="oc_test"
        )

        token_resp = _make_aiohttp_response(200, {
            "code": 9999, "msg": "invalid app_id"
        })

        mock_session = AsyncMock()
        mock_session.post = MagicMock(return_value=token_resp)
        mock_session.__aenter__ = AsyncMock(return_value=mock_session)
        mock_session.__aexit__ = AsyncMock(return_value=False)

        with patch("distribution.publisher.aiohttp.ClientSession", return_value=mock_session):
            result = await pub.send_message("test")

        assert result.success is False
        assert "invalid app_id" in result.error

    @pytest.mark.asyncio
    async def test_send_message_api_error(self):
        pub = FeishuPublisher(
            app_id="test_app", app_secret="test_secret", chat_id="oc_test"
        )

        token_resp = _make_aiohttp_response(200, {
            "code": 0, "tenant_access_token": "tok"
        })
        msg_resp = _make_aiohttp_response(200, {
            "code": 19021, "msg": "send message failed"
        })

        call_count = 0

        def mock_post(url, **kwargs):
            nonlocal call_count
            call_count += 1
            return token_resp if call_count == 1 else msg_resp

        mock_session = AsyncMock()
        mock_session.post = mock_post
        mock_session.__aenter__ = AsyncMock(return_value=mock_session)
        mock_session.__aexit__ = AsyncMock(return_value=False)

        with patch("distribution.publisher.aiohttp.ClientSession", return_value=mock_session):
            result = await pub.send_message("test")

        assert result.success is False
        assert "send message failed" in result.error

    @pytest.mark.asyncio
    async def test_send_digest_no_config(self):
        pub = FeishuPublisher(app_id="", app_secret="", chat_id="")
        result = await pub.send_digest(knowledge_dir=ARTICLES_DIR)
        assert result.success is False

    @pytest.mark.asyncio
    async def test_send_digest_success(self):
        pub = FeishuPublisher(
            app_id="test_app", app_secret="test_secret", chat_id="oc_test"
        )

        token_resp = _make_aiohttp_response(200, {
            "code": 0, "tenant_access_token": "tok"
        })
        msg_resp = _make_aiohttp_response(200, {
            "code": 0, "msg": "success", "data": {"message_id": "om_digest"}
        })

        call_count = 0

        def mock_post(url, **kwargs):
            nonlocal call_count
            call_count += 1
            return token_resp if call_count == 1 else msg_resp

        mock_session = AsyncMock()
        mock_session.post = mock_post
        mock_session.__aenter__ = AsyncMock(return_value=mock_session)
        mock_session.__aexit__ = AsyncMock(return_value=False)

        with patch("distribution.publisher.aiohttp.ClientSession", return_value=mock_session):
            result = await pub.send_digest(
                knowledge_dir=ARTICLES_DIR,
                target_date=date(2026, 5, 5),
                top_n=1,
            )

        assert result.success is True
        assert result.message_id == "om_digest"

    @pytest.mark.asyncio
    async def test_send_digest_empty_fallback(self):
        pub = FeishuPublisher(
            app_id="test_app", app_secret="test_secret", chat_id="oc_test"
        )

        token_resp = _make_aiohttp_response(200, {
            "code": 0, "tenant_access_token": "tok"
        })
        msg_resp = _make_aiohttp_response(200, {
            "code": 0, "msg": "success", "data": {"message_id": "om_empty"}
        })

        call_count = 0

        def mock_post(url, **kwargs):
            nonlocal call_count
            call_count += 1
            return token_resp if call_count == 1 else msg_resp

        mock_session = AsyncMock()
        mock_session.post = mock_post
        mock_session.__aenter__ = AsyncMock(return_value=mock_session)
        mock_session.__aexit__ = AsyncMock(return_value=False)

        with patch("distribution.publisher.aiohttp.ClientSession", return_value=mock_session):
            result = await pub.send_digest(
                knowledge_dir=ARTICLES_DIR,
                target_date=date(2020, 1, 1),
            )

        assert result.success is True

    @pytest.mark.asyncio
    async def test_send_digest_card_payload(self):
        pub = FeishuPublisher(
            app_id="test_app", app_secret="test_secret", chat_id="oc_test"
        )

        token_resp = _make_aiohttp_response(200, {
            "code": 0, "tenant_access_token": "tok"
        })
        msg_resp = _make_aiohttp_response(200, {
            "code": 0, "msg": "success", "data": {"message_id": "om_1"}
        })

        captured_payload = {}

        def mock_post(url, **kwargs):
            nonlocal captured_payload
            if "auth" in url:
                return token_resp
            captured_payload = kwargs.get("json", {})
            return msg_resp

        mock_session = AsyncMock()
        mock_session.post = mock_post
        mock_session.__aenter__ = AsyncMock(return_value=mock_session)
        mock_session.__aexit__ = AsyncMock(return_value=False)

        with patch("distribution.publisher.aiohttp.ClientSession", return_value=mock_session):
            await pub.send_digest(
                knowledge_dir=ARTICLES_DIR,
                target_date=date(2026, 5, 5),
                top_n=1,
            )

        assert captured_payload["receive_id"] == "oc_test"
        assert captured_payload["msg_type"] == "interactive"
        card_content = json.loads(captured_payload["content"])
        assert "header" in card_content
        assert "elements" in card_content


class TestPublishDailyDigest:
    @pytest.mark.asyncio
    async def test_default_publishers(self):
        results = await publish_daily_digest(
            knowledge_dir=ARTICLES_DIR,
            target_date=date(2020, 1, 1),
        )
        assert len(results) == 2
        channels = {r.channel for r in results}
        assert "telegram" in channels
        assert "feishu" in channels

    @pytest.mark.asyncio
    async def test_custom_publishers(self):
        class MockPublisher(BasePublisher):
            @property
            def channel_name(self) -> str:
                return "mock"

            async def send_message(self, text: str) -> PublishResult:
                return PublishResult(channel=self.channel_name, success=True, message_id="m1")

            async def send_digest(self, knowledge_dir, target_date, top_n):
                return PublishResult(channel=self.channel_name, success=True, message_id="d1")

        results = await publish_daily_digest(
            knowledge_dir=ARTICLES_DIR,
            publishers=[MockPublisher()],
        )
        assert len(results) == 1
        assert results[0].success is True
        assert results[0].message_id == "d1"

    @pytest.mark.asyncio
    async def test_concurrent_publish(self):
        call_count = 0

        class CountingPublisher(BasePublisher):
            @property
            def channel_name(self) -> str:
                return "counter"

            async def send_message(self, text: str) -> PublishResult:
                nonlocal call_count
                call_count += 1
                return PublishResult(channel=self.channel_name, success=True)

            async def send_digest(self, knowledge_dir, target_date, top_n):
                nonlocal call_count
                call_count += 1
                return PublishResult(channel=self.channel_name, success=True)

        pubs = [CountingPublisher() for _ in range(5)]
        results = await publish_daily_digest(publishers=pubs)
        assert len(results) == 5
        assert call_count == 5
        assert all(r.success for r in results)

    @pytest.mark.asyncio
    async def test_exception_handled(self):
        class FailingPublisher(BasePublisher):
            @property
            def channel_name(self) -> str:
                return "fail"

            async def send_message(self, text: str) -> PublishResult:
                raise RuntimeError("boom")

            async def send_digest(self, knowledge_dir, target_date, top_n):
                raise RuntimeError("boom")

        results = await publish_daily_digest(publishers=[FailingPublisher()])
        assert len(results) == 1
        assert results[0].success is False
        assert "boom" in results[0].error

    @pytest.mark.asyncio
    async def test_mixed_results(self):
        class OkPublisher(BasePublisher):
            @property
            def channel_name(self) -> str:
                return "ok"

            async def send_message(self, text: str) -> PublishResult:
                return PublishResult(channel=self.channel_name, success=True)

            async def send_digest(self, knowledge_dir, target_date, top_n):
                return PublishResult(channel=self.channel_name, success=True)

        class FailPublisher(BasePublisher):
            @property
            def channel_name(self) -> str:
                return "fail"

            async def send_message(self, text: str) -> PublishResult:
                raise RuntimeError("err")

            async def send_digest(self, knowledge_dir, target_date, top_n):
                raise RuntimeError("err")

        results = await publish_daily_digest(
            publishers=[OkPublisher(), FailPublisher()]
        )
        assert results[0].success is True
        assert results[1].success is False

    @pytest.mark.asyncio
    async def test_empty_publishers_list(self):
        results = await publish_daily_digest(publishers=[])
        assert results == []
