#!/usr/bin/env bash
# ---------------------------------------------------------------------------
# launch_cockpit.sh  —  scChat HITL Agentic Cockpit
#
# Run this on a CPU node (cnode). It will:
#   1. Submit a GPU job (gnode) for Ollama via Slurm
#   2. Wait for the gnode to come online and write its hostname
#   3. Start Streamlit (frontend) on the cnode
#   4. Start the LangGraph pipeline on the cnode, pointed at Ollama on the gnode
#
# Three execution modes (--mode flag or SCCHAT_MODE env var):
#
#   hpc-split   [default] cnode runs frontend+pipeline / gnode runs Ollama
#   docker      Local testing via Docker Compose (no Slurm needed)
#   conda       HPC fallback — everything on one node, pure conda envs
#
# Usage:
#   bash launch_cockpit.sh [--mode hpc-split|docker|conda] <data.h5ad> [--output out.h5ad]
#
# Required env vars (hpc-split mode):
#   OLLAMA_SIF        — path to Ollama Singularity .sif
#   BACKEND_SIF       — path to Scanpy Singularity .sif (optional; falls back to conda)
#   OLLAMA_MODELS_DIR — persistent model cache dir (survives across jobs)
# ---------------------------------------------------------------------------

set -euo pipefail

# ── Argument parsing ──────────────────────────────────────────────────────────
MODE="${SCCHAT_MODE:-hpc-split}"
H5AD_PATH=""
OUTPUT_PATH="workspace/adata_final.h5ad"

while [[ $# -gt 0 ]]; do
    case "$1" in
        --mode)   MODE="$2";        shift 2 ;;
        --output) OUTPUT_PATH="$2"; shift 2 ;;
        -*)       echo "Unknown flag: $1" >&2; exit 1 ;;
        *)        H5AD_PATH="$1";   shift ;;
    esac
done

[[ -z "$H5AD_PATH" ]] && {
    echo "Usage: launch_cockpit.sh [--mode hpc-split|docker|conda] <data.h5ad>" >&2
    exit 1
}

# ── Shared config ─────────────────────────────────────────────────────────────
OLLAMA_SIF="${OLLAMA_SIF:-/path/to/ollama.sif}"
BACKEND_SIF="${BACKEND_SIF:-}"
OLLAMA_MODEL="${OLLAMA_MODEL:-qwen2.5-coder:14b}"
OLLAMA_PORT="${OLLAMA_PORT:-11434}"
OLLAMA_MODELS_DIR="${OLLAMA_MODELS_DIR:-${HOME}/.ollama/models}"
STREAMLIT_PORT=8501
SCCHAT_DIR="$(cd "$(dirname "$0")" && pwd)"
WORKSPACE="${SCCHAT_DIR}/workspace"

# GPU job Slurm parameters (override via env if needed)
GPU_PARTITION="${GPU_PARTITION:-gpu}"
GPU_MEM="${GPU_MEM:-64G}"
GPU_CPUS="${GPU_CPUS:-8}"
GPU_TIME="${GPU_TIME:-12:00:00}"

CNODE=$(hostname)
LOGIN_NODE="${SLURM_SUBMIT_HOST:-<login-node>}"

mkdir -p logs workspace

# ── Banner ────────────────────────────────────────────────────────────────────
cat <<EOF
╔══════════════════════════════════════════════════════════════╗
║              scChat — HITL Agentic QC Cockpit                ║
╠══════════════════════════════════════════════════════════════╣
║  Mode        : $MODE
║  cnode       : $CNODE
║  Input       : $H5AD_PATH
║  Output      : $OUTPUT_PATH
╚══════════════════════════════════════════════════════════════╝
EOF

