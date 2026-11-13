#!/usr/bin/env python3
"""8-bit pixel style for the daily token chart.

Two charts off one geometry:

charts/day/pixel-tokens.svg   columns colored by source only — the plain twin
charts/day/pixel-models.svg   the same columns, each source's pixels shaded by
                              model tier (Claude fable > opus > sonnet, Codex
                              5.5/Sol > terra > luna, Gemini carbon/argon >
                              flash/hydrogen)

The split chart is additive, never a replacement: both are rendered every time,
so a README can embed either. Each daily column is a stack of
discrete square "pixels" on a fixed grid — every pixel is a fixed token
quantum (chosen from 1/2/5 x 10^n so the tallest day fits the grid), each
series rounds UP to whole pixels, and the subtitle states the quantum, so
the quantization is honest. Claude Code fills the column bottom-up first,
Codex continues in the same grid (Tetris-style row packing), which keeps
the stacked-bar reading while the last row of a series may hold a single
square — the staircase feel is real data, not decoration.

Surfaces, text classes and both color modes come from render.THEME via
render.svg_start; model shades extend the Claude orange and Codex blue
palettes locally. The pixel look is pure geometry: shape-rendering: crispEdges,
integer coordinates, square corners, a stepped reveal animation (steps()
easing), and a terminal-cursor blink on the newest pixel of an in-progress day.
Deterministic: same data -> same bytes.

Targets Python 3.9, standard library only. Import with the repo's
scripts/ directory on sys.path (it does `import render`).
"""

import render

# ------------------------------------------------------------------ grid geometry

S = 8                 # pixel square edge
GAPX = 2              # gap between pixels, both directions
PITCH = S + GAPX      # 10px grid pitch
COLS_PER_BAR = 2      # each daily column is two pixels wide
BAR_W = COLS_PER_BAR * PITCH - GAPX          # 18px
MAX_ROWS = 24         # tallest column the grid allows
TICK_ROWS = 5         # one y tick every 5 rows = 10 quanta

PAD_L, PAD_R = 76, 28
PAD_T_PLAIN = 100     # one legend row: the sources
PAD_T_SPLIT = 134     # three legend rows: three model tiers per source
PLOT_H = MAX_ROWS * PITCH                    # 240
W = render.W                                 # 880

# Model tiers are an ORDINAL scale per source hue: deepest/accent = most capable.
# Gemini has only 2 model tiers (Carbon/Argon > Flash/Hydrogen), so its top tier
# uses the brand accent directly (THEME gemini) and Flash/Hydrogen drops to the
# lighter step with a hollow ring (hole = 4), matching Sonnet/Haiku and Luna.
# All four 3-step and 2-step ladders pass dataviz `--ordinal` validation.
MODEL_CSS = (
    "svg{--claude-fable:#9c4a26;--claude-opus:#d06a41;--claude-sonnet:#e59a70;"
    "--codex-core:#245f9f;--codex-terra:#4382c9;--codex-luna:#78a9dc;"
    "--gemini-carbon:#7f4aa3;--gemini-flash:#b385d6}"
    "@media (prefers-color-scheme:dark){svg{--claude-fable:#a84c2b;"
    "--claude-opus:#db7448;--claude-sonnet:#f2aa84;--codex-core:#2f70b1;"
    "--codex-terra:#5b95d6;--codex-luna:#8ab9e8;"
    "--gemini-carbon:#8e58b3;--gemini-flash:#b98bdc}}"
    ".m-claude-fable{fill:var(--claude-fable)}"
    ".m-claude-sonnet{fill:var(--claude-sonnet)}"
    ".m-claude-opus{fill:var(--claude-opus)}"
    ".m-codex-core{fill:var(--codex-core)}"
    ".m-codex-terra{fill:var(--codex-terra)}"
    ".m-codex-luna{fill:var(--codex-luna)}"
    ".m-gemini-carbon{fill:var(--gemini-carbon)}"
    ".m-gemini-flash{fill:var(--gemini-flash)}"
)

PIXEL_CSS = (
    ".px{shape-rendering:crispEdges}"
    ".tt{font-family:var(--fm);fill:var(--primary);font-weight:700;letter-spacing:3px}"
    ".sub{font-family:var(--fm);fill:var(--secondary);letter-spacing:1px}"
    ".ink{fill:var(--primary)}"
    ".gridp{stroke:var(--grid);stroke-width:1;shape-rendering:crispEdges;stroke-dasharray:4 4}"
    ".axp{stroke:var(--axis);stroke-width:2;shape-rendering:crispEdges}"
    # no `to` frame: the animation must settle at each column's own base
    # opacity, so `.wip{opacity:.5}` still fades an in-progress day after
    # the reveal finishes (an explicit to{opacity:1} would override it).
    ".col{animation:rise .5s steps(4,end) both}"
    "@keyframes rise{from{opacity:0;transform:translateY(14px)}}"
    ".blink{animation:blink 1.3s step-end infinite}"
    "@keyframes blink{0%,54%{opacity:1}55%,100%{opacity:.2}}"
)

