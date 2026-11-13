#!/usr/bin/env python3
"""Render the usage charts as dependency-free SVG.

Two stable charts, plus a style gallery. Never one chart with two y-scales.

  charts/tokens.svg              daily tokens, stacked by source (stable URL)
  charts/cost.svg                daily API-equivalent USD       (stable URL)

  charts/day/bar-tokens.svg      the same daily bars, gallery-named
  charts/day/bar-cost.svg
  charts/day/calendar-tokens.svg GitHub-style contribution heatmap
  charts/day/area-tokens.svg     stacked area, animated reveal
  charts/day/card.svg            hero-number stat card for the last 30 days
  charts/week/bar-tokens.svg     weekly bars
  charts/week/bar-cost.svg
  charts/week/ledger-tokens.svg  editorial horizontal ledger, one row per week
  charts/month/bar-tokens.svg    monthly bars
  charts/month/bar-cost.svg
  charts/month/calendar-tokens.svg  a calendar page for the current month

Every style renders on every run; embed whichever URL you like. All are static
SVG with an embedded `prefers-color-scheme` style block, so a single file works
on GitHub in light and dark. Note the limit: that media query follows the
OS/browser setting, NOT GitHub's own theme toggle — an <img>-embedded SVG cannot
see the host page's theme. This is the best available mechanism. CSS animations
inside <style> survive GitHub's sanitizer when referenced via <img>; every
animation ends on the resting state and is disabled under prefers-reduced-motion.

Targets Python 3.9. Standard library only (must run in GitHub Actions and in
anyone's fork without a package install).
"""

import argparse
import datetime as dt
import glob
import json
import os

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DATA_DIR = os.path.join(REPO_ROOT, "data")
CHART_DIR = os.path.join(REPO_ROOT, "charts")

DAYS = 30           # default window: one month of daily columns
WEEKS = 16          # cap for weekly buckets
MONTHS = 12         # cap for monthly buckets
W = 880
PAD_L, PAD_R, PAD_T, PAD_B = 76, 28, 92, 52
PLOT_H = 224
H = PAD_T + PLOT_H + PAD_B
BAR_MAX = 24          # marks/anatomy: cap bar thickness, let the leftover be air
GAP = 2               # the surface gap that separates stacked segments
CAP_R = 4             # rounded data-end; square at the baseline

# Anthropic-derived palette. Surfaces and neutrals are the brand values
# (#faf9f5 / #141413 / #b0aea5 / #e8e6dc); the two categorical slots keep the
# brand accent hues (orange #d97757 for Claude, blue #6a9bcc for Codex) but are
# tuned per mode until scripts/validate_palette.js passes — the official hexes
# fail its chroma floor and dark-mode lightness band. Validated 2026-08-05:
#   light #d06a41,#4382c9 --surface #faf9f5 → ALL PASS (worst CVD dE 20.0)
#   dark  #db7448,#5b95d6 --surface #141413 → ALL PASS (worst CVD dE 18.5)
# Do not substitute without re-validating.
# ramp0..4 are the sequential steps (brand-orange hue) for the calendar views:
# one hue, monotonic lightness (light darkens with magnitude, dark brightens).
# ink3/ink4 are the text inks readable on the ramp3/ramp4 fills of that mode.
THEME = {
    "light": {
        "surface": "#faf9f5", "primary": "#141413", "secondary": "#53524b",
        "muted": "#8a887f", "grid": "#e8e6dc", "axis": "#cbc8bc",
        "claude": "#d06a41", "codex": "#4382c9", "gemini": "#7f4aa3",
        "ramp0": "#edeae0", "ramp1": "#f2cdb9", "ramp2": "#e59a70",
        "ramp3": "#d06a41", "ramp4": "#9c4a26",
        "ink3": "#141413", "ink4": "#ffffff",
    },
    "dark": {
        "surface": "#141413", "primary": "#faf9f5", "secondary": "#b0aea5",
        "muted": "#85837a", "grid": "#292824", "axis": "#383630",
        "claude": "#db7448", "codex": "#5b95d6", "gemini": "#8e58b3",
        "ramp0": "#232221", "ramp1": "#4b2b1b", "ramp2": "#8a4526",
        "ramp3": "#cf6a3e", "ramp4": "#f0a37a",
        "ink3": "#141413", "ink4": "#141413",
    },
}
SERIES = [("claude", "Claude Code"), ("codex", "Codex"), ("gemini", "Gemini")]
SOURCE_TO_SERIES = {"antigravity": "gemini"}
# Anthropic typography: Poppins for headings, Lora for body — with the brand's
# own Arial/Georgia fallbacks, since <img>-embedded SVG cannot load webfonts.
FONT = 'Poppins,Arial,"Helvetica Neue",sans-serif'
FONT_SERIF = 'Lora,Georgia,"Iowan Old Style",serif'
FONT_MONO = 'ui-monospace,"SF Mono",Menlo,Consolas,monospace'


# ------------------------------------------------------------------- load data


def load_days():
    """{date: {'claude': {...}, 'codex': {...}, 'partial': bool}} merged over hosts."""
    days = {}
    for path in sorted(glob.glob(os.path.join(DATA_DIR, "*", "2*.json"))):
        try:
            with open(path, "r", encoding="utf-8") as fh:
                rec = json.load(fh)
        except (ValueError, OSError):
            continue
        date = rec.get("date")
        if not date:
            continue
        slot = days.setdefault(date, {"partial": False})
        if rec.get("status") == "partial":
            slot["partial"] = True
        for raw_source, payload in (rec.get("sources") or {}).items():
            source = SOURCE_TO_SERIES.get(raw_source, raw_source)
            agg = slot.setdefault(source, {"total": 0, "costUSD": 0.0, "models": {}})
            # Hosts are disjoint writers for the same date, so summing is the merge.
            agg["total"] += payload.get("total") or 0
            agg["costUSD"] += payload.get("costUSD") or 0.0
            for model, model_payload in (payload.get("models") or {}).items():
                model_agg = agg["models"].setdefault(model, {"total": 0, "costUSD": 0.0})
                model_agg["total"] += model_payload.get("total") or 0
                model_agg["costUSD"] += model_payload.get("costUSD") or 0.0
    return days


def week_start(date):
    """Monday of the ISO week containing `date`."""
    return date - dt.timedelta(days=date.weekday())


def month_start(date):
    return date.replace(day=1)


def next_month(date):
    return (date.replace(day=28) + dt.timedelta(days=4)).replace(day=1)


def day_total(payload, metric="total"):
    return sum(payload.get(s, {}).get(metric, 0) for s, _ in SERIES)


def empty_bucket(start):
    out = {"start": start, "partial": False}
    for s, _ in SERIES:
        out[s] = {"total": 0, "costUSD": 0.0, "models": {}}
    return out


