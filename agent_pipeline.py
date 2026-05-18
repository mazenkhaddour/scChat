"""
HITL Agentic scRNA-seq pipeline.

Four human-review gates:
  Gate 1 — QC Filtering
  Gate 2 — PCA dimensionality
  Gate 3 — Clustering resolution
  Gate 4 — Cell-type annotation

Frontend ↔ backend communication via JSON files in ./workspace/:
  agent writes  → workspace/gate_state.json
  frontend writes → workspace/human_decision.json
"""

import argparse
import json
import logging
import time
from pathlib import Path
from typing import Any, TypedDict

import httpx
import numpy as np
import scanpy as sc
from langgraph.graph import END, StateGraph

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
logger = logging.getLogger(__name__)

import os

WORKSPACE        = Path(os.environ.get("WORKSPACE_DIR", "workspace"))
GATE_STATE_PATH  = WORKSPACE / "gate_state.json"
DECISION_PATH    = WORKSPACE / "human_decision.json"
OLLAMA_URL       = os.environ.get("OLLAMA_URL",   "http://localhost:11434/api/chat")
MODEL            = os.environ.get("OLLAMA_MODEL", "qwen2.5-coder:14b")
POLL_INTERVAL = 3


# ── Shared state ──────────────────────────────────────────────────────────────

class PipelineState(TypedDict):
    h5ad_path: str
    output_path: str
    gate_id: int
    filtering: dict
    pca: dict
    clustering: dict
    annotation: dict


# ── Communication helpers ─────────────────────────────────────────────────────

def _write_gate(gate_id: int, name: str, status: str,
                proposal: dict, reasoning: str,
                metrics: dict, options: list) -> None:
    WORKSPACE.mkdir(exist_ok=True)
    GATE_STATE_PATH.write_text(json.dumps({
        "gate_id": gate_id,
        "gate_name": name,
        "status": status,
        "agent_proposal": proposal,
        "agent_reasoning": reasoning,
        "metrics": metrics,
        "options": options,
    }, default=str, indent=2))
    logger.info("Gate %d written → %s", gate_id, GATE_STATE_PATH)


def _wait_for_decision() -> dict:
    logger.info("Waiting for human decision…")
    while True:
        if DECISION_PATH.exists():
            try:
                decision = json.loads(DECISION_PATH.read_text())
            except json.JSONDecodeError:
                time.sleep(1)
                continue
            DECISION_PATH.unlink()
            logger.info("Decision received: %s", decision)
            return decision
        time.sleep(POLL_INTERVAL)


def _llm_reason(system: str, user: str) -> str:
    try:
        resp = httpx.post(
            OLLAMA_URL,
            json={
                "model": MODEL,
                "messages": [
                    {"role": "system", "content": system},
                    {"role": "user",   "content": user},
                ],
                "stream": False,
            },
            timeout=180,
        )
        resp.raise_for_status()
        return resp.json()["message"]["content"]
    except Exception as exc:
        logger.warning("Ollama call failed: %s", exc)
        return f"[LLM unavailable — {exc}]"


# ── Node 0: load ──────────────────────────────────────────────────────────────

def load_data(state: PipelineState) -> PipelineState:
    adata = sc.read_h5ad(state["h5ad_path"])
    adata.write_h5ad(WORKSPACE / "_raw.h5ad")
    logger.info("Loaded %d cells × %d genes", adata.n_obs, adata.n_vars)
    return state


# ── Node 1: QC + Gate 1 ───────────────────────────────────────────────────────

