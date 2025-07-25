FROM nikolaik/python-nodejs:python3.10-nodejs20-slim

# Set environment variables
ENV NODE_OPTIONS="--max-old-space-size=4096"

RUN mkdir -p /app/ii_agent

# Install the project into `/app`
WORKDIR /app/ii_agent

# Enable bytecode compilation
ENV UV_COMPILE_BYTECODE=1

# Copy from the cache instead of linking since it's a mounted volume
ENV UV_LINK_MODE=copy

RUN apt-get update && apt-get install -y \
    build-essential \
    procps \
    lsof \
    git \
    tmux \
    bc \
    net-tools \
    unzip


# Copy dependency files first for better layer caching
COPY uv.lock pyproject.toml /app/ii_agent/

# Install the project's dependencies using the lockfile and settings
RUN --mount=type=cache,target=/root/.cache/uv \
    --mount=type=bind,source=uv.lock,target=uv.lock \
    --mount=type=bind,source=pyproject.toml,target=pyproject.toml \
    uv sync --locked --prerelease=allow --no-install-project --no-dev

COPY . /app/ii_agent
RUN --mount=type=cache,target=/root/.cache/uv \
    uv sync --locked --prerelease=allow --no-dev

ENV PATH="/app/ii_agent/.venv/bin:$PATH"

RUN curl -fsSL https://bun.sh/install | bash
RUN curl -fsSL https://code-server.dev/install.sh | sh

RUN npm install -g vercel

RUN mkdir /workspace

WORKDIR /workspace

# Create a startup script to run both services
COPY docker/sandbox/start-services.sh /app/start-services.sh
RUN chmod +x /app/start-services.sh

CMD ["/app/start-services.sh"]
