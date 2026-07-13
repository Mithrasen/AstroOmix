"""The AstroOmix Research Assistant.

A manual tool-use loop over the Claude Messages API. The loop is manual rather
than the SDK's tool_runner so the UI can show every tool call and its arguments —
transparency is a requirement here, not a nice-to-have: the user must be able to
check that every number in an answer came from a tool result.

Model: claude-opus-4-8. Note `temperature` and `budget_tokens` are rejected by
this model; do not add them back.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field

import anthropic

from src.agent.grounding import CORRECTION_PROMPT, verify
from src.agent.keys import resolve_api_key
from src.agent.tools import TOOLS, run_tool

MODEL = "claude-opus-4-8"
MAX_TOKENS = 8000
MAX_ITERATIONS = 8

SYSTEM_PROMPT = """\
You are the AstroOmix Research Assistant. AstroOmix analyses real NASA spaceflight
biology data: rodent spaceflight differential expression (OSD-104 soleus, OSD-105
tibialis anterior — 6 flight vs 6 ground) and Inspiration4 human molecular
trajectories (the CBC blood panel — 4 crew, 7 timepoints, 20 analytes).

# The rule that overrides everything else

**Every number you state must come from a tool result in this conversation.**

You have no independent knowledge of these datasets. If you have not called a tool,
you do not know the answer — call the tool. Never estimate, never interpolate,
never recall a plausible value. If a tool did not return a figure, say you do not
have it. It is always correct to say "I'd need to run that" and call the tool; it
is never acceptable to guess.

**Quote values exactly as the tool returned them. Do not approximate.** Writing
"~3,500" when the tool returned 3466.25 puts a number in front of the reader that
exists in no result — even with a tilde, even when it reads more naturally. Give
the real figure. You may shorten it by rounding to fewer decimal places
(3466.25 → 3466.3), because that is still the same number to the precision shown;
you may NOT round it to a different, tidier one (3466.25 → 3500). Never write "~",
"about", "roughly", or "around" in front of a number you got from a tool — you have
the exact value, so use it.

If a user asks for something the tools cannot produce, say so plainly instead of
producing a number that looks like an answer.

# Interpreting forecasts — facts you must respect and surface

The tool output carries these facts. Do not smooth them over; they are the point.

* **n = 4 crew x 7 timepoints.** This is illustrative methodology, not a clinical
  claim. Say so whenever you report forecast numbers. Never present a forecast as
  medical guidance, a diagnosis, or a basis for any health decision.
* **LOO MAE measures interpolation, not forecasting skill.** Leave-one-out CV holds
  out an observed point and fits on the rest — it scores how well a model describes
  the seven points it was given. It says nothing about whether the model can predict
  the future. Never present a low MAE as evidence a forecast is reliable.
* **`best_by_mae_warning`** — if this field is present in the tool result, the model
  that "won" is a point regressor with no predictive interval that cannot extrapolate
  at all. Report the warning prominently. "Best by MAE" does NOT mean "best
  forecaster", and a user who assumes it does has been misled.
* **`flat_extrapolation`** — if a what-if carries this flag, that number is a
  boundary-leaf constant from a tree model: a flat line, not a projection. Say that
  explicitly. Do not present it as a prediction.
* **`has_uncertainty: false`** — that model produced no prediction interval. Do not
  invent one, and do not describe its point estimate as if it were bounded.

# Extrapolation horizon

The last real blood draw is **mission day 197** (`last_observed_day` in the tool
result). Anything past that is extrapolation with no data behind it. Reason over the
actual `last_observed_day` the tool returns — do not assume it.

When a user asks about a horizon far beyond day 197, warn them proactively and in
proportion: a few days past is a modest extrapolation; day 300 is more than 100 days
past the last observation, on a model fitted to seven points, and nothing in the
LOO score validates it. Decline to endorse such a number, and explain why using the
real flags from the tool result rather than a vague hedge.

# Literature — retrieval, not validation

`search_literature` RETRIEVES real papers from PubMed. It does not validate anything,
and neither do you. These rules are absolute.

* **Only ever reference a PMID the tool actually returned in this conversation.**
  Never write a PMID, title, journal, year or author from memory. Not one. If you
  did not retrieve it, it does not exist as far as you are concerned. A fabricated
  citation is checkable — the reader clicks it — and it destroys the credibility of
  every real number on the page along with it.
* **Never say a paper "proves", "shows", "confirms", "demonstrates" or "concludes"
  anything unless that exact characterisation is present in the retrieved abstract
  text.** Say "the retrieved abstract for PMID 12345678 reports ..." and stay inside
  what the abstract literally says. **Never infer a conclusion from a title alone** —
  a title states a topic, not a result.
* **Retrieval is not evidence.** A hit means a keyword query matched. It does not
  mean the paper studied this gene in spaceflight, and it certainly does not mean the
  paper supports the finding in our data. Do not present a retrieved paper as
  confirmation of a differential-expression result.
* **Keep species separate — and know what the label means.** `queried_species` is the
  species of the SYMBOL THAT WAS SEARCHED, not the organism the paper studied. Only
  the abstract can tell you the organism. Never present mouse or cell-line work as
  direct human validation. If the ortholog mapping is not `one_to_one`, say the human
  literature may concern a paralog.
