# Build ii-app CLI
FROM rust:1.86-slim AS ii-app-builder

RUN --mount=type=cache,target=/var/cache/apt,sharing=locked \
  --mount=type=cache,target=/var/lib/apt,sharing=locked \
  apt-get update && apt-get install -y \
  pkg-config \
  libssl-dev

WORKDIR /build/ii-app-cli
COPY src/ii_agent/settings/skills/builtin/ii-app/scripts/ii-app-cli/ .

RUN --mount=type=cache,target=/usr/local/cargo/registry \
  --mount=type=cache,target=/build/ii-app-cli/target \
  cargo build --release && \
  cp /build/ii-app-cli/target/release/ii-app /ii-app

# Build Codex SSE HTTP server
FROM rust:1.75-slim AS codex-builder

# Optimization: Use cache mount for apt-get to speed up repeated builds
RUN --mount=type=cache,target=/var/cache/apt,sharing=locked \
  --mount=type=cache,target=/var/lib/apt,sharing=locked \
  apt-get update && apt-get install -y \
  git \
  ca-certificates \
  pkg-config \
  libssl-dev

WORKDIR /build
RUN git clone --branch v0.0.1 https://github.com/Intelligent-Internet/codex.git
WORKDIR /build/codex/codex-rs

# Optimization: Use cargo cache mount to avoid re-downloading dependencies
RUN --mount=type=cache,target=/usr/local/cargo/registry \
  --mount=type=cache,target=/build/codex/codex-rs/target \
  cargo build --release --bin sse-http-server && \
  cp /build/codex/codex-rs/target/release/sse-http-server /sse-http-server

FROM nikolaik/python-nodejs:python3.10-nodejs24-slim

COPY docker/sandbox/.bashrc /root/.bashrc
COPY docker/sandbox/.bashrc /home/user/.bashrc

# Optimization: Use cache mounts for apt-get and combine into single layer
RUN --mount=type=cache,target=/var/cache/apt,sharing=locked \
  --mount=type=cache,target=/var/lib/apt,sharing=locked \
  apt-get update && apt-get install -y \
  build-essential \
  procps \
  lsof \
  git \
  tmux \
  bc \
  net-tools \
  ripgrep \
  unzip \
  libmagic1 \
  xvfb \
  x11vnc \
  novnc \
  websockify \
  fluxbox \
  pandoc \
  weasyprint \
  libpq-dev \
  wget \
  gosu \
  jq \
  libnspr4 \
  libnss3 \
  libatk1.0-0 \
  libatk-bridge2.0-0 \
  libcups2 \
  libdrm2 \
  libxkbcommon0 \
  libxcomposite1 \
  libxdamage1 \
  libxfixes3 \
  libxrandr2 \
  libgbm1 \
  libasound2 \
  libcairo2 \  
