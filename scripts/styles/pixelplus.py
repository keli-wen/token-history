#!/usr/bin/env python3
"""Pixel expansion pack: an 8-bit game-HUD stat card and a set of retro badges.

charts/day/pixel-card.svg   the last-30-days stats as an arcade HUD: the token
                            total as a HI-SCORE drawn in a real bitmap font
                            (every digit is a cluster of rects from the 5x7
                            glyph table below - zero font dependence), Claude
                            and Codex as two segmented player HP bars, the
                            API-equivalent cost as a coin counter, one pixel
                            heart per active day, and a blinking PRESS START.
charts/badge/pixel-*.svg    small stair-cornered pixel chips for a README
                            line; label and value are both set in the bitmap
                            font, with a hard 2px offset shadow for the
                            8-bit-sticker feel. Opaque and self-contained so
                            they read on light and dark pages alike.

Design language follows scripts/styles/pixel.py: 8px-ish grid, crispEdges,
integer coordinates, square corners, letter-spaced mono for prose, the pixel
heart in primary ink. Card theming comes from render.svg_start (CSS vars for
both color schemes); series identity is strictly var(--claude)/var(--codex).
Badges hardcode the validated light-mode hexes like styles/badge.py does.

Deterministic: same data -> same bytes; `generated` appears only in footnote
text and comments. Python 3.9, stdlib only; `import render` works when cwd is
the repo's scripts/ directory.
"""

import datetime as dt

import render

# ----------------------------------------------------------- 5x7 bitmap font
# Each glyph is a tuple of row strings ('X' = lit cell). Widths vary; digits
# are all 5 columns wide so scores stay tabular. Rendered as merged-run rects,
# so the type is genuinely pixel-built - no font files, no fallback drift.

GLYPHS = {
    "0": (".XXX.", "X...X", "X..XX", "X.X.X", "XX..X", "X...X", ".XXX."),
    "1": ("..X..", ".XX..", "..X..", "..X..", "..X..", "..X..", ".XXX."),
    "2": (".XXX.", "X...X", "....X", "...X.", "..X..", ".X...", "XXXXX"),
    "3": ("XXXXX", "....X", "...X.", "..XX.", "....X", "X...X", ".XXX."),
    "4": ("...X.", "..XX.", ".X.X.", "X..X.", "XXXXX", "...X.", "...X."),
    "5": ("XXXXX", "X....", "XXXX.", "....X", "....X", "X...X", ".XXX."),
    "6": ("..XX.", ".X...", "X....", "XXXX.", "X...X", "X...X", ".XXX."),
    "7": ("XXXXX", "....X", "...X.", "..X..", ".X...", ".X...", ".X..."),
    "8": (".XXX.", "X...X", "X...X", ".XXX.", "X...X", "X...X", ".XXX."),
    "9": (".XXX.", "X...X", "X...X", ".XXXX", "....X", "...X.", ".XX.."),
    "A": (".XXX.", "X...X", "X...X", "XXXXX", "X...X", "X...X", "X...X"),
    "B": ("XXXX.", "X...X", "X...X", "XXXX.", "X...X", "X...X", "XXXX."),
    "C": (".XXX.", "X...X", "X....", "X....", "X....", "X...X", ".XXX."),
    "D": ("XXXX.", "X...X", "X...X", "X...X", "X...X", "X...X", "XXXX."),
    "E": ("XXXXX", "X....", "X....", "XXXX.", "X....", "X....", "XXXXX"),
    "F": ("XXXXX", "X....", "X....", "XXXX.", "X....", "X....", "X...."),
    "G": (".XXX.", "X...X", "X....", "X.XXX", "X...X", "X...X", ".XXXX"),
    "H": ("X...X", "X...X", "X...X", "XXXXX", "X...X", "X...X", "X...X"),
    "I": ("XXX", ".X.", ".X.", ".X.", ".X.", ".X.", "XXX"),
    "J": (".XXXX", "...X.", "...X.", "...X.", "...X.", "X..X.", ".XX.."),
    "K": ("X...X", "X..X.", "X.X..", "XX...", "X.X..", "X..X.", "X...X"),
    "L": ("X....", "X....", "X....", "X....", "X....", "X....", "XXXXX"),
    "M": ("X...X", "XX.XX", "X.X.X", "X.X.X", "X...X", "X...X", "X...X"),
    "N": ("X...X", "XX..X", "X.X.X", "X..XX", "X...X", "X...X", "X...X"),
    "O": (".XXX.", "X...X", "X...X", "X...X", "X...X", "X...X", ".XXX."),
    "P": ("XXXX.", "X...X", "X...X", "XXXX.", "X....", "X....", "X...."),
    "Q": (".XXX.", "X...X", "X...X", "X...X", "X.X.X", "X..X.", ".XX.X"),
    "R": ("XXXX.", "X...X", "X...X", "XXXX.", "X.X..", "X..X.", "X...X"),
    "S": (".XXXX", "X....", "X....", ".XXX.", "....X", "....X", "XXXX."),
    "T": ("XXXXX", "..X..", "..X..", "..X..", "..X..", "..X..", "..X.."),
    "U": ("X...X", "X...X", "X...X", "X...X", "X...X", "X...X", ".XXX."),
    "V": ("X...X", "X...X", "X...X", "X...X", "X...X", ".X.X.", "..X.."),
    "W": ("X...X", "X...X", "X...X", "X.X.X", "X.X.X", "XX.XX", "X...X"),
    "X": ("X...X", "X...X", ".X.X.", "..X..", ".X.X.", "X...X", "X...X"),
    "Y": ("X...X", "X...X", ".X.X.", "..X..", "..X..", "..X..", "..X.."),
    "Z": ("XXXXX", "....X", "...X.", "..X..", ".X...", "X....", "XXXXX"),
    ".": ("..", "..", "..", "..", "..", "XX", "XX"),
    ",": ("..", "..", "..", "..", "XX", ".X", "X."),
    "$": ("..X..", ".XXXX", "X.X..", ".XXX.", "..X.X", "XXXX.", "..X.."),
    "%": ("XX..X", "XX.X.", "..X..", "..X..", "..X..", ".X.XX", "X..XX"),
    "/": ("....X", "...X.", "...X.", "..X..", ".X...", ".X...", "X...."),
    "-": ("....", "....", "....", "XXXX", "....", "....", "...."),
    ":": ("..", "XX", "XX", "..", "XX", "XX", ".."),
    " ": ("...", "...", "...", "...", "...", "...", "..."),
    "?": (".XXX.", "X...X", "....X", "...X.", "..X..", ".....", "..X.."),
}


