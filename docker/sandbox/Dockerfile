FROM nikolaik/python-nodejs:python3.10-nodejs20-slim

# Set environment variables
ENV NODE_OPTIONS="--max-old-space-size=4096"

RUN apt-get update && apt-get install -y \
    build-essential \
    procps \
    lsof \
    git \
    tmux \
    bc \
    net-tools

#RUN echo 'export PS1="[CMD_BEGIN]\\n\\u@\\h:\\w\\n[CMD_END]"; export PS2=""' >> /root/.bashrc

COPY src/ii_agent/utils/tool_client /app/ii_client

WORKDIR /app

RUN pip install -r ii_client/requirements.txt

RUN npm install -g pnpm vercel

RUN curl -fsSL https://code-server.dev/install.sh | sh

COPY .templates /app/templates

# Create a startup script to run both services
COPY docker/sandbox/start-services.sh /app/start-services.sh
RUN chmod +x /app/start-services.sh

CMD ["/app/start-services.sh"]
