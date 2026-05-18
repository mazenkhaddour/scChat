# scChat

A Human-in-the-Loop (HITL) agentic analysis cockpit for HPC clusters.
The agent runs your analysis autonomously and pauses at structured decision gates
where you review, adjust, and approve before it continues.

Built for single-cell RNA-seq QC as the first pipeline — the underlying
architecture is domain-agnostic.

---

## Architecture

```
Your Laptop
    │
    │  SSH tunnel  (-L 8501:cnode:8501)
    ▼
┌─────────────────────────────────────────────────────────────────────┐
│  cnode  (CPU node)                                                  │
│                                                                     │
│  ┌─────────────────────┐    JSON     ┌───────────────────────────┐ │
│  │   app.py            │◄──────────►│   agent_pipeline.py       │ │
│  │   Streamlit :8501   │  ./workspace│   LangGraph HITL pipeline │ │
│  │                     │            │                           │ │
│  │  Top  : Gate steps  │            │  Gate 1 — QC Filtering    │ │
│  │  Left : Chat        │            │  Gate 2 — PCA             │ │
│  │  Right: Gate viz    │            │  Gate 3 — Clustering      │ │
│  └─────────────────────┘            │  Gate 4 — Annotation      │ │
└────────────────────────────────┬────┴───────────────────────────┘─┘
                                 │  HTTP  http://<gnode>:11434
                                 ▼
┌─────────────────────────────────────────────────────────────────────┐
│  gnode  (GPU node)  — allocated on-demand by launch_cockpit.sh      │
│                                                                     │
│        ollama/ollama:latest  ·  qwen2.5-coder:14b  ·  :11434       │
└─────────────────────────────────────────────────────────────────────┘
```

---

## Docker Images

| Image | Registry | Role |
|---|---|---|
| `mazenkhaddour/scchat-pipeline:latest` | Docker Hub | LangGraph pipeline (scanpy, anndata, leidenalg) |
| `ollama/ollama:latest` | Docker Hub | Ollama LLM server |

---

## HITL Gate Flow

```
[load .h5ad]
    │
 ◆ GATE 1 — QC Filtering       threshold sweep → LLM reasoning → your choice
    │
[normalize → HVG → PCA]
    │
 ◆ GATE 2 — PCA Dimensionality  elbow plot → LLM proposes n_pcs → your choice
    │
[neighbors → UMAP → Leiden sweep]
    │
 ◆ GATE 3 — Clustering          sweep bar + UMAP preview → your resolution
    │
[rank_genes_groups → LLM annotation]
    │
 ◆ GATE 4 — Cell-type Annotation editable label table → your sign-off
    │
[export adata_final.h5ad]
```

---

## Repository Layout

```
scChat/
├── app.py                          # Streamlit entry point
├── agent_pipeline.py               # LangGraph 4-gate pipeline
│
├── launch_cockpit.sh               # Master script — run this on the cnode
├── launch_ollama_job.sh            # Slurm GPU job: starts Ollama on gnode
├── launch_ollama.sh                # Called inside the GPU job (Singularity)
│
├── Dockerfile                      # Source for mazenkhaddour/scchat-pipeline
├── docker-compose.yml              # Local/test stack
├── requirements_backend.txt        # Pinned deps (matches the published image)
├── environment_frontend.yml        # conda env for Streamlit
├── environment_backend.yml         # conda env for pipeline (HPC fallback)
│
├── workspace/                      # JSON bridge — shared between all processes
│   ├── gate_state.json             # pipeline → frontend
│   ├── human_decision.json         # frontend → pipeline
│   └── gnode.txt                   # GPU job → cnode orchestrator
│
└── frontend/
    ├── state/session.py
    ├── chat/panel.py               # Ollama-backed chat (gate-aware system prompt)
    └── viz/gates/
        ├── gate1_filtering.py
        ├── gate2_pca.py
        ├── gate3_clustering.py
        └── gate4_annotation.py
```

---

## Setup & Launch Tutorial

### Prerequisites

