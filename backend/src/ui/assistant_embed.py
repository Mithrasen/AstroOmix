"""The Research Assistant, embedded inside a tab.

One assistant, three placements. The agent, the tools and the RUNTIME GROUNDING
GUARD are the same objects the standalone page used — this module only changes
where the conversation is drawn and which example questions are offered. It calls
`ask()`, which verifies every figure against the tool results before returning,
and it renders `withheld_notice()` when a figure had to be held back. Nothing here
may weaken that path.

Each placement gets its own `scope` so the two assistants on two tabs keep
separate conversations and separate widget keys.
"""

from __future__ import annotations

import streamlit as st

from src.agent.agent import KeyNotConfigured, ask
from src.agent.keys import NOT_CONFIGURED_MESSAGE, resolve_api_key
from src.ui.assistant_page import _render_tool_calls, withheld_notice
from src.ui.icons import orbit


def render_embedded(scope: str, blurb: str, chips: list[str]) -> None:
    """Draw the assistant for one tab.

    `scope` namespaces the widget keys and the transcript. `chips` are the
    clickable example questions for this tab — they fire the identical `ask()`
    path a typed question does.
    """
    st.markdown(
        f'<div class="mc-rule">{orbit(22)}<strong>Research Assistant</strong></div>',
        unsafe_allow_html=True,
    )

    if not resolve_api_key().configured:
        # Graceful, per-tab. The rest of the tab keeps working.
        st.info(NOT_CONFIGURED_MESSAGE, icon="🔑")
        return

    st.caption(blurb)

    log_key = f"chat_{scope}"
    pending_key = f"pending_{scope}"
    if log_key not in st.session_state:
        st.session_state[log_key] = []

    # --- example question chips ---------------------------------------------
    st.markdown('<div class="chips-label">Try one of these</div>',
                unsafe_allow_html=True)
    columns = st.columns(len(chips))
    for index, (column, chip) in enumerate(zip(columns, chips)):
        with column:
            if st.button(chip, key=f"chip_{scope}_{index}", width="stretch"):
                st.session_state[pending_key] = chip
                st.rerun()

    # --- free text -----------------------------------------------------------
    with st.form(key=f"form_{scope}", clear_on_submit=True, border=False):
        left, right = st.columns([6, 1])
        with left:
            typed = st.text_input(
                "Ask anything",
                key=f"text_{scope}",
                placeholder="…or ask your own question about this analysis",
                label_visibility="collapsed",
            )
        with right:
            submitted = st.form_submit_button("Ask", width="stretch",
                                              type="primary")

    question = st.session_state.pop(pending_key, None)
    if submitted and typed.strip():
        question = typed.strip()

    # --- transcript ----------------------------------------------------------
    for entry in st.session_state[log_key]:
        with st.chat_message(entry["role"]):
            if entry["role"] == "assistant":
                _render_tool_calls(entry.get("tool_calls", []))
                withheld_notice(entry.get("withheld"))
            st.markdown(entry["text"])

    if not question:
        return

    st.session_state[log_key].append({"role": "user", "text": question})
    with st.chat_message("user"):
        st.markdown(question)

    with st.chat_message("assistant"):
        # Agentic loops run many seconds — several tool calls, and possibly a
        # grounding self-correction. Without a visible state it reads as frozen.
        with st.spinner("Analysing — calling the analysis code, then verifying "
                        "every figure against it…"):
            try:
                reply = ask(question)
            except KeyNotConfigured:
                st.info(NOT_CONFIGURED_MESSAGE, icon="🔑")
                return
            except Exception as error:  # noqa: BLE001
                st.error(f"The assistant failed: {type(error).__name__}: {error}")
                return

        _render_tool_calls(reply.tool_calls)
        # The runtime guard already redacted anything it could not trace. Say so.
        withheld_notice(reply.withheld)
        st.markdown(reply.text)

        if reply.stopped_early:
            st.warning("Stopped at the tool-call limit.", icon="⚠️")

    st.session_state[log_key].append({
        "role": "assistant",
        "text": reply.text,
        "withheld": reply.withheld,
        "tool_calls": [
            {"name": c.name, "arguments": c.arguments, "result": c.result}
            for c in reply.tool_calls
        ],
    })


# The example questions per tab. Each set includes a METHOD question, because
# "why this model" is the thing a reviewer actually wants to interrogate.
DE_CHIPS = [
    "What are the top differentially expressed genes in soleus?",
    "Why does this use DESeq2 instead of the built-in NB-GLM model?",
    "Which genes are most robust vs. weakest evidence?",
]

FORECAST_CHIPS = [
    "Should I trust LightGBM's day-300 prediction for neutrophils?",
    "Why leave-one-out cross-validation instead of a train/test split?",
    "Is ARIMA or Prophet better for hemoglobin, and why?",
]

METHODS_CHIPS = [
    "Why pydeseq2 rather than R DESeq2 for the deployed app?",
    "How does the runtime grounding guard work?",
    "Why is the n=3 forecast blocked?",
]
