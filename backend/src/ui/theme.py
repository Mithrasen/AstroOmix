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
    "family=Space+Grotesk:wght@500;600;700&"
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
  --display: 'Space Grotesk', 'Inter', -apple-system, sans-serif;
}

html, body, [class*="css"], .stApp { font-family: var(--sans); }

/* --- hide Streamlit's default chrome -------------------------------------
   The hamburger menu, the Deploy button, the footer, and the top-right
   status/decoration. This should read as a product, not a Streamlit demo.
   Both the modern data-testid selectors and the older id/tag selectors are
   listed so it survives a Streamlit version bump. The header element itself
   is only made transparent, never hidden — hiding it takes the sidebar's
   collapse control with it, which strands anyone who closes the sidebar. */
#MainMenu,
[data-testid="stMainMenu"],
[data-testid="stToolbar"],
[data-testid="stToolbarActions"],
[data-testid="stStatusWidget"],
[data-testid="stDecoration"],
[data-testid="stAppDeployButton"],
footer { display: none !important; }

[data-testid="stHeader"], .stApp > header { background: transparent; }

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
h1, h2, h3 { font-family: var(--display); font-weight: 600; letter-spacing: -0.02em; }
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

/* ==========================================================================
   MISSION CONTROL — one language across every page.
   Purely presentational. Nothing below changes a computed value.
   ========================================================================== */

:root {
  /* One cool accent for interactive things. One WARM accent reserved for
     honesty flags — caveats, warnings, withheld figures — so a safety notice is
     visually distinct from a button at a glance and can never be mistaken for
     ordinary chrome. */
  --warn: #d8b968;
  --warn-bg: #2a2113;
  --warn-border: #6b5424;
  --danger: #e0776c;
  --danger-bg: #2a1a1a;
  --danger-border: #6b2d2d;
  --ok: #4ec9a0;
}

/* --- data typography ------------------------------------------------------
   Numbers, gene IDs and accessions are read character-by-character, so they get
   the monospace face everywhere — tables, metrics, code, the tool-call panel. */
[data-testid="stDataFrame"] { font-family: var(--mono); font-size: 13px; }
[data-testid="stMetricValue"], .stCode, code, pre { font-family: var(--mono) !important; }

/* --- honesty flags: WARM, never cool -------------------------------------
   Streamlit's st.warning / st.error carry every caveat in this app: the n=3
   reliability tier, the best_by_mae trap, flat_extrapolation, the withheld-figure
   notice, the not-a-statistical-integration banner. They are styled as one family
   so a judge learns the visual language once. Text is untouched — only colour. */
[data-testid="stAlert"] {
  border-radius: 10px;
  border-left-width: 4px;
  border-left-style: solid;
  line-height: 1.6;
}
/* warning (amber) — a caveat you must read */
[data-testid="stAlert"]:has(svg[data-testid="stAlertDynamicIcon"]),
[data-testid="stAlert"] { border-left-color: var(--warn); }

/* --- section headers with an orbital rule --------------------------------- */
.mc-rule {
  display: flex; align-items: center; gap: 12px;
  margin: 6px 0 14px;
}
.mc-rule::after {
  content: ""; flex: 1; height: 1px;
  background: linear-gradient(90deg, var(--border), transparent);
}

/* --- the case/landing page ------------------------------------------------ */
.hero {
  position: relative;
  border: 1px solid var(--border);
  border-radius: 16px;
  padding: 34px 36px 30px;
  background:
    radial-gradient(ellipse 80% 120% at 88% 0%, rgba(90,169,230,0.10), transparent 60%),
    radial-gradient(ellipse 60% 100% at 0% 100%, rgba(201,162,39,0.06), transparent 60%),
    var(--panel);
  overflow: hidden;
}
.hero .stakes {
  font-size: 14.5px; line-height: 1.65; color: var(--muted);
  max-width: 62ch;
}
.hero h1 {
  font-family: var(--display);
  font-size: 2.05rem; line-height: 1.2;
  margin: 14px 0 12px; letter-spacing: -0.02em;
}
.hero h1 .lede { color: var(--accent); }
.hero h1 .refuse { color: var(--warn); }
.hero .sub {
  font-size: 15px; line-height: 1.7; color: var(--text);
  max-width: 68ch; margin-bottom: 4px;
}

