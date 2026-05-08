#!/usr/bin/env python3
"""
DSGAgraph.py  –  Convert a VCDS multi-channel CSV to an interactive HTML dashboard.
Usage:  python3 DSGAgraph.py <input.csv> <output.html>
"""

import sys
import csv
import json
import os

CHANNELS = [
    {"label": "Vehicle speed",            "unit": "km/h",  "ts_col": 3,  "val_col": 4,  "color": "#1a6fc4"},
    {"label": "Oil pressure – reservoir", "unit": "bar",   "ts_col": 7,  "val_col": 8,  "color": "#e05c2a"},
    {"label": "Aux. hydraulic pump 1",    "unit": "RPM",   "ts_col": 9,  "val_col": 10, "color": "#27a96c"},
    {"label": "Selected gear",            "unit": "",      "ts_col": 5,  "val_col": 6,  "color": "#9b59b6"},
    {"label": "ATF temperature",          "unit": "°C",    "ts_col": 1,  "val_col": 2,  "color": "#c0392b"},
]

def parse_csv(path):
    rows = []
    with open(path, newline='', encoding='utf-8', errors='replace') as f:
        reader = csv.reader(f)
        for i, row in enumerate(reader):
            if i < 7:
                continue
            if not any(row):
                continue
            rows.append(row)
    return rows

def extract_channel(rows, ts_col, val_col):
    times, values = [], []
    for row in rows:
        try:
            t = float(row[ts_col]) if len(row) > ts_col and row[ts_col].strip() else None
            v = float(row[val_col]) if len(row) > val_col and row[val_col].strip() else None
            if t is not None and v is not None:
                times.append(round(t, 3))
                values.append(v)
        except (ValueError, IndexError):
            pass
    return times, values

