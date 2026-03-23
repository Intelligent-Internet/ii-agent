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

# Multi-stage build to obfuscate ii_tool inside Linux environment
FROM nikolaik/python-nodejs:python3.10-nodejs24-slim AS obfuscator

# Optimization: Use pip cache mount
RUN --mount=type=cache,target=/root/.cache/pip \
  pip install pyarmor

# Copy source files and obfuscation script
WORKDIR /obfuscate
COPY src/ii_tool /obfuscate/ii_tool
COPY docker_obfuscate.py /obfuscate/obfuscate.py

# Remove .venv if it exists and run obfuscation in one layer
RUN rm -rf /obfuscate/ii_tool/.venv && \
  python obfuscate.py

# Main application stage
FROM nikolaik/python-nodejs:python3.10-nodejs24-slim

# Copy bashrc to both root (for build) and pn user (for runtime)
COPY docker/sandbox/.bashrc /root/.bashrc
COPY docker/sandbox/.bashrc /home/pn/.bashrc

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
  pandoc \
  weasyprint \
  libpq-dev \
  wget \
  gosu \
&& rm -rf /var/lib/apt/lists/*

# Optimization: Combine all curl installs and npm installs into fewer layers
RUN curl -fsSL https://code-server.dev/install.sh | sh

# Optimization: Use npm cache mount and install playwright package and system deps as root
RUN --mount=type=cache,target=/root/.npm \
  npm install -g playwright@1.55.0 @intelligent-internet/codex @ast-grep/cli @anthropic-ai/claude-code

RUN --mount=type=cache,target=/root/.npm \
  npm install -g vercel

RUN usermod -aG sudo pn
# Install browser binaries as pn user so they're accessible at runtime
USER pn
RUN curl -fsSL https://bun.sh/install | bash
RUN playwright install chromium
USER root
RUN playwright install-deps

# Set environment variables
ENV NODE_OPTIONS="--max-old-space-size=4096"


RUN mkdir -p /app/ii_agent

# Install the project into `/app`
WORKDIR /app/ii_agent

# Enable bytecode compilation
ENV UV_COMPILE_BYTECODE=1

# Copy from the cache instead of linking since it's a mounted volume
ENV UV_LINK_MODE=copy

# Copy dependency files first for better layer caching
COPY uv.lock pyproject.toml /app/ii_agent/

# Optimization: Remove redundant bind mounts (files already copied above)
# Keep cache mount for uv packages
RUN --mount=type=cache,target=/root/.cache/uv \
  uv sync --locked --prerelease=allow --no-install-project --no-dev

# Copy obfuscated ii_tool and PyArmor runtime from build stage
COPY --from=obfuscator /obfuscate/final/ii_tool /app/ii_agent/src/ii_tool
COPY --from=obfuscator /obfuscate/final/pyarmor_runtime_000000 /app/ii_agent/src/pyarmor_runtime_000000

# Optimization: Copy from cached location in codex-builder
COPY --from=codex-builder /sse-http-server /usr/local/bin/sse-http-server

COPY README.md /app/ii_agent/

# Optimization: Combine mkdir and touch into one layer
RUN mkdir -p /app/ii_agent/src/ii_agent && \
  touch /app/ii_agent/src/ii_agent/__init__.py

# Copy config files for root (build time) and pn user (runtime)
RUN mkdir -p /root/.codex /home/pn/.codex /home/pn/.claude
COPY docker/sandbox/template.css /app/template.css
COPY docker/sandbox/claude_template.json /root/.claude.json
COPY docker/sandbox/claude_template.json /home/pn/.claude.json

# COPY Template files
COPY .templates /app/ii_agent/.templates

# Optimization: Use cache mount for final uv sync
RUN --mount=type=cache,target=/root/.cache/uv \
  uv sync --locked --prerelease=allow --no-dev

  
RUN mkdir /workspace
WORKDIR /workspace

# Create a startup script to run both services
COPY docker/sandbox/start-services.sh /app/start-services.sh
COPY docker/sandbox/entrypoint.sh /app/entrypoint.sh
RUN chmod +x /app/start-services.sh /app/entrypoint.sh

# Fix ownership for pn user - give pn access to everything it needs
RUN chown -R pn:pn /home/pn /app /workspace && \
    chmod -R 755 /app && \
    chmod -R 755 /home/pn/.claude

# Set environment for pn user
ENV HOME=/home/pn
ENV PATH="/home/pn/.bun/bin:/app/ii_agent/.venv/bin:$PATH"

ENTRYPOINT ["/app/entrypoint.sh"]
CMD ["bash", "/app/start-services.sh"]
