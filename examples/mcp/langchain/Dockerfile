# syntax=docker/dockerfile:1
FROM ghcr.io/astral-sh/uv:0.11.15 AS uv
FROM python:3.12.13-slim AS build
COPY --from=uv /uv /usr/local/bin/uv
WORKDIR /app
COPY pyproject.toml uv.lock ./
RUN --mount=type=cache,target=/root/.cache/uv uv sync --locked --no-dev --no-install-project
COPY src ./src
RUN --mount=type=cache,target=/root/.cache/uv uv sync --locked --no-dev

FROM python:3.12.13-slim AS runtime
RUN useradd --create-home --uid 10001 agent
WORKDIR /app
COPY --from=build --chown=agent:agent /app /app
USER agent
ENV PATH="/app/.venv/bin:$PATH" PYTHONNOUSERSITE=1 PYTHONUNBUFFERED=1
EXPOSE 8088
ENTRYPOINT ["python", "-m", "agent_example"]
CMD ["--host", "http", "--bind", "0.0.0.0"]
