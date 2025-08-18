# Use Python 3.12 slim image
FROM python:3.12-slim-bookworm
RUN apt-get update && apt-get install -y tmux python3-pip
RUN pip3 install libtmux
# Install the project into `/app`
WORKDIR /app

# Install runtime dependencies
RUN apt-get update && apt-get install -y \
    curl \
    gnupg \
    lsb-release \
    ffmpeg \
    xvfb \
    git \
    && rm -rf /var/lib/apt/lists/*

# Copy project files
COPY . /app

# Create virtual environment and activate it
RUN python -m venv .venv
ENV PATH="/app/.venv/bin:$PATH"

# Upgrade pip
RUN pip install --upgrade pip

# Install the project and its dependencies using pip
RUN pip install -e .

# Install Playwright with dependencies
RUN playwright install --with-deps chromium

# Set environment variables
ENV FILE_STORE_PATH=/.ii_agent
ENV PYTHONUNBUFFERED=1

# Create file store directory
RUN mkdir -p $FILE_STORE_PATH

# Expose port for WebSocket server
EXPOSE 8000
RUN rm -rf workspace 
RUN mkdir workspace