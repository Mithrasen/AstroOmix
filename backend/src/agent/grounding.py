"""Runtime verification: every number in an answer must trace to a tool result.

This ran as a test-only assertion first, which was the wrong place for it. A test
proves the agent *usually* behaves; it does nothing for the user in front of the
app when it doesn't. And we measured the failure rate — roughly one live run in
seven emitted a figure the guard could not verify. Test-only, that is a flaky
test. In production, it is a fabricated number shown to a real person, which is
precisely what this project claims not to do.

So the guard runs on every live response. This module is the single source of
truth; the tests import it rather than restating it, so the thing that is verified
and the thing that ships cannot drift apart.

What counts as grounded
-----------------------
* A value returned by a tool, at any faithful rounding. The agent reporting the
  tool's 3466.255 as "3466.26" is correct behaviour, not fabrication — and note
  Python's own `round(14.075, 2)` gives 14.07, so comparing *rounded* values would
  reject the model's correct "14.08". Hence a half-unit tolerance at the stated
  precision.
* A pairwise difference of two real values. "2910.75 -> 1855.25, a drop of 1055.5"
  is exactly that subtraction, and "which marker recovered fastest" cannot be
  answered without comparing magnitudes of change. Only differences: adding ratios
  and products would inflate the grounded set until a fabricated number could match
  one by coincidence.
* A tool ARGUMENT the agent chose (`extra_days=103`), which legitimately reappears
  as "103 days past day 197". An argument is a request, not a claim about data.
* A small set of structural constants from the system prompt (n = 4 crew,
  7 timepoints, the 0.05 FDR cutoff, "95% interval").

Everything else is withheld.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field

# A minus sign is only a minus sign when NOT preceded by a word character —
# otherwise "day-300" yields a spurious -300 and "R+1" yields +1.
NUMBER = re.compile(r"(?<![\w.])(-?\d+(?:\.\d+)?(?:[eE][+-]?\d+)?)")

# The model writes real typography. Without normalising, "day −92" (U+2212 MINUS)
# loses its sign and never matches the tool's -92.
DASHES = {"−": "-", "–": " ", "—": " ", "‒": " "}

# Structural numerals the system prompt itself supplies — the design of the study,
# not measurements. Deliberately tiny: every addition here is a hole in the guard.
STRUCTURAL = {
    0.0, 1.0, 2.0, 3.0, 4.0, 5.0, 6.0, 7.0,  # crew, timepoints, mission days, n/group
    10.0, 20.0,                               # analyte count
    0.05,                                     # the FDR cutoff
    95.0,                                     # "95% interval"
    100.0,                                    # "100%" / "over 100 days"
}

WITHHELD = "[withheld: unverified]"


@dataclass
class Grounding:
    ok: bool
    unverified: list[str] = field(default_factory=list)
    text: str = ""            # the answer, with unverified figures redacted
    original: str = ""


def normalise(text: str) -> str:
    for bad, good in DASHES.items():
        text = text.replace(bad, good)
    return text


def _decimals(token: str) -> int:
    return len(token.split(".")[1]) if "." in token else 0


def numbers_available(tool_calls) -> list[float]:
    """Every number in any tool result, plus the arguments the agent passed."""
    found: list[float] = []

    def walk(node):
        if isinstance(node, bool):
            return
        if isinstance(node, dict):
            for value in node.values():
                walk(value)
        elif isinstance(node, (list, tuple)):
            for value in node:
                walk(value)
        elif isinstance(node, (int, float)):
            found.append(float(node))
        elif isinstance(node, str):
            for match in NUMBER.finditer(normalise(node)):
                try:
                    found.append(float(match.group()))
                except ValueError:
                    pass

    for call in tool_calls:
        walk(call.result)
        walk(call.arguments)
    return found


def derived_from(available: list[float]) -> list[float]:
    """Pairwise differences, BOTH SIGNS — the arithmetic the questions require.

    Signed, not absolute. A drop from 2910.75 to 1855.25 is naturally written as
    "-1055.5", and an absolute-only set would flag that correct subtraction as
    fabricated — punishing the model for reporting a decrease as negative, which is
    exactly what it should do.
    """
    out: list[float] = []
    for index, first in enumerate(available):
        for second in available[index + 1:]:
            difference = first - second
            out.append(difference)
            out.append(-difference)
    return out


def is_grounded(stated: str, grounded: list[float]) -> bool:
    """True if some real value rounds to `stated`, to within half its last digit."""
    try:
        value = float(stated)
    except ValueError:
        return False
    if value in STRUCTURAL:
        return True
    tolerance = 0.5 * (10 ** -_decimals(stated)) + 1e-9
    return any(abs(candidate - value) <= tolerance for candidate in grounded)


def verify(text: str, tool_calls) -> Grounding:
    """Check every number in `text` against the tool results.

    Returns the answer with any unverifiable figure replaced by `WITHHELD`, so the
    rest of the response — the reasoning, the caveats, the refusals — survives. An
    all-or-nothing block would throw away good content to suppress one number.
    """
    normalised = normalise(text)
    available = numbers_available(tool_calls)
    grounded = available + derived_from(available)

    unverified: list[str] = []
    out: list[str] = []
    cursor = 0

    for match in NUMBER.finditer(normalised):
        token = match.group()
        if is_grounded(token, grounded):
            continue
        unverified.append(token)
        out.append(normalised[cursor:match.start()])
        out.append(WITHHELD)
        cursor = match.end()

    out.append(normalised[cursor:])

    return Grounding(
        ok=not unverified,
        unverified=unverified,
        text="".join(out) if unverified else normalised,
        original=normalised,
    )


CORRECTION_PROMPT = (
    "STOP. Before that answer can be shown, it failed grounding verification.\n\n"
    "These figures appear in your answer but in NO tool result: {figures}\n\n"
    "Every number you state must be a value a tool returned (at any faithful "
    "rounding), a difference between two such values, or a structural constant of "
    "the study. You may not state an estimate, an approximation, a derived "
    "statistic that is not a simple difference, or a figure you carried over from "
    "memory.\n\n"
    "Rewrite your answer now. Either quote the exact tool value instead, or drop "
    "the figure and say in words what you cannot quantify. Do not re-state any of "
    "the figures listed above. Call a tool if you need a number you do not have."
)
