#!/usr/bin/env bash
# ═══════════════════════════════════════════════════════════════════
#  Container entrypoint — supervises the Python CV processor and the
#  Node API in one container.
#
#  Contract:
#    • Python binds 127.0.0.1:$PROCESSOR_PORT  (never public)
#    • Node   binds 0.0.0.0:$PORT              (the only exposed port)
#    • If EITHER process dies, the container exits so the platform
#      restarts it cleanly. A half-dead container that still answers
#      health checks but can't analyse anything is worse than a restart.
# ═══════════════════════════════════════════════════════════════════
set -Eeuo pipefail

PORT="${PORT:-7860}"
PROCESSOR_PORT="${PROCESSOR_PORT:-5001}"
PROCESSOR_HOST="${PROCESSOR_HOST:-127.0.0.1}"

echo "════════════════════════════════════════════════════"
echo " MoveCheck container starting"
echo "   Node API        : 0.0.0.0:${PORT}"
echo "   CV processor    : ${PROCESSOR_HOST}:${PROCESSOR_PORT} (internal)"
echo "   Static frontend : ${SERVE_STATIC_DIR:-<disabled>}"
echo "════════════════════════════════════════════════════"

PY_PID=""
NODE_PID=""

shutdown() {
  echo "→ Shutting down..."
  [[ -n "$PY_PID"   ]] && kill "$PY_PID"   2>/dev/null || true
  [[ -n "$NODE_PID" ]] && kill "$NODE_PID" 2>/dev/null || true
  wait 2>/dev/null || true
  exit 0
}
trap shutdown SIGTERM SIGINT

# ── 1. Python CV processor ────────────────────────────────────────
# Run under gunicorn: Flask's dev server is single-threaded-by-default and
# explicitly not for production use.
#   --workers 1   : each worker loads the MediaPipe heavy model (~hundreds of
#                   MB). One worker keeps memory predictable; concurrency comes
#                   from threads instead.
#   --threads 4   : lets /health answer while an analysis is running, so the
#                   platform's health probe never times out mid-job.
#   --timeout 900 : a 4K clip on a shared vCPU can legitimately run minutes.
cd /app/processor
echo "→ Starting CV processor (gunicorn)..."
gunicorn \
    --bind "${PROCESSOR_HOST}:${PROCESSOR_PORT}" \
    --workers 1 \
    --threads 4 \
    --timeout 900 \
    --graceful-timeout 30 \
    --access-logfile - \
    --error-logfile - \
    --log-level info \
    app:app &
PY_PID=$!

# ── 2. Wait for the processor to accept connections ──────────────
# Importing MediaPipe + TensorFlow Lite takes a while on a cold shared vCPU.
echo "→ Waiting for CV processor to become ready..."
for i in $(seq 1 90); do
  if curl -fsS "http://${PROCESSOR_HOST}:${PROCESSOR_PORT}/health" >/dev/null 2>&1; then
    echo "✓ CV processor ready after ${i}s"
    break
  fi
  if ! kill -0 "$PY_PID" 2>/dev/null; then
    echo "✗ CV processor died during startup — check the traceback above."
    exit 1
  fi
  sleep 1
done

# ── 3. Node API (foreground-ish) ─────────────────────────────────
cd /app/backend
echo "→ Starting Node API..."
node server.js &
NODE_PID=$!

# ── 4. Supervise: exit if either process dies ────────────────────
# `wait -n` returns as soon as the FIRST child exits.
wait -n "$PY_PID" "$NODE_PID"
EXIT_CODE=$?
echo "✗ A service exited (code ${EXIT_CODE}) — stopping container so the platform restarts it."
shutdown
