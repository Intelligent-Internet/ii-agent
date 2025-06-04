FROM nikolaik/python-nodejs:python3.10-nodejs20-slim

RUN apt-get update && apt-get install -y \
    build-essential \
    procps \
    lsof \
    git \
    net-tools

RUN echo 'export PS1="[CMD_BEGIN]\\n\\u@\\h:\\w\\n[CMD_END]"; export PS2=""' >> /root/.bashrc