FROM python:3.11-slim

WORKDIR /app

# System deps for lxml / pdfplumber
RUN apt-get update && apt-get install -y --no-install-recommends \
    gcc libxml2-dev libxslt-dev && \
    rm -rf /var/lib/apt/lists/*

COPY pyproject.toml ./
RUN pip install --no-cache-dir -e ".[api]" 2>/dev/null || \
    pip install --no-cache-dir \
        pydantic pydantic-settings sqlalchemy aiosqlite httpx \
        beautifulsoup4 lxml structlog cachetools tenacity \
        python-dotenv fastapi "uvicorn[standard]" websockets \
        python-dateutil rich

COPY . .

ENV PYTHONUNBUFFERED=1
ENV PYTHONIOENCODING=utf-8
ENV DATABASE_URL=sqlite+aiosqlite:///./careerpilot.db
ENV PORT=8000

EXPOSE $PORT

# Shell form so $PORT is expanded at runtime (Railway sets PORT automatically)
CMD uvicorn api.server:app --host 0.0.0.0 --port ${PORT:-8000}
