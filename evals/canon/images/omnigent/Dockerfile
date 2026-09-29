FROM node:22-slim@sha256:43ac6c60b8f89723f746e8a92ce91abd5017e627ce1ddfe4238355d3a30b772c AS node
FROM ghcr.io/astral-sh/uv@sha256:100047e74f30778ab704942321a09750d6158739573ff58bf3924085cc6cd2d8 AS uv
FROM python:3.12-slim@sha256:229a2c5bfa27522db7815ea81f9bed70af17ccb9de9fc7ad142b1877b5830d36
COPY --from=uv /uv /usr/local/bin/uv
COPY --from=node /usr/local/bin/node /usr/local/bin/node
COPY --from=node /usr/local/lib/node_modules /usr/local/lib/node_modules
RUN ln -s ../lib/node_modules/npm/bin/npm-cli.js /usr/local/bin/npm \
 && ln -s ../lib/node_modules/corepack/dist/corepack.js /usr/local/bin/corepack
WORKDIR /deps
COPY manifests/ ./
ENV UV_PROJECT_ENVIRONMENT=/deps/.venv UV_PYTHON_DOWNLOADS=never UV_LINK_MODE=copy UV_NO_CACHE=1 \
    COREPACK_HOME=/opt/corepack COREPACK_ENABLE_DOWNLOAD_PROMPT=0
# Before omnigent moved its test tools to a dependency group, they were the dev extra.
RUN if grep -q '^\[dependency-groups\]' pyproject.toml; then set -- --group test; else set -- --extra dev; fi \
 && uv sync --frozen --no-install-project --no-install-workspace --no-install-local "$@"
RUN if [ -f pnpm-lock.yaml ]; then corepack pnpm install --frozen-lockfile --ignore-scripts --filter ./web; \
    else cd web && npm ci --legacy-peer-deps --ignore-scripts --no-audit --no-fund; fi \
 && rm -rf /root/.npm /root/.cache /opt/corepack
ENV PATH=/deps/.venv/bin:$PATH
