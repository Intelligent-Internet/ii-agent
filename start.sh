#!/bin/bash

setup_frontend_env() {
  # Check if frontend/.env exists, if not, prompt for Google API credentials
  if [ ! -f "frontend/.env" ]; then
    echo "Provide Google API credentials for drive authentication (optional)"
    
    echo -n "Enter your GOOGLE_API_KEY (optional): "
    read -r GOOGLE_API_KEY
    
    echo -n "Enter your GOOGLE_CLIENT_ID (optional): "
    read -r GOOGLE_CLIENT_ID
    
    echo -n "Enter your GOOGLE_CLIENT_SECRET (optional): "
    read -r GOOGLE_CLIENT_SECRET
    
    # Create the .env file in frontend directory
    cat > frontend/.env << EOF
NEXT_PUBLIC_API_URL=$BACKEND_URL
NEXT_PUBLIC_VSCODE_URL=$BASE_URL
GOOGLE_API_KEY=$GOOGLE_API_KEY
GOOGLE_CLIENT_ID=$GOOGLE_CLIENT_ID
GOOGLE_CLIENT_SECRET=$GOOGLE_CLIENT_SECRET
EOF
    
    echo "Created frontend/.env file"
  else
    echo "[✓] Host IP set to: $HOST_IP"
    echo "[✓] Backend URL: $BACKEND_URL"
    echo "[✓] Base URL: $BASE_URL"
    echo "[✓] Frontend Port: $FRONTEND_PORT"
    echo "[✓] Backend Port: $BACKEND_PORT"
    echo "[✓] Nginx Port: $NGINX_PORT"
    echo ""
    echo "Found existing frontend/.env file"
    echo "Current frontend/.env file contents:"
    echo "─────────────────────────────"
    cat frontend/.env
    echo "─────────────────────────────"
  fi

  echo "Ready to start II-Agent. add --build to the end of the command to rebuild when you change your credentials or host IP"
  echo "Check your credential and press enter to start"
  read -r
}

print_banner() {
echo -e "\033[1;34m"
echo "╔══════════════════════════════════════════════════════════════════╗"
echo "║ ██╗██╗       █████╗  ██████╗ ███████╗███╗   ██╗████████╗         ║"
echo "║ ██║██║      ██╔══██╗██╔════╝ ██╔════╝████╗  ██║╚══██╔══╝         ║"
echo "║ ██║██║█████╗███████║██║  ███╗█████╗  ██╔██╗ ██║   ██║            ║"
echo "║ ██║██║╚════╝██╔══██║██║   ██║██╔══╝  ██║╚██╗██║   ██║            ║"
echo "║ ██║██║      ██║  ██║╚██████╔╝███████╗██║ ╚████║   ██║            ║"
echo "║ ╚═╝╚═╝      ╚═╝  ╚═╝ ╚═════╝ ╚══════╝╚═╝  ╚═══╝   ╚═╝            ║"
echo "║                                                                  ║"
echo "║                          🧠 Powered by @ii.inc                   ║"
echo "╚══════════════════════════════════════════════════════════════════╝"
echo ""
echo -e "\033[0m"
}

get_host_ip() { 
if [[ "$OSTYPE" == "darwin"* ]]; then
  # macOS
  HOST_IP=$(ipconfig getifaddr en0)
elif [[ "$OSTYPE" == "linux-gnu"* ]]; then
  # Linux
  HOST_IP=$(hostname -I | awk '{print $1}')
else
  echo "Unsupported OS type: $OSTYPE"
  HOST_IP="localhost"
fi
echo "$HOST_IP"
}

main() {
  print_banner
  #Get host IP
  export HOST_IP=$(get_host_ip)
  echo "HOST_IP: $HOST_IP"
  #export HOST_IP="CUSTOM_IP"
  #Set up backend environment variables
  export FRONTEND_PORT=3000
  export BACKEND_PORT=8000
  export NGINX_PORT=8080
  export SANDBOX_PORT=17300
  export CODE_SERVER_PORT=9000
  #Change this if you have your own domain and reverse proxy
  export BACKEND_URL=http://localhost:${BACKEND_PORT}

  #Set up public domain and base URL
  export PUBLIC_DOMAIN=${HOST_IP}.nip.io
  export BASE_URL=${HOST_IP}.nip.io:${NGINX_PORT}


  #Set up frontend environment
  setup_frontend_env

  # Start docker-compose with the HOST_IP variable
  docker compose up "$@"
}

main "$@"