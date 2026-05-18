"""Gate 4 — Cell-type annotation: editable label table + top-marker view."""

import json
from pathlib import Path

import pandas as pd
import streamlit as st


def render(gate_state: dict) -> None:
    options  = gate_state.get("options", [])
    metrics  = gate_state.get("metrics", {})

    if not options:
        st.info("No cluster data yet.")
        return

    # ── Top marker genes table (read-only) ────────────────────────────────────
    st.markdown("**Top marker genes per cluster**")
    marker_df = pd.DataFrame([
        {"Cluster": o["cluster"],
         "Top markers": ", ".join(o["top_markers"])}
        for o in options
    ])
    st.dataframe(marker_df, use_container_width=True, hide_index=True)

    st.divider()

    # ── Editable annotation table ─────────────────────────────────────────────
    st.markdown("### Your decision — edit labels as needed")
    edit_df = pd.DataFrame([
        {"Cluster": o["cluster"], "Cell type": o["proposed_label"]}
        for o in options
    ])

    edited = st.data_editor(
        edit_df,
        column_config={
            "Cluster":   st.column_config.TextColumn("Cluster", disabled=True),
            "Cell type": st.column_config.TextColumn("Cell type (editable)"),
        },
        use_container_width=True,
        hide_index=True,
        key="g4_labels",
        num_rows="fixed",
    )

    if st.button("Confirm & continue →", type="primary", key="g4_submit"):
        labels = dict(zip(edited["Cluster"], edited["Cell type"]))
        _write_decision({"labels": labels})
        st.success(f"Annotation sent for {len(labels)} clusters.")


def _write_decision(payload: dict) -> None:
    Path("workspace").mkdir(exist_ok=True)
    Path("workspace/human_decision.json").write_text(json.dumps(payload))
