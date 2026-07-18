# Next Core application image — multi-stage, uv-managed, non-root.
FROM ghcr.io/astral-sh/uv:python3.13-bookworm-slim AS builder
ENV UV_COMPILE_BYTECODE=1 UV_LINK_MODE=copy UV_PYTHON_DOWNLOADS=never
WORKDIR /app
COPY pyproject.toml uv.lock ./
RUN uv sync --frozen --no-install-project --no-dev
COPY src ./src
COPY manage.py README.md ./
RUN uv sync --frozen --no-dev

FROM python:3.13-slim-bookworm AS runtime
RUN groupadd -r nextcore && useradd -r -g nextcore -d /app nextcore
WORKDIR /app
COPY --from=builder --chown=nextcore:nextcore /app /app
ENV PATH="/app/.venv/bin:$PATH" PYTHONUNBUFFERED=1
USER nextcore
EXPOSE 8000
HEALTHCHECK --interval=15s --timeout=5s --retries=5 CMD \
  python -c "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8000/health/live', timeout=4)"
CMD ["gunicorn", "next_core.wsgi:application", "--bind", "0.0.0.0:8000", "--workers", "2", "--access-logfile", "-"]
