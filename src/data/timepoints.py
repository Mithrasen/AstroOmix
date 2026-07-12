"""Mission-day axis for Inspiration4 timepoints.

OSDR labels I4 samples relative to two different anchors:

    L-92, L-44, L-3   days BEFORE launch
    R+1, R+45, ...    days AFTER return

Those cannot be mixed on one axis without knowing the mission length, or the
flight itself collapses to zero and `R+1` lands on launch day. Inspiration4
launched 2021-09-16 and splashed down 2021-09-18: three days aloft.

We put everything on `mission_day`, where launch = day 0:

    L-92  -> -92        (92 days before launch)
    R+1   -> +4         (return is day 3; one day later is day 4)

Forecasting models consume `mission_day`. Anything that treats `R+1` as day 1
is silently compressing the flight out of the timeline.
"""

from __future__ import annotations

import re

# Days from launch (day 0) to splashdown. Inspiration4: 2021-09-16 -> 2021-09-18.
MISSION_DURATION_DAYS = 3

_TIMEPOINT_RE = re.compile(r"^(?P<anchor>[LR])(?P<sign>[+-])(?P<days>\d+)$")


def to_mission_day(label: str, mission_duration: int = MISSION_DURATION_DAYS) -> int:
    """Convert an OSDR timepoint label ('L-92', 'R+1') to a mission day.

    Launch is day 0. Return is `mission_duration`. Raises ValueError on labels
    that do not parse, rather than guessing.
    """
    match = _TIMEPOINT_RE.match(label.strip())
    if not match:
        raise ValueError(f"Unrecognized timepoint label: {label!r}")

    days = int(match["days"])
    offset = -days if match["sign"] == "-" else days

    if match["anchor"] == "L":
        return offset
    return mission_duration + offset


def sort_timepoints(labels, mission_duration: int = MISSION_DURATION_DAYS) -> list[str]:
    """Return labels in chronological order."""
    return sorted(labels, key=lambda x: to_mission_day(x, mission_duration))
