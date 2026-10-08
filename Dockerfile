FROM python:3.12-slim

COPY --from=ghcr.io/astral-sh/uv:0.8 /uv /bin/uv
ENV UV_COMPILE_BYTECODE=1 UV_LINK_MODE=copy PYTHONUNBUFFERED=1

WORKDIR /srv
COPY pyproject.toml uv.lock ./
RUN uv sync --frozen --no-dev --no-install-project
COPY README.md ./
COPY app ./app
RUN uv sync --frozen --no-dev

RUN useradd --create-home appuser
USER appuser
EXPOSE 8000
# Hosting platforms pass the port in $PORT; proxy headers keep https:// URLs and secure cookies right.
CMD ["sh", "-c", "exec /srv/.venv/bin/uvicorn --factory app.main:create_app --host 0.0.0.0 --port ${PORT:-8000} --proxy-headers --forwarded-allow-ips='*'"]
