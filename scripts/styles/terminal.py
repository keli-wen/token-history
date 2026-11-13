"""Style: TERMINAL — the 30-day token history as a terminal session.

A faux terminal window (chrome bar, traffic lights, monospace output) whose
"program output" is an ASCII bar chart: one row per day, htop-style. Thirty
rows is tall, but per-day is the whole point of this idiom — a scrolling
`tokens --last 30d` transcript reads as a log, and weekly folding (5 fat rows)
would throw away the day-to-day rhythm the repo keeps everywhere else.

Bars are <text> rows of block glyphs: the Claude segment wears var(--claude),
the Codex segment var(--codex) (the colored glyph IS the mark); everything
else wears the primary/secondary/muted ink vars. Eighth-block glyphs
(▏▎▍▌▋▊▉█) give sub-cell resolution, and the fractional end of the Claude
segment doubles as the surface gap between stacked segments. Column alignment
does not trust font metrics: every column is its own <text> at a fixed x, and
every glyph run is pinned to the character grid with textLength.

Light mode gets a light terminal, dark mode a dark one — the window chrome is
built entirely from the theme vars (surface/grid/axis), so svg_start's
prefers-color-scheme switch restyles the whole illusion.
"""

import render

W = 880
FS = 12                # monospace font size
LH = 17                # line height of the "terminal output"
CW = 7.25              # character-grid cell width; glyph runs are pinned to it

WIN_X, WIN_Y = 14, 14  # terminal window origin
CHROME_H = 36
PAD_IN = 26            # inner left/right padding of the window

TEXT_X = WIN_X + PAD_IN            # column 0 of the character grid
BAR_X = TEXT_X + 8 * CW            # "MM-DD" + two spaces + one spare cell
TOTAL_X = 828                      # right-aligned totals anchor
MARK_X = TOTAL_X + 4               # one-glyph status column ("*" = partial)
CELLS = 88                         # bar track width in character cells

EIGHTHS = ["", "▏", "▎", "▍", "▌",
           "▋", "▊", "▉"]
BLOCK = "█"

CSS = (
    ".page{fill:var(--grid);opacity:.35}"
    ".win{fill:var(--surface);stroke:var(--axis);stroke-width:1}"
    ".chrome{fill:var(--grid)}"
    ".i2{fill:var(--secondary)}.im{fill:var(--muted)}"
    ".row{animation:fi .3s ease-out both}"
    "@keyframes fi{from{opacity:0}to{opacity:1}}"
    ".cur{animation:blink 1.2s step-end infinite}"
    "@keyframes blink{0%,100%{opacity:1}50%{opacity:0}}"
)


def _bar_glyphs(cells_f):
    """Block-glyph run for a bar `cells_f` character cells long (eighth-cell
    resolution). Any non-zero value renders at least a hairline block."""
    full = int(cells_f)
    eighth = int(round((cells_f - full) * 8))
    if eighth == 8:
        full, eighth = full + 1, 0
    run = BLOCK * full + EIGHTHS[eighth]
    if not run and cells_f > 0:
        run = EIGHTHS[1]
    return run


def _grid_text(add, x, y, run, cls):
    """A glyph run pinned to the character grid: textLength forces each glyph
    onto a CW-wide cell whatever monospace font the platform resolves."""
    add('<text class="tn" x="{:.2f}" y="{}" font-size="{}" textLength="{:.2f}" '
        'lengthAdjust="spacingAndGlyphs"><tspan class="{}">{}</tspan></text>'.format(
            x, y, FS, len(run) * CW, cls, render.esc(run)))


