#!/bin/bash
if [[ "$OSTYPE" == "darwin"* ]]; then
  # macOS
  export HOST_IP=$(ipconfig getifaddr en0)
elif [[ "$OSTYPE" == "linux-gnu"* ]]; then
  # Linux
  export HOST_IP=$(hostname -I | awk '{print $1}')
else
  echo "Unsupported OS type: $OSTYPE"
  export HOST_IP="localhost"
fi

#DEPLOYMENT DOMAIN, CHANGE THIS IF YOU SET UP YOUR OWN DOMAIN AND REVERSE PROXY
echo "Using HOST_IP: $HOST_IP"

#BACKEND ENVIRONMENT VARIABLES
export FRONTEND_PORT=3000
export BACKEND_PORT=8000
export NGINX_PORT=8080
export SANDBOX_PORT=17300
export CODE_SERVER_PORT=9000
export EXTERNAL_PORT=8080

export WORKSPACE_PATH=${PWD}/workspace
export PUBLIC_DOMAIN=${HOST_IP}.nip.io
export BASE_URL=${HOST_IP}.nip.io:${NGINX_PORT}

# Start docker-compose with the HOST_IP variable
docker compose up "$@"
