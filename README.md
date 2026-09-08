<div align="center">

<img src="./assets/icon.svg" width="96" alt="token-history icon: a pixel coin stamped with a rising bar chart">

# token-history

**Never lose your AI-coding history —<br>snapshot it to git daily, chart it a dozen ways, show it anywhere.**

[![Render charts](https://github.com/keli-wen/token-history/actions/workflows/render.yml/badge.svg?branch=master)](https://github.com/keli-wen/token-history/actions/workflows/render.yml)
[![uv](https://img.shields.io/endpoint?url=https://raw.githubusercontent.com/astral-sh/uv/main/assets/badge/v0.json)](https://github.com/astral-sh/uv)
![Python ≥3.9](https://img.shields.io/badge/python-%E2%89%A53.9-3776AB?logo=python&logoColor=white)
![dependencies: zero](https://img.shields.io/badge/dependencies-zero-brightgreen)
![license: MIT](https://img.shields.io/badge/license-MIT-blue)

<img src="./charts/badge/tokens-30d.svg" alt="tokens over the last 30 days"> <img src="./charts/badge/api-equiv-30d.svg" alt="API-equivalent value over the last 30 days"> <img src="./charts/badge/streak.svg" alt="active-day streak">

<img src="./charts/badge/pixel-tokens-30d-sm.svg" alt="pixel badge: tokens over the last 30 days"> <img src="./charts/badge/pixel-api-30d-sm.svg" alt="pixel badge: API-equivalent value"> <img src="./charts/badge/pixel-streak-sm.svg" alt="pixel badge: active-day streak">

</div>

**Copy this repo and every chart on this page becomes yours.** A GitHub profile already carries two name cards — the contribution graph for how much you code, the star count for what others make of it. Your AI token usage is becoming the third: a day-by-day record of how much you actually build with AI. This repo turns yours into one you own:

- **Snapshots your usage into git, daily.** AI coding tools keep usage data only on your disk and quietly expire it — history you don't persist is history you lose. Every number lands in git before that happens, permanently yours.
- **Renders a whole gallery of SVG charts and badges** — self-updating, and embeddable in a GitHub profile README, a blog, or anywhere an `<img>` tag works.
- **Merges every machine and every source.** Multiple hosts combine into one history; Claude Code and Codex are the first two sources (riding on ccusage), with more models and feeds on the roadmap.
- **Sets itself up through your agent.** Hand Claude Code or Codex [one link](#-for-agents-recommended) and say *"set this up"* — it walks itself from fork to first push.

The repo keeps a day-by-day history; the headline chart shows the last 30 days, and every render also produces [an entire gallery of other styles](#chart-gallery) across daily, weekly, and monthly granularity.

<img src="./charts/day/pixel-tokens.svg" width="880" alt="Daily token usage as pixel-art bars: one square per 10M tokens, Claude orange stacked under Codex blue">

## Contents

- [Contents](#contents)
- [Why this exists](#why-this-exists)
- [Quick start](#quick-start)
  - [🤖 For agents (recommended)](#-for-agents-recommended)
  - [🧑 For humans](#-for-humans)
- [Chart gallery](#chart-gallery)
  - [Badges](#badges)
  - [Daily](#daily)
  - [Weekly](#weekly)
  - [Monthly](#monthly)
- [How multi-host works](#how-multi-host-works)
- [How it stays correct](#how-it-stays-correct)
- [Layout](#layout)
- [Design notes](#design-notes)
- [Thanks](#thanks)
- [License](#license)

## Why this exists

<img src="./assets/why.png" width="880" alt="Pixel illustration: on the left a terminal's token stream dissolves into a trash bin; on the right the tokens are stacked safely inside a vault, beneath a framed rising chart">

1. **Usage data disappears.** AI coding tools keep it only on your disk, on a rolling delete. What you don't persist, you lose — permanently.
2. **The record is becoming reputation.** The contribution graph and the star count are the name cards developers already show; a day-by-day history of how much you build with AI is next. Git makes it permanent — and yours.
3. **Visualized, it goes anywhere.** Once rendered to SVG, your usage can be embedded in any README, blog, or site — and this repo ships a whole gallery of good-looking styles to pick from.

## Quick start

> [!IMPORTANT]
> **Fork first.** This repo holds *my* data — you need your own copy to push *yours* into. Cloning this repo directly gives you nowhere to commit.

### 🤖 For agents (recommended)

Hand your coding agent — Claude Code, Codex, whatever you drive — this one link and say *"set this up on my machine"*:

```
https://raw.githubusercontent.com/keli-wen/token-history/master/SETUP.md
```

[`SETUP.md`](./SETUP.md) walks the agent through fork → configure → backfill → render → schedule → first push, with verification steps at each stage.

### 🧑 For humans

**Prerequisites:** Node (for the default `npx ccusage` collector) and [uv](https://docs.astral.sh/uv/) (`curl -LsSf https://astral.sh/uv/install.sh | sh` — no uv? plain `python3` ≥ 3.9 works too). An installed collector executable can replace the Node requirement; see below.

```bash
# 1. Fork this repo on GitHub (button top-right), then clone YOUR fork
git clone https://github.com/<your-username>/token-history && cd token-history
cp config.example.json config.json     # set "host" to a neutral alias like mac-a

# 2. Backfill, render, publish
uv sync                                # one-time: provisions the pinned Python + .venv
./scripts/run.sh collect --all         # grab everything ccusage still has
./scripts/run.sh render                # build every chart locally
git add -A && git commit -m "first snapshot" && git push

# 3. Keep it running (macOS)
./scripts/install-launchd.sh           # 00:30 / 12:00 / 21:00 + every login
```

Not on macOS, or prefer a different trigger? The collector is self-contained, idempotent, and backfills its own gaps — anything periodic works: cron, a systemd timer, or running it by hand. The scheduler is not load-bearing.

### Use an installed collector

To use an installed [turbotokens](https://github.com/maxmoneycash/turbotokens) binary, add this section to `config.json`:

```json
{
  "collector": {
    "executable": "/opt/homebrew/bin/turbotokens"
  }
}
```

Use the path printed by `command -v turbotokens` on your machine. An absolute path also works under launchd's minimal `PATH`. This setting accepts one executable, including paths containing spaces; it does not accept shell commands or extra arguments.

The collector still requests `claude daily` and `codex daily` separately, with the configured dates, timezone, and `--mode auto`. Other executables must accept these arguments and emit the same per-source JSON. Removing `collector` restores `npx -y ccusage@latest` (or your existing `ccusage.spec`). A failed custom executable stops collection.

Custom runs record `collector.name` and `collector.version` in day files and `_meta.json`, using only the executable's basename. Default runs retain `ccusageVersion`. These fields identify the collector used when the file was last updated; the existing rule that preserves larger historical counts still applies.

<details>
<summary><b>How uv is used here</b></summary>

This is a standard uv project: `pyproject.toml` declares the (empty — everything is stdlib) dependency set, `.python-version` pins the interpreter, and `uv.lock` is committed. `uv sync` materialises that into `.venv`, and `uv run` re-syncs automatically — so your terminal, the launchd job at 00:30, and CI all run the exact same Python instead of whatever `python3` happens to be ambient. `run.sh` is a thin wrapper over the same thing (it survives launchd's minimal `PATH`); `uv run scripts/render.py` works directly too. Without uv, `run.sh` falls back to plain `python3` (≥ 3.9) — zero dependencies makes that a real path, not a courtesy.

</details>

To show the charts elsewhere, reference the raw URLs:

```markdown
![tokens](https://raw.githubusercontent.com/<your-username>/token-history/master/charts/tokens.svg)
![cost](https://raw.githubusercontent.com/<your-username>/token-history/master/charts/cost.svg)
```

The URL is stable — no cache-busting query, no write access to your profile repo, nothing to maintain. The tradeoff is that GitHub's CDN may serve a slightly stale image for a few hours. With one data point per day that is invisible.

## Chart gallery

Every run renders **every** style below — the same data, over a dozen ways. This section is deliberately fully expanded: it doubles as a catalog to pick from and as a live test of how each SVG actually behaves inside GitHub's README renderer (light/dark via `prefers-color-scheme`, CSS load animations, font fallbacks). In practice you'd embed just one or two in your own profile README:

```markdown
![usage](https://raw.githubusercontent.com/<your-username>/token-history/master/charts/day/card.svg)
```

`charts/tokens.svg` and `charts/cost.svg` remain stable aliases of the daily bars, so existing embeds never break. Colors and type follow Anthropic's palette (orange = Claude Code, blue = Codex), tuned per mode to pass a color-vision-deficiency check.

### Badges

**`charts/badge/*.svg`** — live shields.io-style stats, rendered from the same data. Inline-sized: drop any of them on a single line of your profile README.

<img src="./charts/badge/tokens-today.svg" alt="tokens today"> <img src="./charts/badge/tokens-30d.svg" alt="tokens over the last 30 days"> <img src="./charts/badge/api-equiv-30d.svg" alt="API-equivalent value over the last 30 days"> <img src="./charts/badge/daily-avg.svg" alt="daily average tokens"> <img src="./charts/badge/split-30d.svg" alt="Claude versus Codex share"> <img src="./charts/badge/streak.svg" alt="active-day streak">

**`charts/badge/pixel-*.svg`** — the same stats as stair-cornered 8-bit arcade chips, every glyph pixel-drawn:

<img src="./charts/badge/pixel-tokens-30d.svg" alt="pixel badge: tokens over the last 30 days"> <img src="./charts/badge/pixel-api-30d.svg" alt="pixel badge: API-equivalent value"> <img src="./charts/badge/pixel-today.svg" alt="pixel badge: tokens today"> <img src="./charts/badge/pixel-avg.svg" alt="pixel badge: daily average"> <img src="./charts/badge/pixel-streak.svg" alt="pixel badge: active-day streak">

…and an 18px small variant of each (`badge/pixel-*-sm.svg`) that sits inline with regular shields badges:

<img src="./charts/badge/pixel-tokens-30d-sm.svg" alt="small pixel badge: tokens 30d"> <img src="./charts/badge/pixel-api-30d-sm.svg" alt="small pixel badge: API-equivalent"> <img src="./charts/badge/pixel-today-sm.svg" alt="small pixel badge: today"> <img src="./charts/badge/pixel-avg-sm.svg" alt="small pixel badge: daily average"> <img src="./charts/badge/pixel-streak-sm.svg" alt="small pixel badge: streak">

### Daily

**`charts/day/pixel-card.svg`** — the last 30 days as an 8-bit game HUD: a bitmap-font HI-SCORE, Claude vs Codex as player HP bars, cost as a coin counter, one pixel heart per active day

<img src="./charts/day/pixel-card.svg" width="880" alt="Pixel game-HUD stat card: HI-SCORE token total, P1/P2 HP bars for Claude and Codex, coin counter, heart streak">

**`charts/day/bar-tokens.svg`** — flat daily bars (also published as `charts/tokens.svg`, the stable legacy URL)

<img src="./charts/day/bar-tokens.svg" width="880" alt="Daily token usage, stacked by source">

**`charts/day/bar-cost.svg`** — the same bars in API-equivalent dollars (also published as `charts/cost.svg`)

<img src="./charts/day/bar-cost.svg" width="880" alt="Daily API-equivalent value, stacked by source">

**`charts/day/calendar-tokens.svg`** — contribution-style calendar heatmap

<img src="./charts/day/calendar-tokens.svg" alt="Daily token calendar: one cell per day, darker means more tokens">

**`charts/day/area-tokens.svg`** — smoothed stacked area with an animated reveal

<img src="./charts/day/area-tokens.svg" width="880" alt="Daily token flow: stacked area of Claude and Codex tokens">

**`charts/day/card.svg`** — hero-number stat card for the last 30 days

<img src="./charts/day/card.svg" width="880" alt="30-day stat card: total tokens, API-equivalent value, peak day, daily average, and the Claude/Codex split">

**`charts/day/pixel-tokens.svg`** — 8-bit pixel bars: every square is 10M tokens on a crisp retro grid, with a blinking cursor on the day still in progress

<img src="./charts/day/pixel-tokens.svg" width="880" alt="Pixel-art daily token bars: stacks of squares, one square per 10M tokens">

**`charts/day/pixel-models.svg`** — the same columns, split by model. Each source keeps its own hue and encodes the tier twice, in lightness *and* in how much of the square is filled — solid, notched, hollow — so the top tier reads even in greyscale (Claude fable › opus › sonnet, Codex 5.5/Sol › Terra › Luna)

<img src="./charts/day/pixel-models.svg" width="880" alt="Pixel-art daily token bars split by model: three orange steps for Claude and three blue steps for Codex, each tier also marked solid, notched or hollow">

**`charts/day/terminal-tokens.svg`** — the last 30 days as a terminal session: an htop-style bar per day, a CLI-style `TOTAL` sign-off, and a blinking cursor

<img src="./charts/day/terminal-tokens.svg" width="880" alt="Terminal-style chart: a shell window with one ASCII bar per day, stacked Claude/Codex block glyphs">

**`charts/day/sketch-tokens.svg`** — an xkcd-style hand-drawn take: two wobbly ink lines, hand-lettered labels, and a scribbled circle around the day the agents took over

<img src="./charts/day/sketch-tokens.svg" width="880" alt="Hand-drawn xkcd-style chart: wobbly Claude and Codex lines with a circled annotation on the peak day">

### Weekly

**`charts/week/bar-tokens.svg`** — weekly bars

<img src="./charts/week/bar-tokens.svg" width="880" alt="Weekly token usage, stacked by source">

**`charts/week/bar-cost.svg`** — weekly API-equivalent dollars

<img src="./charts/week/bar-cost.svg" width="880" alt="Weekly API-equivalent value, stacked by source">

**`charts/week/ledger-tokens.svg`** — editorial ledger, newest week on top

<img src="./charts/week/ledger-tokens.svg" width="880" alt="Weekly ledger: one row per week with a stacked horizontal bar and the total">

### Monthly

**`charts/month/bar-tokens.svg`** — monthly bars

<img src="./charts/month/bar-tokens.svg" width="880" alt="Monthly token usage, stacked by source">

**`charts/month/bar-cost.svg`** — monthly API-equivalent dollars

<img src="./charts/month/bar-cost.svg" width="880" alt="Monthly API-equivalent value, stacked by source">

**`charts/month/calendar-tokens.svg`** — a calendar page for the current month

<img src="./charts/month/calendar-tokens.svg" width="880" alt="Calendar page for the current month, each day shaded and labelled by its token total">

## How multi-host works

Each machine reads **only its own local logs** and writes to its own directory:

```
data/mac-a/2026-08-04.json     ← machine A only ever writes here
data/mac-b/2026-08-04.json     ← machine B only ever writes here
```

Two machines never write the same path, so there is no merge conflict to resolve and no cross-machine deduplication to get wrong. Merging is just addition at render time.

> [!IMPORTANT]
> This relies on the machines' log directories being **disjoint**. Do not sync `~/.claude` or `~/.codex` between machines via iCloud, Dropbox, Syncthing, or a restored backup — both machines would then see the same sessions and the totals would double. Because ccusage reports daily aggregates rather than session IDs, this repo cannot detect that from the data.

## How it stays correct

- **Idempotent.** Re-running for a day overwrites that day. Safe to trigger as often as you like.
- **Self-healing.** Every run re-collects a recall window (`clamp(days since last success + 2, 3, 21)`), so a laptop that was off for a week backfills itself on the next run.
- **Non-destructive for old days.** Beyond 7 days, values may only *grow*. If Claude Code has already cleaned up part of a day, a fresh read returns a smaller number — overwriting would silently corrupt a correct record. A missing day is visible; a shrunken one is not.
- **Version-stamped.** Every file records the ccusage version that produced it. ccusage v15 under-reported output tokens by ~38% relative to v20; if a future upstream change moves the numbers again, the step in the series will be traceable instead of mysterious.
- **No empty commits.** Nothing is committed when nothing changed. Costs are rounded on write, so float noise (~1e-13) doesn't manufacture a diff.
- **Honestly labeled.** The dollar figures are API-equivalent value at published rates — what the usage would be worth, not money spent on a subscription plan.
- **Nothing identifying recorded.** No project names, paths, branches, prompts, or real hostnames — only per-day token counts and model names, under an alias you choose. `config.json` is gitignored so the alias-to-machine mapping stays local.

## Layout

```
config.example.json          copy to config.json, set your host alias
pyproject.toml, uv.lock      uv project: zero dependencies, locked anyway
.python-version              interpreter pin (3.12, provisioned by uv)
scripts/
  run.sh                     entry point: uv if present, python3 otherwise
  collect.py                 ccusage → data/<host>/<date>.json
  render.py                  data/ → charts (every style) + SUMMARY.md
  install-launchd.sh         macOS scheduling (--uninstall to remove)
data/<host>/<date>.json      one file per host per day
charts/tokens.svg, cost.svg  the two headline charts (stable URLs)
charts/{day,week,month}/     the style gallery, all regenerated by CI on every data push
contexts/                    design decisions and the research behind them
```

`.github/workflows/render.yml` re-renders on every push that touches `data/`. Push-triggered rather than scheduled: GitHub's docs acknowledge that scheduled workflows can be delayed, dropped under load, and auto-disabled after 60 days of inactivity. None of that applies to a push trigger, and the charts update the moment data lands.

## Design notes

Everything non-obvious in here has a written reason — measured on real data, not assumed. See [`contexts/`](./contexts):

- [`decisions.md`](./contexts/decisions.md) — what was chosen and why
- [`data-sources.md`](./contexts/data-sources.md) — schemas, dedup, retention, the ccusage version story
- [`pipeline-and-scheduling.md`](./contexts/pipeline-and-scheduling.md) — layout, idempotency, git, launchd, chart constraints

## Thanks

All parsing credit goes to [**ccusage**](https://github.com/ccusage/ccusage) — the de-facto standard for reading local AI-CLI usage logs, supporting ~15 coding CLIs. This repo deliberately does not second-guess it; it adds the persistence, merging, and charts on top.

**Contributions welcome** — new data sources and new chart styles alike. A style is a single drop-in module in [`scripts/styles/`](./scripts/styles) exposing `build_all(days, generated)`; see the existing ones for the contract.

Collector tests use only the Python standard library:

```sh
python3 -m unittest discover -s tests -v
TOKEN_HISTORY_TEST_TURBOTOKENS=/absolute/path/turbotokens python3 -m unittest discover -s tests -v
```

The second command also checks synthetic Claude and Codex logs against the installed binary, with isolated data, offline pricing, date filters, and timezone grouping. Set `TOKEN_HISTORY_TEST_CCUSAGE` to an installed ccusage executable as well to compare both collectors' normalized records. Tests do not read your usage history or publish data.

## License

MIT
