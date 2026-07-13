"""Inline SVG motifs: orbit, helix, molecular node.

Decoration with a job — they say "space biology" at a glance and mark the three
honesty cards. They are deliberately small, low-contrast and never placed over a
chart or a table: readability of the data always wins. All motion is CSS
(`theme.py`), so `prefers-reduced-motion` turns it off in one place.
"""

from __future__ import annotations

ACCENT = "#5aa9e6"
WARN = "#d8b968"
MUTED = "#8b96a8"


def orbit(size: int = 30, color: str = ACCENT, spin: bool = True) -> str:
    """A planet with an inclined orbital path and a travelling satellite."""
    animate = "orbit-spin" if spin else ""
    return f"""
<svg class="motif" width="{size}" height="{size}" viewBox="0 0 40 40" fill="none"
     aria-hidden="true">
  <circle cx="20" cy="20" r="6.5" fill="{color}" fill-opacity="0.18"
          stroke="{color}" stroke-width="1.3"/>
  <g class="{animate}">
    <ellipse cx="20" cy="20" rx="17" ry="7.5" stroke="{color}" stroke-width="1.1"
             stroke-opacity="0.55" transform="rotate(-24 20 20)"/>
    <circle cx="36.5" cy="13" r="2.3" fill="{color}"/>
  </g>
</svg>"""


def helix(size: int = 30, color: str = WARN, drift: bool = True) -> str:
    """A double helix — two strands with base-pair rungs."""
    animate = "helix-drift" if drift else ""
    rungs = "".join(
        f'<line x1="{12 + 1.8 * (i % 2)}" y1="{7 + i * 5}" '
        f'x2="{28 - 1.8 * (i % 2)}" y2="{7 + i * 5}" '
        f'stroke="{color}" stroke-width="1" stroke-opacity="0.5"/>'
        for i in range(6)
    )
    return f"""
<svg class="motif {animate}" width="{size}" height="{size}" viewBox="0 0 40 40"
     fill="none" aria-hidden="true">
  <path d="M12 4 C28 12, 12 20, 28 28 C12 32, 28 36, 12 38" stroke="{color}"
        stroke-width="1.6" stroke-linecap="round"/>
  <path d="M28 4 C12 12, 28 20, 12 28 C28 32, 12 36, 28 38" stroke="{color}"
        stroke-width="1.6" stroke-linecap="round" stroke-opacity="0.75"/>
  {rungs}
</svg>"""


def node(size: int = 30, color: str = ACCENT, pulse: bool = True) -> str:
    """A molecular node graph — a hub with bonded satellites."""
    animate = "node-pulse" if pulse else ""
    return f"""
<svg class="motif" width="{size}" height="{size}" viewBox="0 0 40 40" fill="none"
     aria-hidden="true">
  <line x1="20" y1="20" x2="7" y2="11" stroke="{color}" stroke-width="1.1" stroke-opacity="0.5"/>
  <line x1="20" y1="20" x2="33" y2="9" stroke="{color}" stroke-width="1.1" stroke-opacity="0.5"/>
  <line x1="20" y1="20" x2="10" y2="32" stroke="{color}" stroke-width="1.1" stroke-opacity="0.5"/>
  <line x1="20" y1="20" x2="32" y2="31" stroke="{color}" stroke-width="1.1" stroke-opacity="0.5"/>
  <circle cx="20" cy="20" r="5" fill="{color}" fill-opacity="0.2" stroke="{color}" stroke-width="1.3"/>
  <g class="{animate}">
    <circle cx="7" cy="11" r="2.6" fill="{color}"/>
    <circle cx="33" cy="9" r="2.2" fill="{color}"/>
    <circle cx="10" cy="32" r="2.2" fill="{color}"/>
    <circle cx="32" cy="31" r="2.6" fill="{color}"/>
  </g>
</svg>"""


def logo(size: int = 34) -> str:
    """The mark: an orbital path wrapped around a DNA helix.

    Space AND genetics in one glyph — a satellite alone said "space" and nothing
    about biology, which is half the product.
    """
    return f"""
<svg class="motif" width="{size}" height="{size}" viewBox="0 0 44 44" fill="none"
     aria-hidden="true">
  <!-- orbital path, inclined behind the helix -->
  <ellipse cx="22" cy="22" rx="19" ry="8.5" stroke="{ACCENT}" stroke-width="1.6"
           stroke-opacity="0.75" transform="rotate(-28 22 22)"/>
  <!-- the double helix at the centre -->
  <path d="M16 8 C30 15, 16 22, 30 29 C16 33, 30 37, 16 39" stroke="{WARN}"
        stroke-width="1.9" stroke-linecap="round"/>
  <path d="M30 8 C16 15, 30 22, 16 29 C30 33, 16 37, 30 39" stroke="{WARN}"
        stroke-width="1.9" stroke-linecap="round" stroke-opacity="0.8"/>
  <line x1="18.5" y1="13" x2="27.5" y2="13" stroke="{WARN}" stroke-width="1.1" stroke-opacity="0.55"/>
  <line x1="18.5" y1="22" x2="27.5" y2="22" stroke="{WARN}" stroke-width="1.1" stroke-opacity="0.55"/>
  <line x1="18.5" y1="31" x2="27.5" y2="31" stroke="{WARN}" stroke-width="1.1" stroke-opacity="0.55"/>
  <!-- the satellite on the orbit -->
  <circle cx="39" cy="13.5" r="2.6" fill="{ACCENT}"/>
</svg>"""


def shield(size: int = 30, color: str = WARN) -> str:
    """A shield with a check — the grounding guard."""
    return f"""
<svg class="motif" width="{size}" height="{size}" viewBox="0 0 40 40" fill="none"
     aria-hidden="true">
  <path d="M20 4 L33 9 V20 C33 28 27 34 20 36 C13 34 7 28 7 20 V9 Z"
        fill="{color}" fill-opacity="0.12" stroke="{color}" stroke-width="1.5"/>
  <path d="M14 20 l4.5 4.5 L27 15" stroke="{color}" stroke-width="2"
        stroke-linecap="round" stroke-linejoin="round"/>
</svg>"""
