"""formatter.py 格式化模块测试.

使用真实 knowledge/articles JSON 数据验证三种格式输出。
运行方式: python -m pytest tests/test_formatter.py -v
"""

import json
from datetime import date
from pathlib import Path
from distribution.formatter import (
    generate_daily_digest,
    json_to_feishu,
    json_to_markdown,
    json_to_telegram,
    load_articles,
    _escape_telegram,
    _score_emoji,
    _score_color,
)

PROJECT_ROOT = Path(__file__).resolve().parent.parent
ARTICLES_DIR = str(PROJECT_ROOT / "knowledge" / "articles")

SAMPLE_HIGH = {
    "id": "rss_test_high",
    "source": "rss",
    "title": "Test Article with *Special* Characters [Test]",
    "description": "A test description",
    "url": "https://example.com/article",
    "summary": "这是一篇高质量AI相关文章，深入探讨了大规模语言模型的推理优化策略。",
    "score": 0.92,
    "tags": ["AI推理", "大语言模型", "性能优化"],
    "collected_at": "2026-05-05T14:20:51.844795",
    "analyzed": True,
}

SAMPLE_MID = {
    "id": "github_test_mid",
    "source": "github",
    "title": "Machine Learning Toolkit",
    "description": "ML tools",
    "url": "https://github.com/test/ml-toolkit",
    "summary": "一个通用的机器学习工具包，支持常见的数据预处理和模型训练流程。",
    "score": 0.65,
    "tags": ["机器学习", "工具包"],
    "collected_at": "2026-05-05T10:00:00.000000",
    "analyzed": True,
}

SAMPLE_LOW = {
    "id": "rss_test_low",
    "source": "rss",
    "title": "Random Python Script",
    "description": "some script",
    "url": "https://example.com/python",
    "summary": "一个简单的Python脚本集合，与AI关联度较低。",
    "score": 0.3,
    "tags": ["Python"],
    "collected_at": "2026-05-05T08:00:00.000000",
    "analyzed": True,
}

SAMPLE_NO_ANALYZE = {
    "id": "github_test_na",
    "source": "github",
    "title": "Some Repo",
    "description": "desc",
    "url": "https://github.com/test/repo",
    "summary": "",
    "score": 0.0,
    "tags": [],
    "collected_at": "2026-05-01T12:00:00.000000",
    "analyzed": False,
}


class TestScoreEmoji:
    def test_high_score_green(self):
        assert _score_emoji(0.8) == "\U0001f7e2"
        assert _score_emoji(1.0) == "\U0001f7e2"

    def test_mid_score_yellow(self):
        assert _score_emoji(0.6) == "\U0001f7e1"
        assert _score_emoji(0.79) == "\U0001f7e1"

    def test_low_score_red(self):
        assert _score_emoji(0.0) == "\U0001f534"
        assert _score_emoji(0.59) == "\U0001f534"


class TestScoreColor:
    def test_green(self):
        assert _score_color(0.8) == "green"

    def test_yellow(self):
        assert _score_color(0.6) == "yellow"

    def test_red(self):
        assert _score_color(0.3) == "red"


class TestEscapeTelegram:
    def test_escapes_special_chars(self):
        text = "Hello_World *bold* [link](url)"
        result = _escape_telegram(text)
        assert "\\_" in result
        assert "\\*" in result
        assert "\\[" in result
        assert "\\]" in result
        assert "\\(" in result
        assert "\\)" in result

    def test_plain_text_unchanged(self):
        text = "Hello World"
        assert _escape_telegram(text) == "Hello World"

    def test_all_special_chars(self):
        import string
        special = r"_*[]()~`>#+-=|{}.!"
        for ch in special:
            result = _escape_telegram(ch)
            assert result == f"\\{ch}", f"Failed to escape: {ch!r}"


