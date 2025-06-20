# Backend Dockerfile
FROM python:3.10-slim AS builder

# Install build dependencies
RUN apt-get update && apt-get install -y \
    build-essential \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# Copy only the files needed for installation
COPY pyproject.toml .
COPY README.md .
COPY src/ii_agent/ ./src/ii_agent/

# Install dependencies into a virtual environment
RUN python -m venv /venv
ENV PATH="/venv/bin:$PATH"
RUN pip install --no-cache-dir --upgrade pip \
    && pip install --no-cache-dir .

FROM python:3.10-slim

WORKDIR /app

# Install runtime dependencies only
RUN apt-get update && apt-get install -y \
    curl \
    gnupg \
    lsb-release \
    ffmpeg \
    xvfb \
    && curl -fsSL https://download.docker.com/linux/debian/gpg | gpg --dearmor -o /usr/share/keyrings/docker-archive-keyring.gpg \
    && echo "deb [arch=$(dpkg --print-architecture) signed-by=/usr/share/keyrings/docker-archive-keyring.gpg] https://download.docker.com/linux/debian $(lsb_release -cs) stable" > /etc/apt/sources.list.d/docker.list \
    && apt-get update \
    && apt-get install -y docker-ce-cli \
    && rm -rf /var/lib/apt/lists/*

# Copy virtual environment from builder stage
COPY --from=builder /venv /venv
ENV PATH="/venv/bin:$PATH"

# Copy application code
COPY . .

# Create workspace directory
RUN mkdir -p workspace

# Install Playwright in a single layer
RUN playwright install --with-deps chromium

# Set environment variables
ENV PYTHONUNBUFFERED=1
ENV FILE_STORE=local
ENV FILE_STORE_PATH=/.ii_agent_file_store

RUN mkdir -p $FILE_STORE_PATH

COPY docker/backend/run.sh /app/run.sh
RUN chmod +x /app/run.sh

# Expose port for WebSocket server
EXPOSE 8000

ENTRYPOINT ["/app/run.sh"]