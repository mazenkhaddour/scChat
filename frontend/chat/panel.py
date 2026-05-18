"""Left-column chat panel — Ollama-backed, gate-aware."""

import httpx
import streamlit as st

OLLAMA_URL   = "http://localhost:11434/api/chat"
OLLAMA_MODEL = "qwen2.5-coder:14b"
REQUEST_TIMEOUT = 120


def render_chat_panel() -> None:
    st.subheader("Ask the QC Assistant")

    gate_state = st.session_state.get("gate_state") or {}
    gate_name  = gate_state.get("gate_name", "")
    reasoning  = gate_state.get("agent_reasoning", "")

    if gate_name:
        st.caption(f"Current stage: **{gate_name}**")

    # ── Message history ────────────────────────────────────────────────────────
    for msg in st.session_state.messages:
        with st.chat_message(msg["role"]):
            st.markdown(msg["content"])

    # ── Chat input ─────────────────────────────────────────────────────────────
    if prompt := st.chat_input("Ask about the current analysis step…"):
        st.session_state.messages.append({"role": "user", "content": prompt})
        with st.chat_message("user"):
            st.markdown(prompt)

        with st.chat_message("assistant"):
            with st.spinner("Thinking…"):
                reply = _call_ollama(
                    messages=st.session_state.messages,
                    system=_build_system_prompt(gate_name, reasoning, gate_state),
                )
            st.markdown(reply)

        st.session_state.messages.append({"role": "assistant", "content": reply})


# ── Helpers ───────────────────────────────────────────────────────────────────

def _build_system_prompt(gate_name: str, reasoning: str, gate_state: dict) -> str:
    base = (
        "You are scChat, an expert single-cell RNA-seq bioinformatician assistant. "
        "You are helping the user review analysis decisions on an HPC cluster. "
        "Be concise, precise, and cite biological reasoning when relevant."
    )
    if not gate_name:
        return base

    metrics_summary = ""
    metrics = gate_state.get("metrics", {})
    if metrics:
        # Flatten top-level numeric values only to keep the prompt short
        kv = {k: v for k, v in metrics.items() if not isinstance(v, (list, dict))}
        if kv:
            metrics_summary = f"\nKey metrics: {kv}"

    return (
        f"{base}\n\n"
        f"Current analysis gate: {gate_name}.\n"
        f"Agent reasoning: {reasoning}{metrics_summary}\n\n"
        "Answer the user's question in the context of this gate. "
        "If they ask about a parameter, explain the biological implication."
    )


def _call_ollama(messages: list[dict], system: str) -> str:
    payload = {
        "model":    OLLAMA_MODEL,
        "messages": [{"role": "system", "content": system}] + messages,
        "stream":   False,
    }
    try:
        resp = httpx.post(OLLAMA_URL, json=payload, timeout=REQUEST_TIMEOUT)
        resp.raise_for_status()
        return resp.json()["message"]["content"]
    except httpx.ConnectError:
        return (
            "**Ollama server is not reachable** (localhost:11434). "
            "Make sure `launch_ollama.sh` is running on the GPU node."
        )
    except Exception as exc:
        return f"**Ollama error:** {exc}"