class TestJsonToMarkdown:
    def test_basic_fields(self):
        result = json_to_markdown(SAMPLE_HIGH)
        assert "## Test Article" in result
        assert "**来源**: rss" in result
        assert "**日期**: 2026-05-05" in result
        assert "相关性" in result
        assert "\U0001f7e2" in result
        assert "`AI推理`" in result
        assert "大规模语言模型" in result
        assert "[原文链接](https://example.com/article)" in result

    def test_score_emoji_high(self):
        assert "\U0001f7e2" in json_to_markdown(SAMPLE_HIGH)

    def test_score_emoji_mid(self):
        assert "\U0001f7e1" in json_to_markdown(SAMPLE_MID)

    def test_score_emoji_low(self):
        assert "\U0001f534" in json_to_markdown(SAMPLE_LOW)

    def test_no_summary(self):
        result = json_to_markdown(SAMPLE_NO_ANALYZE)
        assert "暂无摘要" in result

    def test_no_tags(self):
        result = json_to_markdown(SAMPLE_NO_ANALYZE)
        assert "无标签" in result


class TestJsonToTelegram:
    def test_basic_fields(self):
        result = json_to_telegram(SAMPLE_HIGH)
        assert "Test Article" in result
        assert "rss" in result
        assert "0.9" in result
        assert "https://example.com/article" in result

    def test_special_chars_escaped(self):
        result = json_to_telegram(SAMPLE_HIGH)
        assert "\\*" not in result.replace("\\*", "")
        assert "\\[" not in result.replace("\\[", "")
        assert "\\]" not in result.replace("\\]", "")

    def test_link_format(self):
        result = json_to_telegram(SAMPLE_HIGH)
        assert "[Test Article" in result
        assert "https://example.com/article)" in result

    def test_tags_with_hashtag(self):
        result = json_to_telegram(SAMPLE_HIGH)
        assert "#AI推理" in result
        assert "#大语言模型" in result
        assert "#性能优化" in result

    def test_no_summary_placeholder(self):
        result = json_to_telegram(SAMPLE_NO_ANALYZE)
        assert "暂无摘要" in result

    def test_pipe_escaped(self):
        article = {"title": "A|B", "source": "test", "url": "", "summary": "x", "score": 0.5, "tags": []}
        result = json_to_telegram(article)
        assert "\\|" in result


class TestJsonToFeishu:
    def test_returns_dict(self):
        result = json_to_feishu(SAMPLE_HIGH)
        assert isinstance(result, dict)

    def test_msg_type_interactive(self):
        assert json_to_feishu(SAMPLE_HIGH)["msg_type"] == "interactive"

    def test_header_template_green(self):
        card = json_to_feishu(SAMPLE_HIGH)
        assert card["card"]["header"]["template"] == "green"

    def test_header_template_yellow(self):
        card = json_to_feishu(SAMPLE_MID)
        assert card["card"]["header"]["template"] == "yellow"

    def test_header_template_red(self):
        card = json_to_feishu(SAMPLE_LOW)
        assert card["card"]["header"]["template"] == "red"

    def test_header_title(self):
        card = json_to_feishu(SAMPLE_HIGH)
        assert card["card"]["header"]["title"]["content"] == SAMPLE_HIGH["title"]

    def test_has_button_with_url(self):
        card = json_to_feishu(SAMPLE_HIGH)
        actions = [
            e["actions"]
            for e in card["card"]["elements"]
            if e.get("tag") == "action"
        ]
        assert len(actions) == 1
        btn = actions[0][0]
        assert btn["url"] == SAMPLE_HIGH["url"]

    def test_no_button_when_no_url(self):
        article = {**SAMPLE_HIGH, "url": ""}
        card = json_to_feishu(article)
        action_elements = [e for e in card["card"]["elements"] if e.get("tag") == "action"]
        assert len(action_elements) == 0

    def test_serializable(self):
        card = json_to_feishu(SAMPLE_HIGH)
        json_str = json.dumps(card, ensure_ascii=False)
        assert len(json_str) > 0


