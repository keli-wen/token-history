#!/usr/bin/env python3
"""Shields.io-style flat badges for the token-usage record.

Six small inline badges, faithful to the shields.io "flat" style: 20px tall,
rx=3, #555 label segment, colored value segment, Verdana 11px white text drawn
twice (a .3-opacity #010101 shadow at y+1, then white), and the classic subtle
#bbb top gradient at 10% opacity. Widths are computed from real Verdana advance
widths (2048 units/em) and locked in with textLength, exactly as shields does,
so text never clips and never floats in excess padding.

Badges are deliberately theme-independent — authentic shields badges do not
adapt to dark mode, and these do not either. Deterministic output; the
`generated` stamp is embedded as an SVG comment only.

Python 3.9, stdlib only. `import render` works when cwd is the repo's scripts/.
"""

import datetime as dt

import render

# Value colors: the repo's validated brand accents where the stat is about the
# record itself, plus the shields classic brightgreen for the streak stat.
ORANGE = "#d06a41"   # Claude accent (light-mode validated brand value)
BLUE = "#4382c9"     # Codex accent
PURPLE = "#7f4aa3"   # Gemini accent
GREEN = "#4c1"       # shields brightgreen, streak-style stats
LABEL_BG = "#555"    # shields flat label segment

FONT = "Verdana,Geneva,DejaVu Sans,sans-serif"

# Verdana glyph advance widths in font units (2048 units per em). Multiplied by
# 11/2048 for the 11px badge text. Unknown characters fall back to ~7.1px; the
# textLength attribute makes any residual estimate error invisible.
_EM = 2048.0
_W = {
    " ": 727, "!": 811, '"': 959, "#": 1679, "$": 1303, "%": 2412, "&": 1499,
    "'": 563, "(": 979, ")": 979, "*": 1303, "+": 1679, ",": 727, "-": 979,
    ".": 727, "/": 1090, ":": 818, ";": 818, "<": 1679, "=": 1679, ">": 1679,
    "?": 1219, "@": 2048,
    "A": 1400, "B": 1404, "C": 1430, "D": 1579, "E": 1293, "F": 1177,
    "G": 1588, "H": 1540, "I": 855, "J": 931, "K": 1417, "L": 1147,
    "M": 1767, "N": 1532, "O": 1612, "P": 1235, "Q": 1612, "R": 1424,
    "S": 1400, "T": 1262, "U": 1499, "V": 1400, "W": 2025, "X": 1403,
    "Y": 1260, "Z": 1403,
    "[": 979, "\\": 1090, "]": 979, "^": 1679, "_": 1303, "`": 1303,
    "a": 1255, "b": 1303, "c": 1085, "d": 1303, "e": 1244, "f": 721,
    "g": 1303, "h": 1303, "i": 563, "j": 563, "k": 1186, "l": 563,
    "m": 1998, "n": 1303, "o": 1253, "p": 1303, "q": 1303, "r": 861,
    "s": 1067, "t": 797, "u": 1303, "v": 1212, "w": 1674, "x": 1212,
    "y": 1212, "z": 1067,
    "{": 1303, "|": 1090, "}": 1303, "~": 1679,
    "·": 758,   # · the label separator
    "≈": 1679,  # ≈
}
for _d in "0123456789":
    _W[_d] = 1303


def _text_width(text):
    units = sum(_W.get(ch, 1331) for ch in text)
    return units * 11.0 / _EM


