# ===========================================
# Document Intelligence API - Production Dockerfile
# Optimized for Google Cloud Run Deployment with UV
# ===========================================

# Use Python 3.12 slim image for optimal security and size
FROM python:3.12-slim

# Set environment variables for Python and UV
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PYTHONPATH=/app \
    PORT=8080 \
    UV_COMPILE_BYTECODE=1 \
    UV_LINK_MODE=copy

# Install system dependencies and UV
RUN apt-get update && apt-get install -y \
    --no-install-recommends \
    gcc \
    g++ \
    build-essential \
    curl \
    && rm -rf /var/lib/apt/lists/* \
    && apt-get clean

# Install uv
COPY --from=ghcr.io/astral-sh/uv:latest /uv /bin/uv

# Create non-root user for security
RUN groupadd -r appuser && useradd -r -g appuser appuser

# Set working directory
WORKDIR /app

# Copy dependency files first for better Docker layer caching
COPY pyproject.toml uv.lock ./

# Install Python dependencies with UV (much faster than pip)
RUN uv sync --frozen --no-cache --no-dev

# Copy application code
COPY app/ ./app/

# Copy additional scripts that might be needed
COPY setup_gcp_bucket.py ./

# Create necessary directories and set permissions
RUN mkdir -p /app/logs /app/tmp /home/appuser/.cache \
    && chown -R appuser:appuser /app /home/appuser \
    && chmod -R 755 /app /home/appuser

# Switch to non-root user
USER appuser

# Expose port (Cloud Run will set PORT environment variable)
EXPOSE 8080

# Health check for Cloud Run
HEALTHCHECK --interval=30s --timeout=10s --start-period=5s --retries=3 \
    CMD curl -f http://localhost:${PORT}/health || exit 1

# Production startup command with UV
# Cloud Run provides PORT environment variable
CMD exec uv run uvicorn app.main:app \
    --host 0.0.0.0 \
    --port ${PORT} \
    --workers 1 \
    --access-log \
    --no-use-colors