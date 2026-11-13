"""XKCD-style hand-drawn line chart of daily AI-coding token usage.

One chart: charts/day/sketch-tokens.svg. Two wobbly lines (Claude Code and
Codex daily totals, NOT stacked), hand-drawn axes with arrowheads, direct
hand-written labels at the line ends with curvy arrows, and a scribbled
circle + dry caption on the peak day.

Determinism: all wobble comes from a tiny LCG seeded with crc32 of a constant
tag per path — same data in, byte-identical SVG out. No `random`, no time.

Targets Python 3.9, stdlib only. Reuses render.py helpers for theming.
"""

import math
import zlib

import render

W = 880
H = 400
PAD_L, PAD_R, PAD_T, PAD_B = 84, 168, 96, 62
PLOT_W = W - PAD_L - PAD_R
PLOT_H = H - PAD_T - PAD_B

FONT_HAND = '"Chalkboard SE","Comic Sans MS","Segoe Print","Bradley Hand",cursive'

SKETCH_CSS = (
    ".hx{{font-family:{f};fill:var(--primary)}}"
    ".hx2{{font-family:{f};fill:var(--secondary)}}"
    ".hxm{{font-family:{f};fill:var(--muted)}}"
    ".ink{{stroke:var(--primary);fill:none;stroke-linecap:round;stroke-linejoin:round}}"
    ".ln{{fill:none;stroke-width:2.5;stroke-linecap:round;stroke-linejoin:round}}"
    ".lc{{stroke:var(--claude)}}"
    ".lx{{stroke:var(--codex)}}"
    ".lg{{stroke:var(--gemini)}}"
    ".draw{{stroke-dasharray:3200;animation:dw 1.5s ease-out both}}"
    "@keyframes dw{{from{{stroke-dashoffset:3200}}to{{stroke-dashoffset:0}}}}"
    ".late{{animation:fi .5s ease-out 1.25s both}}"
    "@keyframes fi{{from{{opacity:0}}to{{opacity:1}}}}"
).format(f=FONT_HAND)


# ------------------------------------------------------------- seeded scribble


def _rng(tag):
    """Tiny deterministic LCG in [0,1), seeded from a constant string tag."""
    state = (zlib.crc32(tag.encode("utf-8")) ^ 0x9E3779B9) & 0xFFFFFFFF

    def rnd():
        nonlocal state
        state = (state * 1664525 + 1013904223) & 0xFFFFFFFF
        return state / 4294967296.0

    return rnd


def _jit(rnd, amp):
    return (rnd() * 2.0 - 1.0) * amp


def _smooth(pts):
    """Midpoint-quadratic smoothing: gentle curves through a wobbled polyline."""
    if len(pts) < 3:
        return "M{:.1f},{:.1f} L{:.1f},{:.1f}".format(
            pts[0][0], pts[0][1], pts[-1][0], pts[-1][1])
    d = ["M{:.1f},{:.1f}".format(pts[0][0], pts[0][1])]
    for i in range(1, len(pts) - 1):
        mx = (pts[i][0] + pts[i + 1][0]) / 2.0
        my = (pts[i][1] + pts[i + 1][1]) / 2.0
        d.append("Q{:.1f},{:.1f} {:.1f},{:.1f}".format(pts[i][0], pts[i][1], mx, my))
    d.append("L{:.1f},{:.1f}".format(pts[-1][0], pts[-1][1]))
    return " ".join(d)


