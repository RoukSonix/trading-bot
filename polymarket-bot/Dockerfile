# =============================================================================
# Polymarket Bot - Dockerfile (Monorepo)
# =============================================================================
# Build context: monorepo root (trading-bots/)
# =============================================================================

FROM python:3.12-slim AS base

WORKDIR /app

RUN apt-get update && apt-get install -y --no-install-recommends \
    gcc \
    libffi-dev \
    curl \
    && rm -rf /var/lib/apt/lists/* \
    && apt-get clean

RUN useradd --create-home --shell /bin/bash appuser

COPY polymarket-bot/pyproject.toml ./polymarket-bot/
RUN cd polymarket-bot && pip install --no-cache-dir --upgrade pip \
    && pip install --no-cache-dir -e .

# Copy shared modules
COPY --chown=appuser:appuser shared/ ./shared/

# Copy polymarket-bot source
COPY --chown=appuser:appuser polymarket-bot/src/ ./polymarket-bot/src/

RUN mkdir -p /app/polymarket-bot/data /app/polymarket-bot/logs \
    && chown -R appuser:appuser /app/polymarket-bot/data /app/polymarket-bot/logs

ENV PYTHONPATH=/app:/app/polymarket-bot/src
ENV PYTHONUNBUFFERED=1

USER appuser
WORKDIR /app/polymarket-bot

CMD ["echo", "Polymarket bot not yet implemented"]