**Docker / local machine**
- Docker Desktop ≥ 4.x (Mac / Windows / Linux)
- [NVIDIA Container Toolkit](https://docs.nvidia.com/datacenter/cloud-native/container-toolkit/install-guide.html) if you want GPU acceleration locally
- ~20 GB free disk space for the model

**HPC cluster**
- Slurm workload manager
- Singularity / Apptainer available on compute nodes
- Access to a GPU partition (`gpu` by default)
- conda or mamba installed in your user environment

---

### Option A — Docker (local testing)

This is the quickest way to test the full stack on your laptop.

#### Step 1 — Pull the images

```bash
docker pull mazenkhaddour/scchat-pipeline:latest
docker pull ollama/ollama:latest
```

#### Step 2 — Clone the repo

```bash
git clone <repo-url> scChat
cd scChat
mkdir -p workspace
```

#### Step 3 — Launch the stack

```bash
# Replace with the absolute path to the folder containing your .h5ad file
# and the filename of the file itself
H5AD_PATH=/absolute/path/to/data/folder \
H5AD_FILENAME=your_data.h5ad \
docker compose up
```

Docker Compose starts four services in order:

```
ollama          — LLM server (GPU if available, CPU otherwise)
ollama-pull     — downloads qwen2.5-coder:14b once, then exits
pipeline        — LangGraph agent (mazenkhaddour/scchat-pipeline)
frontend        — Streamlit dashboard on :8501
```

The model download (~9 GB) only happens the first time.
Subsequent runs use the `ollama_models` Docker volume.

#### Step 4 — Open the dashboard

```
http://localhost:8501
```

#### Step 5 — Work through the gates

1. Wait for the pipeline to finish its first sweep (Gate 1 bar chart appears).
2. Read the agent's reasoning in the expander.
3. Ask follow-up questions in the chat panel.
4. Select your threshold / parameter and click **Confirm & continue →**.
5. Repeat for Gates 2–4.
6. Final `.h5ad` is written to `workspace/adata_final.h5ad`.

#### To stop

```bash
docker compose down          # stops containers, keeps model volume
docker compose down -v       # also deletes the model volume
```

---

### Option B — HPC split mode (production)

The cnode runs Streamlit + the pipeline.
The gnode runs Ollama only — allocated automatically by the script.

#### Step 1 — Set up environments on the cnode

```bash
# Frontend
conda env create -f environment_frontend.yml

# Pipeline (if not using Singularity)
conda env create -f environment_backend.yml
```

#### Step 2 — Configure paths

Open `launch_cockpit.sh` and set (or export before calling):

```bash
export OLLAMA_SIF=/path/to/ollama.sif        # Singularity image for Ollama
export OLLAMA_MODELS_DIR=/scratch/$USER/.ollama/models  # persistent model cache
export BACKEND_SIF=/path/to/scanpy.sif       # optional; leave empty to use conda
export GPU_PARTITION=gpu                     # your cluster's GPU partition name
export GPU_TIME=12:00:00                     # how long to hold the GPU node
```

> **Tip:** You can convert the Docker images to Singularity .sif files:
> ```bash
> singularity pull ollama.sif docker://ollama/ollama:latest
> singularity pull scchat-pipeline.sif docker://mazenkhaddour/scchat-pipeline:latest
> ```

#### Step 3 — Launch from the cnode

```bash
bash launch_cockpit.sh --mode hpc-split /path/to/data.h5ad
```

The script:
1. Submits `launch_ollama_job.sh` as a GPU batch job
2. Waits for the gnode to write its hostname to `workspace/gnode.txt`
3. Polls `http://<gnode>:11434` until Ollama is healthy
4. Starts Streamlit + pipeline on the cnode, both pointed at the gnode
5. Prints your SSH tunnel command

Output will look like:

```
╔══════════════════════════════════════════════════════════════╗
║  GPU job 847291 running on gnode: gpu-node-07
║
║  SSH TUNNEL — run this on your laptop:
║    ssh -L 8501:cnode01:8501 myuser@login.cluster.edu
║
║  Then open:  http://localhost:8501
╚══════════════════════════════════════════════════════════════╝
```

#### Step 4 — Open the SSH tunnel

On your laptop:

```bash
ssh -L 8501:<cnode-hostname>:8501 <user>@<login-node>
```

Then open `http://localhost:8501`.

#### Step 5 — Work through the gates

Same as Option A, Step 5.

When the pipeline finishes, the script cancels the GPU job automatically.

---

### Option C — Single-node conda (HPC fallback)

No containers, everything on one node:

```bash
bash launch_cockpit.sh --mode conda /path/to/data.h5ad
```

Useful when the GPU queue is busy or for debugging.

---

## Environment Variables Reference

| Variable | Default | Description |
|---|---|---|
| `OLLAMA_URL` | `http://localhost:11434/api/chat` | Ollama API endpoint seen by the pipeline |
| `OLLAMA_MODEL` | `qwen2.5-coder:14b` | Model tag to use |
| `WORKSPACE_DIR` | `workspace` | Path where JSON bridge files are written |
| `OLLAMA_SIF` | `/path/to/ollama.sif` | Singularity image for Ollama (HPC) |
| `BACKEND_SIF` | _(empty)_ | Singularity image for pipeline (HPC, optional) |
| `OLLAMA_MODELS_DIR` | `~/.ollama/models` | Persistent model cache directory |
| `GPU_PARTITION` | `gpu` | Slurm partition for the GPU job |
| `GPU_MEM` | `64G` | Memory for the GPU job |
| `GPU_TIME` | `12:00:00` | Walltime for the GPU job |

---

## Workspace JSON Schemas

**`workspace/gate_state.json`** — written by the pipeline at each gate:
```json
{
  "gate_id": 1,
  "gate_name": "QC Filtering",
  "status": "ready_for_review",
  "agent_proposal": { "threshold_label": "g300-5000_mt20", "cells_retained": 241100 },
  "agent_reasoning": "Based on the QC metrics...",
  "metrics": { "total_cells": 300000, "trials": [] },
  "options": []
}
```

**`workspace/human_decision.json`** — written by Streamlit on submit:
```json
{ "chosen_threshold": "g300-5000_mt20" }
```

**`workspace/gnode.txt`** — written by the GPU job on startup:
```
gpu-node-07
```

---

## Roadmap

- [x] Streamlit HITL dashboard (4 gate renderers + chat)
- [x] LangGraph pipeline (4 gates + Ollama reasoning)
- [x] JSON file-poll bridge (pipeline ↔ frontend)
- [x] cnode → gnode dynamic GPU allocation via Slurm
- [x] Docker image (`mazenkhaddour/scchat-pipeline`) + Compose stack
- [ ] Multi-sample batch mode (Slurm array job per sample)
- [ ] Streaming LLM tokens in chat bubbles
- [ ] Per-gate figure export (PNG) to workspace
- [ ] Session audit log → PDF report (all decisions + reasoning)