def fill_buckets(days, buckets, key):
    for date_str, payload in days.items():
        start = key(dt.date.fromisoformat(date_str))
        if start not in buckets:
            continue
        row = buckets[start]
        if payload.get("partial"):
            row["partial"] = True
        for source, _ in SERIES:
            if source in payload:
                row[source]["total"] += payload[source]["total"]
                row[source]["costUSD"] += payload[source]["costUSD"]
                for model, model_payload in payload[source].get("models", {}).items():
                    model_agg = row[source]["models"].setdefault(
                        model, {"total": 0, "costUSD": 0.0})
                    model_agg["total"] += model_payload.get("total") or 0
                    model_agg["costUSD"] += model_payload.get("costUSD") or 0.0
    return [buckets[k] for k in sorted(buckets)]


def bucket(days, span, weekly=False):
    """Fold per-day records into `span` consecutive buckets ending on the last
    day with data.

    Daily is the default. Over a month-long window weekly aggregation leaves
    only four or five fat columns, which reads worse than thirty thin ones and
    hides the day-to-day rhythm that is the point of keeping the record.
    """
    if not days:
        return []
    last = max(dt.date.fromisoformat(d) for d in days)
    key = week_start if weekly else (lambda d: d)
    step = dt.timedelta(weeks=1) if weekly else dt.timedelta(days=1)
    first = key(last) - step * (span - 1)
    buckets = {first + step * i: empty_bucket(first + step * i) for i in range(span)}
    return fill_buckets(days, buckets, key)


def bucket_months(days, cap=MONTHS):
    """Monthly buckets from the first month with data to the last, newest `cap`."""
    if not days:
        return []
    dates = [dt.date.fromisoformat(d) for d in days]
    starts = []
    cur = month_start(min(dates))
    while cur <= month_start(max(dates)):
        starts.append(cur)
        cur = next_month(cur)
    starts = starts[-cap:]
    buckets = {s: empty_bucket(s) for s in starts}
    return fill_buckets(days, buckets, month_start)


def weeks_covering(days):
    dates = [dt.date.fromisoformat(d) for d in days]
    return (week_start(max(dates)) - week_start(min(dates))).days // 7 + 1


# --------------------------------------------------------------------- helpers


def compact_tokens(value):
    for limit, suffix in ((1e9, "B"), (1e6, "M"), (1e3, "K")):
        if value >= limit:
            scaled = value / limit
            return "{:.0f}{}".format(scaled, suffix) if scaled >= 10 else "{:.1f}{}".format(scaled, suffix)
    return "{:,.0f}".format(value)


def compact_cost(value):
    if value >= 100 or value == 0:
        return "${:,.0f}".format(value)
    return "${:,.1f}".format(value)


def nice_ticks(peak):
    """Clean tick steps (1/2/2.5/5 x 10^n), choosing the division that wastes the
    least headroom. Trying only one tick count leaves charts with a half-empty
    plot (peak $2,223 under a $4,000 axis)."""
    if peak <= 0:
        return [0, 1]
    best = None
    for count in (4, 5, 6):
        raw = peak / float(count)
        exp = 0
        scaled = raw
        while scaled >= 10:
            scaled /= 10.0
            exp += 1
        while scaled < 1:
            scaled *= 10.0
            exp -= 1
        magnitude = 10.0 ** exp
        for mult in (1, 2, 2.5, 5, 10):
            step = mult * magnitude
            if step * count >= peak:
                break
        top = step * count
        if best is None or top < best[0]:
            best = (top, count, step)
    _, count, step = best
    return [step * i for i in range(count + 1)]


def quartile_bins(values):
    """[q25, q50, q75] over the non-zero values, for the 4-level calendar ramp."""
    vals = sorted(v for v in values if v > 0)
    if not vals:
        return [0, 0, 0]
    def q(p):
        i = (len(vals) - 1) * p
        lo = int(i)
        hi = min(lo + 1, len(vals) - 1)
        return vals[lo] + (vals[hi] - vals[lo]) * (i - lo)
    return [q(0.25), q(0.5), q(0.75)]


def level_of(value, bins):
    if value <= 0:
        return 0
    for i, b in enumerate(bins):
        if value <= b:
            return i + 1
    return 4