def _badge(label, segments, generated):
    """One flat badge. `segments` is [(text, color)]; usually one value segment,
    the split badge uses two so each share wears its series color."""
    pad = 10  # 5px each side, the shields horizontal padding
    label_tw = int(round(_text_width(label)))
    left_w = label_tw + pad
    seg_ws = []
    for text, _ in segments:
        tw = int(round(_text_width(text)))
        seg_ws.append((tw, tw + pad))
    total_w = left_w + sum(w for _, w in seg_ws)
    value_text = " / ".join(t for t, _ in segments)
    aria = "{}: {}".format(label, value_text)

    out = []
    add = out.append
    add('<svg xmlns="http://www.w3.org/2000/svg" '
        'xmlns:xlink="http://www.w3.org/1999/xlink" width="{w}" height="20" '
        'role="img" aria-label="{aria}">'.format(w=total_w, aria=render.esc(aria)))
    add('<title>{}</title>'.format(render.esc(aria)))
    add('<!-- generated {} -->'.format(render.esc(generated)))
    add('<linearGradient id="s" x2="0" y2="100%">'
        '<stop offset="0" stop-color="#bbb" stop-opacity=".1"/>'
        '<stop offset="1" stop-opacity=".1"/></linearGradient>')
    add('<clipPath id="r"><rect width="{}" height="20" rx="3" fill="#fff"/>'
        '</clipPath>'.format(total_w))
    add('<g clip-path="url(#r)">')
    add('<rect width="{}" height="20" fill="{}"/>'.format(left_w, LABEL_BG))
    x = left_w
    for (_, color), (_, w) in zip(segments, seg_ws):
        add('<rect x="{}" width="{}" height="20" fill="{}"/>'.format(x, w, color))
        x += w
    add('<rect width="{}" height="20" fill="url(#s)"/>'.format(total_w))
    add('</g>')
    add('<g fill="#fff" text-anchor="middle" font-family="{}" '
        'text-rendering="geometricPrecision" font-size="110">'.format(FONT))

    def text_pair(cx, text, tl):
        # shields renders every run twice: shadow first, then the white text
        e = render.esc(text)
        add('<text aria-hidden="true" x="{x}" y="150" fill="#010101" '
            'fill-opacity=".3" transform="scale(.1)" textLength="{tl}">{t}</text>'
            .format(x=int(round(cx * 10)), tl=tl * 10, t=e))
        add('<text x="{x}" y="140" transform="scale(.1)" fill="#fff" '
            'textLength="{tl}">{t}</text>'.format(x=int(round(cx * 10)), tl=tl * 10, t=e))

    text_pair(left_w / 2.0 + 1, label, label_tw)
    x = left_w
    for (text, _), (tw, w) in zip(segments, seg_ws):
        text_pair(x + w / 2.0 - 1, text, tw)
        x += w
    add('</g>')
    add('</svg>')
    return "".join(out)


def build_all(days, generated):
    """Return [(relpath, svg)] for the badge set, all under badge/."""
    rows = render.bucket(days, 30)
    tokens = [sum(r[s]["total"] for s, _ in render.SERIES) for r in rows]
    total30 = sum(tokens)
    cost30 = sum(sum(r[s]["costUSD"] for s, _ in render.SERIES) for r in rows)
    today = tokens[-1] if tokens else 0
    active = sum(1 for t in tokens if t > 0)
    avg = total30 / float(active) if active else 0
    claude30 = sum(r["claude"]["total"] for r in rows)
    codex30 = sum(r["codex"]["total"] for r in rows)
    gemini30 = sum(r["gemini"]["total"] for r in rows)
    split_sum = claude30 + codex30 + gemini30
    if split_sum > 0:
        claude_pct = int(round(100.0 * claude30 / split_sum))
        codex_pct = int(round(100.0 * codex30 / split_sum))
        gemini_pct = max(0, 100 - claude_pct - codex_pct)
    else:
        claude_pct = codex_pct = gemini_pct = 0

    # active-day streak: consecutive recorded days with usage, ending on the
    # newest day in the record (a missing date breaks the streak)
    streak = 0
    if days:
        cur = max(dt.date.fromisoformat(d) for d in days)
        while cur.isoformat() in days and render.day_total(days[cur.isoformat()]) > 0:
            streak += 1
            cur -= dt.timedelta(days=1)

    badges = [
        ("badge/tokens-today.svg", "tokens · today",
         [(render.compact_tokens(today), ORANGE)]),
        ("badge/tokens-30d.svg", "tokens · 30d",
         [(render.compact_tokens(total30), ORANGE)]),
        ("badge/api-equiv-30d.svg", "api equiv · 30d",
         [(render.compact_cost(cost30), BLUE)]),
        ("badge/daily-avg.svg", "daily avg",
         [(render.compact_tokens(avg), BLUE)]),
        ("badge/split-30d.svg", "claude / codex / gemini",
         [("{}%".format(claude_pct), ORANGE),
          ("{}%".format(codex_pct), BLUE),
          ("{}%".format(gemini_pct), PURPLE)]),
        ("badge/streak.svg", "streak",
         [("{} day{}".format(streak, "" if streak == 1 else "s"), GREEN)]),
    ]
    return [(rel, _badge(label, segs, generated)) for rel, label, segs in badges]
