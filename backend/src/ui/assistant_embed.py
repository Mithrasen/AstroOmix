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
from src.agent.keys import NOT_CONFIGURED_MESSAGE, diagnose_secrets, resolve_api_key
from src.ui.assistant_page import _render_tool_calls
from src.ui.icons import orbit
from src.ui.literature_cards import render_papers, render_signals

# The verifier is FINAL. When it withholds, the model's own draft is not shown at
# all — because the draft is exactly where the arguing happens: it debates the
# check, insists its answer "stands", and reprints the very numbers that were
# withheld, which defeats the withholding. So on failure the prose is dropped and
# this replaces it. Nothing about the guard's logic changes; only what is drawn.
WITHHELD_MESSAGE = (
    "Some statements could not be matched reliably to the analysis output or to the "
    "retrieved literature, so the answer was withheld. You can inspect the verified "
    "results and the retrieved papers below, or ask again."
)


def _render_answer(text: str, withheld, tool_calls=()) -> None:
    """Draw an answer — or, if the verifier withheld anything, only the notice.

    Never renders the draft when `withheld` is non-empty. A partially-redacted
    draft still leaks: the surrounding sentences restate the suppressed figure in
    words, and the model's rebuttal of the verifier reads as though the check were
    wrong. One neutral message is the whole output. A fabricated PMID withholds on
    exactly the same terms as a fabricated number.

    The retrieved papers are drawn even when the prose is withheld: they are the
    tool's own output, not the model's, and the reader can still use them.
    """
    render_signals(tool_calls, withheld)

    if withheld:
        st.warning(WITHHELD_MESSAGE, icon="🛡️")
    else:
        st.markdown(text)

    render_papers(tool_calls)


def render_popout(scope: str, blurb: str, chips: list[str]) -> None:
    """The assistant as a compact pop-out. The analysis is the page; this assists it.

    Closed by default, and the trigger is a small right-aligned button rather than
    a full-width bar — `width="stretch"` made it span the page and dominate the
    thing it exists to support. The panel itself overlays; it does not displace the
    analysis below.

    `st.popover`, not `st.dialog`: a popover survives the rerun a widget click
    causes, whereas a modal that closed on every rerun would kill the agent
    mid-answer.
    """
    _, trigger = st.columns([3, 1])
    with trigger:
        with st.popover("🛰️  Research Assistant"):
            render_embedded(scope, blurb, chips)


def render_embedded(scope: str, blurb: str, chips: list[str]) -> None:
    """Draw the assistant for one tab.

    `scope` namespaces the widget keys and the transcript. `chips` are the
    clickable example questions — they fire the identical `ask()` path a typed
    question does.
    """
    st.markdown(
        f'<div class="mc-rule">{orbit(22)}<strong>Research Assistant</strong></div>',
        unsafe_allow_html=True,
    )

    if not resolve_api_key().configured:
        # Graceful, per-tab. The rest of the tab keeps working.
        st.info(NOT_CONFIGURED_MESSAGE, icon="🔑")
        # WHY it is not configured, in an expander. On Cloud there is no shell to
        # print from, so without this a correctly-set-but-unreadable secret is
        # indistinguishable from no secret at all. Key NAMES only — never a value.
        with st.expander("Diagnostics"):
            st.caption(diagnose_secrets())
        return

    st.caption(blurb)

    log_key = f"chat_{scope}"
    if log_key not in st.session_state:
        st.session_state[log_key] = []

    question = None

    # --- example question chips ---------------------------------------------
    # Handled in-run rather than via st.rerun(): a rerun from inside the popover
    # is survivable, but not needing one is simpler and cannot close the panel.
    st.markdown('<div class="chips-label">Try one of these</div>',
                unsafe_allow_html=True)
    columns = st.columns(len(chips))
    for index, (column, chip) in enumerate(zip(columns, chips)):
        with column:
            if st.button(chip, key=f"chip_{scope}_{index}", width="stretch"):
                question = chip

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

    if submitted and typed.strip():
        question = typed.strip()

    # --- transcript ----------------------------------------------------------
    for entry in st.session_state[log_key]:
        with st.chat_message(entry["role"]):
            if entry["role"] == "assistant":
                _render_tool_calls(entry.get("tool_calls", []))
                _render_answer(entry["text"], entry.get("withheld"),
                               entry.get("tool_calls", []))
            else:
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
        _render_answer(reply.text, reply.withheld, reply.tool_calls)

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
# Science questions, not implementation questions. A researcher wants to know what
# the data says; the "why this engine" reasoning belongs in Methods.
DE_CHIPS = [
    "Which genes show the strongest evidence of change?",
    "Which of these genes have published spaceflight or microgravity literature?",
    "Is the evidence for these genes from mouse, human, or cell models?",
    "What are the main limitations of this comparison?",
]

FORECAST_CHIPS = [
    "Should I trust LightGBM's day-300 prediction for neutrophils?",
    "Which blood markers changed most across the mission?",
    "What are the main limitations of this analysis?",
]
