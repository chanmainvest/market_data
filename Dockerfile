# Backend image — uv-managed Python service.
# Mirrors the trade_history house style.
FROM ghcr.io/astral-sh/uv:python3.12-bookworm-slim

WORKDIR /app

ENV UV_LINK_MODE=copy \
    UV_COMPILE_BYTECODE=1 \
    UV_PROJECT_ENVIRONMENT=/app/.venv \
    PATH="/app/.venv/bin:$PATH"

# Install deps first (better layer caching).
COPY pyproject.toml uv.lock ./
RUN uv sync --locked --no-dev --no-install-project

# Copy the rest of the source (mdata package + scrapers).
COPY . .

# Install the project itself (registers the `mdata` console script).
RUN uv sync --locked --no-dev

EXPOSE 8000
CMD ["mdata", "serve", "--host", "0.0.0.0", "--port", "8000"]
