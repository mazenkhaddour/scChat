"""Centralised Streamlit session-state initialisation."""

import streamlit as st


def init_session() -> None:
    defaults: dict = {
        # Chat history
        "messages": [],
        # File bridge paths
        "gate_state_path":  "workspace/gate_state.json",
        "decision_path":    "workspace/human_decision.json",
        # Latest parsed gate state dict (None until backend writes it)
        "gate_state": None,
        # Convenience mirror of gate_state["gate_id"] for quick reads
        "gate_id": 0,
    }
    for key, value in defaults.items():
        if key not in st.session_state:
            st.session_state[key] = value