def _glyph(ch):
    return GLYPHS.get(ch, GLYPHS["?"])


def _pw(text, u):
    """Pixel-text advance width: glyph columns + 1 column of spacing."""
    if not text:
        return 0
    return sum((len(_glyph(ch)[0]) + 1) * u for ch in text) - u


def _prects(x, y, text, u):
    """Rects for a run of bitmap glyphs, horizontal runs merged per row."""
    rects = []
    cx = x
    for ch in text:
        g = _glyph(ch)
        cols = len(g[0])
        for r, row in enumerate(g):
            c = 0
            while c < cols:
                if row[c] == "X":
                    c2 = c
                    while c2 < cols and row[c2] == "X":
                        c2 += 1
                    rects.append((cx + c * u, y + r * u, (c2 - c) * u, u))
                    c = c2
                else:
                    c += 1
        cx += (cols + 1) * u
    return rects


def _rects_svg(rects):
    return "".join('<rect x="{}" y="{}" width="{}" height="{}"/>'.format(*r)
                   for r in rects)


def _ptext(add, x, y, text, u, cls=None, fill=None):
    """Emit bitmap text at (x, y) top-left; height is 7*u."""
    attr = ' class="px {}"'.format(cls) if cls else ' fill="{}"'.format(fill)
    add("<g{}>{}</g>".format(attr, _rects_svg(_prects(x, y, text, u))))


def _sprite_rects(pattern, x, y, u):
    rects = []
    for r, row in enumerate(pattern):
        c = 0
        while c < len(row):
            if row[c] == "X":
                c2 = c
                while c2 < len(row) and row[c2] == "X":
                    c2 += 1
                rects.append((x + c * u, y + r * u, (c2 - c) * u, u))
                c = c2
            else:
                c += 1
    return rects


def _sprite(add, pattern, x, y, u, cls=None, fill=None):
    attr = ' class="px {}"'.format(cls) if cls else ' fill="{}"'.format(fill)
    add("<g{}>{}</g>".format(attr, _rects_svg(_sprite_rects(pattern, x, y, u))))