def esc(text):
    return (str(text).replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;"))


def cap_path(x, y, w, h, r):
    """Column with a rounded data-end and a square baseline."""
    r = max(0.0, min(float(r), w / 2.0, h))
    if r <= 0:
        return 'M{x:.1f},{y:.1f} h{w:.1f} v{h:.1f} h-{w:.1f} Z'.format(x=x, y=y, w=w, h=h)
    return (
        'M{x:.1f},{yb:.1f} V{yt:.1f} a{r:.1f},{r:.1f} 0 0 1 {r:.1f},-{r:.1f} '
        'h{inner:.1f} a{r:.1f},{r:.1f} 0 0 1 {r:.1f},{r:.1f} V{yb:.1f} Z'
    ).format(x=x, yb=y + h, yt=y + r, r=r, inner=w - 2 * r)


def cap_path_h(x, y, w, h, rl, rr):
    """Horizontal bar segment with independently rounded left/right ends."""
    rl = max(0.0, min(float(rl), w / 2.0, h / 2.0))
    rr = max(0.0, min(float(rr), w / 2.0, h / 2.0))
    p = ['M{:.1f},{:.1f}'.format(x + rl, y), 'H{:.1f}'.format(x + w - rr)]
    if rr:
        p.append('A{r:.1f},{r:.1f} 0 0 1 {:.1f},{:.1f}'.format(x + w, y + rr, r=rr))
        p.append('V{:.1f}'.format(y + h - rr))
        p.append('A{r:.1f},{r:.1f} 0 0 1 {:.1f},{:.1f}'.format(x + w - rr, y + h, r=rr))
    else:
        p.append('V{:.1f}'.format(y + h))
    p.append('H{:.1f}'.format(x + rl))
    if rl:
        p.append('A{r:.1f},{r:.1f} 0 0 1 {:.1f},{:.1f}'.format(x, y + h - rl, r=rl))
        p.append('V{:.1f}'.format(y + rl))
        p.append('A{r:.1f},{r:.1f} 0 0 1 {:.1f},{:.1f}'.format(x + rl, y, r=rl))
    else:
        p.append('V{:.1f}'.format(y))
    p.append('Z')
    return ' '.join(p)


def smooth_path(pts):
    """Catmull-Rom smoothing with control points clamped to each segment's y-range,
    so the curve never overshoots below a zero-run (no dips under the baseline)."""
    if len(pts) < 2:
        return ''
    d = 'M{:.1f},{:.1f}'.format(pts[0][0], pts[0][1])
    for i in range(len(pts) - 1):
        p0 = pts[max(i - 1, 0)]
        p1, p2 = pts[i], pts[i + 1]
        p3 = pts[min(i + 2, len(pts) - 1)]
        c1x = p1[0] + (p2[0] - p0[0]) / 6.0
        c1y = p1[1] + (p2[1] - p0[1]) / 6.0
        c2x = p2[0] - (p3[0] - p1[0]) / 6.0
        c2y = p2[1] - (p3[1] - p1[1]) / 6.0
        lo, hi = min(p1[1], p2[1]), max(p1[1], p2[1])
        c1y = min(max(c1y, lo), hi)
        c2y = min(max(c2y, lo), hi)
        d += ' C{:.1f},{:.1f} {:.1f},{:.1f} {:.1f},{:.1f}'.format(c1x, c1y, c2x, c2y, p2[0], p2[1])
    return d


def svg_start(w, h, title, extra_css=""):
    """Open an SVG with the shared theme: CSS vars for both color schemes, the
    text/series/ramp classes, and the reduced-motion kill switch."""
    light, dark = THEME["light"], THEME["dark"]
    css_vars = lambda t: " ".join("--{}:{};".format(k, v) for k, v in t.items())
    out = []
    add = out.append
    add('<svg xmlns="http://www.w3.org/2000/svg" width="{}" height="{}" '
        'viewBox="0 0 {} {}" role="img" aria-label="{}">'.format(w, h, w, h, esc(title)))
    add("<style>")
    add("svg{{--f:{};--fs:{};--fm:{};{}}}".format(FONT, FONT_SERIF, FONT_MONO, css_vars(light)))
    add("@media (prefers-color-scheme: dark){{svg{{{}}}}}".format(css_vars(dark)))
    add(".bg{fill:var(--surface)}")
    add(".grid{stroke:var(--grid);stroke-width:1;shape-rendering:crispEdges}")
    add(".axis{stroke:var(--axis);stroke-width:1;shape-rendering:crispEdges}")
    add(".t{font-family:var(--f);fill:var(--primary)}")
    add(".t2{font-family:var(--f);fill:var(--secondary)}")
    add(".tm{font-family:var(--f);fill:var(--muted);font-variant-numeric:tabular-nums}")
    add(".ts{font-family:var(--fs);fill:var(--primary)}")
    add(".tn{font-family:var(--fm);fill:var(--primary);font-variant-numeric:tabular-nums}")
    add("".join(".s-{s}{{fill:var(--{s})}}".format(s=s) for s, _ in SERIES))
    add(".r0{fill:var(--ramp0)}.r1{fill:var(--ramp1)}.r2{fill:var(--ramp2)}"
        ".r3{fill:var(--ramp3)}.r4{fill:var(--ramp4)}")
    add(".on3{fill:var(--ink3)}.on4{fill:var(--ink4)}")
    add(".wip{opacity:.5}")
    if extra_css:
        add(extra_css)
    add("@media (prefers-reduced-motion: reduce){*{animation:none !important}}")
    add("</style>")
    add('<rect class="bg" width="{}" height="{}"/>'.format(w, h))
    return out


def draw_legend(add, x, y):
    """Swatch legend. Always present for >= 2 series; identity is never
    color-alone. "in progress" is deliberately NOT a legend entry: it is a state
    both series can be in, and a third swatch reads as a third category."""
    for source, label in SERIES:
        add('<rect class="s-{}" x="{}" y="{}" width="10" height="10" rx="2"/>'.format(source, x, y))
        add('<text class="t2" x="{}" y="{}" font-size="12">{}</text>'.format(x + 16, y + 9, esc(label)))
        x += 22 + len(label) * 7


# ------------------------------------------------------------ style: bar chart


def build_svg(rows, metric, title, subtitle, footnote, fmt,
              xfmt=None, bar_max=BAR_MAX):
    xfmt = xfmt or (lambda d: d.strftime("%m/%d"))
    peak = max([sum(r[s][metric] for s, _ in SERIES) for r in rows] + [0])
    ticks = nice_ticks(peak)
    top = ticks[-1] or 1
    plot_w = W - PAD_L - PAD_R
    slot = plot_w / float(len(rows))
    bar_w = min(bar_max, slot * 0.62)
    # aim for <= 9 x-axis labels whatever the bucket count
    stride = max(1, -(-len(rows) // 9))

    def y_of(value):
        return PAD_T + PLOT_H - (value / float(top)) * PLOT_H

    out = svg_start(W, H, title)
    add = out.append

    # ---- heading
    add('<text class="t" x="{}" y="30" font-size="17" font-weight="600">{}</text>'.format(PAD_L - 48, esc(title)))
    add('<text class="t2" x="{}" y="50" font-size="12">{}</text>'.format(PAD_L - 48, esc(subtitle)))
    draw_legend(add, PAD_L - 48, 62)

    # ---- gridlines + y ticks (no gridline at zero — the baseline already draws it)
    for tick in ticks:
        y = y_of(tick)
        if tick > 0:
            add('<line class="grid" x1="{}" y1="{:.1f}" x2="{}" y2="{:.1f}"/>'.format(PAD_L, y, W - PAD_R, y))
        add('<text class="tm" x="{}" y="{:.1f}" font-size="11" text-anchor="end">{}</text>'.format(
            PAD_L - 10, y + 4, esc(fmt(tick))))
    base_y = y_of(0)
    add('<line class="axis" x1="{}" y1="{:.1f}" x2="{}" y2="{:.1f}"/>'.format(PAD_L, base_y, W - PAD_R, base_y))

    # ---- columns
    totals = [sum(r[s][metric] for s, _ in SERIES) for r in rows]
    peak_idx = totals.index(max(totals)) if any(totals) else -1
    for i, row in enumerate(rows):
        cx = PAD_L + slot * (i + 0.5)
        x = cx - bar_w / 2.0
        stack = 0.0
        drawn = [(s, row[s][metric]) for s, _ in SERIES if row[s][metric] > 0]
        for j, (source, value) in enumerate(drawn):
            y_top = y_of(stack + value)
            y_bot = y_of(stack)
            h = y_bot - y_top
            is_top = (j == len(drawn) - 1)
            if not is_top:
                h = max(0.0, h - GAP)          # surface gap does the separating
                y_top = y_bot - h
            cls = "s-{}{}".format(source, " wip" if row["partial"] else "")
            add('<path class="{}" d="{}"/>'.format(cls, cap_path(x, y_top, bar_w, h, CAP_R if is_top else 0)))
            stack += value

        # x labels: thin them out so the band never crowds, and anchor the
        # sequence to the right so the most recent bucket is always labelled.
        if (len(rows) - 1 - i) % stride == 0:
            add('<text class="tm" x="{:.1f}" y="{}" font-size="10.5" text-anchor="middle">{}</text>'.format(
                cx, PAD_T + PLOT_H + 20, xfmt(row["start"])))

    # ---- selective direct labels: the peak and the most recent bucket only
    for idx in {peak_idx, len(rows) - 1}:
        if idx < 0 or not totals[idx]:
            continue
        cx = PAD_L + slot * (idx + 0.5)
        add('<text class="t" x="{:.1f}" y="{:.1f}" font-size="11.5" font-weight="600" '
            'text-anchor="middle">{}</text>'.format(cx, y_of(totals[idx]) - 8, esc(fmt(totals[idx]))))

    add('<text class="tm" x="{}" y="{}" font-size="10.5">{}</text>'.format(
        PAD_L - 48, H - 14, esc(footnote)))
    add("</svg>")
    return "\n".join(out)


# ------------------------------------------- style: contribution calendar (day)


def build_day_calendar(days, generated):
    """GitHub-style contribution heatmap: weeks as columns, Mon-Sun as rows,
    sequential blue by daily total tokens (quartile bins over non-zero days)."""
    totals = {d: day_total(days[d]) for d in days}
    dates = sorted(dt.date.fromisoformat(d) for d in days)
    first, last = dates[0], dates[-1]
    end_w = week_start(last)
    start_w = week_start(first)
    span = (end_w - start_w).days // 7 + 1
    span = max(8, min(26, span))
    start_w = end_w - dt.timedelta(weeks=span - 1)

    cell, pitch = 13, 16
    pad_l, pad_t = 64, 96
    grid_w = span * pitch - (pitch - cell)
    w = max(560, pad_l + grid_w + 28)
    grid_h = 7 * pitch - (pitch - cell)
    h = pad_t + grid_h + 74

    in_window = {d: v for d, v in totals.items()
                 if dt.date.fromisoformat(d) >= start_w}
    bins = quartile_bins(in_window.values())
    window_total = sum(in_window.values())
    peak_date = max(in_window, key=in_window.get) if in_window else None

    title = "Token calendar"
    subtitle = "{} – {} · {} tokens".format(
        max(first, start_w).strftime("%b %d, %Y"), last.strftime("%b %d, %Y"),
        compact_tokens(window_total))
    if peak_date and in_window[peak_date] > 0:
        subtitle += " · peak {} on {}".format(
            compact_tokens(in_window[peak_date]),
            dt.date.fromisoformat(peak_date).strftime("%b %d"))

    out = svg_start(w, h, title)
    add = out.append
    add('<text class="t" x="28" y="30" font-size="17" font-weight="600">{}</text>'.format(esc(title)))
    add('<text class="t2" x="28" y="50" font-size="12">{}</text>'.format(esc(subtitle)))

    # month labels above the grid, one per month transition
    prev_month = None
    for wi in range(span):
        monday = start_w + dt.timedelta(weeks=wi)
        if monday.month != prev_month:
            add('<text class="tm" x="{}" y="{}" font-size="10.5">{}</text>'.format(
                pad_l + wi * pitch, pad_t - 8, monday.strftime("%b")))
            prev_month = monday.month

    for row, name in ((0, "Mon"), (2, "Wed"), (4, "Fri")):
        add('<text class="tm" x="{}" y="{}" font-size="10" text-anchor="end">{}</text>'.format(
            pad_l - 8, pad_t + row * pitch + 10, name))

    partial_today = False
    for wi in range(span):
        for dow in range(7):
            date = start_w + dt.timedelta(weeks=wi, days=dow)
            if date > last:
                continue                    # the future gets no cell
            key = date.isoformat()
            value = totals.get(key, 0)
            wip = days.get(key, {}).get("partial", False)
            partial_today = partial_today or wip
            add('<rect class="r{}{}" x="{}" y="{}" width="{}" height="{}" rx="3"/>'.format(
                level_of(value, bins), " wip" if wip else "",
                pad_l + wi * pitch, pad_t + dow * pitch, cell, cell))

    # ramp legend on its own row under the grid, so it never meets the footnote
    lx = w - 28 - (5 * pitch + 30)
    ly = pad_t + grid_h + 16
    add('<text class="tm" x="{}" y="{}" font-size="10.5" text-anchor="end">Less</text>'.format(lx - 6, ly + 10))
    for i in range(5):
        add('<rect class="r{}" x="{}" y="{}" width="{}" height="{}" rx="3"/>'.format(
            i, lx + i * pitch, ly, cell, cell))
    add('<text class="tm" x="{}" y="{}" font-size="10.5">More</text>'.format(lx + 5 * pitch + 4, ly + 10))

    add('<text class="tm" x="28" y="{}" font-size="10.5">Generated {}</text>'.format(
        h - 14, generated))
    add("</svg>")
    return "\n".join(out)


# --------------------------------------------------- style: stacked area (day)


AREA_CSS = (
    "".join(
        ".g-{s}-1{{stop-color:var(--{s});stop-opacity:.45}}"
        ".g-{s}-2{{stop-color:var(--{s});stop-opacity:.05}}"
        ".e-{s}{{stroke:var(--{s});stroke-width:2;fill:none;stroke-linejoin:round}}"
        .format(s=s) for s, _ in SERIES
    ) +
    ".gridd{stroke:var(--grid);stroke-width:1;stroke-dasharray:2 4}"
    ".dot{stroke:var(--surface);stroke-width:2}"
    ".rise{animation:rise .9s cubic-bezier(.2,.7,.3,1) both}"
    "@keyframes rise{from{opacity:0;transform:translateY(12px)}to{opacity:1;transform:none}}"
    ".late{animation:fadein .5s ease-out .55s both}"
    "@keyframes fadein{from{opacity:0}to{opacity:1}}"
)


def build_area(rows, generated):
    """Stacked area of daily tokens across SERIES, gradient fills, smoothed
    edges, an animated reveal, and direct labels on the right edge."""
    pad_l, pad_r, pad_t, pad_b = 76, 136, 92, 52
    plot_h = 236
    h = pad_t + plot_h + pad_b
    n = len(rows)
    plot_w = W - pad_l - pad_r

    per_s = [[r[s]["total"] for r in rows] for s, _ in SERIES]
    cum_levels = []
    running = [0] * n
    for vals in per_s:
        running = [a + b for a, b in zip(running, vals)]
        cum_levels.append(running)
    totals = cum_levels[-1]
    peak = max(totals + [0])
    ticks = nice_ticks(peak)
    top = ticks[-1] or 1

    def x_of(i):
        return pad_l + plot_w * (i / float(n - 1))

    def y_of(value):
        return pad_t + plot_h - (value / float(top)) * plot_h

    cum_pts = [[(x_of(i), y_of(lvl[i])) for i in range(n)] for lvl in cum_levels]

    span = "{} – {}".format(rows[0]["start"].strftime("%b %d, %Y"),
                            rows[-1]["start"].strftime("%b %d, %Y"))
    title = "Daily token flow"
    subtitle = "{} · {} tokens over {} days".format(span, compact_tokens(sum(totals)), n)

    out = svg_start(W, h, title, AREA_CSS)
    add = out.append

    add('<defs>')
    for s, _ in SERIES:
        add('<linearGradient id="g-{s}" x1="0" y1="0" x2="0" y2="1">'
            '<stop offset="0" class="g-{s}-1"/><stop offset="1" class="g-{s}-2"/></linearGradient>'.format(s=s))
    add('</defs>')

    add('<text class="ts" x="28" y="32" font-size="20" font-style="italic">{}</text>'.format(esc(title)))
    add('<text class="t2" x="28" y="52" font-size="12">{}</text>'.format(esc(subtitle)))

    # dotted grid + y ticks
    for tick in ticks:
        y = y_of(tick)
        if tick > 0:
            add('<line class="gridd" x1="{}" y1="{:.1f}" x2="{}" y2="{:.1f}"/>'.format(pad_l, y, W - pad_r, y))
        add('<text class="tm" x="{}" y="{:.1f}" font-size="11" text-anchor="end">{}</text>'.format(
            pad_l - 10, y + 4, esc(compact_tokens(tick))))
    base_y = y_of(0)
    add('<line class="axis" x1="{}" y1="{:.1f}" x2="{}" y2="{:.1f}"/>'.format(pad_l, base_y, W - pad_r, base_y))

    # bands (animated as one group; resting state is fully visible)
    add('<g class="rise">')
    for idx, (s, _) in enumerate(SERIES):
        top_p = cum_pts[idx]
        if idx == 0:
            area_d = (smooth_path(top_p) +
                      ' L{:.1f},{:.1f} L{:.1f},{:.1f} Z'.format(top_p[-1][0], base_y, top_p[0][0], base_y))
        else:
            bottom_rev = smooth_path(list(reversed(cum_pts[idx - 1])))
            area_d = smooth_path(top_p) + ' ' + bottom_rev.replace('M', 'L', 1) + ' Z'
        add('<path fill="url(#g-{})" d="{}"/>'.format(s, area_d))
    for idx, (s, _) in enumerate(SERIES):
        add('<path class="e-{}" d="{}"/>'.format(s, smooth_path(cum_pts[idx])))
    add('</g>')

    # x labels
    stride = max(1, -(-n // 9))
    for i in range(n):
        if (n - 1 - i) % stride == 0:
            add('<text class="tm" x="{:.1f}" y="{}" font-size="10.5" text-anchor="middle">{}</text>'.format(
                x_of(i), pad_t + plot_h + 20, rows[i]["start"].strftime("%m/%d")))

    # right-edge direct labels with collision avoidance (bottom-to-top order)
    add('<g class="late">')
    lab_x = W - pad_r + 12
    prev_y = base_y + 20
    placed = []
    for idx, (s, label) in enumerate(SERIES):
        bot_v = cum_levels[idx - 1][-1] if idx > 0 else 0
        mid_v = bot_v + per_s[idx][-1] / 2.0
        y = min(y_of(mid_v), base_y - 24, prev_y - 44)
        y = max(y, PAD_T + 8)
        prev_y = y
        placed.append((y, s, label, per_s[idx][-1]))
    # forward pass in case top clamped
    for i in range(len(placed) - 2, -1, -1):
        y, s, label, val = placed[i]
        ny = placed[i + 1][0]
        if y - ny < 44:
            placed[i] = (min(base_y - 24, ny + 44), s, label, val)
    for y, source, label, value in placed:
        add('<circle class="s-{} dot" cx="{}" cy="{:.1f}" r="4"/>'.format(source, lab_x, y))
        add('<text class="t2" x="{}" y="{:.1f}" font-size="12">{}</text>'.format(
            lab_x + 10, y + 4, esc(label)))
        add('<text class="tn" x="{}" y="{:.1f}" font-size="12.5" font-weight="600">{}</text>'.format(
            lab_x + 10, y + 21, compact_tokens(value)))
    # peak label
    if peak > 0:
        pi = totals.index(peak)
        add('<circle class="dot" cx="{:.1f}" cy="{:.1f}" r="3.5" fill="var(--primary)"/>'.format(
            x_of(pi), y_of(peak)))
        add('<text class="t" x="{:.1f}" y="{:.1f}" font-size="11.5" font-weight="600" '
            'text-anchor="middle">{}</text>'.format(x_of(pi), y_of(peak) - 10, compact_tokens(peak)))
    add('</g>')

    add('<text class="tm" x="28" y="{}" font-size="10.5">Generated {}</text>'.format(h - 14, generated))
    add("</svg>")
    return "\n".join(out)


# ------------------------------------------------------ style: stat card (day)


CARD_CSS = (
    ".b{animation:lift .7s cubic-bezier(.2,.7,.3,1) both}"
    "@keyframes lift{from{opacity:0;transform:translateY(8px)}to{opacity:1;transform:none}}"
)


def fmt_hero(value):
    if value >= 1e9:
        return "{:.2f}B".format(value / 1e9)
    if value >= 1e8:
        return "{:.0f}M".format(value / 1e6)
    if value >= 1e6:
        return "{:.1f}M".format(value / 1e6)
    return compact_tokens(value)


def build_card(rows, generated):
    """Hero-number stat card: the 30-day totals as typography, not marks. The
    only plot is a thin 100% split bar showing the per-source share."""
    w, h = 880, 236
    tokens = [sum(r[s]["total"] for s, _ in SERIES) for r in rows]
    total = sum(tokens)
    cost = sum(sum(r[s]["costUSD"] for s, _ in SERIES) for r in rows)
    active = sum(1 for t in tokens if t > 0)
    peak = max(tokens + [0])
    peak_day = rows[tokens.index(peak)]["start"] if peak else None
    avg = total / float(active) if active else 0
    src_totals = [(s, lbl, sum(r[s]["total"] for r in rows)) for s, lbl in SERIES]

    title = "AI coding usage — last 30 days"
    out = svg_start(w, h, title, CARD_CSS)
    add = out.append

    # hero block
    add('<g class="b">')
    add('<text class="tm" x="48" y="58" font-size="10.5" letter-spacing="2.5">LAST 30 DAYS · TOKENS</text>')
    add('<text class="ts" x="46" y="122" font-size="58" font-weight="700">{}</text>'.format(fmt_hero(total)))
    add('<text class="t2" x="48" y="150" font-size="13">≈ {} API-equivalent</text>'.format(
        compact_cost(cost)))
    add('</g>')

    add('<line class="axis" x1="400" y1="46" x2="400" y2="150"/>')

    tiles = [
        ("PEAK DAY", compact_tokens(peak), peak_day.strftime("%b %d") if peak_day else "—"),
        ("DAILY AVG", compact_tokens(avg), "per active day"),
        ("ACTIVE DAYS", "{} / {}".format(active, len(rows)), "days with usage"),
    ]
    for i, (label, value, sub) in enumerate(tiles):
        x = 440 + i * 150
        add('<g class="b" style="animation-delay:{}ms">'.format(120 + i * 90))
        add('<text class="tm" x="{}" y="64" font-size="10" letter-spacing="1.8">{}</text>'.format(x, esc(label)))
        add('<text class="ts" x="{}" y="100" font-size="26" font-weight="700">{}</text>'.format(x, esc(value)))
        add('<text class="tm" x="{}" y="122" font-size="11">{}</text>'.format(x, esc(sub)))
        add('</g>')

    # 100% split bar
    bar_x, bar_y, bar_w, bar_h = 48, 176, w - 96, 9
    nonzero = [(s, lbl, val) for s, lbl, val in src_totals if val > 0]
    avail_w = bar_w - GAP * max(0, len(nonzero) - 1)
    add('<g class="b" style="animation-delay:320ms">')
    cx = bar_x
    for idx, (s, _, val) in enumerate(nonzero):
        seg_w = avail_w * (val / float(total)) if total else 0.0
        rl = 4.5 if idx == 0 else 0.0
        rr = 4.5 if idx == len(nonzero) - 1 else 0.0
        add('<path class="s-{}" d="{}"/>'.format(s, cap_path_h(cx, bar_y, seg_w, bar_h, rl, rr)))
        cx += seg_w + GAP
    lx = 53
    for s, lbl, val in src_totals:
        pct = 100.0 * val / total if total else 0.0
        txt = "{} {:.0f}% · {}".format(lbl, pct, compact_tokens(val))
        add('<circle class="s-{}" cx="{}" cy="203" r="4"/>'.format(s, lx))
        add('<text class="t2" x="{}" y="207" font-size="12">{}</text>'.format(lx + 10, esc(txt)))
        lx += 34 + len(txt) * 6.8
    add('</g>')

    add('<text class="tm" x="48" y="{}" font-size="10">Generated {}</text>'.format(h - 10, generated))
    add("</svg>")
    return "\n".join(out)


# -------------------------------------------------- style: weekly ledger (week)


def build_ledger(rows, generated):
    """Editorial ledger: one row per week, newest first — a week-range label, a
    stacked horizontal bar scaled to the busiest week, and the total in tabular
    numerals. No axis; the numbers themselves are the scale."""
    rows = [r for r in rows]
    header, row_h, foot_h = 96, 32, 44
    w = W
    h = header + len(rows) * row_h + foot_h
    label_x, bar_x = 28, 180
    value_x = w - 32
    bar_w_max = value_x - 64 - bar_x
    bar_h = 13

    totals = [sum(r[s]["total"] for s, _ in SERIES) for r in rows]
    max_total = max(totals + [1])
    peak_idx = totals.index(max(totals)) if any(totals) else -1
    grand = sum(totals)

    title = "Weekly ledger"
    span = "{} – {}".format(rows[0]["start"].strftime("%b %d, %Y"),
                            (rows[-1]["start"] + dt.timedelta(days=6)).strftime("%b %d, %Y"))
    subtitle = "{} · {} tokens over {} weeks".format(span, compact_tokens(grand), len(rows))

    out = svg_start(w, h, title)
    add = out.append
    add('<text class="ts" x="{}" y="32" font-size="20" font-style="italic">{}</text>'.format(label_x, esc(title)))
    add('<text class="t2" x="{}" y="52" font-size="12">{}</text>'.format(label_x, esc(subtitle)))
    draw_legend(add, label_x, 64)

    def week_label(s):
        e = s + dt.timedelta(days=6)
        if s.month == e.month:
            return "{} {:02d} – {:02d}".format(s.strftime("%b"), s.day, e.day)
        return "{} – {}".format(s.strftime("%b %d"), e.strftime("%b %d"))

    for di, row in enumerate(reversed(rows)):
        i = len(rows) - 1 - di                     # index in chronological order
        y = header + di * row_h
        cy = y + row_h / 2.0
        add('<line class="grid" x1="{}" y1="{}" x2="{}" y2="{}"/>'.format(
            label_x, y + row_h, value_x, y + row_h))
        add('<text class="t2" x="{}" y="{:.1f}" font-size="12.5">{}</text>'.format(
            label_x, cy + 4, week_label(row["start"])))

        x = bar_x
        drawn = [(s, row[s]["total"]) for s, _ in SERIES if row[s]["total"] > 0]
        for j, (source, value) in enumerate(drawn):
            seg = bar_w_max * value / float(max_total)
            if j < len(drawn) - 1:
                seg = max(0.0, seg - GAP)
            cls = "s-{}{}".format(source, " wip" if row["partial"] else "")
            add('<path class="{}" d="{}"/>'.format(cls, cap_path_h(
                x, cy - bar_h / 2.0, seg, bar_h,
                6 if j == 0 else 0, 6 if j == len(drawn) - 1 else 0)))
            x += seg + GAP
        mark = " *" if row["partial"] else ""
        weight = ' font-weight="700"' if i == peak_idx else ""
        cls = "tn" if i == peak_idx else "tm"
        add('<text class="{}" x="{}" y="{:.1f}" font-size="12" text-anchor="end"{}>{}{}</text>'.format(
            cls, value_x, cy + 4, weight, compact_tokens(totals[i]), mark))

    add('<text class="tm" x="{}" y="{}" font-size="10.5">Generated {}</text>'.format(
        label_x, h - 14, generated))
    add("</svg>")
    return "\n".join(out)


# ---------------------------------------------- style: calendar page (month)


MONTH_CSS = (
    ".pop{animation:pop .45s cubic-bezier(.2,.7,.3,1) both}"
    "@keyframes pop{from{opacity:0;transform:translateY(6px)}to{opacity:1;transform:none}}"
    ".future{fill:none;stroke:var(--grid);stroke-dasharray:3 4}"
    ".ring{fill:none;stroke:var(--primary);stroke-width:1.5}"
)


def build_month_page(days, generated):
    """A calendar page for the current month: one rounded cell per day, filled by
    the sequential ramp, with the day number and the day's tokens in the cell —
    a chart/table hybrid, so every value is readable without color."""
    last = max(dt.date.fromisoformat(d) for d in days)
    first_of = month_start(last)
    n_days = (next_month(first_of) - first_of).days
    lead = first_of.weekday()
    n_rows = -(-(lead + n_days) // 7)

    pad, gap = 36, 8
    w = W
    cell_w = (w - 2 * pad - 6 * gap) / 7.0
    cell_h = 64
    grid_top = 132
    h = int(grid_top + n_rows * (cell_h + gap) - gap + 52)

    month_days = {d: days[d] for d in days
                  if month_start(dt.date.fromisoformat(d)) == first_of}
    totals = {d: day_total(month_days[d]) for d in month_days}
    bins = quartile_bins(totals.values())
    m_tokens = sum(totals.values())
    m_cost = sum(sum(month_days[d].get(s, {}).get("costUSD", 0.0) for s, _ in SERIES)
                 for d in month_days)

    title = last.strftime("%B %Y")
    out = svg_start(w, h, "Token calendar — " + title, MONTH_CSS)
    add = out.append
    add('<text class="ts" x="{}" y="54" font-size="30">{}</text>'.format(pad, esc(title)))
    add('<text class="t2" x="{}" y="78" font-size="12.5">{} tokens · {} API-equivalent so far</text>'.format(
        pad, compact_tokens(m_tokens), compact_cost(m_cost)))

    for i, name in enumerate(("MON", "TUE", "WED", "THU", "FRI", "SAT", "SUN")):
        add('<text class="tm" x="{:.1f}" y="{}" font-size="10" letter-spacing="1.5">{}</text>'.format(
            pad + i * (cell_w + gap) + 10, grid_top - 12, name))

    partial_today = False
    for day in range(1, n_days + 1):
        idx = lead + day - 1
        r, c = divmod(idx, 7)
        x = pad + c * (cell_w + gap)
        y = grid_top + r * (cell_h + gap)
        date = first_of + dt.timedelta(days=day - 1)
        key = date.isoformat()
        value = totals.get(key, 0)
        level = level_of(value, bins)
        wip = month_days.get(key, {}).get("partial", False)
        partial_today = partial_today or wip
        ink = {3: "on3", 4: "on4"}.get(level)
        add('<g class="pop" style="animation-delay:{}ms">'.format(idx * 14))
        if date > last:
            add('<rect class="future" x="{:.1f}" y="{}" width="{:.1f}" height="{}" rx="10"/>'.format(
                x, y, cell_w, cell_h))
            add('<text class="tm" x="{:.1f}" y="{}" font-size="12">{}</text>'.format(x + 10, y + 20, day))
        else:
            add('<rect class="r{}{}" x="{:.1f}" y="{}" width="{:.1f}" height="{}" rx="10"/>'.format(
                level, " wip" if wip else "", x, y, cell_w, cell_h))
            num_cls = ink or "t2"
            add('<text class="{}" x="{:.1f}" y="{}" font-size="12" font-weight="600" '
                'font-family="var(--f)">{}</text>'.format(num_cls, x + 10, y + 20, day))
            if value > 0:
                val_cls = ink or "t2"
                add('<text class="{}" x="{:.1f}" y="{}" font-size="11" text-anchor="end" '
                    'font-family="var(--fm)">{}</text>'.format(
                        val_cls, x + cell_w - 10, y + cell_h - 10, compact_tokens(value)))
            if wip:
                add('<rect class="ring" x="{:.1f}" y="{}" width="{:.1f}" height="{}" rx="10"/>'.format(
                    x + 0.75, y + 0.75, cell_w - 1.5, cell_h - 1.5))
        add('</g>')

    # ramp legend bottom right, footnote bottom left
    cell, pitch = 13, 16
    lx = w - pad - (5 * pitch + 66)
    ly = h - 30
    add('<text class="tm" x="{}" y="{}" font-size="10.5" text-anchor="end">Less</text>'.format(lx - 6, ly + 10))
    for i in range(5):
        add('<rect class="r{}" x="{}" y="{}" width="{}" height="{}" rx="3"/>'.format(
            i, lx + i * pitch, ly, cell, cell))
    add('<text class="tm" x="{}" y="{}" font-size="10.5">More</text>'.format(lx + 5 * pitch + 4, ly + 10))

    add('<text class="tm" x="{}" y="{}" font-size="10.5">Generated {}</text>'.format(
        pad, h - 16, generated))
    add("</svg>")
    return "\n".join(out)


# ---------------------------------------------------------------------- output


def write_summary(path, rows, days):
    """The charts' table twin.

    A chart must never be the only way to read a value — colour-blind readers,
    screen readers, and anyone on a text-only view need the numbers themselves.
    """
    tok_cols = " | ".join(lbl + " tokens" for _, lbl in SERIES)
    cost_cols = " | ".join(lbl + " $" for _, lbl in SERIES)
    sep1 = "|".join(["---"] + ["--:"] * (len(SERIES) * 2 + 2))
    lines = [
        "# Summary",
        "",
        "Auto-generated by `scripts/render.py`. The table twin of the charts — "
        "every plotted value is readable here without relying on colour.",
        "",
        "## By bucket",
        "",
        "| Starting | {} | Total tokens | {} | Total $ |".format(tok_cols, cost_cols),
        "|{}|".format(sep1),
    ]
    for row in reversed(rows):
        toks = [row[s]["total"] for s, _ in SERIES]
        costs = [row[s]["costUSD"] for s, _ in SERIES]
        mark = " *" if row["partial"] else ""
        cells = (
            [row["start"].isoformat() + mark]
            + ["{:,}".format(t) for t in toks]
            + ["{:,}".format(sum(toks))]
            + ["${:,.2f}".format(c) for c in costs]
            + ["${:,.2f}".format(sum(costs))]
        )
        lines.append("| {} |".format(" | ".join(cells)))
    sep2 = "|".join(["---"] + ["--:"] * (len(SERIES) * 2))
    lines += ["", "`*` still in progress.", "", "## Last 30 days", "",
              "| Date | {} | {} |".format(tok_cols, cost_cols),
              "|{}|".format(sep2)]
    for date_str in sorted(days, reverse=True)[:30]:
        day = days[date_str]
        toks = [(day.get(s) or {}).get("total", 0) for s, _ in SERIES]
        costs = [(day.get(s) or {}).get("costUSD", 0.0) for s, _ in SERIES]
        mark = " *" if day.get("partial") else ""
        cells = (
            [date_str + mark]
            + ["{:,}".format(t) for t in toks]
            + ["${:,.2f}".format(c) for c in costs]
        )
        lines.append("| {} |".format(" | ".join(cells)))
    lines += ["", "Full day-by-day history lives in `data/<host>/<date>.json`.", ""]
    with open(path, "w", encoding="utf-8") as fh:
        fh.write("\n".join(lines))


def load_style_modules():
    """Discover scripts/styles/*.py plugins.

    Each plugin exposes build_all(days, generated) -> [(relpath, svg_str), ...]
    and may `import render` for the shared helpers. Kept as separate files so a
    new style is one dropped-in module, not a merge into this one.
    """
    import importlib.util
    styles_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)), "styles")
    mods = []
    for path in sorted(glob.glob(os.path.join(styles_dir, "*.py"))):
        name = os.path.splitext(os.path.basename(path))[0]
        if name.startswith("_"):
            continue
        spec = importlib.util.spec_from_file_location("style_" + name, path)
        mod = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(mod)
        if hasattr(mod, "build_all"):
            mods.append((name, mod))
    return mods


def bar_meta(period, current, generated):
    """(title, footnote) x (tokens, cost) shared by all bar charts.

    Footnotes carry ONLY the generated stamp (repo-wide policy): the prose that
    used to live here (token composition, cost-is-not-spend, faded-means-in-
    progress) now lives in the README and SUMMARY, not on every chart.
    """
    foot = "Generated {}".format(generated)
    return ("{} token usage".format(period), foot,
            "{} API-equivalent value".format(period), foot)


def bar_pair(rows, period, current, unit, generated, xfmt=None, bar_max=BAR_MAX):
    """Render the tokens+cost bar pair for one bucket granularity."""
    span_end = rows[-1]["start"] + (dt.timedelta(days=6) if unit == "weeks" else dt.timedelta(0))
    span = "{} – {}".format(rows[0]["start"].strftime("%b %d, %Y"), span_end.strftime("%b %d, %Y"))
    if unit == "months":
        span = "{} – {}".format(rows[0]["start"].strftime("%b %Y"), rows[-1]["start"].strftime("%b %Y"))
    grand_tokens = sum(sum(r[s]["total"] for s, _ in SERIES) for r in rows)
    grand_cost = sum(sum(r[s]["costUSD"] for s, _ in SERIES) for r in rows)
    t_title, t_foot, c_title, c_foot = bar_meta(period, current, generated)
    tokens_svg = build_svg(
        rows, "total", t_title,
        "{} · {} tokens over {} {}".format(span, compact_tokens(grand_tokens), len(rows), unit),
        t_foot, compact_tokens, xfmt=xfmt, bar_max=bar_max)
    cost_svg = build_svg(
        rows, "costUSD", c_title,
        "{} · {} over {} {}".format(span, compact_cost(grand_cost), len(rows), unit),
        c_foot, compact_cost, xfmt=xfmt, bar_max=bar_max)
    return tokens_svg, cost_svg


def main():
    ap = argparse.ArgumentParser(description="Render the usage charts.")
    ap.add_argument("--days", type=int, default=DAYS, help="daily buckets (default)")
    ap.add_argument("--weeks", type=int, help="switch charts/tokens.svg + cost.svg to weekly buckets")
    ap.add_argument("--out", default=CHART_DIR)
    args = ap.parse_args()

    days = load_days()
    if not days:
        print("no data under {}, nothing to render".format(DATA_DIR))
        return

    generated = dt.datetime.now(dt.timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
    last_data = max(dt.date.fromisoformat(d) for d in days)
    written = []

    def write(rel, content):
        path = os.path.join(args.out, rel)
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(path, "w", encoding="utf-8") as fh:
            fh.write(content + "\n")
        written.append(os.path.relpath(path, REPO_ROOT))

    # ---- the two stable charts (URL-compatible with the original layout)
    weekly = args.weeks is not None
    legacy_rows = bucket(days, args.weeks if weekly else args.days, weekly=weekly)
    tokens_svg, cost_svg = bar_pair(
        legacy_rows, "Weekly" if weekly else "Daily", "week" if weekly else "day",
        "weeks" if weekly else "days", generated)
    write("tokens.svg", tokens_svg)
    write("cost.svg", cost_svg)

    # ---- gallery: day/
    daily_rows = bucket(days, DAYS)
    d_tokens, d_cost = bar_pair(daily_rows, "Daily", "day", "days", generated)
    write(os.path.join("day", "bar-tokens.svg"), d_tokens)
    write(os.path.join("day", "bar-cost.svg"), d_cost)
    write(os.path.join("day", "calendar-tokens.svg"), build_day_calendar(days, generated))
    if len(daily_rows) >= 2:
        write(os.path.join("day", "area-tokens.svg"), build_area(daily_rows, generated))
    write(os.path.join("day", "card.svg"), build_card(daily_rows, generated))

    # ---- gallery: week/
    week_span = max(4, min(WEEKS, weeks_covering(days)))
    week_rows = bucket(days, week_span, weekly=True)
    # a week whose Sunday is still ahead of the data is in progress even if
    # every collected day in it is final
    if week_rows and last_data < week_rows[-1]["start"] + dt.timedelta(days=6):
        week_rows[-1]["partial"] = True
    w_tokens, w_cost = bar_pair(week_rows, "Weekly", "week", "weeks", generated, bar_max=32)
    write(os.path.join("week", "bar-tokens.svg"), w_tokens)
    write(os.path.join("week", "bar-cost.svg"), w_cost)
    write(os.path.join("week", "ledger-tokens.svg"), build_ledger(week_rows, generated))

    # ---- gallery: month/
    month_rows = bucket_months(days)
    if month_rows and last_data < next_month(month_rows[-1]["start"]) - dt.timedelta(days=1):
        month_rows[-1]["partial"] = True
    m_tokens, m_cost = bar_pair(month_rows, "Monthly", "month", "months", generated,
                                xfmt=lambda d: d.strftime("%b"), bar_max=44)
    write(os.path.join("month", "bar-tokens.svg"), m_tokens)
    write(os.path.join("month", "bar-cost.svg"), m_cost)
    write(os.path.join("month", "calendar-tokens.svg"), build_month_page(days, generated))

    # ---- style plugins (pixel, terminal, sketch, badge, ...)
    # A broken plugin must not take the core charts down with it, but it must
    # not pass CI silently either: render everything, then fail loudly.
    failures = []
    for name, mod in load_style_modules():
        try:
            for rel, svg in mod.build_all(days, generated):
                write(rel, svg)
        except Exception as exc:
            failures.append("{}: {}".format(name, exc))

    for rel in written:
        print("wrote {}".format(rel))
    if failures:
        raise SystemExit("style plugin failure: " + "; ".join(failures))

    summary = os.path.join(REPO_ROOT, "SUMMARY.md")
    write_summary(summary, legacy_rows, days)
    print("wrote {}".format(os.path.relpath(summary, REPO_ROOT)))


if __name__ == "__main__":
    main()