# ══════════════════════════════════════════════════════════════════════════════
# MODE: docker
# ══════════════════════════════════════════════════════════════════════════════
if [[ "$MODE" == "docker" ]]; then
    echo "[cockpit] Docker mode — delegating to docker-compose."
    H5AD_DIR="$(dirname "$(realpath "$H5AD_PATH")")"
    H5AD_FILE="$(basename "$H5AD_PATH")"
    H5AD_PATH="$H5AD_DIR" H5AD_FILENAME="$H5AD_FILE" OLLAMA_MODEL="$OLLAMA_MODEL" \
        docker compose --project-directory "$SCCHAT_DIR" \
                       --file "${SCCHAT_DIR}/docker-compose.yml" \
                       up --build --abort-on-container-exit
    exit $?
fi

# ══════════════════════════════════════════════════════════════════════════════
# MODE: hpc-split  (cnode orchestrates, gnode runs Ollama)
# ══════════════════════════════════════════════════════════════════════════════
if [[ "$MODE" == "hpc-split" ]]; then

    # ── Step 1: submit GPU job for Ollama ─────────────────────────────────────
    rm -f "${WORKSPACE}/gnode.txt"

    echo "[cockpit] Submitting GPU job for Ollama (partition: ${GPU_PARTITION})…"
    GPU_JOB_ID=$(
        OLLAMA_SIF="$OLLAMA_SIF" \
        OLLAMA_MODEL="$OLLAMA_MODEL" \
        OLLAMA_PORT="$OLLAMA_PORT" \
        OLLAMA_MODELS_DIR="$OLLAMA_MODELS_DIR" \
        WORKSPACE="$WORKSPACE" \
        sbatch --parsable \
            --partition="$GPU_PARTITION" \
            --gres=gpu:1 \
            --mem="$GPU_MEM" \
            --cpus-per-task="$GPU_CPUS" \
            --time="$GPU_TIME" \
            --job-name=scchat-gpu \
            --output="logs/scchat_gpu_%j.log" \
            --error="logs/scchat_gpu_%j.err" \
            "${SCCHAT_DIR}/launch_ollama_job.sh"
    )
    echo "[cockpit] GPU job submitted: ID=${GPU_JOB_ID}"

    # ── Step 2: wait for gnode to register itself ─────────────────────────────
    echo "[cockpit] Waiting for gnode to come online…"
    WAIT=0
    MAX_WAIT=300   # 5 min — adjust for your cluster's queue
    until [[ -s "${WORKSPACE}/gnode.txt" ]]; do
        if (( WAIT >= MAX_WAIT )); then
            echo "[cockpit] ERROR: gnode did not register within ${MAX_WAIT}s. Cancelling job." >&2
            scancel "$GPU_JOB_ID" 2>/dev/null || true
            exit 1
        fi
        sleep 5
        (( WAIT += 5 ))
    done

    GNODE=$(cat "${WORKSPACE}/gnode.txt")
    OLLAMA_URL="http://${GNODE}:${OLLAMA_PORT}/api/chat"
    echo "[cockpit] gnode is: $GNODE"
    echo "[cockpit] Ollama URL: $OLLAMA_URL"

    # ── Step 3: wait for Ollama REST API to be healthy ────────────────────────
    echo "[cockpit] Waiting for Ollama on gnode to become healthy…"
    until curl -sf "http://${GNODE}:${OLLAMA_PORT}/api/tags" > /dev/null 2>&1; do
        sleep 5
    done
    echo "[cockpit] Ollama is healthy on ${GNODE}."

    # ── Print SSH tunnel instructions ─────────────────────────────────────────
    cat <<EOF

