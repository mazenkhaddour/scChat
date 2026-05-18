"""Right-column visualisation panel — dispatches to the active gate renderer."""

import json
import time
from pathlib import Path

import streamlit as st

from frontend.viz.gates import (
    gate1_filtering,
    gate2_pca,
    gate3_clustering,
    gate4_annotation,
)

_GATE_RENDERERS = {
    1: gate1_filtering.render,
    2: gate2_pca.render,
    3: gate3_clustering.render,
    4: gate4_annotation.render,
}


def render_viz_panel() -> None:
    gate_state = _poll_gate_state()

    if gate_state is None:
        _render_idle()
        return

    gate_id = gate_state.get("gate_id", 0)
    status  = gate_state.get("status", "")

    if gate_id == 5 or status == "complete":
        _render_complete(gate_state)
        return

    renderer = _GATE_RENDERERS.get(gate_id)
    if renderer is None:
        st.info("Pipeline initialising — waiting for the first gate…")
        return

    # ── Agent reasoning expander ───────────────────────────────────────────────
    reasoning = gate_state.get("agent_reasoning", "")
    if reasoning:
        with st.expander("Agent reasoning", expanded=True):
            st.markdown(reasoning)

    st.divider()
    renderer(gate_state)


# ── Helpers ───────────────────────────────────────────────────────────────────

def _poll_gate_state() -> dict | None:
    path = Path(st.session_state.gate_state_path)
    if not path.exists():
        return None
    try:
        data = json.loads(path.read_text())
        st.session_state.gate_state = data
        st.session_state.gate_id    = data.get("gate_id", 0)
        return data
    except (json.JSONDecodeError, OSError):
        return st.session_state.get("gate_state")


def _render_idle() -> None:
    st.info("Waiting for the pipeline to start…")
    st.caption("Make sure `launch_cockpit.sh` is running on the compute node.")


def _render_complete(gate_state: dict) -> None:
    st.success("Pipeline complete!")
    metrics = gate_state.get("metrics", {})
    if metrics:
        st.json(metrics)
    st.balloons()
