"""Gate 2 — PCA dimensionality: elbow plot + n_pcs selector."""

import json
from pathlib import Path

import plotly.graph_objects as go
import streamlit as st


def render(gate_state: dict) -> None:
    metrics  = gate_state.get("metrics", {})
    options  = gate_state.get("options", [])
    proposal = gate_state.get("agent_proposal", {})

    var_ratio  = metrics.get("variance_ratio", [])
    cumulative = metrics.get("cumulative", [])

    # ── Elbow plot ─────────────────────────────────────────────────────────────
    if var_ratio:
        pcs = list(range(1, len(var_ratio) + 1))
        fig = go.Figure()
        fig.add_trace(go.Scatter(
            x=pcs, y=[v * 100 for v in var_ratio],
            mode="lines+markers", name="Per-PC variance %",
            line={"color": "#00b4d8"},
        ))
        fig.add_trace(go.Scatter(
            x=pcs, y=[v * 100 for v in cumulative],
            mode="lines", name="Cumulative variance %",
            line={"color": "#ff6b6b", "dash": "dot"},
            yaxis="y2",
        ))
        proposed_pc = proposal.get("n_pcs")
        if proposed_pc:
            fig.add_vline(x=proposed_pc, line_dash="dash", line_color="#ffd166",
                          annotation_text=f"Proposed: PC {proposed_pc}",
                          annotation_position="top right")
        fig.update_layout(
            title="PCA variance explained",
            xaxis_title="Principal component",
            yaxis_title="Variance explained (%)",
            yaxis2={"title": "Cumulative (%)", "overlaying": "y",
                    "side": "right", "range": [0, 100]},
            legend={"orientation": "h", "y": -0.25},
            height=400,
        )
        st.plotly_chart(fig, use_container_width=True)

    # ── Decision widget ───────────────────────────────────────────────────────
    st.markdown("### Your decision")
    labels = [o["label"] for o in options]
    n_pcs_map = {o["label"]: o["n_pcs"] for o in options}
    default_idx = 0

    chosen_label = st.selectbox("Select number of PCs", labels,
                                index=default_idx, key="g2_npcs")
    chosen_npcs  = n_pcs_map[chosen_label]

    if options:
        chosen_opt = next(o for o in options if o["label"] == chosen_label)
        st.caption(f"Variance explained: **{chosen_opt['var_explained']}%**")

    if st.button("Confirm & continue →", type="primary", key="g2_submit"):
        _write_decision({"n_pcs": chosen_npcs})
        st.success(f"Decision sent: **{chosen_npcs} PCs**")


def _write_decision(payload: dict) -> None:
    Path("workspace").mkdir(exist_ok=True)
    Path("workspace/human_decision.json").write_text(json.dumps(payload))
