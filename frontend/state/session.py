"""Centralised Streamlit session-state initialisation."""

import streamlit as st


def init_session() -> None:
    """Seed all session-state keys on first load."""
    defaults: dict = {
        # Chat history: list of {"role": "user"|"assistant", "content": str}
        "messages": [],
        # Path the backend writes completed trial data to
        "trials_path": "workspace/trials_output.json",
        # Path this frontend writes the user decision to
        "decision_path": "workspace/human_decision.json",
        # Cached dataframe of the latest trial results (None until loaded)
        "trials_df": None,
        # Currently selected threshold key from the dropdown
        "selected_threshold": None,
        # Simple flag: has the backend finished its sweep?
        "backend_ready": False,
    }
    for key, value in defaults.items():
        if key not in st.session_state:
            st.session_state[key] = value
