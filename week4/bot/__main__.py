"""bot/__main__.py — 知识库机器人 CLI 入口

提供两种运行模式:
  python -m bot              → 交互式命令行 REPL (开发调试用)
  python -m bot --serve      → 启动轻量 HTTP 健康检查服务 (Docker 容器用)
"""

import argparse
import json
import logging
import os
import sys
from http.server import HTTPServer, BaseHTTPRequestHandler
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from dotenv import load_dotenv

load_dotenv()

logger = logging.getLogger(__name__)


def run_repl() -> None:
    """交互式命令行 REPL — 直接与 KnowledgeBot 对话。"""
    from bot.knowledge_bot import KnowledgeBot

    bot = KnowledgeBot()
    print("=" * 50)
    print("  AI 知识库机器人 — REPL 模式")
    print("  输入 /help 查看命令，输入 quit 退出")
    print("=" * 50)

    user_id = os.getenv("REPL_USER_ID", "repl_user")
    while True:
        try:
            text = input("\n>>> ").strip()
            if text.lower() in ("quit", "exit", "q"):
                break
            if not text:
                continue
            response = bot.handle_message(user_id, text)
            print(response)
        except KeyboardInterrupt:
            print("\n退出")
            break
        except Exception as e:
            print(f"错误: {e}")


class HealthHandler(BaseHTTPRequestHandler):
    """健康检查 HTTP Handler。"""

    def do_GET(self) -> None:
        if self.path == "/health":
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.end_headers()
            self.wfile.write(json.dumps({"status": "ok", "service": "kb-bot"}).encode())
        else:
            self.send_response(404)
            self.end_headers()

    def log_message(self, format, *args):
        logger.info(f"HTTP {format % args}")


def run_server(port: int = 8080) -> None:
    """启动轻量 HTTP 服务（健康检查 + 知识库 API）。

    Args:
        port: 监听端口
    """
    server = HTTPServer(("0.0.0.0", port), HealthHandler)
    logger.info(f"Bot HTTP 服务启动于 0.0.0.0:{port}")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        logger.info("服务关闭")
        server.server_close()


if __name__ == "__main__":
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(levelname)s] %(message)s",
    )

    parser = argparse.ArgumentParser(description="AI 知识库机器人入口")
    parser.add_argument("--serve", action="store_true", help="启动 HTTP 服务模式")
    parser.add_argument("--port", type=int, default=8080, help="HTTP 服务端口")
    args = parser.parse_args()

    if args.serve:
        run_server(port=args.port)
    else:
        run_repl()
