# ============================================================
# Stage 1: base — runtime system deps, fonts, tini
# ============================================================
FROM ghcr.io/astral-sh/uv:python3.12-trixie-slim AS base

WORKDIR /app

# tini as PID 1 — proper signal handling & zombie reaping
# git + openssh-client are needed here because uv sync runs in later
# stages that inherit from base
RUN apt-get update && apt-get install -y --no-install-recommends \
    tini \
    curl \
    ffmpeg \
    libmagic1 \
    file \
    fonts-noto \
    fonts-noto-cjk \
    fonts-noto-color-emoji \
    fonts-freefont-ttf \
    openssh-client \
    git \
    nodejs \
    npm \
    ruby-full \
    ruby-dev \
    build-essential \
 && rm -rf /var/lib/apt/lists/*

# Install fastlane for iOS code signing and TestFlight submission
RUN gem install fastlane --no-document

RUN fc-cache -fv

# ============================================================
# Stage 2: dependencies — uv sync (deps only) + Playwright
# ============================================================
FROM base AS dependencies

# Enable bytecode compilation
ENV UV_COMPILE_BYTECODE=1
# Copy from the cache instead of linking since it's a mounted volume
ENV UV_LINK_MODE=copy

# Install the project's dependencies using the lockfile and settings
# SSH mount is required to access private git repositories
# ssh-keyscan adds GitHub host key so git doesn't prompt during clone
RUN --mount=type=cache,target=/root/.cache/uv \
    --mount=type=bind,source=uv.lock,target=uv.lock \
    --mount=type=bind,source=pyproject.toml,target=pyproject.toml \
    --mount=type=ssh \
    mkdir -p /root/.ssh && ssh-keyscan github.com >> /root/.ssh/known_hosts && \
    uv sync --locked --no-install-project --no-dev --extra a2a

# Install only headless shell (no full Chromium browser — saves ~600MB)
# --with-deps installs required system libraries
RUN uv run playwright install --with-deps --only-shell chromium \
 && rm -rf /var/lib/apt/lists/*

# ============================================================
# Stage 3: production — COPY source + uv sync (project) + entrypoint
# ============================================================
FROM dependencies AS production

# Copy only files needed for the backend build
COPY pyproject.toml uv.lock README.md alembic.ini ./
COPY src/ src/
COPY migrations/ migrations/
COPY scripts/start.sh scripts/
COPY docker/backend/entrypoint.sh /entrypoint.sh

# Install the project itself (source code only — deps are already cached)
RUN --mount=type=cache,target=/root/.cache/uv \
    --mount=type=ssh \
    mkdir -p /root/.ssh && ssh-keyscan github.com >> /root/.ssh/known_hosts && \
    uv sync --locked --no-dev --extra a2a

# Remove build-only tools not needed at runtime
RUN apt-get purge -y --auto-remove openssh-client git \
 && rm -rf /var/lib/apt/lists/* /root/.ssh

RUN chmod +x /entrypoint.sh /app/scripts/start.sh

# Build manifest — written by stack_control.sh at build time.
# Inspect with: docker exec <container> cat /app/build-manifest.json
# Manifest is written to <repo>/build-manifest-backend.json by
# scripts/stack_control.sh before invoking the build (file rather than
# build-arg avoids Linux ARG_MAX limits on large tracked_files lists).
ARG MANIFEST_FILE=build-manifest-backend.json
COPY ${MANIFEST_FILE} /app/build-manifest.json

# Place executables in the environment at the front of the path
ENV PATH="/app/.venv/bin:$PATH"

ENV PYTHONUNBUFFERED=1

EXPOSE 8000

ENTRYPOINT ["tini", "-s", "--", "/entrypoint.sh"]
CMD ["api"]