def gate1_filtering(state: PipelineState) -> PipelineState:
    adata = sc.read_h5ad(WORKSPACE / "_raw.h5ad")

    adata.var["mt"] = adata.var_names.str.startswith("MT-")
    sc.pp.calculate_qc_metrics(adata, qc_vars=["mt"], inplace=True)

    sweep = [
        {"min_genes": 200, "max_genes": 6000, "max_pct_mito": 25},
        {"min_genes": 300, "max_genes": 5000, "max_pct_mito": 20},
        {"min_genes": 500, "max_genes": 4000, "max_pct_mito": 15},
        {"min_genes": 800, "max_genes": 3500, "max_pct_mito": 10},
    ]
    trials = []
    for t in sweep:
        mask = (
            (adata.obs["n_genes_by_counts"] >= t["min_genes"])
            & (adata.obs["n_genes_by_counts"] <= t["max_genes"])
            & (adata.obs["pct_counts_mt"] <= t["max_pct_mito"])
        )
        retained = int(mask.sum())
        trials.append({
            "threshold_label": f"g{t['min_genes']}-{t['max_genes']}_mt{t['max_pct_mito']}",
            "cells_retained": retained,
            "pct_retained": round(100 * retained / adata.n_obs, 1),
            **t,
        })

    metrics = {
        "total_cells": adata.n_obs,
        "total_genes": adata.n_vars,
        "median_genes": round(float(np.median(adata.obs["n_genes_by_counts"])), 1),
        "median_counts": round(float(np.median(adata.obs["total_counts"])), 1),
        "pct_high_mt": round(float((adata.obs["pct_counts_mt"] > 20).mean() * 100), 2),
        "trials": trials,
    }

    reasoning = _llm_reason(
        system="You are an expert single-cell bioinformatician. Be concise.",
        user=(
            f"Dataset: {adata.n_obs} cells, {adata.n_vars} genes. "
            f"Median genes/cell: {metrics['median_genes']}. "
            f"Cells with >20% MT: {metrics['pct_high_mt']}%. "
            f"Threshold sweep results: {json.dumps(trials)}. "
            "Recommend the best threshold profile and explain why in 3-4 sentences."
        ),
    )

    _write_gate(1, "QC Filtering", "ready_for_review",
                proposal=trials[1], reasoning=reasoning,
                metrics=metrics, options=trials)

    decision = _wait_for_decision()
    label = decision.get("chosen_threshold", trials[1]["threshold_label"])
    chosen = next((t for t in trials if t["threshold_label"] == label), trials[1])

    mask = (
        (adata.obs["n_genes_by_counts"] >= chosen["min_genes"])
        & (adata.obs["n_genes_by_counts"] <= chosen["max_genes"])
        & (adata.obs["pct_counts_mt"] <= chosen["max_pct_mito"])
    )
    adata_f = adata[mask].copy()
    adata_f.write_h5ad(WORKSPACE / "_filtered.h5ad")
    logger.info("After filtering: %d cells", adata_f.n_obs)

    return {**state, "gate_id": 1, "filtering": {**chosen, "cells_after": adata_f.n_obs}}


# ── Node 2: Normalize → PCA + Gate 2 ─────────────────────────────────────────

def gate2_pca(state: PipelineState) -> PipelineState:
    adata = sc.read_h5ad(WORKSPACE / "_filtered.h5ad")

    sc.pp.normalize_total(adata, target_sum=1e4)
    sc.pp.log1p(adata)
    sc.pp.highly_variable_genes(adata, n_top_genes=2000)
    sc.tl.pca(adata, svd_solver="arpack")

    var_ratio = adata.uns["pca"]["variance_ratio"].tolist()
    cumvar    = np.cumsum(var_ratio).tolist()

    diffs = np.diff(var_ratio[:50])
    elbow = int(np.argmin(diffs) + 2)

    options = [
        {"label": f"Elbow ({elbow} PCs)",      "n_pcs": elbow, "var_explained": round(cumvar[elbow - 1] * 100, 1)},
        {"label": "Standard (30 PCs)",          "n_pcs": 30,    "var_explained": round(cumvar[29] * 100, 1)},
        {"label": "Conservative (50 PCs)",      "n_pcs": 50,    "var_explained": round(cumvar[49] * 100, 1)},
    ]

    reasoning = _llm_reason(
        system="You are an expert single-cell bioinformatician. Be concise.",
        user=(
            f"Variance explained by first 50 PCs (percent): "
            f"{[round(v * 100, 2) for v in var_ratio[:50]]}. "
            f"Elbow heuristic: PC {elbow}. "
            "Recommend n_pcs and explain in 3-4 sentences."
        ),
    )

    _write_gate(2, "PCA Dimensionality", "ready_for_review",
                proposal=options[0], reasoning=reasoning,
                metrics={"variance_ratio": var_ratio[:50], "cumulative": cumvar[:50]},
                options=options)

    decision = _wait_for_decision()
    n_pcs = int(decision.get("n_pcs", elbow))

    adata.write_h5ad(WORKSPACE / "_pca.h5ad")
    return {**state, "gate_id": 2,
            "pca": {"n_pcs": n_pcs, "var_explained": round(cumvar[n_pcs - 1] * 100, 1)}}


# ── Node 3: Neighbors → UMAP → Leiden + Gate 3 ───────────────────────────────

