#!/usr/bin/env bash
# ---------------------------------------------------------------------------
# launch_ollama.sh
# Starts the Ollama server inside a Singularity container on a GPU node,
# waits until it is healthy, then pulls the target model.
#
# Usage (called by launch_cockpit.sh — not normally run directly):
#   bash launch_ollama.sh
#
# Required env vars (set defaults below or export before calling):
#   OLLAMA_SIF    — path to the Ollama Singularity .sif image
#   OLLAMA_MODEL  — model tag to pull  (default: qwen2.5-coder:14b)
#   OLLAMA_PORT   — port to bind       (default: 11434)
# ---------------------------------------------------------------------------

set -euo pipefail

OLLAMA_SIF="${OLLAMA_SIF:-/path/to/ollama.sif}"
OLLAMA_MODEL="${OLLAMA_MODEL:-qwen2.5-coder:14b}"
OLLAMA_PORT="${OLLAMA_PORT:-11434}"
OLLAMA_HOST="http://localhost:${OLLAMA_PORT}"

# Ollama stores models here — bind-mount a persistent directory so the model
# survives across jobs and does not have to be re-downloaded every time.
OLLAMA_MODELS_DIR="${OLLAMA_MODELS_DIR:-${HOME}/.ollama/models}"
mkdir -p "$OLLAMA_MODELS_DIR"

echo "[Ollama] SIF image : $OLLAMA_SIF"
echo "[Ollama] Model     : $OLLAMA_MODEL"
echo "[Ollama] Port      : $OLLAMA_PORT"
echo "[Ollama] Model dir : $OLLAMA_MODELS_DIR"

# ── 1. Start server ───────────────────────────────────────────────────────────
singularity exec --nv \
    --env OLLAMA_HOST="0.0.0.0:${OLLAMA_PORT}" \
    --bind "${OLLAMA_MODELS_DIR}:/root/.ollama/models" \
    "$OLLAMA_SIF" \
    ollama serve &

OLLAMA_PID=$!
echo "[Ollama] Server PID: $OLLAMA_PID"

# ── 2. Wait for server to be healthy ─────────────────────────────────────────
echo "[Ollama] Waiting for server to become ready…"
MAX_WAIT=120
WAITED=0
until curl -sf "${OLLAMA_HOST}/api/tags" > /dev/null 2>&1; do
    if (( WAITED >= MAX_WAIT )); then
        echo "[Ollama] ERROR: server did not start within ${MAX_WAIT}s." >&2
        kill "$OLLAMA_PID" 2>/dev/null
        exit 1
    fi
    sleep 3
    (( WAITED += 3 ))
done
echo "[Ollama] Server ready after ${WAITED}s."

# ── 3. Pull model (skipped if already cached) ─────────────────────────────────
echo "[Ollama] Checking / pulling model: ${OLLAMA_MODEL}"
singularity exec --nv \
    --env OLLAMA_HOST="0.0.0.0:${OLLAMA_PORT}" \
    --bind "${OLLAMA_MODELS_DIR}:/root/.ollama/models" \
    "$OLLAMA_SIF" \
    ollama pull "$OLLAMA_MODEL"

echo "[Ollama] Model ready: ${OLLAMA_MODEL}"

# Keep the server alive (wait blocks until the container exits)
wait "$OLLAMA_PID"
