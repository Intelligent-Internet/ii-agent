#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR=$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)
cd "$ROOT_DIR"

echo "🔍 Running legacy namespace guard"

# Guard against Python imports that reach back into the legacy agent module.
IMPORT_PATTERN="ii_"'agent'
PYTHON_VIOLATIONS=$(grep -R "^\s*from ${IMPORT_PATTERN}\|^\s*import ${IMPORT_PATTERN}" \
  --include="*.py" \
  --exclude-dir=.git \
  --exclude-dir=node_modules \
  --exclude-dir=.venv \
  --exclude-dir=adapters/ii_bridge \
  || true)

if [[ -n "$PYTHON_VIOLATIONS" ]]; then
  echo "❌ Detected legacy Python imports:\n$PYTHON_VIOLATIONS"
  exit 1
fi

echo "✅ Python imports clean"

# Guard against stray legacy string references.
LEGACY_TOKEN="ii-"'agent'
STRING_VIOLATIONS=$(grep -R "$LEGACY_TOKEN" \
  --exclude-dir=.git \
  --exclude-dir=node_modules \
  --exclude-dir=.venv \
  --exclude-dir=adapters/ii_bridge \
  || true)

if [[ -n "$STRING_VIOLATIONS" ]]; then
  echo "❌ Detected legacy string references:\n$STRING_VIOLATIONS"
  exit 1
fi

echo "✅ Legacy string references clean"
