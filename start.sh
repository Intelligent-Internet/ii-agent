#!/bin/bash
# Detect OS type and set HOST_IP appropriately

if [ -n "$COMPOSE_PROFILE" ]; then
  export USE_DOCKER_SANDBOX=$COMPOSE_PROFILE
else
  export COMPOSE_PROFILE=local
fi

echo "Using Profile " $COMPOSE_PROFILE

# Create workspace directory if it doesn't exist
if [ ! -d "${PWD}/workspace" ]; then
  mkdir ${PWD}/workspace
  echo "Created workspace directory"
fi

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
export PUBLIC_DOMAIN=${HOST_IP}.nip.io

#BACKEND ENVIRONMENT VARIABLES
export PROXY_SERVER_PORT=9000
export FRONTEND_PORT=3000
export BACKEND_PORT=8000
export WORKSPACE_PATH=${PWD}/workspace

# Start docker-compose with the HOST_IP variable
COMPOSE_PROJECT_NAME=agent docker compose -f docker/docker-compose.yaml --profile $COMPOSE_PROFILE up "$@"
