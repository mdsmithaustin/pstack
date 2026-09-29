FROM ghcr.io/astral-sh/uv@sha256:100047e74f30778ab704942321a09750d6158739573ff58bf3924085cc6cd2d8 AS uv
FROM python:3.14-slim@sha256:51dafde81dbdb6ebde285137a295cf18a47ca95234fe388a343719cb97305b3d
COPY --from=uv /uv /usr/local/bin/uv
WORKDIR /deps
COPY manifests/ ./
ENV UV_PROJECT_ENVIRONMENT=/deps/.venv UV_PYTHON_DOWNLOADS=never UV_LINK_MODE=copy UV_NO_CACHE=1
RUN uv sync --frozen --no-install-project --no-install-workspace --no-install-local --group dev
ENV PATH=/deps/.venv/bin:$PATH
