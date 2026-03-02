# =============================================================================
# Trading Bot - Multi-stage Dockerfile
# =============================================================================
# Supports: API (FastAPI), Dashboard (Streamlit), Bot (Trading Engine)
# =============================================================================

# -----------------------------------------------------------------------------
# Stage 1: Base image with dependencies
# -----------------------------------------------------------------------------
FROM python:3.14-slim AS base

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
COPY requirements.txt ./
RUN pip install --no-cache-dir --upgrade pip \
    && pip install --no-cache-dir -r requirements.txt

# -----------------------------------------------------------------------------
# Stage 2: Production image
# -----------------------------------------------------------------------------
FROM base AS production

WORKDIR /app

# Copy source code
COPY --chown=appuser:appuser pyproject.toml ./
COPY --chown=appuser:appuser src/ ./src/
COPY --chown=appuser:appuser scripts/ ./scripts/

# Install the package in editable mode
RUN pip install --no-cache-dir -e .

# Create data and logs directories
RUN mkdir -p /app/data /app/logs \
    && chown -R appuser:appuser /app/data /app/logs

# Environment variables
ENV PYTHONPATH=/app/src
ENV PYTHONUNBUFFERED=1
ENV LOG_LEVEL=INFO

# Expose ports
EXPOSE 8000 8501

# Switch to non-root user
USER appuser

# Default: run dashboard (both API + Streamlit)
CMD ["python", "scripts/run_dashboard.py"]

# -----------------------------------------------------------------------------
# Stage 3: API service
# -----------------------------------------------------------------------------
FROM production AS api

EXPOSE 8000

CMD ["python", "-m", "uvicorn", "trading_bot.api.main:app", \
     "--host", "0.0.0.0", "--port", "8000"]

# -----------------------------------------------------------------------------
# Stage 4: Dashboard (Streamlit)
# -----------------------------------------------------------------------------
FROM production AS dashboard

EXPOSE 8501

CMD ["python", "-m", "streamlit", "run", \
     "src/trading_bot/dashboard/app.py", \
     "--server.port", "8501", \
     "--server.address", "0.0.0.0", \
     "--server.headless", "true", \
     "--browser.gatherUsageStats", "false"]

# -----------------------------------------------------------------------------
# Stage 5: Trading bot
# -----------------------------------------------------------------------------
FROM production AS bot

CMD ["python", "-m", "trading_bot.main"]