def _densify(pts, step):
    dense = [pts[0]]
    for i in range(len(pts) - 1):
        (x1, y1), (x2, y2) = pts[i], pts[i + 1]
        seg = math.hypot(x2 - x1, y2 - y1)
        k = max(1, int(seg // step))
        for j in range(1, k + 1):
            t = j / float(k)
            dense.append((x1 + (x2 - x1) * t, y1 + (y2 - y1) * t))
    return dense


def _sketch_path(pts, tag, amp=1.5, step=9.0, overshoot=0.0):
    """Hand-drawn path: subdivide every ~step px, wander each interior point
    by +/-amp (seeded), then smooth. `overshoot` extends both ends a touch
    past the true endpoints for the inked feel."""
    rnd = _rng(tag)
    pts = list(pts)
    if overshoot and len(pts) >= 2:
        def ext(a, b, d):
            dx, dy = b[0] - a[0], b[1] - a[1]
            n = math.hypot(dx, dy) or 1.0
            return (b[0] + dx / n * d, b[1] + dy / n * d)
        pts[0] = ext(pts[1], pts[0], overshoot)
        pts[-1] = ext(pts[-2], pts[-1], overshoot)
    dense = _densify(pts, step)
    wob = []
    last = len(dense) - 1
    for i, (x, y) in enumerate(dense):
        a = amp * (0.4 if i in (0, last) else 1.0)
        wob.append((x + _jit(rnd, a * 0.5), y + _jit(rnd, a)))
    return _smooth(wob)


def _arrowhead(x, y, ang, size=7.0):
    """Two little barb strokes forming a V at (x, y), pointing along `ang`."""
    a1 = ang + math.radians(152)
    a2 = ang - math.radians(152)
    return ("M{:.1f},{:.1f} L{:.1f},{:.1f} M{:.1f},{:.1f} L{:.1f},{:.1f}".format(
        x + math.cos(a1) * size, y + math.sin(a1) * size, x, y,
        x, y, x + math.cos(a2) * size, y + math.sin(a2) * size))


def _curve_arrow(x1, y1, x2, y2, bend):
    """Quadratic-bezier arrow from (x1,y1) to (x2,y2); returns (path d, tip angle)."""
    mx, my = (x1 + x2) / 2.0, (y1 + y2) / 2.0
    dx, dy = x2 - x1, y2 - y1
    n = math.hypot(dx, dy) or 1.0
    cx, cy = mx - dy / n * bend, my + dx / n * bend
    d = "M{:.1f},{:.1f} Q{:.1f},{:.1f} {:.1f},{:.1f}".format(x1, y1, cx, cy, x2, y2)
    return d, math.atan2(y2 - cy, x2 - cx)


def _scribble_ellipse(cx, cy, rx, ry, tag):
    """A casually-closed ellipse: ~1.13 loops with a wandering radius."""
    rnd = _rng(tag)
    pts = []
    steps = 30
    total = 2 * math.pi * 1.13
    a0 = -0.7
    for i in range(steps + 1):
        t = a0 + total * i / float(steps)
        kx = 1.0 + _jit(rnd, 0.08)
        ky = 1.0 + _jit(rnd, 0.10)
        pts.append((cx + math.cos(t) * rx * kx, cy + math.sin(t) * ry * ky))
    return _smooth(pts)


# ------------------------------------------------------------------- the chart


def _build_sketch(rows, generated):
    n = len(rows)
    per_s = {s: [r[s]["total"] for r in rows] for s, _ in render.SERIES}
    all_vals = [v for vals in per_s.values() for v in vals]
    peak = max(all_vals + [0])
    ticks = render.nice_ticks(peak)
    top = ticks[-1] or 1
    grand = sum(all_vals)
    partial_last = bool(rows[-1].get("partial"))

    def x_of(i):
        return PAD_L + PLOT_W * (i / float(n - 1))

    def y_of(v):
        return PAD_T + PLOT_H - (v / float(top)) * PLOT_H

    base_y = PAD_T + PLOT_H
    title = "MY AI TOKEN CONSUMPTION"
    label = "Hand-drawn chart of daily AI coding token usage, {} to {}".format(
        rows[0]["start"].isoformat(), rows[-1]["start"].isoformat())

    out = render.svg_start(W, H, label, SKETCH_CSS)
    add = out.append
    rot = _rng("labels")  # one stream for every casual text rotation

    def hand_text(x, y, size, txt, cls="hx", anchor="start", weight=None, tilt=2.0):
        r = _jit(rot, tilt)
        w = ' font-weight="{}"'.format(weight) if weight else ""
        add('<text class="{}" x="{:.1f}" y="{:.1f}" font-size="{}" text-anchor="{}"'
            '{} transform="rotate({:.1f} {:.1f} {:.1f})">{}</text>'.format(
                cls, x, y, size, anchor, w, r, x, y, render.esc(txt)))

    # ---- heading
    hand_text(28, 46, 23, title, weight="700", tilt=1.2)
    hand_text(30, 68, 12.5, "{} – {}  ·  {} tokens, allegedly".format(
        rows[0]["start"].strftime("%b %d").upper(),
        rows[-1]["start"].strftime("%b %d").upper(),
        render.compact_tokens(grand)), cls="hx2", tilt=1.0)

    # ---- hand-drawn axes with arrowheads
    y_top_end = PAD_T - 20
    x_right_end = PAD_L + PLOT_W + 28
    add('<path class="ink" stroke-width="2" d="{}"/>'.format(
        _sketch_path([(PAD_L, base_y), (PAD_L, y_top_end)], "axis-y",
                     amp=1.1, overshoot=4.0)))
    add('<path class="ink" stroke-width="2" d="{}"/>'.format(
        _arrowhead(PAD_L, y_top_end - 4, -math.pi / 2.0)))
    add('<path class="ink" stroke-width="2" d="{}"/>'.format(
        _sketch_path([(PAD_L, base_y), (x_right_end, base_y)], "axis-x",
                     amp=1.1, overshoot=4.0)))
    add('<path class="ink" stroke-width="2" d="{}"/>'.format(
        _arrowhead(x_right_end + 4, base_y, 0.0)))

    # ---- sparse ticks: marks at every step, handwriting labels every other one
    for ti, tick in enumerate(ticks):
        if tick <= 0:
            continue
        y = y_of(tick)
        add('<path class="ink" stroke-width="1.6" d="{}"/>'.format(
            _sketch_path([(PAD_L - 5, y), (PAD_L + 3, y)], "tick-y{}".format(ti),
                         amp=0.7, step=4.0)))
        if ti % 2 == 0:
            hand_text(PAD_L - 11, y + 4, 12, render.compact_tokens(tick),
                      cls="hxm", anchor="end")
    for i in (0, (n - 1) // 3, 2 * (n - 1) // 3, n - 1):
        x = x_of(i)
        add('<path class="ink" stroke-width="1.6" d="{}"/>'.format(
            _sketch_path([(x, base_y - 2), (x, base_y + 6)], "tick-x{}".format(i),
                         amp=0.7, step=4.0)))
        hand_text(x, base_y + 22, 12, rows[i]["start"].strftime("%b %d").upper(),
                  cls="hxm", anchor="middle")

    # ---- the wobbly lines (draw-in animation; resting state fully visible)
    line_specs = (
        ("claude", "lc", "0s", "CLAUDE CODE", "var(--claude)"),
        ("codex", "lx", ".3s", "CODEX", "var(--codex)"),
        ("gemini", "lg", ".6s", "GEMINI", "var(--gemini)"),
    )
    series_geom = {}
    for source, cls_k, delay, _, _ in line_specs:
        vals = per_s[source]
        pts = [(x_of(i), y_of(v)) for i, v in enumerate(vals)]
        series_geom[source] = pts
        add('<path class="ln {} draw" style="animation-delay:{}" d="{}"/>'.format(
            cls_k, delay, _sketch_path(pts, "line-" + source, amp=2.1, step=8.0,
                                       overshoot=3.0)))

    # ---- direct hand-written labels at the line ends, with curvy arrows
    mark = "*" if partial_last else ""
    lab_x = PAD_L + PLOT_W + 34
    ends = sorted(
        [(y_of(per_s[s][-1]), s, lbl, per_s[s][-1], stroke)
         for s, _, _, lbl, stroke in line_specs],
        key=lambda t: t[0],
    )
    placed_y = [min(max(e[0], PAD_T + 12), base_y - 24) for e in ends]
    for i in range(1, len(placed_y)):
        if placed_y[i] - placed_y[i - 1] < 40:
            placed_y[i] = placed_y[i - 1] + 40
    if placed_y[-1] > base_y - 18:
        shift = placed_y[-1] - (base_y - 18)
        placed_y = [y - shift for y in placed_y]
        for i in range(len(placed_y) - 2, -1, -1):
            if placed_y[i + 1] - placed_y[i] < 40:
                placed_y[i] = placed_y[i + 1] - 40
    for (ey, source, name, val, stroke), ly in zip(ends, placed_y):
        d, ang = _curve_arrow(lab_x - 2, ly - 4, PAD_L + PLOT_W + 7, ey,
                              10.0 if ey > ly else -10.0)
        add('<g class="late">')
        add('<path fill="none" stroke="{}" stroke-width="1.6" stroke-linecap="round" '
            'd="{}"/>'.format(stroke, d))
        add('<path fill="none" stroke="{}" stroke-width="1.6" stroke-linecap="round" '
            'd="{}"/>'.format(stroke, _arrowhead(PAD_L + PLOT_W + 7, ey, ang, 5.5)))
        hand_text(lab_x + 4, ly - 6, 13, name, weight="700")
        hand_text(lab_x + 4, ly + 10, 12, render.compact_tokens(val) + mark, cls="hx2")
        add('</g>')

    # ---- xkcd annotation: scribble around the peak point + dry caption
    if peak > 0:
        p_src = max(per_s, key=lambda s: max(per_s[s]))
        p_i = per_s[p_src].index(peak)
        px, py = x_of(p_i), y_of(peak)
        add('<g class="late">')
        add('<path class="ink" stroke-width="1.6" d="{}"/>'.format(
            _scribble_ellipse(px + 1, py + 3, 21, 16, "peak-ring")))
        cap_x = min(max(px + 118, 240), W - PAD_R - 40)
        cap_y = max(PAD_T - 8, py - 52)
        d, ang = _curve_arrow(cap_x - 8, cap_y + 8, px + 26, py - 8, -14.0)
        add('<path class="ink" stroke-width="1.4" d="{}"/>'.format(d))
        add('<path class="ink" stroke-width="1.4" d="{}"/>'.format(
            _arrowhead(px + 26, py - 8, ang, 5.5)))
        hand_text(cap_x, cap_y, 13.5, "THE DAY THE AGENTS TOOK OVER", weight="700",
                  tilt=1.4)
        hand_text(cap_x + 2, cap_y + 17, 12, "({} tokens. one day. {}.)".format(
            render.compact_tokens(peak),
            rows[p_i]["start"].strftime("%b %d").lower()), cls="hx2", tilt=1.4)
        add('</g>')

    # ---- footnote
    hand_text(28, H - 14, 11, "Generated {}".format(generated), cls="hxm", tilt=0.8)

    add("</svg>")
    return "\n".join(out)


# --------------------------------------------------------------------- contract


def build_all(days, generated):
    """Returns [(relpath, svg_string)] for the hand-drawn/xkcd style."""
    rows = render.bucket(days, render.DAYS)
    if len(rows) < 2:
        return []
    return [("day/sketch-tokens.svg", _build_sketch(rows, generated))]
