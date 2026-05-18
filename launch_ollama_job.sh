#!/usr/bin/env bash
# ---------------------------------------------------------------------------
# launch_ollama_job.sh
# Submitted as a dedicated GPU batch job by launch_cockpit.sh.
# Writes its node hostname to workspace/gnode.txt so the cnode orchestrator
# knows where to point OLLAMA_URL, then runs Ollama until the job is cancelled.
#
# Do NOT call this script directly — submit via launch_cockpit.sh.
# ---------------------------------------------------------------------------

#SBATCH --job-name=scchat-gpu
#SBATCH --partition=gpu
#SBATCH --gres=gpu:1
#SBATCH --mem=64G
#SBATCH --cpus-per-task=8
#SBATCH --time=12:00:00
#SBATCH --output=logs/scchat_gpu_%j.log
#SBATCH --error=logs/scchat_gpu_%j.err

set -euo pipefail

OLLAMA_SIF="${OLLAMA_SIF:-/path/to/ollama.sif}"
OLLAMA_MODEL="${OLLAMA_MODEL:-qwen2.5-coder:14b}"
OLLAMA_PORT="${OLLAMA_PORT:-11434}"
OLLAMA_MODELS_DIR="${OLLAMA_MODELS_DIR:-${HOME}/.ollama/models}"
WORKSPACE="${WORKSPACE:-$(pwd)/workspace}"

mkdir -p logs "$WORKSPACE" "$OLLAMA_MODELS_DIR"

GNODE=$(hostname)
echo "[gnode] Running on: $GNODE"

# Signal the cnode orchestrator that we are alive and ready to start
echo "$GNODE" > "${WORKSPACE}/gnode.txt"
echo "[gnode] Hostname written to workspace/gnode.txt"

# Start Ollama (blocks until job is cancelled)
export OLLAMA_SIF OLLAMA_MODEL OLLAMA_PORT OLLAMA_MODELS_DIR
bash "$(dirname "$0")/launch_ollama.sh"