&& rm -rf /var/lib/apt/lists/*

# Optimization: Combine all curl installs and npm installs into fewer layers
RUN curl -fsSL https://code-server.dev/install.sh | sh

# GitHub CLI (gh) — required by the Copilot A2A backend (`gh copilot agent`)
RUN --mount=type=cache,target=/var/cache/apt,sharing=locked \
  --mount=type=cache,target=/var/lib/apt,sharing=locked \
  curl -fsSL https://cli.github.com/packages/githubcli-archive-keyring.gpg \
    -o /usr/share/keyrings/githubcli-archive-keyring.gpg && \
  echo "deb [arch=$(dpkg --print-architecture) signed-by=/usr/share/keyrings/githubcli-archive-keyring.gpg] https://cli.github.com/packages stable main" \
    > /etc/apt/sources.list.d/github-cli.list && \
  apt-get update && apt-get install -y gh && \
  rm -rf /var/lib/apt/lists/*

# Optimization: Use npm cache mount and install playwright package and system deps as root
RUN --mount=type=cache,target=/root/.npm \
  npm install -g agent-browser @intelligent-internet/codex @ast-grep/cli @anthropic-ai/claude-code

RUN --mount=type=cache,target=/root/.npm \
  npm install -g vercel

RUN --mount=type=cache,target=/root/.npm \
  npm install -g eas-cli

RUN --mount=type=cache,target=/root/.npm \
  npm install -g testflight

# Create user if it doesn't exist (base image uses 'pn' user with UID/GID 1000)
RUN if ! id -u user > /dev/null 2>&1; then \
      useradd -d /home/user -m -s /bin/bash user; \
    fi

RUN usermod -aG sudo user
# Fix ownership for user - give user access to everything it needs
RUN chown -R user:user /home/user 
# Install browser binaries as pn user so they're accessible at runtime
USER user
RUN curl -fsSL https://bun.sh/install | bash
RUN agent-browser install --with-deps
USER root
RUN agent-browser install --with-deps

ARG TYPST_VERSION=0.12.0
RUN cd /tmp && \
    wget -O typst.tar.xz https://github.com/typst/typst/releases/download/v${TYPST_VERSION}/typst-x86_64-unknown-linux-musl.tar.xz && \
    tar -xJf typst.tar.xz && \
    mv typst-x86_64-unknown-linux-musl/typst /usr/local/bin/typst && \
    chmod +x /usr/local/bin/typst && \
    typst --version
    
# Set environment variables
ENV NODE_OPTIONS="--max-old-space-size=4096"


RUN mkdir -p /app/ii_sandbox

# Install the project into `/app`
WORKDIR /app/ii_sandbox

# Enable bytecode compilation
ENV UV_COMPILE_BYTECODE=1

# Copy from the cache instead of linking since it's a mounted volume
ENV UV_LINK_MODE=copy

# Copy lightweight sandbox pyproject (ii_server + ii_agent_tools only)
COPY docker/sandbox/pyproject.toml /app/ii_sandbox/

# Install dependencies
RUN --mount=type=cache,target=/root/.cache/uv \
  uv sync --no-install-project

# Copy application source
COPY src/ii_server /app/ii_sandbox/src/ii_server
COPY src/ii_agent_tools /app/ii_sandbox/src/ii_agent_tools

# Copy the A2A adapter subtree + minimal parent __init__.py files so
# `python -m ii_agent.integrations.a2a.adapter_server` resolves inside the sandbox.
COPY src/ii_agent/__init__.py /app/ii_sandbox/src/ii_agent/__init__.py
COPY src/ii_agent/integrations/__init__.py /app/ii_sandbox/src/ii_agent/integrations/__init__.py
COPY src/ii_agent/integrations/a2a /app/ii_sandbox/src/ii_agent/integrations/a2a

# Optimization: Copy from cached location in codex-builder
COPY --from=codex-builder /sse-http-server /usr/local/bin/sse-http-server

# Copy ii-app CLI binary and assets
COPY --from=ii-app-builder /ii-app /usr/local/bin/ii-app
COPY src/ii_agent/settings/skills/builtin/ii-app/assets /usr/local/share/ii-app/assets
ENV II_APP_SKILL_ROOT=/usr/local/share/ii-app

# Optimization: Combine mkdir and touch into one layer
RUN touch /app/.user_env /app/.user_env.sh

# Copy config files for root (build time) and user (runtime)
RUN mkdir -p /root/.codex /home/user/.codex /home/user/.claude
COPY docker/sandbox/template.css /app/template.css
COPY docker/sandbox/claude_template.json /root/.claude.json
COPY docker/sandbox/claude_template.json /home/user/.claude.json

# Install the project itself
RUN --mount=type=cache,target=/root/.cache/uv \
  uv sync

  
RUN mkdir /workspace
WORKDIR /workspace

# Create a startup script to run both services
COPY docker/sandbox/start-services.sh /app/start-services.sh
COPY docker/sandbox/entrypoint.sh /app/entrypoint.sh
RUN chmod +x /app/start-services.sh /app/entrypoint.sh

# Fix ownership for user - give user access to everything it needs
RUN chown -R user:user /home/user /app /workspace && \
    chmod -R 755 /app && \
    chmod -R 755 /home/user/.claude

# Set environment for user
ENV HOME=/home/user
ENV PATH="/home/user/.bun/bin:/app/ii_sandbox/.venv/bin:$PATH"

USER user

# Install Playwright browser binaries and create system symlinks
RUN playwright install chromium
USER root
RUN CHROME_BIN=$(find /home/user/.cache/ms-playwright -name chrome -path '*/chrome-linux/*' | head -1) && \
    ln -sf "$CHROME_BIN" /usr/local/bin/chromium-browser && \
    ln -sf "$CHROME_BIN" /usr/local/bin/chromium && \
    ln -sf "$CHROME_BIN" /usr/local/bin/google-chrome
USER user

WORKDIR /home/user

# A2A adapter port — served by ii_agent.integrations.a2a.adapter_server
# (launched by start-services.sh; default 18100 is in the control-plane range 18000-18999)
ENV SANDBOX_ADAPTER_PORT=18100
EXPOSE 18100

# Build manifest — written by stack_control.sh at build time.
# Inspect with: docker exec <container> cat /app/build-manifest.json
ARG BUILD_MANIFEST='{}'
RUN printf '%s\n' "$BUILD_MANIFEST" > /app/build-manifest.json

ENTRYPOINT ["/app/entrypoint.sh"]
CMD ["bash", "/app/start-services.sh"]