# The tier is carried TWICE: by the lightness step and by how much of the 8px
# cell is filled. Doubling up is what makes the split legible at a glance
# instead of merely present — and it keeps the tiers apart in greyscale, under
# colorblindness, and for the palest step whose contrast sits near the floor.
# Ink drops monotonically with the tier, so visual weight and depth agree.
# Holes are even and centered on the 2px sub-grid: solid, notched, hollow ring.
# Holes are even and centered on the 2px sub-grid: solid, notched, hollow ring.
# For 2-tier sources (Gemini), top tier is solid (0) and fast tier is hollow (4).
TIER_HOLE = (0, 2, 4)

MODEL_GROUPS = {
    # The real Claude ladder is fable > opus > sonnet > haiku, but haiku is
    # effectively unused (0.1% of tokens ever), so it rides in the bottom tier
    # rather than buying a fourth colour step and texture for a rounding error.
    # It is named in the legend so the tier never lies about what it contains.
    "claude": (
        ("claude-fable", "FABLE", ("fable",)),
        ("claude-opus", "OPUS", ("opus",)),
        ("claude-sonnet", "SONNET / HAIKU", ("sonnet", "haiku")),
    ),
    "codex": (
        ("codex-core", "5.5 / SOL", ("gpt-5.5", "gpt-5.6-sol", "gpt-6.1-sol", "astra")),
        ("codex-terra", "TERRA", ("terra",)),
        ("codex-luna", "LUNA", ("luna",)),
    ),
    "gemini": (
        ("gemini-carbon", "CARBON / ARGON", ("carbon", "argon")),
        ("gemini-flash", "FLASH / HYDROGEN", ("flash", "hydrogen")),
    ),
}

# tier hole of every model key, so 2-tier sources share the solid/hollow grammar
TIER_HOLE_BY_KEY = {
    key: TIER_HOLE[0 if i == 0 else (-1 if i == len(groups) - 1 else i)]
    for groups in MODEL_GROUPS.values()
    for i, (key, _, _) in enumerate(groups)
}

# 7x6 pixel heart, drawn as tiny rects in primary ink (decorative, never a series hue)
HEART = (
    ".XX.XX.",
    "XXXXXXX",
    "XXXXXXX",
    ".XXXXX.",
    "..XXX..",
    "...X...",
)