.persona {
  border: 1px solid var(--border);
  border-left: 3px solid var(--accent);
  border-radius: 10px;
  padding: 16px 18px;
  background: var(--panel);
}
.persona .who {
  font-size: 11px; letter-spacing: 0.09em; text-transform: uppercase;
  color: var(--accent); font-weight: 600; margin-bottom: 6px;
}
.persona p { margin: 0; font-size: 14px; line-height: 1.65; color: var(--text); }

/* honesty strip — the differentiator, stated plainly */
.honesty {
  display: grid; grid-template-columns: repeat(auto-fit, minmax(240px, 1fr));
  gap: 14px;
}
.honesty .card {
  border: 1px solid var(--border);
  border-top: 3px solid var(--warn);
  border-radius: 10px;
  padding: 16px 18px;
  background: var(--panel);
  transition: border-color 180ms ease, box-shadow 180ms ease, transform 180ms ease;
}
.honesty .card:hover {
  transform: translateY(-2px);
  border-color: var(--warn);
  box-shadow: 0 0 22px rgba(216,185,104,0.14);
}
.honesty .card h4 {
  margin: 10px 0 6px; font-size: 14px; font-weight: 700;
  font-family: var(--display); color: var(--text);
}
.honesty .card p { margin: 0; font-size: 12.5px; line-height: 1.6; color: var(--muted); }
.honesty .card svg { display: block; }

/* --- inline SVG motifs: subtle, never competing with data ----------------- */
.motif { opacity: 0.85; transition: opacity 220ms ease, transform 220ms ease; }
.motif:hover { opacity: 1; }
.orbit-spin { transform-origin: center; animation: orbit 26s linear infinite; }
.helix-drift { animation: helixdrift 7s ease-in-out infinite; transform-origin: center; }
.node-pulse { animation: nodepulse 3.4s ease-in-out infinite; transform-origin: center; }

@keyframes orbit { to { transform: rotate(360deg); } }
@keyframes helixdrift { 0%,100% { transform: translateY(0); } 50% { transform: translateY(-3px); } }
@keyframes nodepulse { 0%,100% { opacity: .55; } 50% { opacity: 1; } }

/* Motion is decoration. Anyone who has asked the OS to stop it gets a static
   page — the icons read fine still. Same rule the starfield already follows. */
@media (prefers-reduced-motion: reduce) {
  .orbit-spin, .helix-drift, .node-pulse { animation: none !important; }
  .honesty .card:hover { transform: none; }
}

/* --- co-equal paths: the built-in example vs. your own data ---------------- */
[data-baseweb="tab-list"] {
  gap: 6px;
  border-bottom: 1px solid var(--border);
}
[data-baseweb="tab"] {
  font-family: var(--sans); font-weight: 600; font-size: 14px;
  padding: 9px 16px; border-radius: 8px 8px 0 0;
  transition: color 160ms ease, background 160ms ease;
}
[data-baseweb="tab"]:hover { background: rgba(90,169,230,0.07); }
[aria-selected="true"][data-baseweb="tab"] { color: var(--accent); }

/* ==========================================================================
   WEB-APP SHELL — header nav instead of a sidebar.
   ========================================================================== */

/* The sidebar is gone. Hide its rail and collapse control so nothing of the
   dashboard chrome remains. */
section[data-testid="stSidebar"],
[data-testid="stSidebarCollapsedControl"],
[data-testid="collapsedControl"] { display: none !important; }

.block-container { padding-top: 1.2rem; max-width: 1240px; }

