"""scChat — HITL Agentic QC Cockpit entry point."""

import time

import streamlit as st

from frontend.chat.panel import render_chat_panel
from frontend.state.session import init_session
from frontend.viz.panel import render_viz_panel

# ── Page config ───────────────────────────────────────────────────────────────
st.set_page_config(
    page_title="scChat · QC Cockpit",
    page_icon="🧬",
    layout="wide",
    initial_sidebar_state="collapsed",
)

# ── Session init ──────────────────────────────────────────────────────────────
init_session()

# ── Header ────────────────────────────────────────────────────────────────────
logo_col, title_col = st.columns([1, 6], gap="medium")
with logo_col:
    st.image("scChat.jpeg", width=120)
with title_col:
    st.title("scChat — HITL Agentic QC Cockpit")
    st.caption("Human-in-the-Loop agentic pipeline · Ollama + LangGraph on HPC")

st.divider()

# ── Gate progress bar ─────────────────────────────────────────────────────────
GATES = ["Filtering", "PCA", "Clustering", "Annotation", "Complete"]
gate_id = st.session_state.get("gate_id", 0)

progress_cols = st.columns(len(GATES))
for i, (col, label) in enumerate(zip(progress_cols, GATES), start=1):
    with col:
        if i < gate_id:
            st.markdown(f"✅ **{label}**")
        elif i == gate_id:
            st.markdown(f"🔄 **{label}**")
        else:
            st.markdown(f"⬜ {label}")

st.divider()

# ── Two-column layout ─────────────────────────────────────────────────────────
left, right = st.columns([1, 1], gap="large")

with left:
    render_chat_panel()

with right:
    render_viz_panel()

# ── Polling: rerun every 3 s while waiting for a gate or pipeline to advance ──
current_gate_id    = st.session_state.get("gate_id", 0)
current_gate_state = st.session_state.get("gate_state") or {}
pipeline_done      = current_gate_state.get("status") == "complete"

if not pipeline_done:
    time.sleep(3)
    st.rerun()
