"""Iframe-isolated UI components. Styling only — no analysis code here.

Why these use `components.html` and not `st.markdown`
----------------------------------------------------
Streamlit re-runs the whole script top-to-bottom on *every* interaction, anywhere
on the page. A count-up animation injected via `st.markdown` would therefore
restart from zero every time an unrelated widget changed — tick a filter checkbox
and every counter on the page flickers back to 0 and re-counts. That is worse
than no animation.

`components.html` renders into an iframe whose content is set by an HTML string.
Streamlit only remounts that iframe when the string *changes*. So as long as the
HTML is a pure function of the values (no timestamps, no randomness, nothing
non-deterministic), an unrelated rerun produces a byte-identical string, the
iframe is left alone, and the counter holds its final value without re-animating.

That determinism is load-bearing, not incidental. Do not put a nonce, a
`Date.now()`, or a random id in these templates.
"""

from __future__ import annotations

import json

import streamlit as st
import streamlit.components.v1 as components

_FONTS = (
    "@import url('https://fonts.googleapis.com/css2?"
    "family=Inter:wght@400;500;600;700&"
    "family=JetBrains+Mono:wght@500;700&display=swap');"
)

_BASE_CSS = """
html, body { background: transparent; margin: 0; padding: 0; }
* { box-sizing: border-box; }
body {
  font-family: 'Inter', -apple-system, BlinkMacSystemFont, 'Segoe UI', sans-serif;
  color: #e6e9ef;
}
.mono { font-family: 'JetBrains Mono', ui-monospace, monospace; }
"""

# ease-out cubic: fast at first, settling gently — reads as deceleration into the
# final value rather than a linear tick.
_EASE = "1 - Math.pow(1 - t, 3)"

_DURATION_MS = 900


def animated_counters(items: list[dict], height: int = 118) -> None:
    """A row of count-up tiles.

    Each item: {label, value, color?, text?}
      value : the real number. Counts 0 -> value once, on first render.
      text  : if given, shown verbatim instead of a counter (for non-numeric
              tiles like "DESeq2 (pydeseq2)").

    The displayed final value is `value` formatted with thousands separators —
    identical to what `st.metric` showed. The animation never alters the number.
    """
    payload = json.dumps(items)

    html = f"""
<style>
{_FONTS}
{_BASE_CSS}
.row {{ display: flex; gap: 14px; flex-wrap: wrap; }}
.tile {{
  flex: 1 1 180px;
  background: #141922;
  border: 1px solid #232b39;
  border-radius: 10px;
  padding: 14px 16px;
  transition: border-color 180ms ease, box-shadow 180ms ease, transform 180ms ease;
}}
.tile:hover {{
  border-color: #5aa9e6;
  box-shadow: 0 0 0 1px rgba(90,169,230,0.22), 0 0 20px rgba(90,169,230,0.16);
  transform: translateY(-1px);
}}
.label {{
  font-size: 11px; font-weight: 600; letter-spacing: 0.07em;
  text-transform: uppercase; color: #8b96a8; margin-bottom: 6px;
}}
.value {{ font-size: 30px; font-weight: 700; line-height: 1.15; }}
.value.text {{ font-size: 19px; }}
</style>
<div class="row" id="row"></div>
<script>
const items = {payload};
const row = document.getElementById("row");

for (const item of items) {{
  const tile = document.createElement("div");
  tile.className = "tile";

  const label = document.createElement("div");
  label.className = "label";
  label.textContent = item.label;

  const value = document.createElement("div");
  value.className = "value mono" + (item.text ? " text" : "");
  if (item.color) value.style.color = item.color;

  if (item.text) {{
    value.textContent = item.text;
  }} else {{
    const target = Number(item.value);
    const start = performance.now();
    const fmt = (n) => n.toLocaleString("en-US");
    value.textContent = fmt(0);
    const step = (now) => {{
      const t = Math.min((now - start) / {_DURATION_MS}, 1);
      const eased = {_EASE};
      value.textContent = fmt(Math.round(target * eased));
      if (t < 1) requestAnimationFrame(step);
      else value.textContent = fmt(target);   // land exactly on the real value
    }};
    requestAnimationFrame(step);
  }}

  tile.appendChild(label);
  tile.appendChild(value);
  row.appendChild(tile);
}}
</script>
"""
    components.html(html, height=height)