class TestLoadArticles:
    def test_loads_from_real_dir(self):
        articles = load_articles(ARTICLES_DIR)
        assert len(articles) > 0
        for a in articles:
            assert "id" in a
            assert "title" in a

    def test_empty_dir(self):
        articles = load_articles("nonexistent_dir")
        assert articles == []

    def test_skips_invalid_json(self, tmp_path):
        (tmp_path / "good.json").write_text('{"id":"1","title":"ok"}', encoding="utf-8")
        (tmp_path / "bad.json").write_text("not json{{{", encoding="utf-8")
        articles = load_articles(str(tmp_path))
        assert len(articles) == 1
        assert articles[0]["id"] == "1"


class TestGenerateDailyDigest:
    def test_returns_three_formats(self):
        result = generate_daily_digest(
            knowledge_dir=ARTICLES_DIR,
            target_date=date(2026, 5, 5),
            top_n=3,
        )
        assert "markdown" in result
        assert "telegram" in result
        assert "feishu" in result

    def test_markdown_contains_header(self):
        result = generate_daily_digest(
            knowledge_dir=ARTICLES_DIR,
            target_date=date(2026, 5, 5),
            top_n=2,
        )
        assert "# AI 知识简报 - 2026-05-05" in result["markdown"]

    def test_telegram_escaped(self):
        result = generate_daily_digest(
            knowledge_dir=ARTICLES_DIR,
            target_date=date(2026, 5, 5),
            top_n=2,
        )
        assert "AI 知识简报" in result["telegram"]
        assert "\\-" in result["telegram"]

    def test_feishu_is_json_string(self):
        result = generate_daily_digest(
            knowledge_dir=ARTICLES_DIR,
            target_date=date(2026, 5, 5),
            top_n=2,
        )
        parsed = json.loads(result["feishu"])
        assert parsed["msg_type"] == "interactive"
        assert "card" in parsed

    def test_no_articles_returns_empty_msg(self):
        result = generate_daily_digest(
            knowledge_dir=ARTICLES_DIR,
            target_date=date(2020, 1, 1),
        )
        assert "暂无新增知识条目" in result["markdown"]
        assert "暂无新增知识条目" in result["telegram"]
        assert "暂无新增知识条目" in result["feishu"]

    def test_top_n_limits_results(self):
        result = generate_daily_digest(
            knowledge_dir=ARTICLES_DIR,
            target_date=date(2026, 5, 5),
            top_n=1,
        )
        md = result["markdown"]
        article_sections = md.split("## ")[1:]
        assert len(article_sections) == 1

    def test_default_date_today(self):
        result = generate_daily_digest(knowledge_dir=ARTICLES_DIR)
        assert "markdown" in result
        assert "telegram" in result
        assert "feishu" in result


class TestIntegrationWithRealData:
    """用真实 articles JSON 文件做集成测试."""

    def test_real_article_markdown(self):
        articles = load_articles(ARTICLES_DIR)
        analyzed = [a for a in articles if a.get("analyzed")]
        if not analyzed:
            return
        article = analyzed[0]
        result = json_to_markdown(article)
        assert "## " in result
        assert "**来源**:" in result

    def test_real_article_telegram(self):
        articles = load_articles(ARTICLES_DIR)
        analyzed = [a for a in articles if a.get("analyzed")]
        if not analyzed:
            return
        article = analyzed[0]
        result = json_to_telegram(article)
        assert isinstance(result, str)
        assert len(result) > 0

    def test_real_article_feishu(self):
        articles = load_articles(ARTICLES_DIR)
        analyzed = [a for a in articles if a.get("analyzed")]
        if not analyzed:
            return
        article = analyzed[0]
        result = json_to_feishu(article)
        assert result["msg_type"] == "interactive"
        assert "card" in result
        json.dumps(result, ensure_ascii=False)
