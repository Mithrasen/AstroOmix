"""Visual theme for the Streamlit app. Styling only — no analysis code here.

`inject_theme()` emits one <style> block. It must be called once, before any page
content, so the rules are in place before Streamlit paints.

Readability is the constraint that governs everything below. A starfield behind a
data table is a very easy way to make numbers harder to read, so:

* the field sits on a fixed pseudo-element at z-index 0 with `pointer-events:none`,
  and never on the content layer;
* the stars are dim (max 0.5 alpha on a #0b0e14 ground) and small (1-2px);
* every surface that carries text or data — panels, tables, charts, the sidebar —
  gets an opaque background, so nothing is ever read *through* the starfield;
* body text stays at the full #e6e9ef from .streamlit/config.toml, unchanged.
"""

from __future__ import annotations

import streamlit as st

# Inter for prose, JetBrains Mono for anything numeric or identifier-like. The
# pairing is functional, not decorative: gene IDs, accessions and p-values are
# strings you compare character by character, and a monospace face with
# unambiguous 0/O and 1/l is genuinely easier to scan.
_FONTS = (
    "@import url('https://fonts.googleapis.com/css2?"
    "family=Inter:wght@400;500;600;700&"
    "family=JetBrains+Mono:wght@400;500;700&display=swap');"
)

_CSS = """
:root {
  --bg: #0b0e14;
  --panel: #141922;
  --border: #232b39;
  --text: #e6e9ef;
  --muted: #8b96a8;
  --accent: #5aa9e6;
  --mono: 'JetBrains Mono', ui-monospace, SFMono-Regular, Menlo, monospace;
  --sans: 'Inter', -apple-system, BlinkMacSystemFont, 'Segoe UI', sans-serif;
}

html, body, [class*="css"], .stApp { font-family: var(--sans); }

/* --- starfield -----------------------------------------------------------
   Three layered radial-gradient dot fields at different scales, drifting at
   different speeds for a weak parallax. Pure CSS: no canvas, no JS, no
   per-frame work beyond a compositor transform, so it costs nothing.
   pointer-events:none so it can never intercept a click on a widget. */
.stApp::before {
  content: "";
  position: fixed;
  top: -50%; left: -50%;
  width: 200%; height: 200%;
  pointer-events: none;
  z-index: 0;
  background-image:
    radial-gradient(1.4px 1.4px at 20% 30%, rgba(230,233,239,0.50) 50%, transparent 51%),
    radial-gradient(1.4px 1.4px at 75% 15%, rgba(230,233,239,0.42) 50%, transparent 51%),
    radial-gradient(1.2px 1.2px at 45% 70%, rgba(230,233,239,0.38) 50%, transparent 51%),
    radial-gradient(1.6px 1.6px at 88% 62%, rgba(90,169,230,0.40) 50%, transparent 51%),
    radial-gradient(1px 1px at 10% 85%, rgba(230,233,239,0.32) 50%, transparent 51%),
    radial-gradient(1px 1px at 62% 45%, rgba(230,233,239,0.28) 50%, transparent 51%);
  background-size: 340px 340px, 480px 480px, 260px 260px,
                   620px 620px, 200px 200px, 400px 400px;
  animation: drift 220s linear infinite;
  opacity: 0.55;
}

/* A single faint nebula wash, to stop the field reading as flat noise. */
.stApp::after {
  content: "";
  position: fixed;
  inset: 0;
  pointer-events: none;
  z-index: 0;
  background:
    radial-gradient(ellipse 70% 50% at 15% 0%, rgba(90,169,230,0.07), transparent 60%),
    radial-gradient(ellipse 60% 50% at 90% 100%, rgba(201,162,39,0.05), transparent 60%);
}

@keyframes drift {
  from { transform: translate3d(0, 0, 0); }
  to   { transform: translate3d(-340px, -240px, 0); }
}

/* Respect the OS setting. An indefinitely animating background is a real
   accessibility problem for some users, and the field works fine static. */
@media (prefers-reduced-motion: reduce) {
  .stApp::before { animation: none; }
}

/* Content sits above the field, always. */
.stApp > header, [data-testid="stAppViewContainer"] > .main,
section[data-testid="stSidebar"] { position: relative; z-index: 1; }

/* --- readability: opaque surfaces ---------------------------------------
   Nothing that carries text or data is ever read *through* the starfield. */
section[data-testid="stSidebar"] {
  background: #0d111a;
  border-right: 1px solid var(--border);
}
[data-testid="stDataFrame"], .js-plotly-plot, [data-testid="stAlert"],
[data-testid="stExpander"], [data-testid="stTable"] {
  background: var(--panel);
  border-radius: 10px;
}
[data-testid="stDataFrame"], [data-testid="stExpander"] {
  border: 1px solid var(--border);
}

/* --- typography ---------------------------------------------------------- */
h1, h2, h3 { font-family: var(--sans); font-weight: 700; letter-spacing: -0.02em; }
h1 { font-size: 2.0rem; }
h2 { font-size: 1.45rem; }
h3 { font-size: 1.1rem; }

/* Monospace for the things you read character by character. */
code, kbd, pre, [data-testid="stMetricValue"] { font-family: var(--mono) !important; }

/* --- spacing: tighten Streamlit's very generous defaults ----------------- */
.block-container { padding-top: 2.6rem; padding-bottom: 4rem; max-width: 1400px; }
[data-testid="stVerticalBlock"] { gap: 0.85rem; }
h2 { margin-top: 1.4rem; margin-bottom: 0.4rem; }
[data-testid="stCaptionContainer"] { margin-top: -0.25rem; }

/* --- interactive: soft glow on hover ------------------------------------
   Subtle. A border-colour shift plus a low-alpha ring — polished, not flashy. */
.stButton > button, .stDownloadButton > button {
  font-family: var(--sans);
  font-weight: 600;
  border: 1px solid var(--border);
  border-radius: 8px;
  background: var(--panel);
  color: var(--text);
  transition: border-color 160ms ease, box-shadow 160ms ease, transform 160ms ease;
}
.stButton > button:hover, .stDownloadButton > button:hover {
  border-color: var(--accent);
  box-shadow: 0 0 0 1px rgba(90,169,230,0.25), 0 0 18px rgba(90,169,230,0.18);
  transform: translateY(-1px);
}

[data-baseweb="select"] > div, .stTextInput input, .stNumberInput input {
  border-radius: 8px !important;
  transition: border-color 160ms ease, box-shadow 160ms ease;
}
[data-baseweb="select"] > div:hover,
.stTextInput input:hover, .stNumberInput input:hover {
  border-color: var(--accent) !important;
  box-shadow: 0 0 14px rgba(90,169,230,0.14);
}

[data-testid="stExpander"] summary { transition: color 160ms ease; }
[data-testid="stExpander"]:hover { border-color: var(--accent); }

/* Table rows: a faint accent wash on hover, no colour change to the text. */
[data-testid="stDataFrame"] { transition: box-shadow 200ms ease; }
[data-testid="stDataFrame"]:hover { box-shadow: 0 0 22px rgba(90,169,230,0.10); }

/* Sidebar nav */
section[data-testid="stSidebar"] label { transition: color 140ms ease; }
section[data-testid="stSidebar"] label:hover { color: var(--accent); }
"""


def inject_theme() -> None:
    """Emit the theme's <style> block. Call once, before any page content."""
    st.markdown(f"<style>{_FONTS}{_CSS}</style>", unsafe_allow_html=True)