def cardinality_counters(counts: dict, meta: dict, height: int = 168) -> None:
    """The five ortholog-cardinality tiles, as count-ups.

    `meta` maps key -> (label, color, blurb) — passed in rather than duplicated,
    so the labels and colours stay defined in one place in the app.
    """
    items = [
        {
            "key": key,
            "label": meta[key][0],
            "color": meta[key][1],
            "blurb": meta[key][2],
            "value": int(counts.get(key, 0)),
        }
        for key in meta
    ]
    payload = json.dumps(items)

    html = f"""
<style>
{_FONTS}
{_BASE_CSS}
.row {{ display: flex; gap: 12px; flex-wrap: wrap; }}
.card {{
  flex: 1 1 190px;
  background: #141922;
  border: 1px solid #232b39;
  border-radius: 10px;
  padding: 13px 15px;
  transition: border-color 180ms ease, box-shadow 180ms ease, transform 180ms ease;
}}
.card:hover {{ transform: translateY(-2px); }}
.count {{ font-size: 27px; font-weight: 700; line-height: 1.2; }}
.name {{ font-size: 13px; font-weight: 600; margin-top: 1px; }}
.blurb {{ font-size: 11px; color: #8b96a8; margin-top: 5px; line-height: 1.45; }}
</style>
<div class="row" id="row"></div>
<script>
const items = {payload};
const row = document.getElementById("row");

for (const item of items) {{
  const card = document.createElement("div");
  card.className = "card";
  card.style.borderTop = "3px solid " + item.color;
  card.onmouseenter = () => {{
    card.style.borderColor = item.color;
    card.style.boxShadow = "0 0 20px " + item.color + "26";
  }};
  card.onmouseleave = () => {{
    card.style.borderColor = "#232b39";
    card.style.borderTopColor = item.color;
    card.style.boxShadow = "none";
  }};

  const count = document.createElement("div");
  count.className = "count mono";
  count.style.color = item.color;

  const name = document.createElement("div");
  name.className = "name";
  name.textContent = item.label;

  const blurb = document.createElement("div");
  blurb.className = "blurb";
  blurb.textContent = item.blurb;

  const target = Number(item.value);
  const start = performance.now();
  const fmt = (n) => n.toLocaleString("en-US");
  count.textContent = fmt(0);
  const step = (now) => {{
    const t = Math.min((now - start) / {_DURATION_MS}, 1);
    const eased = {_EASE};
    count.textContent = fmt(Math.round(target * eased));
    if (t < 1) requestAnimationFrame(step);
    else count.textContent = fmt(target);
  }};
  requestAnimationFrame(step);

  card.appendChild(count);
  card.appendChild(name);
  card.appendChild(blurb);
  row.appendChild(card);
}}
</script>
"""
    components.html(html, height=height)


# --- mission timeline --------------------------------------------------------

# Which mission each dataset flew on, and the ordering of those missions.
#
# Every fact shown on hover comes from config/datasets.yaml. The only thing added
# here is the grouping and the left-to-right order, and that order asserts one
# claim: Rodent Research 1 flew before Inspiration4. Inspiration4's launch date
# (2021-09-16) is already in the codebase as the anchor of the mission-day axis
# (src/forecast/prophet_model.py). No launch date is invented for RR-1 — none is
# shown, because none is in the repo to source it from.
MISSIONS = [
    {
        "key": "rodent",
        "name": "Rodent Research 1",
        "sub": "Mus musculus · hindlimb muscle",
        "date": "",
        "color": "#c9a227",
        "match": lambda s: s["organism"] == "Mus musculus",
    },
    {
        "key": "i4",
        "name": "Inspiration4",
        "sub": "Homo sapiens · 4 crew, 3-day mission",
        "date": "launch 2021-09-16",
        "color": "#5aa9e6",
        "match": lambda s: s["organism"] == "Homo sapiens",
    },
]


