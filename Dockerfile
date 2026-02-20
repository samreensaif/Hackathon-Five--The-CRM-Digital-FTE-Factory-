# Customer Success Digital FTE — Dockerfile (Render.com Edition)
# =================================================================
# Python 3.11 slim image with PostgreSQL client libraries.
# Used for both the API service and the worker service via CMD override.
#
# Build:
#   docker build -t fte-render .
#
# Run API:
#   docker run -e DATABASE_URL=... fte-render
#
# Run Worker:
#   docker run -e DATABASE_URL=... fte-render python -m workers.message_processor

FROM python:3.11-slim

# Build args / labels
LABEL maintainer="TechCorp Engineering"
LABEL description="Customer Success Digital FTE — Render.com Edition"

# Prevents Python from writing .pyc files and enables unbuffered output
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

# Install system dependencies required by asyncpg and other native libs
RUN apt-get update && apt-get install -y --no-install-recommends \
        gcc \
        libpq-dev \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# Install Python dependencies first (layer-cached unless requirements.txt changes)
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy application source from the 4-Render-Deploy/ subdirectory
COPY 4-Render-Deploy/ /app/

# Expose the API port
EXPOSE 8000

# Health check (Render also polls /health via render.yaml healthCheckPath)
HEALTHCHECK --interval=30s --timeout=10s --start-period=20s --retries=3 \
    CMD python -c "import urllib.request; urllib.request.urlopen('http://localhost:8000/health')"

# Default command: run the FastAPI server
# Override with: python -m workers.message_processor  (for the worker service)
CMD ["uvicorn", "api.main:app", "--host", "0.0.0.0", "--port", "8000"]