/* --- header bar ---------------------------------------------------------- */
.appbar {
  display: flex; align-items: center; gap: 14px;
  padding: 4px 2px 14px;
  border-bottom: 1px solid var(--border);
  margin-bottom: 6px;
}
.appbar .wordmark {
  font-family: var(--display);
  font-weight: 700; font-size: 19px; letter-spacing: -0.01em;
  color: var(--text); display: flex; align-items: center; gap: 9px;
}
.appbar .wordmark .dot { color: var(--accent); }
.appbar .spacer { flex: 1; }
.appbar .tag {
  font-size: 11.5px; color: var(--muted);
  border: 1px solid var(--border); border-radius: 999px;
  padding: 3px 10px;
}

/* Streamlit buttons are the only clickable primitive available, so the nav is
   built from them and restyled to read as header links rather than buttons. */
.navrow .stButton > button {
  background: transparent;
  border: 1px solid transparent;
  color: var(--muted);
  font-weight: 600; font-size: 13.5px;
  padding: 6px 12px;
  border-radius: 8px;
  transition: color 150ms ease, background 150ms ease, border-color 150ms ease;
  box-shadow: none;
}
.navrow .stButton > button:hover {
  color: var(--text);
  background: rgba(90,169,230,0.08);
  border-color: var(--border);
  transform: none;
  box-shadow: none;
}
.navrow .stButton > button[kind="primary"] {
  color: var(--accent);
  background: rgba(90,169,230,0.10);
  border-color: rgba(90,169,230,0.35);
}

/* --- landing hero: breathing room, not a control panel -------------------- */
.landing { padding: 26px 0 8px; }
.landing .kicker {
  font-size: 11px; letter-spacing: 0.14em; text-transform: uppercase;
  color: var(--accent); font-weight: 700; margin-bottom: 14px;
}
.landing h1 {
  font-family: var(--display);
  font-size: 3.1rem; line-height: 1.06; letter-spacing: -0.03em;
  margin: 0 0 14px;
}
.landing .tagline {
  font-size: 19px; line-height: 1.5; color: var(--accent);
  font-weight: 500; margin-bottom: 22px; max-width: 30ch;
}
.landing .intro {
  font-size: 15.5px; line-height: 1.75; color: var(--text);
  max-width: 66ch; margin-bottom: 14px;
}
.landing .intro em { color: var(--warn); font-style: normal; font-weight: 600; }
.landing .orient {
  font-size: 14.5px; line-height: 1.75; color: var(--muted);
  max-width: 68ch;
}
.landing .orient strong { color: var(--text); font-weight: 600; }

/* --- example-question chips ---------------------------------------------- */
.chips-label {
  font-size: 11px; letter-spacing: 0.09em; text-transform: uppercase;
  color: var(--muted); font-weight: 600; margin: 4px 0 8px;
}
.chiprow .stButton > button {
  background: rgba(90,169,230,0.06);
  border: 1px solid var(--border);
  color: var(--text);
  font-weight: 500; font-size: 12.5px;
  text-align: left; line-height: 1.45;
  padding: 10px 13px; border-radius: 999px;
  white-space: normal; height: auto; min-height: 44px;
}
.chiprow .stButton > button:hover {
  border-color: var(--accent);
  background: rgba(90,169,230,0.12);
  box-shadow: 0 0 16px rgba(90,169,230,0.14);
}

/* --- the "see an example" reveal ------------------------------------------ */
.examplecard {
  border: 1px solid var(--border);
  border-radius: 12px;
  padding: 18px 20px;
  background: var(--panel);
}

/* --- loading state ------------------------------------------------------- */
[data-testid="stSpinner"] { color: var(--accent); font-size: 13.5px; }
"""


def inject_theme() -> None:
    """Emit the theme's <style> block. Call once, before any page content."""
    st.markdown(f"<style>{_FONTS}{_CSS}</style>", unsafe_allow_html=True)