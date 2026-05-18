"""Left-column chat panel — placeholder implementation."""

import json
from pathlib import Path

import streamlit as st


def render_chat_panel() -> None:
    """Render the conversational control deck in the left column."""
    st.subheader("Control Deck")

    # ── Message history ──────────────────────────────────────────────────────
    for msg in st.session_state.messages:
        with st.chat_message(msg["role"]):
            st.markdown(msg["content"])

    # ── Threshold selector (appears once backend sweep is complete) ──────────
    if st.session_state.backend_ready and st.session_state.trials_df is not None:
        _render_threshold_selector()

    # ── Chat input ───────────────────────────────────────────────────────────
    if prompt := st.chat_input("Ask the QC assistant…"):
        st.session_state.messages.append({"role": "user", "content": prompt})
        with st.chat_message("user"):
            st.markdown(prompt)

        # TODO: wire to Ollama / LangGraph backend via REST or file-poll
        reply = "[LLM placeholder] Response will appear here once the agent pipeline is connected."
        st.session_state.messages.append({"role": "assistant", "content": reply})
        with st.chat_message("assistant"):
            st.markdown(reply)


def _render_threshold_selector() -> None:
    """Dropdown + submit button for choosing a filtering threshold."""
    df = st.session_state.trials_df
    options = df["threshold_label"].tolist() if "threshold_label" in df.columns else []

    st.divider()
    st.markdown("**Select a filtering threshold to proceed:**")

    chosen = st.selectbox(
        label="Threshold profile",
        options=options,
        key="selected_threshold",
    )

    if st.button("Submit threshold", type="primary"):
        decision = {"chosen_threshold": chosen}
        Path(st.session_state.decision_path).parent.mkdir(parents=True, exist_ok=True)
        Path(st.session_state.decision_path).write_text(json.dumps(decision))
        st.success(f"Decision written — backend will resume with **{chosen}**.")
        st.session_state.backend_ready = False  # hide selector until next sweep