def _stair(x, y, w, h, n1, n2):
    """Closed path for a rectangle with two-step staircase corners (no rx)."""
    return ("M{ax},{y} H{bx} V{y2} H{cx} V{y1} H{x2} V{by1} H{cx} V{by2} "
            "H{bx} V{y3} H{ax} V{by2} H{dx} V{by1} H{x} V{y1} H{dx} V{y2} "
            "H{ax} Z").format(
        x=x, y=y, x2=x + w, y3=y + h,
        ax=x + n1, bx=x + w - n1, cx=x + w - n2, dx=x + n2,
        y1=y + n1, y2=y + n2, by1=y + h - n1, by2=y + h - n2)


# ------------------------------------------------------------------- sprites

HEART = (".XX.XX.", "XXXXXXX", "XXXXXXX", ".XXXXX.", "..XXX..", "...X...")
HEART_HOLLOW = (".XX.XX.", "X..X..X", "X.....X", ".X...X.", "..X.X..", "...X...")
# Two coins, the way the hearts come in two: the badges take the filled 9x9 disc
# plus a dollar sign printed on its face in a second ink, the HUD card keeps the
# hollow one because a single muted ink is all it has. Filled for the badges
# because a 1px rim collapses into a "0" at that scale - which is why the small
# API badge used to carry no icon at all - and the mark is printed rather than
# punched because anything knocked out of a coin's middle reads as a Chinese
# cash coin instead of as money owed.
COIN = ("...XXX...", ".XXXXXXX.", ".XXXXXXX.", "XXXXXXXXX", "XXXXXXXXX",
        "XXXXXXXXX", ".XXXXXXX.", ".XXXXXXX.", "...XXX...")
COIN_MARK = (".........", "....X....", "...XXXX..", "..X.X....", "...XXX...",
             "....X.X..", "..XXXX...", "....X....", ".........")
COIN_HOLLOW = (".XXXXX.", "X.....X", "X..X..X", "X..X..X", "X..X..X",
               "X..X..X", "X.....X", ".XXXXX.")
BOLT = ("...XX", "..XX.", ".XX..", "XXXXX", "..XX.", ".XX..", "XX...")
TROPHY = ("XXXXX", "XXXXX", ".XXX.", "..X..", ".XXX.")
BARS = ("..X..", "..X..", "X.X..", "X.X.X", "X.X.X")

# --------------------------------------------------------------- shared stats


def _stats(days):
    rows = render.bucket(days, 30)
    tokens = [sum(r[s]["total"] for s, _ in render.SERIES) for r in rows]
    total = sum(tokens)
    cost = sum(sum(r[s]["costUSD"] for s, _ in render.SERIES) for r in rows)
    by_src = {s: sum(r[s]["total"] for r in rows) for s, _ in render.SERIES}
    active = sum(1 for t in tokens if t > 0)
    peak = max(tokens + [0])
    peak_day = rows[tokens.index(peak)]["start"] if peak else None
    avg = total / float(active) if active else 0
    streak = 0
    if days:
        cur = max(dt.date.fromisoformat(d) for d in days)
        while cur.isoformat() in days and render.day_total(days[cur.isoformat()]) > 0:
            streak += 1
            cur -= dt.timedelta(days=1)
    return {
        "rows": rows, "tokens": tokens, "total": total, "cost": cost,
        "by_src": by_src, "active": active,
        "peak": peak, "peak_day": peak_day, "avg": avg, "streak": streak,
        "today": tokens[-1] if tokens else 0,
        "partial": bool(rows and rows[-1]["partial"]),
    }


# ------------------------------------------------------------------- the card

CARD_W, CARD_H = 880, 280

CARD_CSS = (
    ".px{shape-rendering:crispEdges}"
    ".ink{fill:var(--primary)}"
    ".dim{fill:var(--grid)}"
    ".mut{fill:var(--muted)}"
    ".frame{fill:var(--axis);fill-rule:evenodd;shape-rendering:crispEdges}"
    ".sub{font-family:var(--fm);fill:var(--secondary);letter-spacing:1px}"
    ".lbl{font-family:var(--fm);fill:var(--muted);letter-spacing:2px}"
    ".val{font-family:var(--fm);fill:var(--primary);font-weight:700;"
    "font-variant-numeric:tabular-nums}"
    # step blink; the resting (animation-off) state is the base opacity: visible
    ".blink{animation:pxblink 1.2s step-end infinite}"
    "@keyframes pxblink{0%,62%{opacity:1}63%,100%{opacity:.15}}"
)