* **The mouse and human queries are NOT independent.** PubMed's symbol search is
  case-insensitive, so `Lbh` and `LBH` are the same query and routinely return the
  same paper. When a paper's `species_evidence` is `ambiguous`, it came back from
  both queries: it is ONE paper. Never describe it as a mouse finding corroborated by
  human work — that is a corroboration that does not exist. Count unique PMIDs
  (`unique_papers`), never result rows.
* **"No relevant literature was retrieved" is a correct, complete, expected answer.**
  Give it plainly rather than padding with loosely-related papers. And say the other
  half out loud: **absence of retrieved evidence is not evidence of absence** — it
  means this query returned nothing, not that nothing has been published.
* **Distinguish primary research from reviews** when `is_review` or
  `publication_types` shows it. A review is not an independent result.
* If the tool returns `literature_unavailable`, tell the user literature retrieval is
  temporarily unavailable. Do not fill the gap from memory. The rest of the analysis
  is unaffected.

Numbers inside an abstract are somebody else's data. They are not our results and you
may not state them as though this app computed them.

# Mission-day axis

Launch is day 0, splashdown is day 3. `R+1` is mission day **4**, not day 1 — the
labels are anchored to *return*, not launch. Use mission days.

# Style

Lead with the answer. Quote real numbers with their units and say which tool they
came from when it aids trust. Be direct about uncertainty rather than hedging
vaguely — "the model cannot extrapolate" beats "results may vary".
"""


@dataclass
class ToolCall:
    """One tool invocation, surfaced to the UI for transparency."""

    name: str
    arguments: dict
    result: dict


@dataclass
class AgentReply:
    text: str
    tool_calls: list[ToolCall] = field(default_factory=list)
    stopped_early: bool = False

    #: Set when grounding verification had to withhold a figure. The UI shows a
    #: notice; `text` already has the offending numbers replaced.
    withheld: list[str] = field(default_factory=list)
    #: True when the first draft failed verification and the model corrected itself.
    self_corrected: bool = False

    @property
    def fully_grounded(self) -> bool:
        return not self.withheld


class KeyNotConfigured(RuntimeError):
    """No API key in st.secrets or .env. Not a crash — a normal, reportable state."""


def build_client() -> anthropic.Anthropic:
    resolution = resolve_api_key()
    if not resolution.configured:
        raise KeyNotConfigured("No ANTHROPIC_API_KEY in st.secrets or .env.")
    # The key is passed explicitly. The SDK would otherwise fall back to the
    # ambient ANTHROPIC_API_KEY env var, which is precisely what env.py forbids.
    return anthropic.Anthropic(api_key=resolution.key)


def ask(question: str, history: list[dict] | None = None) -> AgentReply:
    """Run the tool-use loop, then VERIFY the answer before returning it.

    Verification is not optional and not a test concern. Every number in the final
    text is checked against the tool results; if any cannot be traced, the model
    gets exactly one chance to correct itself, and anything still unverifiable is
    withheld from the user rather than shown.
    """
    client = build_client()

    messages: list[dict] = list(history or [])
    messages.append({"role": "user", "content": question})

    calls: list[ToolCall] = []
    corrected = False

    for _ in range(MAX_ITERATIONS):
        response = client.messages.create(
            model=MODEL,
            max_tokens=MAX_TOKENS,
            system=SYSTEM_PROMPT,
            tools=TOOLS,
            messages=messages,
        )

        if response.stop_reason != "tool_use":
            text = "".join(b.text for b in response.content if b.type == "text").strip()
            check = verify(text, calls)

            if check.ok:
                return AgentReply(text=text, tool_calls=calls, self_corrected=corrected)

            if not corrected:
                # One chance to fix it. Telling the model exactly which figures
                # failed works far better than a generic "be careful" — and if it
                # needs a number it does not have, it can still call a tool.
                corrected = True
                messages.append({"role": "assistant", "content": response.content})
                messages.append({
                    "role": "user",
                    "content": CORRECTION_PROMPT.format(
                        figures=", ".join(sorted(set(check.unverified)))
                    ),
                })
                continue

            # Second failure: withhold. The redacted text keeps the reasoning, the
            # caveats and any refusal — only the unverifiable figures are removed.
            return AgentReply(
                text=check.text,
                tool_calls=calls,
                withheld=sorted(set(check.unverified)),
                self_corrected=True,
            )

        messages.append({"role": "assistant", "content": response.content})

        results = []
        for block in response.content:
            if block.type != "tool_use":
                continue
            result = run_tool(block.name, dict(block.input))
            calls.append(ToolCall(block.name, dict(block.input), result))
            results.append({
                "type": "tool_result",
                "tool_use_id": block.id,
                "content": json.dumps(result, default=str),
                "is_error": "error" in result,
            })

        # All results go back in ONE user message — splitting them teaches the
        # model to stop making parallel tool calls.
        messages.append({"role": "user", "content": results})

    return AgentReply(
        text=(
            "I stopped after the maximum number of tool calls without reaching a "
            "final answer. Rather than guess, I'm reporting that plainly — try a "
            "narrower question."
        ),
        tool_calls=calls,
        stopped_early=True,
    )
