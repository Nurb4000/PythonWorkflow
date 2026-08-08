#!/usr/bin/env bash
# Build the e2e image if needed and run each test in it.
# Usage:
#   bash tests/e2e/run-e2e.sh [script.js ...]
# Env: E2E_BASE (default http://localhost:3000), E2E_CDP (default http://127.0.0.1:9222/json/version)
set -euo pipefail
cd "$(dirname "$0")"
IMAGE="${E2E_IMAGE:-pythonworkflow-e2e}"

if ! docker image inspect "$IMAGE" >/dev/null 2>&1; then
  echo "Building $IMAGE ..."
  docker build -t "$IMAGE" .
fi

TESTS=("$@")
if [ ${#TESTS[@]} -eq 0 ]; then
  TESTS=(smoke.js designer-save.js entry-form-task.js)
fi

status=0
for t in "${TESTS[@]}"; do
  echo "=====> $t"
  if ! docker run --rm --network host \
    -v "$PWD:/e2e:ro" \
    -e NODE_PATH=/work/node_modules \
    -e E2E_BASE="${E2E_BASE:-http://localhost:3000}" \
    -e E2E_CDP="${E2E_CDP:-http://127.0.0.1:9222/json/version}" \
    "$IMAGE" node "/e2e/$t"; then
    echo "=====> $t FAILED"
    status=1
  fi
done
exit $status
