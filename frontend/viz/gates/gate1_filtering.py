"""Gate 1 — QC Filtering: bar chart + threshold selector."""

import json
from pathlib import Path

import pandas as pd
import plotly.graph_objects as go
import streamlit as st


def render(gate_state: dict) -> None:
    metrics  = gate_state.get("metrics", {})
    options  = gate_state.get("options", [])
    proposal = gate_state.get("agent_proposal", {})

    # ── Summary cards ─────────────────────────────────────────────────────────
    c1, c2, c3, c4 = st.columns(4)
    c1.metric("Total cells",    f"{metrics.get('total_cells', '—'):,}")
    c2.metric("Total genes",    f"{metrics.get('total_genes', '—'):,}")
    c3.metric("Median genes/cell", metrics.get("median_genes", "—"))
    c4.metric("Cells >20% MT",  f"{metrics.get('pct_high_mt', '—')}%")

    st.divider()

    # ── Decay bar chart ───────────────────────────────────────────────────────
    if options:
        df = pd.DataFrame(options)
        fig = go.Figure()
        fig.add_trace(go.Bar(
            x=df["threshold_label"],
            y=df["cells_retained"],
            text=df["pct_retained"].astype(str) + "%",
            textposition="outside",
            marker_color="#00b4d8",
        ))
        fig.update_layout(
            title="Cells retained per threshold profile",
            xaxis_title="Threshold",
            yaxis_title="Cells retained",
            height=380,
            margin={"t": 50, "b": 80},
        )
        st.plotly_chart(fig, use_container_width=True)

    # ── Decision widget ───────────────────────────────────────────────────────
    st.markdown("### Your decision")
    labels = [o["threshold_label"] for o in options]
    default_idx = labels.index(proposal.get("threshold_label", labels[1])) if labels else 0

    chosen = st.selectbox("Select a threshold profile", labels,
                          index=default_idx, key="g1_threshold")

    if st.button("Confirm & continue →", type="primary", key="g1_submit"):
        _write_decision({"chosen_threshold": chosen})
        st.success(f"Decision sent: **{chosen}**")


def _write_decision(payload: dict) -> None:
    Path("workspace").mkdir(exist_ok=True)
    Path("workspace/human_decision.json").write_text(json.dumps(payload))
