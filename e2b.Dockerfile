FROM nikolaik/python-nodejs:python3.10-nodejs20-slim

WORKDIR /app

RUN apt-get update && apt-get install -y \
    build-essential \
    procps \
    lsof \
    git \
    net-tools

COPY src/ii_agent/utils/tool_client /app/ii_client
COPY templates /app/templates

RUN pip install -r ii_client/requirements.txt

RUN mkdir -p /workspace

CMD ["python", "-m", "ii_client.sandbox_server", "--port", "17300" , "--cwd", "/workspace"]
