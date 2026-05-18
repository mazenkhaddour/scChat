"""scChat — scRNA-seq QC cockpit entry point."""

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
st.title("scChat — single-cell QC Cockpit")
st.caption("Conversational quality-control dashboard · powered by Ollama + LangGraph on HPC")
st.divider()

# ── Two-column layout ─────────────────────────────────────────────────────────
left, right = st.columns([1, 1], gap="large")

with left:
    render_chat_panel()

with right:
    render_viz_panel()

# ── Polling loop: rerun every 3 s while backend hasn't signalled ready ────────
if not st.session_state.backend_ready:
    time.sleep(3)
    st.rerun()