def mission_timeline(studies: list[dict], height: int = 300) -> None:
    """Horizontal mission timeline. Hover a node for that dataset's real record.

    Tooltip content is read straight out of datasets.yaml — organism, tissue,
    assay, design, notes. Nothing is invented for decoration.
    """
    groups = []
    for mission in MISSIONS:
        members = [s for s in studies if mission["match"](s)]
        if members:
            groups.append({
                "name": mission["name"],
                "sub": mission["sub"],
                "date": mission["date"],
                "color": mission["color"],
                "datasets": [
                    {
                        "accession": s["accession"],
                        "label": s["label"],
                        "organism": s["organism"],
                        "tissue": s["tissue"],
                        "assay": s["assay"],
                        "design": s["design"],
                        "module": s["module"],
                        "notes": (s.get("notes") or "").strip(),
                    }
                    for s in members
                ],
            })

    payload = json.dumps(groups)

    html = f"""
<style>
{_FONTS}
{_BASE_CSS}
#wrap {{ position: relative; }}
svg {{ width: 100%; height: 230px; display: block; }}
.axis {{ stroke: #2b3547; stroke-width: 2; }}
.node {{ cursor: pointer; transition: r 140ms ease; }}
.mission-name {{ font-size: 13px; font-weight: 700; }}
.mission-sub  {{ font-size: 10.5px; fill: #8b96a8; }}
.acc {{ font-family: 'JetBrains Mono', monospace; font-size: 11px; fill: #c3cad6; }}
#tip {{
  position: absolute; pointer-events: none; opacity: 0;
  transition: opacity 120ms ease;
  background: #0d111a; border: 1px solid #2b3547; border-radius: 8px;
  padding: 10px 12px; max-width: 300px; font-size: 12px; line-height: 1.5;
  box-shadow: 0 8px 28px rgba(0,0,0,0.55);
  z-index: 5;
}}
#tip .t-acc {{ font-family: 'JetBrains Mono', monospace; font-weight: 700; }}
#tip .t-row {{ color: #8b96a8; margin-top: 3px; }}
#tip .t-notes {{ margin-top: 7px; color: #c3cad6; font-size: 11.5px; }}
</style>
<div id="wrap">
  <svg id="tl" viewBox="0 0 1000 230" preserveAspectRatio="xMidYMid meet"></svg>
  <div id="tip"></div>
</div>
<script>
const groups = {payload};
const svg = document.getElementById("tl");
const tip = document.getElementById("tip");
const NS = "http://www.w3.org/2000/svg";
const mk = (n, a) => {{
  const e = document.createElementNS(NS, n);
  for (const k in a) e.setAttribute(k, a[k]);
  return e;
}};

const Y = 132;                                  // the timeline axis
const L = 70, R = 930;
svg.appendChild(mk("line", {{x1: L, y1: Y, x2: R, y2: Y, class: "axis"}}));

// Arrowhead: time runs left to right.
const head = mk("path", {{d: `M ${{R}} ${{Y}} l -9 -5 l 0 10 z`, fill: "#2b3547"}});
svg.appendChild(head);

const span = R - L;
const slot = span / groups.length;

groups.forEach((g, gi) => {{
  const cx = L + slot * (gi + 0.5);

  // Mission marker on the axis.
  svg.appendChild(mk("line",
    {{x1: cx, y1: Y - 26, x2: cx, y2: Y + 26, stroke: g.color, "stroke-width": 2, opacity: 0.55}}));

  const title = mk("text", {{x: cx, y: Y - 46, "text-anchor": "middle", fill: g.color, class: "mission-name"}});
  title.textContent = g.name;
  svg.appendChild(title);

  const sub = mk("text", {{x: cx, y: Y - 31, "text-anchor": "middle", class: "mission-sub"}});
  sub.textContent = g.date ? g.sub + " · " + g.date : g.sub;
  svg.appendChild(sub);

  // One node per dataset, spread horizontally under the mission marker.
  const n = g.datasets.length;
  const step = 108;
  const x0 = cx - (step * (n - 1)) / 2;

  g.datasets.forEach((d, di) => {{
    const x = x0 + step * di;

    svg.appendChild(mk("line",
      {{x1: cx, y1: Y, x2: x, y2: Y + 44, stroke: g.color, "stroke-width": 1, opacity: 0.35}}));

    const halo = mk("circle", {{cx: x, cy: Y + 44, r: 11, fill: g.color, opacity: 0.16}});
    svg.appendChild(halo);

    const node = mk("circle",
      {{cx: x, cy: Y + 44, r: 5.5, fill: g.color, stroke: "#0b0e14", "stroke-width": 1.5, class: "node"}});
    svg.appendChild(node);

    const acc = mk("text", {{x: x, y: Y + 72, "text-anchor": "middle", class: "acc"}});
    acc.textContent = d.accession;
    svg.appendChild(acc);

    const show = (evt) => {{
      node.setAttribute("r", 8);
      halo.setAttribute("opacity", 0.34);
      tip.innerHTML =
        `<div class="t-acc" style="color:${{g.color}}">${{d.accession}}</div>` +
        `<div class="t-row">${{d.organism}} · ${{d.tissue}}</div>` +
        `<div class="t-row">${{d.assay}}</div>` +
        `<div class="t-row">${{d.design}}</div>` +
        (d.notes ? `<div class="t-notes">${{d.notes}}</div>` : "");
      const box = svg.getBoundingClientRect();
      const scale = box.width / 1000;
      tip.style.left = Math.min(x * scale + 16, box.width - 316) + "px";
      tip.style.top  = (Y + 44) * (box.height / 230) + 14 + "px";
      tip.style.opacity = 1;
    }};
    const hide = () => {{
      node.setAttribute("r", 5.5);
      halo.setAttribute("opacity", 0.16);
      tip.style.opacity = 0;
    }};
    node.addEventListener("mouseenter", show);
    node.addEventListener("mouseleave", hide);
  }});
}});
</script>
"""
    components.html(html, height=height)
