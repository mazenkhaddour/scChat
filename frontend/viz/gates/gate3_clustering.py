"""Gate 3 — Clustering resolution: sweep bar + UMAP scatter + slider."""

import json
from pathlib import Path

import numpy as np
import plotly.graph_objects as go
import streamlit as st


def render(gate_state: dict) -> None:
    metrics  = gate_state.get("metrics", {})
    options  = gate_state.get("options", [])
    proposal = gate_state.get("agent_proposal", {})

    sweep      = metrics.get("resolution_sweep", options)
    umap_sample = metrics.get("umap_sample", [])

    col_left, col_right = st.columns([1, 1])

    # ── Cluster count sweep ────────────────────────────────────────────────────
    with col_left:
        if sweep:
            resolutions = [o["resolution"] for o in sweep]
            n_clusters  = [o["n_clusters"]  for o in sweep]
            fig = go.Figure(go.Bar(
                x=[str(r) for r in resolutions],
                y=n_clusters,
                text=n_clusters,
                textposition="outside",
                marker_color="#90e0ef",
            ))
            fig.update_layout(
                title="Clusters vs resolution",
                xaxis_title="Leiden resolution",
                yaxis_title="Number of clusters",
                height=350,
            )
            st.plotly_chart(fig, use_container_width=True)

    # ── UMAP preview (sampled) ─────────────────────────────────────────────────
    with col_right:
        if umap_sample:
            coords = np.array(umap_sample)
            fig = go.Figure(go.Scatter(
                x=coords[:, 0], y=coords[:, 1],
                mode="markers",
                marker={"size": 3, "color": "#caf0f8", "opacity": 0.6},
            ))
            fig.update_layout(
                title=f"UMAP preview (n={len(umap_sample):,} sampled cells)",
                xaxis={"visible": False}, yaxis={"visible": False},
                height=350,
                plot_bgcolor="#0e1117",
                paper_bgcolor="#0e1117",
                font_color="white",
            )
            st.plotly_chart(fig, use_container_width=True)

    # ── Decision widget ────────────────────────────────────────────────────────
    st.markdown("### Your decision")
    available_res = [o["resolution"] for o in sweep] if sweep else [0.2, 0.4, 0.6, 0.8, 1.0]
    proposed_res  = float(proposal.get("resolution", 0.6))
    default_idx   = available_res.index(proposed_res) if proposed_res in available_res else 2

    chosen_res = st.select_slider(
        "Leiden resolution",
        options=available_res,
        value=available_res[default_idx],
        key="g3_resolution",
    )

    if sweep:
        match = next((o for o in sweep if o["resolution"] == chosen_res), None)
        if match:
            st.caption(f"→ **{match['n_clusters']} clusters** at resolution {chosen_res}")

    if st.button("Confirm & continue →", type="primary", key="g3_submit"):
        _write_decision({"resolution": chosen_res})
        st.success(f"Decision sent: resolution **{chosen_res}**")


def _write_decision(payload: dict) -> None:
    Path("workspace").mkdir(exist_ok=True)
    Path("workspace/human_decision.json").write_text(json.dumps(payload))
