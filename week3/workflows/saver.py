"""Save processed articles to individual JSON files."""

import hashlib
import json
import logging
import re
from pathlib import Path
from typing import Any

from config import ARTICLES_DIR

logger = logging.getLogger(__name__)

# Windows 文件名非法字符
_ILLEGAL_FILENAME_RE = re.compile(r'[<>:"/\\|?*\x00-\x1f]')


def _sanitizeFilename(title: str) -> str:
    """将标题转换为安全的文件名。

    - 去除前后空白
    - 替换 Windows 非法字符为下划线
    - 合并连续空白/下划线
    - 截断至 80 字符（保留扩展名空间）
    - 空标题兜底为 'untitled'

    Args:
        title: 原始标题文本。

    Returns:
        清洗后的安全文件名（不含扩展名）。
    """
    name = title.strip()
    name = _ILLEGAL_FILENAME_RE.sub("_", name)
    name = re.sub(r"[\s_]+", "_", name)
    name = name.strip("_")

    if not name:
        name = "untitled"

    # 截断过长文件名
    if len(name) > 80:
        name = name[:80].rstrip("_")

    return name


class Saver:
    """Save processed articles to individual JSON files."""

    def __init__(self, dry_run: bool = False) -> None:
        self.dry_run = dry_run

    def _resolveFilename(
        self, item: dict[str, Any], usedNames: dict[str, str]
    ) -> str:
        """根据标题生成唯一文件名。

    同名 + 同 URL → 返回相同文件名（由调用方删除旧文件后覆盖写入）。
    同名 + 不同 URL → 追加数字后缀。
    标题为空 → 回退到 id / url 哈希。

        Args:
            item: 文章数据字典。
            usedNames: 已使用的文件名 → URL 映射。

        Returns:
            不含扩展名的唯一文件名。
        """
        title = (item.get("title") or "").strip()
        baseName = _sanitizeFilename(title) if title else ""
        url = item.get("url", "")

        # 标题为空时用 id 或 url 哈希兜底
        if not baseName or baseName == "untitled":
            articleId = item.get("id", "")
            if not articleId:
                articleId = hashlib.md5(
                    item.get("url", "").encode()
                ).hexdigest()[:12]
            baseName = articleId

        # 同名：通过 URL 判断是否为同一篇文章
        if baseName in usedNames:
            if usedNames[baseName] == url:
                # 同一篇文章，返回原名以便覆盖旧文件
                logger.info("覆盖重复文章: %s (url=%s)", baseName, url)
                return baseName
            # 同名但不同 URL，追加数字后缀
            finalName = baseName
            counter = 2
            while finalName in usedNames:
                if usedNames[finalName] == url:
                    logger.info("覆盖重复文章: %s (url=%s)", finalName, url)
                    return finalName
                finalName = f"{baseName}_{counter}"
                counter += 1
            usedNames[finalName] = url
            return finalName

        usedNames[baseName] = url
        return baseName

    def save_articles(self, items: list[dict[str, Any]]) -> list[Path]:
        """Save each article as individual JSON file."""
        savedPaths: list[Path] = []
        usedNames: dict[str, str] = {}

        for item in items:
            fileName = self._resolveFilename(item, usedNames)
            articleFile = ARTICLES_DIR / f"{fileName}.json"

            if self.dry_run:
                logger.info("[DRY-RUN] Would save article to %s", articleFile)
            else:
                # 删除旧文件后写入新内容
                if articleFile.exists():
                    articleFile.unlink()
                    logger.info("删除旧文件: %s", articleFile)
                with open(articleFile, "w", encoding="utf-8") as f:
                    json.dump(item, f, ensure_ascii=False, indent=2)
                savedPaths.append(articleFile)

        if not self.dry_run:
            logger.info("Saved %d articles to %s", len(savedPaths), ARTICLES_DIR)
        return savedPaths