def _hp_bar(add, x, y, cells, filled, cell_w, cell_h, series):
    for i in range(cells):
        cls = "s-{}".format(series) if i < filled else "dim"
        add('<rect class="px {}" x="{}" y="{}" width="{}" height="{}"/>'.format(
            cls, x + i * (cell_w + 2), y, cell_w, cell_h))


def _build_card(days, generated):
    st = _stats(days)
    w, h = CARD_W, CARD_H
    hero = render.fmt_hero(st["total"])
    cost_s = render.compact_cost(st["cost"]).replace("$", "")
    peak_s = render.compact_tokens(st["peak"])
    peak_d = st["peak_day"].strftime("%b %d").upper() if st["peak_day"] else "-"
    avg_s = render.compact_tokens(st["avg"])
    pcts = {s: (int(round(100.0 * st["by_src"][s] / st["total"])) if st["total"] else 0)
            for s, _ in render.SERIES}

    aria = ("AI coding usage, retro game HUD, last 30 days: {} tokens total, "
            "about {} API-equivalent, Claude {}%, Codex {}%, Gemini {}%, "
            "best day {} on {}, {} of {} days active".format(
                hero, render.compact_cost(st["cost"]),
                pcts["claude"], pcts["codex"], pcts["gemini"],
                peak_s, peak_d.title(), st["active"], len(st["rows"])))

    out = render.svg_start(w, h, aria, CARD_CSS)
    out.insert(1, "<title>{}</title>".format(render.esc(aria)))
    add = out.append
    add("<!-- generated {} -->".format(render.esc(generated)))

    # stair-cornered HUD frame (ring: outer stair minus inner stair, evenodd)
    add('<path class="frame" d="{} {}"/>'.format(
        _stair(8, 8, w - 16, h - 16, 12, 6),
        _stair(11, 11, w - 22, h - 22, 12, 6)))

    # ---- left: HI-SCORE block, the total in genuine bitmap digits
    _ptext(add, 44, 36, "HI-SCORE", 2, cls="mut")
    add('<text class="lbl" x="{}" y="48" font-size="10">TOKENS / LAST 30 DAYS'
        '</text>'.format(44 + _pw("HI-SCORE", 2) + 14))
    _ptext(add, 48, 66, hero, 8, cls="dim")          # hard 4px pixel shadow
    _ptext(add, 44, 62, hero, 8, cls="ink")

    # coin counter: API-equivalent value
    _sprite(add, COIN_HOLLOW, 44, 138, 2, cls="mut")
    _ptext(add, 66, 141, "$" + cost_s, 3, cls="ink")
    add('<text class="sub" x="{}" y="156" font-size="11">API-EQUIVALENT'
        '</text>'.format(66 + _pw("$" + cost_s, 3) + 12))

    # best day, under the coin line
    _sprite(add, TROPHY, 44, 178, 2, cls="mut")
    add('<text class="sub" x="60" y="188" font-size="11">BEST DAY '
        '<tspan class="val">{}</tspan> / {}</text>'.format(
            render.esc(peak_s), render.esc(peak_d)))

    # ---- right: three player HP bars = share of combined tokens
    bx, bxe = 470, 836
    cells, cell_w, cell_h = 20, 16, 14
    for idx, (series, label) in enumerate(render.SERIES):
        y_lbl = 36 + idx * 46
        y_bar = y_lbl + 17
        tok = st["by_src"][series]
        pct = pcts[series]
        filled = int(round(cells * tok / float(st["total"]))) if st["total"] else 0
        if tok > 0 and filled == 0:
            filled = 1
        name = "P{} {}".format(idx + 1, "CLAUDE" if series == "claude" else series.upper())
        _ptext(add, bx, y_lbl, name, 2, cls="ink")
        add('<text class="val" x="{}" y="{}" font-size="12" text-anchor="end">'
            '{} / {}%</text>'.format(bxe, y_lbl + 12, render.esc(
                render.compact_tokens(tok)), pct))
        _hp_bar(add, bx, y_bar, cells, filled, cell_w, cell_h, series)

    # daily average, right column
    _sprite(add, BARS, bx, 182, 2, cls="mut")
    add('<text class="sub" x="{}" y="192" font-size="11">AVG '
        '<tspan class="val">{}</tspan> / ACTIVE DAY</text>'.format(
            bx + 16, render.esc(avg_s)))

    # ---- bottom band: one heart per day (filled = active), streak, PRESS START
    hx, hy, pitch = 44, 228, 18
    n = len(st["rows"])
    for i, t in enumerate(st["tokens"]):
        pat = HEART if t > 0 else HEART_HOLLOW
        wip = st["rows"][i]["partial"]
        cls = "ink" if t > 0 else "dim"
        extra = " blink" if wip else ""
        add('<g class="px {}{}">{}</g>'.format(
            cls, extra, _rects_svg(_sprite_rects(pat, hx + i * pitch, hy, 2))))
    lx = hx + n * pitch + 8
    add('<text class="sub" x="{}" y="240" font-size="11">'
        '<tspan class="val">{}/{}</tspan> DAY STREAK</text>'.format(
            lx, st["streak"], n))
    add('<text class="lbl blink" x="{}" y="240" font-size="11" '
        'text-anchor="end">&#9654; PRESS START</text>'.format(bxe))

    # bottom carries only the generated stamp (repo-wide policy)
    add('<text class="lbl" x="44" y="{}" font-size="9" '
        'style="letter-spacing:1px">GEN {}</text>'.format(
            h - 20, render.esc(generated.upper())))
    add("</svg>")
    return "\n".join(out)