def build_terminal(days, generated):
    rows = render.bucket(days, 30)
    n = len(rows)

    totals = [sum(r[s]["total"] for s, _ in render.SERIES) for r in rows]
    grand = sum(totals)
    grand_by = {s: sum(r[s]["total"] for r in rows) for s, _ in render.SERIES}
    cost = sum(sum(r[s]["costUSD"] for s, _ in render.SERIES) for r in rows)
    peak = max(totals + [1])
    peak_idx = totals.index(max(totals)) if any(totals) else -1
    scale = peak / float(CELLS)            # tokens per character cell
    any_partial = any(r["partial"] for r in rows)

    # ---- vertical layout: everything sits on the LH line grid
    y0 = WIN_Y + CHROME_H + 24             # first baseline inside the window

    def line(i):
        return y0 + i * LH

    li_prompt = 0
    li_legend = 2
    li_rows = 4                            # first day row
    li_sep = li_rows + n                   # separator rule
    li_total = li_sep + 1
    li_split = li_total + 1
    li_foot = li_split + 2
    li_cursor = li_foot + 1

    win_h = (line(li_cursor) + 14) - WIN_Y
    h = WIN_Y + win_h + 14

    title = "Terminal — daily token usage, last {} days".format(n)
    out = render.svg_start(W, h, title, CSS)
    add = out.append

    # ---- window chrome
    add('<rect class="page" width="{}" height="{}"/>'.format(W, h))
    add('<rect class="win" x="{}" y="{}" width="{}" height="{}" rx="10"/>'.format(
        WIN_X, WIN_Y, W - 2 * WIN_X, win_h))
    add('<path class="chrome" d="M{x},{yb} v-{vh} a10,10 0 0 1 10,-10 h{iw} '
        'a10,10 0 0 1 10,10 v{vh} Z"/>'.format(
            x=WIN_X, yb=WIN_Y + CHROME_H, vh=CHROME_H - 10, iw=W - 2 * WIN_X - 20))
    add('<line class="axis" x1="{}" y1="{}" x2="{}" y2="{}"/>'.format(
        WIN_X, WIN_Y + CHROME_H, W - WIN_X, WIN_Y + CHROME_H))
    for i, dot in enumerate(("#ff5f57", "#febc2e", "#28c840")):
        add('<circle cx="{}" cy="{}" r="5.5" fill="{}"/>'.format(
            WIN_X + 22 + i * 18, WIN_Y + CHROME_H / 2, dot))
    add('<text class="tn" x="{}" y="{}" font-size="12" text-anchor="middle">'
        '<tspan class="i2">~/token-history — {}d</tspan></text>'.format(
            W // 2, WIN_Y + CHROME_H / 2 + 4, n))

    # ---- prompt
    add('<text class="tn" x="{}" y="{}" font-size="{}"><tspan class="im">$ </tspan>'
        'tokens --last {}d --by source</text>'.format(TEXT_X, line(li_prompt), FS, n))

    # ---- legend line (terminal idiom: a commented key above the output)
    ly = line(li_legend)
    lx = TEXT_X
    _grid_text(add, lx, ly, "#", "im")
    lx += 2 * CW
    for source, label in ((s, l.lower().replace(" ", "-")) for s, l in render.SERIES):
        _grid_text(add, lx, ly, BLOCK * 2, "s-{}".format(source))
        lx += 3 * CW
        add('<text class="tn" x="{:.2f}" y="{}" font-size="{}"><tspan class="i2">{}'
            '</tspan></text>'.format(lx, ly, FS, render.esc(label)))
        lx += (len(label) + 3) * CW
    tail = "stacked · {} ≈ {} tokens".format(BLOCK, render.compact_tokens(scale))
    if any_partial:
        tail += " · * in progress (faded)"
    add('<text class="tn" x="{:.2f}" y="{}" font-size="{}"><tspan class="im">{}'
        '</tspan></text>'.format(lx, ly, FS, render.esc(tail)))

    # ---- one row per day
    for i, row in enumerate(rows):
        y = line(li_rows + i)
        is_peak = (i == peak_idx)
        wip = row["partial"]
        delay = ' style="animation-delay:{}ms"'.format(i * 18)
        add('<g class="row"{}>'.format(delay))

        date_cls = "i2" if is_peak else "im"
        date_w = ' font-weight="600"' if is_peak else ""
        add('<text class="tn" x="{}" y="{}" font-size="{}"{}><tspan class="{}">{}'
            '</tspan></text>'.format(TEXT_X, y, FS, date_w, date_cls,
                                     row["start"].strftime("%m-%d")))

        wip_cls = " wip" if wip else ""
        bx = BAR_X
        for s, _ in render.SERIES:
            run = _bar_glyphs(row[s]["total"] / scale)
            if run:
                _grid_text(add, bx, y, run, "s-" + s + wip_cls)
                bx += len(run) * CW

        num_w = ' font-weight="700"' if is_peak else ""
        num_cls = "" if is_peak else ' class="i2"'
        add('<text class="tn" x="{}" y="{}" font-size="{}" text-anchor="end"{}>'
            '<tspan{}>{}</tspan></text>'.format(
                TOTAL_X, y, FS, num_w, num_cls, render.compact_tokens(totals[i])))
        if wip:
            add('<text class="tn" x="{}" y="{}" font-size="{}">'
                '<tspan class="im">*</tspan></text>'.format(MARK_X, y, FS))
        add('</g>')

    # ---- summary block, the way real CLI tools sign off
    sep_y = line(li_sep) - 5
    add('<line class="grid" x1="{}" y1="{}" x2="{}" y2="{}"/>'.format(
        TEXT_X, sep_y, W - WIN_X - PAD_IN, sep_y))

    add('<text class="tn" x="{}" y="{}" font-size="{}" font-weight="700">TOTAL  '
        '{} tokens<tspan class="i2" font-weight="400"> · {} API-equivalent'
        '</tspan></text>'.format(
            TEXT_X, line(li_total), FS,
            "{:.2f}B".format(grand / 1e9) if grand >= 1e9 else render.compact_tokens(grand),
            render.compact_cost(cost)))

    sy = line(li_split)
    sx = TEXT_X + 7 * CW                   # align under the TOTAL value
    for source, label in render.SERIES:
        value = grand_by[source]
        share = 100.0 * value / grand if grand else 0.0
        _grid_text(add, sx, sy, BLOCK, "s-{}".format(source))
        sx += 2 * CW
        text = "{} {} ({:.0f}%)".format(
            label.lower().replace(" ", "-"), render.compact_tokens(value), share)
        add('<text class="tn" x="{:.2f}" y="{}" font-size="{}"><tspan class="i2">{}'
            '</tspan></text>'.format(sx, sy, FS, render.esc(text)))
        sx += (len(text) + 2) * CW
    if peak_idx >= 0 and sx + 18 * CW < W - WIN_X - PAD_IN:
        add('<text class="tn" x="{:.2f}" y="{}" font-size="{}"><tspan class="im">'
            'peak {} on {}</tspan></text>'.format(
                sx, sy, FS, render.compact_tokens(peak),
                rows[peak_idx]["start"].strftime("%m-%d")))

    foot = "# Generated {}".format(generated)
    add('<text class="tn" x="{}" y="{}" font-size="{}"><tspan class="im">{}'
        '</tspan></text>'.format(TEXT_X, line(li_foot), FS, render.esc(foot)))

    add('<text class="tn" x="{}" y="{}" font-size="{}"><tspan class="im">$ </tspan>'
        '<tspan class="cur">{}</tspan></text>'.format(
            TEXT_X, line(li_cursor), FS, BLOCK))

    add("</svg>")
    return "\n".join(out)


def build_all(days, generated):
    return [("day/terminal-tokens.svg", build_terminal(days, generated))]
