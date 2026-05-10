# ============================================================
# AI 知识库 V4 — 生产 Docker 镜像
# ============================================================
# 多阶段构建：构建层安装依赖，运行层只拷贝必要文件
# ============================================================

FROM python:3.12-slim AS builder

WORKDIR /build

RUN apt-get update && \
    apt-get install -y --no-install-recommends gcc && \
    rm -rf /var/lib/apt/lists/*

COPY requirements.txt .
RUN pip install --no-cache-dir --prefix=/install -r requirements.txt

# ============================================================
# 运行层
# ============================================================
FROM python:3.12-slim

LABEL maintainer="AI Knowledge Base Team"
LABEL version="4.0"
LABEL description="AI 知识库 V4 产品版 — 采集、分析、分发、交互"

WORKDIR /app

COPY --from=builder /install /usr/local

COPY workflows/ ./workflows/
COPY patterns/ ./patterns/
COPY pipeline/ ./pipeline/
COPY distribution/ ./distribution/
COPY bot/ ./bot/
COPY openclaw/ ./openclaw/
COPY hooks/ ./hooks/
COPY mcp/ ./mcp/
COPY tests/ ./tests/
COPY AGENTS.md .

RUN mkdir -p /app/knowledge/raw /app/knowledge/articles /app/data

RUN groupadd -r appuser && useradd -r -g appuser appuser && \
    chown -R appuser:appuser /app
USER appuser

HEALTHCHECK --interval=60s --timeout=10s --start-period=30s --retries=3 \
    CMD python -c "import sys; sys.exit(0)"
