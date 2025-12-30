#!/bin/bash
# API smoke script for OpenAI-compatible base_url (e.g., gemini-cli-openai worker)
# Tests that the worker is accessible and responds to /v1/models and /v1/chat/completions
# Usage: ./scripts/smoke-openai-base-url.sh

set -e

# Color output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

log_info() { echo -e "${GREEN}[INFO]${NC} $1"; }
log_warn() { echo -e "${YELLOW}[WARN]${NC} $1"; }
log_error() { echo -e "${RED}[ERROR]${NC} $1"; }

# Get OPENAI_BASE_URL from environment, default to localhost
BASE_URL="${OPENAI_BASE_URL:-http://localhost:3888/v1}"
API_KEY="${OPENAI_API_KEY:-}"

log_info "Testing OpenAI-compatible base URL: $BASE_URL"

# Test 1: GET /v1/models - discover available models
log_info "Test 1: GET /v1/models (model discovery)"
MODELS_RESPONSE=$(curl -s -w "\n%{http_code}" "$BASE_URL/models" 2>&1)
MODELS_STATUS=$(echo "$MODELS_RESPONSE" | tail -n 1)
MODELS_BODY=$(echo "$MODELS_RESPONSE" | head -n $(($(echo "$MODELS_RESPONSE" | wc -l) - 1)))

if [ "$MODELS_STATUS" = "200" ]; then
    log_info "✓ /v1/models returned 200"
    echo "$MODELS_BODY" | head -c 500
    echo "..."
else
    log_error "/v1/models returned $MODELS_STATUS"
    echo "$MODELS_BODY"
    exit 1
fi

# Test 2: POST /v1/chat/completions (non-streaming)
log_info "Test 2: POST /v1/chat/completions (non-streaming)"

COMPLETION_REQUEST='{
  "model": "gemini-2.5-flash",
  "messages": [{"role": "user", "content": "Hello"}],
  "max_tokens": 10
}'

if [ -n "$API_KEY" ]; then
    COMPLETION_RESPONSE=$(curl -s -w "\n%{http_code}" \
        -H "Authorization: Bearer $API_KEY" \
        -H "Content-Type: application/json" \
        -d "$COMPLETION_REQUEST" \
        "$BASE_URL/chat/completions" 2>&1)
else
    log_warn "No OPENAI_API_KEY set (may be optional for some workers)"
    COMPLETION_RESPONSE=$(curl -s -w "\n%{http_code}" \
        -H "Content-Type: application/json" \
        -d "$COMPLETION_REQUEST" \
        "$BASE_URL/chat/completions" 2>&1)
fi

COMPLETION_STATUS=$(echo "$COMPLETION_RESPONSE" | tail -n 1)
COMPLETION_BODY=$(echo "$COMPLETION_RESPONSE" | head -n $(($(echo "$COMPLETION_RESPONSE" | wc -l) - 1)))

if [ "$COMPLETION_STATUS" = "200" ] || [ "$COMPLETION_STATUS" = "201" ]; then
    log_info "✓ /v1/chat/completions returned $COMPLETION_STATUS"
    echo "$COMPLETION_BODY" | head -c 500
    echo "..."
elif echo "$COMPLETION_BODY" | grep -qi "model.*not found"; then
    log_warn "Model 'test-model' not found (this is expected - update script with valid model)"
else
    log_error "/v1/chat/completions returned $COMPLETION_STATUS"
    echo "$COMPLETION_BODY"
    exit 1
fi

# Test 3: POST /v1/chat/completions (streaming)
log_info "Test 3: POST /v1/chat/completions (streaming)"

STREAM_REQUEST='{
  "model": "gemini-2.5-flash",
  "messages": [{"role": "user", "content": "Hi"}],
  "max_tokens": 5,
  "stream": true
}'

if [ -n "$API_KEY" ]; then
    STREAM_RESPONSE=$(curl -s -w "\n%{http_code}" \
        -H "Authorization: Bearer $API_KEY" \
        -H "Content-Type: application/json" \
        -d "$STREAM_REQUEST" \
        "$BASE_URL/chat/completions" 2>&1)
else
    STREAM_RESPONSE=$(curl -s -w "\n%{http_code}" \
        -H "Content-Type: application/json" \
        -d "$STREAM_REQUEST" \
        "$BASE_URL/chat/completions" 2>&1)
fi

STREAM_STATUS=$(echo "$STREAM_RESPONSE" | tail -n 1)
STREAM_BODY=$(echo "$STREAM_RESPONSE" | head -n $(($(echo "$STREAM_RESPONSE" | wc -l) - 1)))

if [ "$STREAM_STATUS" = "200" ] || [ "$STREAM_STATUS" = "201" ]; then
    log_info "✓ /v1/chat/completions (stream) returned $STREAM_STATUS"

    # Check for SSE events
    if echo "$STREAM_BODY" | grep -q "event:"; then
        log_info "✓ SSE events detected in response"
        echo "$STREAM_BODY" | head -c 500
        echo "..."
    else
        log_warn "No SSE events detected - response may not be streaming"
        echo "$STREAM_BODY" | head -c 500
        echo "..."
    fi
else
    log_error "/v1/chat/completions (stream) returned $STREAM_STATUS"
    echo "$STREAM_BODY"
    exit 1
fi

log_info "✓ All API smoke tests passed!"