def gate3_clustering(state: PipelineState) -> PipelineState:
    adata = sc.read_h5ad(WORKSPACE / "_pca.h5ad")
    n_pcs = state["pca"]["n_pcs"]

    sc.pp.neighbors(adata, n_pcs=n_pcs)
    sc.tl.umap(adata)

    resolutions = [0.2, 0.4, 0.6, 0.8, 1.0]
    options = []
    for res in resolutions:
        key = f"leiden_{res}"
        sc.tl.leiden(adata, resolution=res, key_added=key)
        n_clusters = int(adata.obs[key].nunique())
        options.append({"resolution": res, "n_clusters": n_clusters,
                        "label": f"res={res} → {n_clusters} clusters"})

    umap_coords = adata.obsm["X_umap"].tolist()

    reasoning = _llm_reason(
        system="You are an expert single-cell bioinformatician. Be concise.",
        user=(
            f"Dataset: {adata.n_obs} cells. "
            f"Clustering sweep: {json.dumps(options)}. "
            "Recommend a Leiden resolution and explain in 3-4 sentences."
        ),
    )

    _write_gate(3, "Clustering Resolution", "ready_for_review",
                proposal=options[2],  # default 0.6
                reasoning=reasoning,
                metrics={"n_cells": adata.n_obs, "umap_sample": umap_coords[:500],
                         "resolution_sweep": options},
                options=options)

    decision = _wait_for_decision()
    resolution = float(decision.get("resolution", 0.6))
    adata.obs["leiden"] = adata.obs[f"leiden_{resolution}"]

    adata.write_h5ad(WORKSPACE / "_clustered.h5ad")
    return {**state, "gate_id": 3,
            "clustering": {"resolution": resolution,
                           "n_clusters": int(adata.obs["leiden"].nunique())}}


# ── Node 4: Marker genes → annotation + Gate 4 ───────────────────────────────

def gate4_annotation(state: PipelineState) -> PipelineState:
    adata = sc.read_h5ad(WORKSPACE / "_clustered.h5ad")

    sc.tl.rank_genes_groups(adata, groupby="leiden", method="wilcoxon")
    clusters = sorted(adata.obs["leiden"].unique().tolist(), key=int)

    top_markers: dict[str, list[str]] = {}
    for c in clusters:
        top_markers[c] = (
            sc.get.rank_genes_groups_df(adata, group=c)
            .head(10)["names"]
            .tolist()
        )

    reasoning = _llm_reason(
        system=(
            "You are an expert single-cell bioinformatician. "
            "Annotate clusters based on marker genes. "
            'Reply ONLY with valid JSON in the form {"0": "T cell", "1": "B cell", ...}.'
        ),
        user=f"Top 10 marker genes per cluster:\n{json.dumps(top_markers, indent=2)}",
    )

    try:
        start = reasoning.find("{")
        end   = reasoning.rfind("}") + 1
        proposed = json.loads(reasoning[start:end])
    except Exception:
        proposed = {c: f"Cluster {c}" for c in clusters}

    options = [
        {"cluster": c,
         "proposed_label": proposed.get(c, f"Cluster {c}"),
         "top_markers": top_markers[c][:5]}
        for c in clusters
    ]

    _write_gate(4, "Cell-type Annotation", "ready_for_review",
                proposal=proposed, reasoning=reasoning,
                metrics={"n_clusters": len(clusters), "top_markers": top_markers},
                options=options)

    decision = _wait_for_decision()
    final_labels = decision.get("labels", proposed)

    adata.obs["cell_type"] = adata.obs["leiden"].map(final_labels).fillna("Unknown")
    output = state.get("output_path", str(WORKSPACE / "adata_final.h5ad"))
    adata.write_h5ad(output)
    logger.info("Saved final .h5ad to %s", output)

    return {**state, "gate_id": 4, "annotation": {"labels": final_labels}}


# ── Node 5: wrap-up ───────────────────────────────────────────────────────────

def export_done(state: PipelineState) -> PipelineState:
    _write_gate(5, "Complete", "complete",
                proposal={}, reasoning="Pipeline finished. Final .h5ad saved.",
                metrics={k: state[k] for k in ("filtering", "pca", "clustering", "annotation")},
                options=[])
    logger.info("Pipeline complete.")
    return {**state, "gate_id": 5}


# ── Graph assembly ────────────────────────────────────────────────────────────

def build_pipeline() -> Any:
    g = StateGraph(PipelineState)
    for name, fn in [
        ("load",        load_data),
        ("gate1",       gate1_filtering),
        ("gate2",       gate2_pca),
        ("gate3",       gate3_clustering),
        ("gate4",       gate4_annotation),
        ("export",      export_done),
    ]:
        g.add_node(name, fn)

    g.set_entry_point("load")
    g.add_edge("load",   "gate1")
    g.add_edge("gate1",  "gate2")
    g.add_edge("gate2",  "gate3")
    g.add_edge("gate3",  "gate4")
    g.add_edge("gate4",  "export")
    g.add_edge("export", END)
    return g.compile()


# ── Entry point ───────────────────────────────────────────────────────────────

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="scChat HITL pipeline")
    parser.add_argument("h5ad", help="Path to input .h5ad file")
    parser.add_argument("--output", default="workspace/adata_final.h5ad")
    args = parser.parse_args()

    build_pipeline().invoke({
        "h5ad_path":   args.h5ad,
        "output_path": args.output,
        "gate_id":     0,
        "filtering":   {},
        "pca":         {},
        "clustering":  {},
        "annotation":  {},
    })