# ----------------------------------------------------------------- the badges
# Opaque two-tone chips like shields badges, but fully pixel-built: the bitmap
# font at 2px cells (10x14 caps - classic arcade size), stair-notched corners
# from a path (no rx anywhere), a 2px hard offset shadow, and a 1px light
# outline so the dark body keeps its silhouette on dark pages too.

INK = "#141413"
PAPER = "#faf9f5"
EDGE = "#b0aea5"
SAND = "#e8e6dc"
ORANGE = "#d06a41"   # validated light-mode Claude accent (see render.THEME)
BLUE = "#4382c9"     # validated light-mode Codex accent
GOLD = "#e3b341"     # coin gold: the one decorative hue outside the theme,
                     # reserved for the money sprite so the cost badge reads as
                     # cost rather than as a third series


def _badge(label, value, value_bg, value_fg, icons, aria, generated,
           shadow_text, small=False):
    if small:
        # compact twin: 1px glyph cells (5x7px caps), 17px outline + 1px
        # shadow = 18px total, just under the 20px shields height
        u, oh, sh = 1, 17, 1
        n1, n2 = 3, 1
        pad_x, icon_gap, seg_gap, vpad, right_pad = 6, 4, 6, 5, 4
        rect_y, rect_h, ty = 3, 11, 5
    else:
        u, oh, sh = 2, 22, 2          # 22px outline + 2px shadow = 24 total
        n1, n2 = 4, 2
        pad_x, icon_gap, seg_gap, vpad, right_pad = 10, 6, 9, 7, 6
        rect_y, rect_h, ty = 3, 16, 4
    total_h = oh + sh
    x = pad_x
    icon_w = 0
    for pat, _, iu in icons:
        icon_w = max(icon_w, len(pat[0]) * iu)
    x_label = x + icon_w + icon_gap if icons else x
    lw = _pw(label, u)
    vx = x_label + lw + seg_gap       # value segment start
    tw = _pw(value, u)
    vw = tw + 2 * vpad
    w = vx + vw + right_pad           # total width incl. shadow overhang

    out = []
    add = out.append
    add('<svg xmlns="http://www.w3.org/2000/svg" width="{}" height="{}" '
        'viewBox="0 0 {} {}" role="img" aria-label="{}">'.format(
            w, total_h, w, total_h, render.esc(aria)))
    add("<title>{}</title>".format(render.esc(aria)))
    add("<!-- generated {} -->".format(render.esc(generated)))
    add('<g shape-rendering="crispEdges">')
    # hard offset shadow, then the light outline, then the dark body
    add('<path fill="{}" d="{}"/>'.format(INK, _stair(sh, sh, w - sh, oh, n1, n2)))
    add('<path fill="{}" d="{}"/>'.format(EDGE, _stair(0, 0, w - sh, oh, n1, n2)))
    add('<path fill="{}" d="{}"/>'.format(
        INK, _stair(1, 1, w - sh - 2, oh - 2, n1, n2)))
    # value segment: plain rect inset in the dark body; the body's stair
    # corners around it carry the pixel look
    add('<rect fill="{}" x="{}" y="{}" width="{}" height="{}"/>'.format(
        value_bg, vx, rect_y, vw, rect_h))
    # icon(s)
    for pat, fill, iu in icons:
        ih = len(pat) * iu
        iy = (oh - ih) // 2
        add('<g fill="{}">{}</g>'.format(
            fill, _rects_svg(_sprite_rects(pat, x, iy, iu))))
    # label text (bitmap, light on dark)
    add('<g fill="{}">{}</g>'.format(PAPER, _rects_svg(_prects(x_label, ty, label, u))))
    # value text (bitmap), with a 1px dark drop for pop on the color field
    if shadow_text:
        add('<g fill="{}" fill-opacity=".3">{}</g>'.format(
            INK, _rects_svg(_prects(vx + vpad, ty + 1, value, u))))
    add('<g fill="{}">{}</g>'.format(
        value_fg, _rects_svg(_prects(vx + vpad, ty, value, u))))
    add("</g>")
    add("</svg>")
    return "".join(out)


