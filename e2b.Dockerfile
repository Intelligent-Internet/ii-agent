FROM nikolaik/python-nodejs:python3.10-nodejs20-slim

WORKDIR /app

RUN apt-get update && apt-get install -y \
    build-essential \
    procps \
    lsof \
    git \
    tmux \
    bc \
    net-tools \
    unzip

COPY src/ii_agent/utils/tool_client /app/ii_client

RUN pip install -r ii_client/requirements.txt

RUN curl -fsSL https://bun.sh/install | bash
RUN curl -fsSL https://code-server.dev/install.sh | sh

RUN npm install -g vercel

COPY .templates /app/templates

RUN mkdir -p /workspace

# Create a startup script to run both services
COPY docker/sandbox/start-services.sh /app/start-services.sh
RUN chmod +x /app/start-services.sh

CMD ["cd /app && ./start-services.sh"]
