# Use a Python image with uv pre-installed
FROM ghcr.io/astral-sh/uv:python3.12-trixie-slim

# Install the project into `/app`
WORKDIR /app

# Enable bytecode compilation
ENV UV_COMPILE_BYTECODE=1

# Copy from the cache instead of linking since it's a mounted volume
ENV UV_LINK_MODE=copy

# Install runtime dependencies
RUN apt-get update && apt-get install -y \
    curl \
    gnupg \
    lsb-release \
    ffmpeg \
    xvfb \
    libmagic1 \
    file \
    fonts-noto \
    fonts-noto-cjk \
    fonts-noto-color-emoji \
    fonts-freefont-ttf \
 && rm -rf /var/lib/apt/lists/*

RUN fc-cache -fv
# Install the project's dependencies using the lockfile and settings
RUN --mount=type=cache,target=/root/.cache/uv \
    --mount=type=bind,source=uv.lock,target=uv.lock \
    --mount=type=bind,source=pyproject.toml,target=pyproject.toml \
    uv sync --locked --prerelease=allow --no-install-project --no-dev

# Install Playwright in a single layer
RUN uv run playwright install --with-deps chromium

# Then, add the rest of the project source code and install it
# Installing separately from its dependencies allows optimal layer caching
COPY . /app
RUN --mount=type=cache,target=/root/.cache/uv \
    uv sync --locked --prerelease=allow --no-dev

RUN chmod +x /app/start.sh
RUN chmod +x /app/scripts/run_sandbox_timeout_extension.sh

# Place executables in the environment at the front of the path
ENV PATH="/app/.venv/bin:$PATH"

ENV FILE_STORE_PATH=/.ii_agent

# Set environment variables
ENV PYTHONUNBUFFERED=1

RUN mkdir -p $FILE_STORE_PATH

# Expose port for WebSocket server
EXPOSE 8000


ENTRYPOINT ["/app/start.sh"]

CMD []