def build_html(channels_data, out_path):
    js_data = json.dumps(channels_data, separators=(',', ':'))

    html = """<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>DSG Graph</title>
<style>
  * { box-sizing: border-box; margin: 0; padding: 0; }
  body {
    font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif;
    background: #f0f2f5;
    color: #333;
    padding: 16px;
  }
  h1 { font-size: 15px; font-weight: 700; margin-bottom: 12px; color: #111; letter-spacing: 0.02em; }

  #controls {
    background: #fff;
    border: 1px solid #ddd;
    border-radius: 8px;
    padding: 12px 16px;
    margin-bottom: 12px;
    display: flex;
    flex-direction: column;
    gap: 8px;
  }
  .ctrl-divider {
    border: none;
    border-top: 1px solid #f0f0f0;
    margin: 2px 0;
  }
  .ctrl-row { display: flex; align-items: center; gap: 10px; }
  .ctrl-label {
    font-size: 11px;
    color: #888;
    white-space: nowrap;
    width: 96px;
    flex-shrink: 0;
    text-transform: uppercase;
    letter-spacing: 0.04em;
  }
  .ctrl-slider { flex: 1; cursor: pointer; height: 4px; }
  .ctrl-slider.pos  { accent-color: #1a6fc4; }
  .ctrl-slider.win  { accent-color: #555; }
  .ctrl-slider.cur  { accent-color: #e8900a; }
  .ctrl-value {
    font-size: 12px;
    font-variant-numeric: tabular-nums;
    font-weight: 600;
    min-width: 130px;
    text-align: right;
  }
  .ctrl-value.pos { color: #1a6fc4; }
  .ctrl-value.win { color: #555; }
  .ctrl-value.cur { color: #e8900a; }

  #charts { display: flex; flex-direction: column; gap: 6px; }

  .chart-wrap {
    background: #fff;
    border: 1px solid #ddd;
    border-radius: 8px;
    padding: 8px 12px 4px 12px;
    overflow: hidden;
  }
  .chart-title { font-size: 12px; font-weight: 600; color: #444; margin-bottom: 2px; }
  canvas { display: block; width: 100% !important; }
</style>
</head>
<body>

<h1>DSG Transmission Data</h1>

<div id="controls">
  <div class="ctrl-row">
    <span class="ctrl-label">Position</span>
    <input type="range" class="ctrl-slider pos" id="posSlider" min="0" max="100" value="0" step="0.5">
    <span class="ctrl-value pos" id="posDisplay">0.0 – 60.0 s</span>
  </div>
  <div class="ctrl-row">
    <span class="ctrl-label">Window</span>
    <input type="range" class="ctrl-slider win" id="winSlider" min="30" max="300" value="60" step="5">
    <span class="ctrl-value win" id="winDisplay">60 s</span>
  </div>
  <hr class="ctrl-divider">
  <div class="ctrl-row">
    <span class="ctrl-label">Cursor</span>
    <input type="range" class="ctrl-slider cur" id="curSlider" min="0" max="100" value="0" step="0.1">
    <span class="ctrl-value cur" id="curDisplay">0.0 s</span>
  </div>
</div>

<div id="charts"></div>

<script>
const CHANNELS = """ + js_data + """;

// ── animated state ────────────────────────────────────────────────────────
let t0Cur  = 0,  t0Tgt  = 0;
let winCur = 60, winTgt = 60;
let curCur = 0,  curTgt = 0;   // cursor absolute time
let rafId  = null;

const LERP = 0.16;
function lerp(a, b, k) { return a + (b - a) * k; }

// ── global time bounds ────────────────────────────────────────────────────
let gMin = Infinity, gMax = -Infinity;
CHANNELS.forEach(ch => ch.times.forEach(t => {
  if (t < gMin) gMin = t;
  if (t > gMax) gMax = t;
}));

// ── build canvases ────────────────────────────────────────────────────────
const chartsDiv = document.getElementById('charts');
const canvases  = [];

CHANNELS.forEach(ch => {
  const wrap  = document.createElement('div');
  wrap.className = 'chart-wrap';
  const title = document.createElement('div');
  title.className = 'chart-title';
  title.textContent = ch.label + (ch.unit ? ` (${ch.unit})` : '');
  // colour dot in title
  title.innerHTML =
    `<span style="display:inline-block;width:8px;height:8px;border-radius:50%;background:${ch.color};margin-right:5px;vertical-align:middle"></span>`
    + title.textContent;
  wrap.appendChild(title);
  const canvas = document.createElement('canvas');
  canvas.height = 110;
  wrap.appendChild(canvas);
  chartsDiv.appendChild(wrap);
  canvases.push(canvas);
});

// ── sliders ───────────────────────────────────────────────────────────────
const posSlider  = document.getElementById('posSlider');
const winSlider  = document.getElementById('winSlider');
const curSlider  = document.getElementById('curSlider');
const posDisplay = document.getElementById('posDisplay');
const winDisplay = document.getElementById('winDisplay');
const curDisplay = document.getElementById('curDisplay');

function updatePosRange() {
  posSlider.min  = gMin;
  posSlider.max  = Math.max(gMin, gMax - winTgt);
  posSlider.step = 0.5;
}
function updateCurRange() {
  curSlider.min  = gMin;
  curSlider.max  = gMax;
  curSlider.step = 0.1;
}

updatePosRange();
updateCurRange();
posSlider.value = gMin;
curSlider.value = gMin;
t0Cur = t0Tgt = gMin;
curCur = curTgt = gMin;

function fmtSec(s) {
  if (s < 60) return s.toFixed(1) + ' s';
  const m = Math.floor(s / 60), sec = Math.round(s % 60);
  return sec > 0 ? `${m}m ${sec}s` : `${m}m`;
}

function updateDisplays() {
  const t0 = parseFloat(posSlider.value);
  posDisplay.textContent = `${t0.toFixed(1)} – ${(t0 + winTgt).toFixed(1)} s`;
  winDisplay.textContent = fmtSec(winTgt);
  curDisplay.textContent = parseFloat(curSlider.value).toFixed(1) + ' s';
}
updateDisplays();

posSlider.addEventListener('input', () => {
  t0Tgt = parseFloat(posSlider.value);
  updateDisplays(); kick();
});
winSlider.addEventListener('input', () => {
  winTgt = parseInt(winSlider.value);
  updatePosRange();
  const maxPos = Math.max(gMin, gMax - winTgt);
  if (parseFloat(posSlider.value) > maxPos) posSlider.value = maxPos;
  t0Tgt = parseFloat(posSlider.value);
  updateDisplays(); kick();
});
curSlider.addEventListener('input', () => {
  curTgt = parseFloat(curSlider.value);
  updateDisplays(); kick();
});

// ── animation ─────────────────────────────────────────────────────────────
function kick() { if (!rafId) rafId = requestAnimationFrame(frame); }

function frame() {
  rafId = null;
  t0Cur  = lerp(t0Cur,  t0Tgt,  LERP);
  winCur = lerp(winCur, winTgt, LERP);
  curCur = lerp(curCur, curTgt, LERP);

  CHANNELS.forEach((ch, i) => drawChart(canvases[i], ch, t0Cur, winCur, curCur));

  const settled =
    Math.abs(t0Cur  - t0Tgt)  < 0.005 &&
    Math.abs(winCur - winTgt) < 0.05  &&
    Math.abs(curCur - curTgt) < 0.005;
  if (!settled) rafId = requestAnimationFrame(frame);
}

// ── draw one chart ─────────────────────────────────────────────────────────
function drawChart(canvas, ch, t0, win, cursorT) {
  const t1  = t0 + win;
  const dpr = window.devicePixelRatio || 1;
  const W   = canvas.parentElement.clientWidth - 24;
  const H   = 110;

  canvas.width        = W * dpr;
  canvas.height       = H * dpr;
  canvas.style.width  = W + 'px';
  canvas.style.height = H + 'px';

  const ctx = canvas.getContext('2d');
  ctx.scale(dpr, dpr);

  const PL = 52, PR = 8, PT = 8, PB = 22;
  const pW = W - PL - PR, pH = H - PT - PB;

  // fixed global y range
  const yr = { min: ch.yMin, max: ch.yMax };

  const xPx = t => PL + (t - t0) / win * pW;
  const yPx = v => PT + (1 - (v - yr.min) / (yr.max - yr.min)) * pH;

  // background
  ctx.fillStyle = '#fff';
  ctx.fillRect(0, 0, W, H);

  // horizontal grid
  ctx.strokeStyle = '#ebebeb'; ctx.lineWidth = 1;
  const nG = 4;
  for (let i = 0; i <= nG; i++) {
    const y = yPx(yr.min + (yr.max - yr.min) * i / nG);
    ctx.beginPath(); ctx.moveTo(PL, y); ctx.lineTo(W - PR, y); ctx.stroke();
  }

  // vertical grid
  const nX = win <= 60 ? 6 : win <= 120 ? 8 : 10;
  ctx.strokeStyle = '#f2f2f2';
  for (let i = 0; i <= nX; i++) {
    const x = xPx(t0 + win * i / nX);
    ctx.beginPath(); ctx.moveTo(x, PT); ctx.lineTo(x, H - PB); ctx.stroke();
  }

  // y labels
  ctx.fillStyle = '#999'; ctx.font = '10px sans-serif';
  ctx.textAlign = 'right'; ctx.textBaseline = 'middle';
  for (let i = 0; i <= nG; i++) {
    const v = yr.min + (yr.max - yr.min) * i / nG;
    let lbl;
    if (ch.label.includes('gear'))            lbl = Math.round(v).toString();
    else if (Math.abs(v) >= 1000)             lbl = (v / 1000).toFixed(1) + 'k';
    else if (Math.abs(yr.max - yr.min) > 5)  lbl = Math.round(v).toString();
    else                                       lbl = v.toFixed(1);
    ctx.fillText(lbl, PL - 5, yPx(v));
  }

  // x labels
  ctx.textAlign = 'center'; ctx.textBaseline = 'alphabetic'; ctx.fillStyle = '#999';
  for (let i = 0; i <= nX; i++) {
    const t = t0 + win * i / nX;
    const x = xPx(t);
    const lbl = t >= 60
      ? Math.floor(t/60) + 'm' + (Math.round(t % 60) > 0 ? Math.round(t%60)+'s' : '')
      : t.toFixed(0) + 's';
    ctx.fillText(lbl, x, H - 4);
    ctx.strokeStyle = '#ddd'; ctx.lineWidth = 1;
    ctx.beginPath(); ctx.moveTo(x, H - PB); ctx.lineTo(x, H - PB + 3); ctx.stroke();
  }

  // clip region for data + cursor
  ctx.save();
  ctx.beginPath(); ctx.rect(PL, PT, pW, pH); ctx.clip();

  // data line
  const pts = [];
  for (let i = 0; i < ch.times.length; i++) {
    if (ch.times[i] >= t0 - 2 && ch.times[i] <= t1 + 2)
      pts.push({ t: ch.times[i], v: ch.values[i] });
  }

  if (pts.length > 1) {
    const isGear = ch.label.toLowerCase().includes('gear');
    ctx.strokeStyle = ch.color || '#1a6fc4';
    ctx.lineWidth   = 1.8;
    ctx.lineJoin = ctx.lineCap = 'round';
    ctx.beginPath();

    if (isGear) {
      pts.forEach((p, i) => {
        if (i === 0) { ctx.moveTo(xPx(p.t), yPx(p.v)); }
        else {
          ctx.lineTo(xPx(p.t), yPx(pts[i-1].v));
          ctx.lineTo(xPx(p.t), yPx(p.v));
        }
      });
    } else {
      ctx.moveTo(xPx(pts[0].t), yPx(pts[0].v));
      for (let i = 1; i < pts.length - 1; i++) {
        const mx = (xPx(pts[i].t) + xPx(pts[i+1].t)) / 2;
        const my = (yPx(pts[i].v) + yPx(pts[i+1].v)) / 2;
        ctx.quadraticCurveTo(xPx(pts[i].t), yPx(pts[i].v), mx, my);
      }
      ctx.lineTo(xPx(pts[pts.length-1].t), yPx(pts[pts.length-1].v));
    }
    ctx.stroke();
  }

  // cursor vertical line (only if within visible window)
  if (cursorT >= t0 && cursorT <= t1) {
    const cx = xPx(cursorT);

    // shaded region left of cursor (subtle)
    ctx.fillStyle = 'rgba(232,144,10,0.06)';
    ctx.fillRect(PL, PT, cx - PL, pH);

    // cursor line
    ctx.strokeStyle = '#e8900a';
    ctx.lineWidth   = 1.5;
    ctx.setLineDash([4, 3]);
    ctx.beginPath();
    ctx.moveTo(cx, PT);
    ctx.lineTo(cx, PT + pH);
    ctx.stroke();
    ctx.setLineDash([]);

    // cursor dot: interpolate value at cursor time
    let dotV = null;
    for (let i = 0; i < ch.times.length - 1; i++) {
      if (ch.times[i] <= cursorT && ch.times[i+1] >= cursorT) {
        const frac = (cursorT - ch.times[i]) / (ch.times[i+1] - ch.times[i]);
        dotV = ch.values[i] + frac * (ch.values[i+1] - ch.values[i]);
        break;
      }
    }
    if (dotV !== null) {
      const cy = yPx(dotV);
      // halo
      ctx.beginPath();
      ctx.arc(cx, cy, 5, 0, Math.PI * 2);
      ctx.fillStyle = 'rgba(232,144,10,0.2)';
      ctx.fill();
      // dot
      ctx.beginPath();
      ctx.arc(cx, cy, 3, 0, Math.PI * 2);
      ctx.fillStyle = '#e8900a';
      ctx.fill();
      ctx.strokeStyle = '#fff';
      ctx.lineWidth   = 1.2;
      ctx.stroke();

      // value label
      const valStr = ch.label.includes('gear')
        ? Math.round(dotV).toString()
        : Math.abs(dotV) >= 1000
          ? (dotV/1000).toFixed(2) + 'k'
          : Math.abs(yr.max - yr.min) > 5
            ? Math.round(dotV).toString()
            : dotV.toFixed(1);
      const unitStr = ch.unit ? ' ' + ch.unit : '';
      const labelText = valStr + unitStr;

      ctx.font = 'bold 10px sans-serif';
      ctx.textBaseline = 'middle';
      const lw = ctx.measureText(labelText).width;
      // position label: prefer right of cursor, flip if too close to right edge
      const lx = (cx + 8 + lw + 4 < PL + pW) ? cx + 8 : cx - 8 - lw - 4;
      // pill background
      ctx.fillStyle = 'rgba(232,144,10,0.9)';
      const lh = 14, lr = 3;
      ctx.beginPath();
      ctx.roundRect(lx - 2, cy - lh/2, lw + 6, lh, lr);
      ctx.fill();
      // label text
      ctx.fillStyle = '#fff';
      ctx.textAlign = 'left';
      ctx.fillText(labelText, lx + 1, cy);
    }
  }

  ctx.restore();

  // border
  ctx.strokeStyle = '#d0d0d0'; ctx.lineWidth = 1;
  ctx.strokeRect(PL, PT, pW, pH);
}

// ── initial draw ──────────────────────────────────────────────────────────
function redrawAll() {
  CHANNELS.forEach((ch, i) => drawChart(canvases[i], ch, t0Cur, winCur, curCur));
}
window.addEventListener('resize', redrawAll);
redrawAll();
</script>
</body>
</html>
"""
    with open(out_path, 'w', encoding='utf-8') as f:
        f.write(html)
    print(f"Written -> {out_path}")

def main():
    if len(sys.argv) != 3:
        print("Usage: python3 DSGAgraph.py <input.csv> <output.html>")
        sys.exit(1)
    csv_path, html_path = sys.argv[1], sys.argv[2]
    if not os.path.isfile(csv_path):
        print(f"Error: file not found: {csv_path}"); sys.exit(1)
    print(f"Parsing {csv_path} ...")
    rows = parse_csv(csv_path)
    print(f"  {len(rows)} data rows")
    channels_data = []
    for ch in CHANNELS:
        times, values = extract_channel(rows, ch["ts_col"], ch["val_col"])
        print(f"  {ch['label']}: {len(times)} points, t=[{min(times,default=0):.1f}, {max(times,default=0):.1f}]")
        vmin = min(values, default=0)
        vmax = max(values, default=1)
        if vmin == vmax:
            vmin -= 1; vmax += 1
        pad = (vmax - vmin) * 0.08
        channels_data.append({"label": ch["label"], "unit": ch["unit"],
                               "color": ch["color"], "times": times, "values": values,
                               "yMin": round(vmin - pad, 4), "yMax": round(vmax + pad, 4)})
    build_html(channels_data, html_path)

if __name__ == "__main__":
    main()
