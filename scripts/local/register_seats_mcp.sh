#!/bin/bash
# Register SEATS MCP server with ii-agent

# Configuration
API_URL="http://localhost:8000"
MCP_SERVER_URL="http://host.docker.internal:4000/mcp"

echo "=== Registering SEATS MCP Server ==="
echo "API URL: $API_URL"
echo "MCP Server URL: $MCP_SERVER_URL"
echo

# Step 1: Dev login to get access token
echo "Step 1: Logging in with dev credentials..."
LOGIN_RESPONSE=$(curl -s -X GET "$API_URL/auth/dev/login")
ACCESS_TOKEN=$(echo "$LOGIN_RESPONSE" | grep -o '"access_token":"[^"]*"' | cut -d'"' -f4)

if [ -z "$ACCESS_TOKEN" ]; then
    echo "ERROR: Failed to get access token"
    echo "Response: $LOGIN_RESPONSE"
    exit 1
fi

echo "✓ Logged in successfully"
echo

# Step 2: Create MCP settings with SEATS server
echo "Step 2: Registering SEATS MCP server..."
MCP_CONFIG='{
  "mcp_config": {
    "mcpServers": {
      "seats": {
        "url": "'"$MCP_SERVER_URL"'",
        "transport": "streamable-http"
      }
    }
  }
}'

CREATE_RESPONSE=$(curl -s -X POST "$API_URL/user-settings/mcp" \
  -H "Authorization: Bearer $ACCESS_TOKEN" \
  -H "Content-Type: application/json" \
  -d "$MCP_CONFIG")

echo "Response: $CREATE_RESPONSE"
echo

# Step 3: Verify registration
echo "Step 3: Verifying MCP settings..."
VERIFY_RESPONSE=$(curl -s -X GET "$API_URL/user-settings/mcp?only_active=true" \
  -H "Authorization: Bearer $ACCESS_TOKEN")

echo "Active MCP Settings:"
echo "$VERIFY_RESPONSE" | python3 -m json.tool 2>/dev/null || echo "$VERIFY_RESPONSE"
echo

echo "=== Registration Complete ==="
echo
echo "Next steps:"
echo "1. Start a new chat session"
echo "2. The SEATS MCP server tools should now be available"
echo "3. Check backend logs: docker compose -f docker-compose.local-only.yaml logs backend --tail=50"
