# =============================================================================
# Binance Trading Bot - Multi-stage Dockerfile (Monorepo)
# =============================================================================
# Supports: API (FastAPI), Dashboard (Streamlit), Bot (Trading Engine)
# Build context: monorepo root (trading-bots/)
# =============================================================================

# -----------------------------------------------------------------------------
# Stage 1: Base image with dependencies
# -----------------------------------------------------------------------------
FROM python:3.12-slim AS base

WORKDIR /app

# Install system dependencies
RUN apt-get update && apt-get install -y --no-install-recommends \
    gcc \
    libffi-dev \
    curl \
    && rm -rf /var/lib/apt/lists/* \
    && apt-get clean

# Create non-root user for security
RUN useradd --create-home --shell /bin/bash appuser

# Copy and install Python dependencies
COPY binance-bot/requirements.txt ./
RUN pip install --no-cache-dir --upgrade pip \
    && pip install --no-cache-dir -r requirements.txt

# -----------------------------------------------------------------------------
# Stage 2: Production image
# -----------------------------------------------------------------------------
FROM base AS production

WORKDIR /app

# Copy shared modules
COPY --chown=appuser:appuser shared/ ./shared/

# Copy binance-bot source code
COPY --chown=appuser:appuser binance-bot/pyproject.toml binance-bot/README.md ./binance-bot/
COPY --chown=appuser:appuser binance-bot/src/ ./binance-bot/src/
COPY --chown=appuser:appuser binance-bot/scripts/ ./binance-bot/scripts/

# Install the package
RUN cd binance-bot && pip install --no-cache-dir -e .

# Create data and logs directories
RUN mkdir -p /app/binance-bot/data /app/binance-bot/logs \
    && chown -R appuser:appuser /app/binance-bot/data /app/binance-bot/logs

# Environment variables - PYTHONPATH includes monorepo root and binance-bot src
ENV PYTHONPATH=/app:/app/binance-bot/src
ENV PYTHONUNBUFFERED=1
ENV LOG_LEVEL=INFO

# Expose ports
EXPOSE 8000 8501

# Switch to non-root user
USER appuser

WORKDIR /app/binance-bot

# Default: run dashboard (both API + Streamlit)
CMD ["python", "scripts/run_dashboard.py"]

# -----------------------------------------------------------------------------
# Stage 3: API service
# -----------------------------------------------------------------------------
FROM production AS api

EXPOSE 8000

CMD ["python", "-m", "uvicorn", "shared.api.main:app", \
     "--host", "0.0.0.0", "--port", "8000"]

# -----------------------------------------------------------------------------
# Stage 4: Dashboard (Streamlit)
# -----------------------------------------------------------------------------
FROM production AS dashboard

EXPOSE 8501

CMD ["python", "-m", "streamlit", "run", \
     "/app/shared/dashboard/app.py", \
     "--server.port", "8501", \
     "--server.address", "0.0.0.0", \
     "--server.headless", "true", \
     "--browser.gatherUsageStats", "false"]

# -----------------------------------------------------------------------------
# Stage 5: Trading bot
# -----------------------------------------------------------------------------
FROM production AS bot

CMD ["python", "scripts/run_paper_trading.py"]
