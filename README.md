# scChat — Single-Cell QC Cockpit

A headless, zero-root interactive quality-control dashboard for scRNA-seq data,
designed to run entirely on an HPC compute node via Singularity containers.

---

## Architecture

```
┌─────────────────────────────────────────────────────────────────┐
│                        HPC Compute Node                         │
│                                                                 │
│  ┌──────────────────┐      JSON files      ┌─────────────────┐ │
│  │  agent_pipeline  │ ──────────────────── │    app.py       │ │
│  │  (LangGraph +    │  workspace/          │  (Streamlit     │ │
│  │   Scanpy/h5ad)   │  trials_output.json  │   port 8501)    │ │
│  │                  │  human_decision.json │                 │ │
│  └────────┬─────────┘                      └────────┬────────┘ │
│           │                                         │          │
│  ┌────────▼─────────┐                               │          │
│  │   Ollama server  │ ◄─────────────────────────────┘          │
│  │  (Qwen2.5-Coder  │        localhost:11434                   │
│  │    14B on GPU)   │                                          │
│  └──────────────────┘                                          │
└─────────────────────────────────────────────────────────────────┘
         ▲
         │  SSH tunnel  ssh -L 8501:<node>:8501
         │
    Your laptop
    localhost:8501
```

Three independent layers communicate without any shared stdin:

| Layer | Runtime | Role |
|---|---|---|
| **Ollama (GPU)** | Singularity (Ollama image) | Hosts Qwen2.5-Coder 14B locally — no data leaves the cluster |
| **agent_pipeline.py** | Singularity (Scanpy/Miniconda) | Sweeps filtering thresholds, writes trial results, waits for user decision |
| **app.py** | `scchat-frontend` conda env | Streamlit dashboard — chat + live Plotly decay curves |

---

## Repository Layout

```
scChat/
├── app.py                        # Streamlit entry point
├── environment_frontend.yml      # conda env for the dashboard
├── workspace/                    # shared JSON bridge (gitignored at runtime)
│   └── .gitkeep
└── frontend/
    ├── state/session.py          # st.session_state initialisation
    ├── chat/panel.py             # left column: chat + threshold selector
    └── viz/panel.py              # right column: dataframe + decay curve
```

> `agent_pipeline.py` and the Slurm launch script (`launch_cockpit.sh`) live
> alongside this repo and are documented separately.

---

## Frontend Package

### `frontend/state/session.py`
Seeds every `st.session_state` key on first load so the rest of the app can
assume all keys exist. Edit this file to add new shared state.

### `frontend/chat/panel.py`
Renders the left column:
- Scrollable chat history with `st.chat_message` bubbles.
- A threshold-selector dropdown + **Submit** button that appears automatically
  once `backend_ready` is `True` and trial data is available.
- Stub slot for the Ollama LLM call (marked `# TODO`).

### `frontend/viz/panel.py`
Renders the right column:
- Polls `workspace/trials_output.json` on every rerun.
- Displays a searchable `st.dataframe` of all trial rows.
- Draws a dual-axis Plotly scatter: **cells retained** (left y) and
  **% retained** (right y) across threshold profiles.

### Workspace JSON schema

**`trials_output.json`** (written by `agent_pipeline.py`):
```json
[
  { "threshold_label": "strict_200",  "cells_retained": 287400, "pct_retained": 95.8 },
  { "threshold_label": "strict_500",  "cells_retained": 241100, "pct_retained": 80.4 },
  ...
]
```

**`human_decision.json`** (written by Streamlit on submit):
```json
{ "chosen_threshold": "strict_500" }
```

---

## Setup

### 1. Create the conda environment

```bash
conda env create -f environment_frontend.yml
conda activate scchat-frontend
```

### 2. Run locally (development)

```bash
streamlit run app.py
```

### 3. Run on HPC (headless via Slurm)

The Slurm script `launch_cockpit.sh` handles this automatically. The relevant
Streamlit invocation inside the script is:

```bash
streamlit run app.py \
  --server.port 8501 \
  --server.headless true \
  --server.address 0.0.0.0
```

### 4. Connect from your laptop

Once the job is running, open an SSH tunnel:

```bash
ssh -L 8501:<compute-node-hostname>:8501 <user>@<cluster-login-node>
```

Then open `http://localhost:8501` in your browser.

---

## Data Flow (step by step)

```
1. Slurm allocates GPU node → launch_cockpit.sh starts Ollama + Streamlit
2. agent_pipeline.py loads .h5ad, runs threshold sweep
3. Writes workspace/trials_output.json, then enters a sleep-poll loop
4. Streamlit detects JSON (3-second rerun loop), renders table + decay curve
5. Threshold dropdown appears in the chat panel
6. User selects threshold → clicks Submit
7. Streamlit writes workspace/human_decision.json
8. agent_pipeline.py detects decision file, deletes it, resumes (PCA → UMAP → clustering)
```

---

## Development Roadmap

- [ ] `agent_pipeline.py` — LangGraph sweep loop + JSON emission
- [ ] `launch_cockpit.sh` — Slurm script (GPU, 128 GB RAM, Singularity init)
- [ ] Wire `chat/panel.py` LLM stub to Ollama REST (`POST /api/chat`)
- [ ] Add per-sample metadata panel to the viz column
- [ ] Streaming token output in chat bubbles
