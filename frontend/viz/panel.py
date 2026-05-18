"""Right-column visualisation panel — placeholder implementation."""

import json
from pathlib import Path

import pandas as pd
import plotly.graph_objects as go
import streamlit as st


def render_viz_panel() -> None:
    """Render the visual insight deck in the right column."""
    st.subheader("Visual Insight Deck")

    trials_path = Path(st.session_state.trials_path)

    if not trials_path.exists():
        _render_waiting_placeholder()
        return

    df = _load_trials(trials_path)
    if df is None or df.empty:
        st.warning("trials_output.json found but contains no data yet.")
        return

    # Cache into session state so the chat panel can read it
    st.session_state.trials_df = df
    st.session_state.backend_ready = True

    _render_dataframe(df)
    st.divider()
    _render_decay_curve(df)


# ── helpers ──────────────────────────────────────────────────────────────────

def _render_waiting_placeholder() -> None:
    st.info("Waiting for the backend to produce `workspace/trials_output.json`…")
    # Placeholder decay-curve outline so the layout doesn't collapse
    fig = go.Figure()
    fig.update_layout(
        title="Library complexity decay (no data yet)",
        xaxis_title="Threshold",
        yaxis_title="Cells retained",
        height=400,
        paper_bgcolor="rgba(0,0,0,0)",
        plot_bgcolor="rgba(0,0,0,0)",
    )
    st.plotly_chart(fig, use_container_width=True)


def _load_trials(path: Path) -> pd.DataFrame | None:
    try:
        data = json.loads(path.read_text())
        return pd.DataFrame(data)
    except Exception as exc:  # noqa: BLE001
        st.error(f"Could not parse trials JSON: {exc}")
        return None


def _render_dataframe(df: pd.DataFrame) -> None:
    st.markdown("**Filtering trial results**")
    st.dataframe(df, use_container_width=True, hide_index=True)


def _render_decay_curve(df: pd.DataFrame) -> None:
    """Plot cells-retained vs threshold if the expected columns are present."""
    # Expected schema from agent_pipeline.py (to be confirmed):
    #   threshold_label | cells_retained | pct_retained
    x_col = "threshold_label" if "threshold_label" in df.columns else df.columns[0]
    y_col = "cells_retained" if "cells_retained" in df.columns else df.columns[1] if len(df.columns) > 1 else None

    fig = go.Figure()

    if y_col:
        fig.add_trace(go.Scatter(
            x=df[x_col],
            y=df[y_col],
            mode="lines+markers",
            name="Cells retained",
            line={"color": "#00b4d8", "width": 2},
            marker={"size": 7},
        ))
        if "pct_retained" in df.columns:
            fig.add_trace(go.Scatter(
                x=df[x_col],
                y=df["pct_retained"],
                mode="lines+markers",
                name="% retained",
                yaxis="y2",
                line={"color": "#ff6b6b", "dash": "dot"},
                marker={"size": 6},
            ))
            fig.update_layout(
                yaxis2={"title": "% retained", "overlaying": "y", "side": "right", "range": [0, 100]},
            )

    fig.update_layout(
        title="Library complexity decay across thresholds",
        xaxis_title="Threshold profile",
        yaxis_title="Cells retained",
        height=420,
        legend={"orientation": "h", "y": -0.2},
    )
    st.plotly_chart(fig, use_container_width=True)