╔══════════════════════════════════════════════════════════════╗
║  GPU job ${GPU_JOB_ID} running on gnode: ${GNODE}
║
║  SSH TUNNEL — run this on your laptop:
║    ssh -L ${STREAMLIT_PORT}:${CNODE}:${STREAMLIT_PORT} ${USER}@${LOGIN_NODE}
║
║  Then open:  http://localhost:${STREAMLIT_PORT}
╚══════════════════════════════════════════════════════════════╝
EOF

    # ── Step 4: start Streamlit on cnode ─────────────────────────────────────
    echo "[cockpit] Starting Streamlit on cnode (port ${STREAMLIT_PORT})…"
    conda run -n scchat-frontend --no-capture-output \
        streamlit run "${SCCHAT_DIR}/app.py" \
            --server.port "$STREAMLIT_PORT" \
            --server.headless true \
            --server.address 0.0.0.0 \
            --server.fileWatcherType none &
    STREAMLIT_PID=$!
    echo "[cockpit] Streamlit PID: $STREAMLIT_PID"

    # ── Step 5: start pipeline on cnode, Ollama on gnode ─────────────────────
    echo "[cockpit] Starting pipeline on cnode…"

    PIPELINE_ENV=(
        OLLAMA_URL="$OLLAMA_URL"
        OLLAMA_MODEL="$OLLAMA_MODEL"
        WORKSPACE_DIR="$WORKSPACE"
    )

    if [[ -n "$BACKEND_SIF" ]]; then
        env "${PIPELINE_ENV[@]}" \
            singularity exec --nv \
                --bind "${SCCHAT_DIR}:/app" \
                --bind "${WORKSPACE}:/app/workspace" \
                "$BACKEND_SIF" \
                python /app/agent_pipeline.py "$H5AD_PATH" --output "$OUTPUT_PATH" &
    else
        env "${PIPELINE_ENV[@]}" \
            conda run -n scchat-backend --no-capture-output \
                python "${SCCHAT_DIR}/agent_pipeline.py" "$H5AD_PATH" --output "$OUTPUT_PATH" &
    fi

    PIPELINE_PID=$!
    echo "[cockpit] Pipeline PID: $PIPELINE_PID"

    # ── Step 6: wait, then tear down ─────────────────────────────────────────
    wait "$PIPELINE_PID"
    EXIT_CODE=$?
    echo "[cockpit] Pipeline finished (exit ${EXIT_CODE}). Shutting down."

    kill "$STREAMLIT_PID" 2>/dev/null || true
    scancel "$GPU_JOB_ID" 2>/dev/null || true
    rm -f "${WORKSPACE}/gnode.txt"

    exit "$EXIT_CODE"
fi

# ══════════════════════════════════════════════════════════════════════════════
# MODE: conda  (everything on one node, no containers)
# ══════════════════════════════════════════════════════════════════════════════
if [[ "$MODE" == "conda" ]]; then

    export OLLAMA_SIF OLLAMA_MODEL OLLAMA_PORT OLLAMA_MODELS_DIR
    bash "${SCCHAT_DIR}/launch_ollama.sh" &
    OLLAMA_LAUNCHER_PID=$!

    until curl -sf "http://localhost:${OLLAMA_PORT}/api/tags" > /dev/null 2>&1; do sleep 3; done
    echo "[cockpit] Ollama ready (single-node mode)."

    conda run -n scchat-frontend --no-capture-output \
        streamlit run "${SCCHAT_DIR}/app.py" \
            --server.port "$STREAMLIT_PORT" \
            --server.headless true \
            --server.address 0.0.0.0 \
            --server.fileWatcherType none &
    STREAMLIT_PID=$!

    OLLAMA_URL="http://localhost:${OLLAMA_PORT}/api/chat" \
    OLLAMA_MODEL="$OLLAMA_MODEL" \
    WORKSPACE_DIR="$WORKSPACE" \
        conda run -n scchat-backend --no-capture-output \
            python "${SCCHAT_DIR}/agent_pipeline.py" "$H5AD_PATH" --output "$OUTPUT_PATH" &
    PIPELINE_PID=$!

    wait "$PIPELINE_PID"
    EXIT_CODE=$?
    kill "$STREAMLIT_PID" "$OLLAMA_LAUNCHER_PID" 2>/dev/null || true
    exit "$EXIT_CODE"
fi

echo "Unknown mode: $MODE" >&2
exit 1