def _ceil_div(a, b):
    return -(-a // b)


def _tier_cell(add, key, x, y, size, blink="", label=None):
    """One textured square: the tier's fill, then its hole in the surface color.

    The hole is painted rather than cut out, so the dashed gridline behind a
    column can never show through the middle of a pixel.
    """
    cls = "s-" + key if key in ("claude", "codex", "gemini") else "m-" + key
    title = "<title>{}</title>".format(render.esc(label)) if label else ""
    add('<rect class="px {}{}" x="{}" y="{}" width="{}" height="{}">{}</rect>'.format(
        cls, blink, x, y, size, size, title))
    hole = TIER_HOLE_BY_KEY.get(key, 0) * size // S
    if hole:
        off = (size - hole) // 2
        add('<rect class="px bg{}" x="{}" y="{}" width="{}" height="{}"/>'.format(
            blink, x + off, y + off, hole, hole))


def _model_group(source, model):
    lowered = model.lower()
    for key, label, needles in MODEL_GROUPS[source]:
        if any(needle in lowered for needle in needles):
            return key, label
    return source, source.upper()


def _source_pixels(source, payload, quantum):
    """Keep the source pixel count exact, then shade its pixels by model share.

    Sampling at evenly spaced pixel midpoints avoids independently rounding every
    small model upward, which would make a model-split column look taller than the
    original source-total column.
    """
    total = payload["total"]
    count = _ceil_div(total, quantum) if total > 0 else 0
    if not count:
        return []

    grouped = {key: 0 for key, _, _ in MODEL_GROUPS[source]}
    labels = {key: label for key, label, _ in MODEL_GROUPS[source]}
    unknown = 0
    for model, model_payload in payload.get("models", {}).items():
        key, label = _model_group(source, model)
        value = model_payload.get("total") or 0
        if key == source:
            unknown += value
        else:
            grouped[key] += value
            labels[key] = label

    known = sum(grouped.values()) + unknown
    unknown += max(0, total - known)
    weighted = [(key, labels[key], grouped[key]) for key, _, _ in MODEL_GROUPS[source]
                if grouped[key] > 0]
    if unknown > 0:
        weighted.append((source, source.upper(), unknown))
    weight_total = sum(value for _, _, value in weighted)
    if not weight_total:
        return [(source, source.upper())] * count

    pixels = []
    group_idx = 0
    boundary = weighted[0][2]
    for i in range(count):
        midpoint = (i + 0.5) * weight_total / float(count)
        while group_idx < len(weighted) - 1 and midpoint > boundary:
            group_idx += 1
            boundary += weighted[group_idx][2]
        pixels.append((weighted[group_idx][0], weighted[group_idx][1]))
    return pixels


def _series_pixels(row, quantum, split):
    """One (class key, label) per pixel, Claude still stacked below Codex.

    Both charts get the same pixel COUNT per source - the split chart only
    re-colors what the plain one already draws - so a column is exactly as tall
    either way and the two charts can never disagree about a day.
    """
    out = []
    for source, label in render.SERIES:
        if split:
            out.extend(_source_pixels(source, row[source], quantum))
        else:
            total = row[source]["total"]
            out.extend([(source, label)] * (_ceil_div(total, quantum) if total > 0 else 0))
    return out


def _rows_needed(row, quantum):
    return _ceil_div(len(_series_pixels(row, quantum, False)), COLS_PER_BAR)


def _pick_quantum(rows):
    """Smallest nice quantum (1/2/5 x 10^n tokens) whose tallest column fits."""
    candidates = sorted(m * 10 ** e for e in range(5, 12) for m in (1, 2, 5))
    for q in candidates:
        if max([_rows_needed(r, q) for r in rows] + [0]) <= MAX_ROWS:
            return q
    return candidates[-1]


def _heart(add, x, y, px):
    add('<g class="ink px">')
    for r, line in enumerate(HEART):
        for c, ch in enumerate(line):
            if ch == "X":
                add('<rect x="{}" y="{}" width="{}" height="{}"/>'.format(
                    x + c * (px + 1), y + r * (px + 1), px, px))
    add('</g>')


def _source_legend(add, x, y):
    """Square-cornered take on render.draw_legend — same classes, same labels."""
    for source, label in render.SERIES:
        add('<rect class="px s-{}" x="{}" y="{}" width="8" height="8"/>'.format(source, x, y + 1))
        add('<text class="t2" x="{}" y="{}" font-size="12" font-family="var(--fm)">{}</text>'.format(
            x + 14, y + 9, render.esc(label)))
        x += 20 + len(label) * 8


def _model_legend(add, x, y):
    """Compact legend rows make the within-source shade scale explicit."""
    for row_idx, (source, _) in enumerate(render.SERIES):
        cy = y + row_idx * 17
        label = source.upper()
        add('<text class="tm" x="{}" y="{}" font-size="9.5" '
            'font-family="var(--fm)" letter-spacing="1">{}</text>'.format(x, cy + 9, label))
        cursor = x + 62
        for key, model_label, _ in MODEL_GROUPS[source]:
            # the swatch wears the texture too — that is what teaches it
            _tier_cell(add, key, cursor, cy + 1, 8)
            add('<text class="t2" x="{}" y="{}" font-size="10" '
                'font-family="var(--fm)">{}</text>'.format(
                    cursor + 13, cy + 9, render.esc(model_label)))
            cursor += 23 + len(model_label) * 6


def _build_pixel(rows, generated, split):
    n = len(rows)
    plot_w = W - PAD_L - PAD_R
    slot = plot_w / float(n)
    quantum = _pick_quantum(rows)
    pad_t = PAD_T_SPLIT if split else PAD_T_PLAIN
    base_y = pad_t + PLOT_H
    h = base_y + 56

    totals = [sum(r[s]["total"] for s, _ in render.SERIES) for r in rows]
    grand = sum(totals)
    peak_idx = totals.index(max(totals)) if any(totals) else -1

    span = "{} - {}, {}".format(rows[0]["start"].strftime("%b %d").upper(),
                                rows[-1]["start"].strftime("%b %d").upper(),
                                rows[-1]["start"].year)
    subtitle = "{} / {} TOKENS OVER {} DAYS / 1PX = {}".format(
        span, render.compact_tokens(grand), n, render.compact_tokens(quantum))
    if split:
        title = "DAILY TOKENS BY MODEL"
        aria = ("Daily token usage by source and model, 8-bit pixel chart, "
                "{}".format(span))
        subtitle += " / SOLID TO HOLLOW = TOP TIER DOWN"
    else:
        title = "DAILY TOKENS"
        aria = "Daily token usage, 8-bit pixel chart, {}".format(span)

    out = render.svg_start(W, h, aria, PIXEL_CSS + (MODEL_CSS if split else ""))
    add = out.append

    # ---- heading: chunky letter-spaced monospace fakes a bitmap face
    add('<text class="tt" x="28" y="36" font-size="17">{}</text>'.format(render.esc(title)))
    add('<text class="sub" x="28" y="57" font-size="11">{}</text>'.format(render.esc(subtitle)))
    (_model_legend if split else _source_legend)(add, 28, 67)
    _heart(add, W - PAD_R - 34, 24, 4)

    # ---- y grid: one axis, dashed "pixel" gridlines every TICK_ROWS rows
    for r in range(0, MAX_ROWS + 1, TICK_ROWS):
        y = base_y - r * PITCH
        value = r * COLS_PER_BAR * quantum
        if r > 0:
            add('<line class="gridp" x1="{}" y1="{}" x2="{}" y2="{}"/>'.format(
                PAD_L, y, W - PAD_R, y))
        add('<text class="tm" x="{}" y="{}" font-size="10.5" text-anchor="end">{}</text>'.format(
            PAD_L - 10, y + 4, render.esc(render.compact_tokens(value))))
    add('<line class="axp" x1="{}" y1="{}" x2="{}" y2="{}"/>'.format(
        PAD_L, base_y + 1, W - PAD_R, base_y + 1))

    # ---- columns of pixels
    stride = max(1, -(-n // 9))
    col_rows = []
    for i, row in enumerate(rows):
        x0 = int(round(PAD_L + slot * (i + 0.5) - BAR_W / 2.0))
        wip = row["partial"]
        squares = _series_pixels(row, quantum, split)
        col_rows.append(_ceil_div(len(squares), COLS_PER_BAR))

        if squares:
            add('<g class="col{}" style="animation-delay:{}ms">'.format(
                " wip" if wip else "", i * 18))
            for k, (key, label) in enumerate(squares):
                r, c = divmod(k, COLS_PER_BAR)
                x = x0 + c * PITCH
                y = base_y - (r * PITCH + S)
                blink = " blink" if (wip and i == n - 1 and k == len(squares) - 1) else ""
                if split:
                    # a model matching no group falls back to its flat source
                    # hue and stays solid, so it can never go unpainted
                    _tier_cell(add, key, x, y, S, blink, label)
                else:
                    add('<rect class="px s-{}{}" x="{}" y="{}" width="{}" height="{}"/>'.format(
                        key, blink, x, y, S, S))
            add('</g>')

        # x labels, right-anchored stride so the newest day is always named
        if (n - 1 - i) % stride == 0:
            add('<text class="tm" x="{}" y="{}" font-size="10.5" text-anchor="middle" '
                'font-family="var(--fm)">{}</text>'.format(
                    int(round(PAD_L + slot * (i + 0.5))), base_y + 19,
                    row["start"].strftime("%m/%d")))

    # ---- selective direct labels: peak + latest only (true totals, not pixels)
    label_idx = set()
    if peak_idx >= 0:
        label_idx.add(peak_idx)
    if n and totals[n - 1] > 0 and (peak_idx == n - 1 or n - 1 - peak_idx > 1):
        label_idx.add(n - 1)
    for idx in sorted(label_idx):
        cx = int(round(PAD_L + slot * (idx + 0.5)))
        clear = max(col_rows[max(0, idx - 1): idx + 1] or [0])   # clear the left neighbor too
        y = base_y - max(col_rows[idx], clear) * PITCH - 6
        add('<text class="tn" x="{}" y="{}" font-size="11" font-weight="700" '
            'text-anchor="middle">{}</text>'.format(cx, y, render.esc(
                render.compact_tokens(totals[idx]))))

    add('<text class="tm" x="28" y="{}" font-size="10.5">Generated {}</text>'.format(
        h - 14, generated))
    add("</svg>")
    return "\n".join(out)


def build_all(days, generated):
    """Returns [(relpath, svg_string)] for the 8-bit pixel style.

    Two charts off one geometry: the plain source stack, and the model-split
    twin. The split one is additive - it never replaces pixel-tokens.svg, so a
    README can embed either without inheriting the other's legend.
    """
    rows = render.bucket(days, render.DAYS)
    if not rows:
        return []
    return [("day/pixel-tokens.svg", _build_pixel(rows, generated, False)),
            ("day/pixel-models.svg", _build_pixel(rows, generated, True))]