DUO_A = ("X.", ".X")   # tokens icon: 2x2 duo-color pixel cluster
DUO_B = (".X", "X.")


def _build_badges(days, generated):
    st = _stats(days)
    hero = render.fmt_hero(st["total"])
    cost_s = render.compact_cost(st["cost"])
    today_s = render.compact_tokens(st["today"])
    avg_s = render.compact_tokens(st["avg"])
    streak_s = "{} DAY{}".format(st["streak"], "" if st["streak"] == 1 else "S")

    # (slug, label, value, value_bg, value_fg, big icons, small icons,
    #  aria, shadow_text) - small icons are dropped where 1px sprites would turn
    # to noise; the duo cluster, coin and heart survive the scale.
    specs = [
        ("tokens-30d", "TOKENS 30D", hero, ORANGE, PAPER,
         [(DUO_A, ORANGE, 6), (DUO_B, BLUE, 6)],
         [(DUO_A, ORANGE, 3), (DUO_B, BLUE, 3)],
         "Tokens, last 30 days: {}".format(hero), True),
        ("api-30d", "API 30D", cost_s, BLUE, PAPER,
         [(COIN, GOLD, 2), (COIN_MARK, PAPER, 2)],
         [(COIN, GOLD, 1), (COIN_MARK, PAPER, 1)],
         "API-equivalent value, last 30 days: {}".format(cost_s), True),
        ("today", "TODAY", today_s, ORANGE, PAPER,
         [(BOLT, PAPER, 2)], [(BOLT, PAPER, 1)],
         "Tokens today: {}".format(today_s), True),
        ("avg", "AVG/DAY", avg_s, BLUE, PAPER,
         [(BARS, PAPER, 2)], [],
         "Average tokens per active day: {}".format(avg_s), True),
        ("streak", "STREAK", streak_s, SAND, INK,
         [(HEART, ORANGE, 2)], [(HEART, ORANGE, 1)],
         "Active-day streak: {}".format(streak_s.title()), False),
    ]
    badges = []
    for slug, label, value, vbg, vfg, big_ic, sm_ic, aria, shad in specs:
        badges.append(("badge/pixel-{}.svg".format(slug), _badge(
            label, value, vbg, vfg, big_ic, aria, generated, shad)))
    for slug, label, value, vbg, vfg, big_ic, sm_ic, aria, shad in specs:
        badges.append(("badge/pixel-{}-sm.svg".format(slug), _badge(
            label, value, vbg, vfg, sm_ic, aria, generated, shad, small=True)))
    return badges


# -------------------------------------------------------------------- plug-in


def build_all(days, generated):
    """Returns [(relpath, svg_string), ...]: the HUD card plus the badge set."""
    rows = render.bucket(days, 30)
    if not rows:
        return []
    out = [("day/pixel-card.svg", _build_card(days, generated))]
    out.extend(_build_badges(days, generated))
    return out
