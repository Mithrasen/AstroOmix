"""The Research Assistant page.

Shows every tool call the agent made, with its arguments and the raw result, so a
reader can check that each number in the answer came from a computed value rather
than from the model's imagination. That transparency is the point of the page, not
decoration.
"""

from __future__ import annotations

import json

import streamlit as st

from src.agent.agent import KeyNotConfigured, ask
from src.agent.keys import NOT_CONFIGURED_MESSAGE, resolve_api_key

EXAMPLES = [
    "Which blood markers recovered fastest after return?",
    "Should I trust LightGBM's day-300 prediction for neutrophils?",
    "What are the top differentially expressed genes in soleus?",
    "Is ARIMA or Prophet better for hemoglobin, and why?",
]


def render():
    st.header("Research Assistant")

    resolution = resolve_api_key()

    if not resolution.configured:
        # Friendly, not a crash. Every other page keeps working.
        st.info(NOT_CONFIGURED_MESSAGE, icon="🔑")
        st.caption(
            "The assistant only ever reports numbers computed by this app's own "
            "analysis code — it has no independent knowledge of these datasets."
        )
        return

    st.caption(
        "Asks the real analysis code and reports only what it returns. It never "
        "invents a forecast value, a metric, or a gene, and it surfaces the "
        "project's caveats rather than smoothing them over. "
        f"(Key source: `{resolution.source}`.)"
    )

    if "assistant_log" not in st.session_state:
        st.session_state.assistant_log = []

    with st.expander("Example questions", expanded=False):
        for example in EXAMPLES:
            st.markdown(f"- {example}")

    question = st.chat_input("Ask about the forecasts, the DE results, or the data…")

    for entry in st.session_state.assistant_log:
        with st.chat_message(entry["role"]):
            if entry["role"] == "assistant":
                _render_tool_calls(entry.get("tool_calls", []))
                if entry.get("withheld"):
                    st.warning(
                        f"Held back {_count(len(entry['withheld']))} that could not "
                        "be verified against the computed data: "
                        f"`{'`, `'.join(entry['withheld'])}`",
                        icon="🛡️",
                    )
            st.markdown(entry["text"])

    if not question:
        return

    st.session_state.assistant_log.append({"role": "user", "text": question})
    with st.chat_message("user"):
        st.markdown(question)

    with st.chat_message("assistant"):
        with st.spinner("Calling the analysis code…"):
            try:
                reply = ask(question)
            except KeyNotConfigured:
                st.info(NOT_CONFIGURED_MESSAGE, icon="🔑")
                return
            except Exception as error:  # noqa: BLE001
                st.error(f"The assistant failed: {type(error).__name__}: {error}")
                return

        _render_tool_calls(reply.tool_calls)

        # Grounding verification ran on this response. If a figure could not be
        # traced to a tool result, it has already been removed from the text —
        # say so plainly rather than showing a redaction with no explanation.
        if reply.withheld:
            st.warning(
                f"**I couldn't verify {_count(len(reply.withheld))} against the "
                "computed data, so I've held "
                f"{'it' if len(reply.withheld) == 1 else 'them'} back.** Every "
                "number here is checked against the actual tool output before you "
                "see it; anything that can't be traced is withheld rather than "
                "shown. The rest of the answer stands.\n\n"
                f"Withheld: `{'`, `'.join(reply.withheld)}`",
                icon="🛡️",
            )

        st.markdown(reply.text)

        if reply.stopped_early:
            st.warning("Stopped at the tool-call limit.", icon="⚠️")

    st.session_state.assistant_log.append({
        "role": "assistant",
        "text": reply.text,
        "withheld": reply.withheld,
        "tool_calls": [
            {"name": c.name, "arguments": c.arguments, "result": c.result}
            for c in reply.tool_calls
        ],
    })


def _count(n: int) -> str:
    return "one figure" if n == 1 else f"{n} figures"


def _render_tool_calls(calls) -> None:
    """Transparency: what was called, with what, and what came back."""
    if not calls:
        return

    names = ", ".join(
        f"`{c['name'] if isinstance(c, dict) else c.name}`" for c in calls
    )
    with st.expander(f"🔧 {len(calls)} tool call(s): {names}", expanded=False):
        for call in calls:
            name = call["name"] if isinstance(call, dict) else call.name
            arguments = call["arguments"] if isinstance(call, dict) else call.arguments
            result = call["result"] if isinstance(call, dict) else call.result

            st.markdown(f"**{name}**")
            st.code(json.dumps(arguments, indent=2), language="json")
            st.caption("Returned:")
            st.code(json.dumps(result, indent=2, default=str)[:4000], language="json")
            st.divider()
