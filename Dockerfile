FROM python:3.12-slim AS base

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

WORKDIR /app

COPY --from=ghcr.io/astral-sh/uv:latest /uv /usr/local/bin/uv

FROM base AS deps

COPY pyproject.toml uv.lock ./
RUN uv sync --frozen --no-dev --no-install-project

FROM base AS runtime

COPY --from=deps /app/.venv /app/.venv
ENV PATH="/app/.venv/bin:$PATH" \
    PYTHONPATH="/app/src"

COPY src/ ./src/

EXPOSE 8000

CMD ["uvicorn", "maas.main:app", "--host", "0.0.0.0", "--port", "8000"]
