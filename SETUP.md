# SETUP.md — agent setup guide

You are a coding agent setting up **token-history** for your user: a repo that
snapshots their local AI-coding token usage (Claude Code, Codex, Gemini) into git every
day and renders it into SVG charts for a GitHub profile README. Follow the steps
in order; each has a verification. Ask the user only where marked **ASK**.

## 0. Prerequisites

Check, and install what's missing (with the user's consent):

```bash
node --version          # needed for `npx ccusage`
uv --version            # preferred runner; optional — python3 >= 3.9 also works
git --version
gh auth status          # optional but makes forking easier
```

## 1. Fork and clone

The user needs their **own fork** — this repo holds someone else's data, so
cloning it directly leaves nowhere to push.

With `gh` (preferred):

```bash
gh repo fork keli-wen/token-history --clone --default-branch-only
cd token-history
```

Without `gh`: have the user fork `https://github.com/keli-wen/token-history` in
the browser, then `git clone git@github.com:<their-username>/token-history.git`.

**Verify:** `git remote -v` shows the user's fork as `origin` (pushable).

## 2. Configure

```bash
cp config.example.json config.json
```

Edit `config.json` and set `"host"` to a **neutral alias** like `mac-a`.
**ASK** the user which alias they want if they run multiple machines.

Privacy rules (the repo is typically public):
- The alias must NOT be the real hostname. `config.json` is gitignored — keep it so.
- Never sync `~/.claude`, `~/.codex`, or `~/.gemini` between machines (iCloud/Dropbox/Syncthing);
  each machine must read only its own logs or totals will double-count.

**Verify:** `git check-ignore config.json` prints the path.

## 3. Backfill and render

```bash
uv sync                        # skip if no uv; run.sh falls back to python3
./scripts/run.sh collect --all # pulls everything ccusage can still see locally
./scripts/run.sh render        # writes charts/*.svg + SUMMARY.md
```

Notes:
- Data lands in `data/<alias>/<date>.json`, one file per day. Local coding-CLI
  logs expire (Claude Code: ~30 days), so backfilling on day one preserves the
  maximum history — do not defer this step.
- The collector is idempotent; re-running is always safe.

**Verify:** `ls data/*/ | head` shows dated JSON files; `ls charts/day/` shows
SVGs; open one chart and confirm it renders.

## 4. First push

```bash
git add -A
git commit -m "first snapshot"
git push
```

GitHub Actions (`.github/workflows/render.yml`) re-renders charts automatically
on every future data push — no further setup.

**Verify:** the fork's Actions tab shows a green "Render charts" run, and the
fork's README displays charts with the user's data (CDN may lag a few minutes).

## 5. Schedule

macOS:

```bash
./scripts/install-launchd.sh   # 00:30 / 12:00 / 21:00 + on every login
```

Linux/other: install any periodic trigger for
`<repo>/scripts/run.sh collect && git -C <repo> push` — e.g. a cron line every
8 hours. Exact timing is not load-bearing: the collector backfills its own gaps.

**Verify (macOS):** `launchctl print gui/$(id -u)/com.token-history.collect`
shows the job loaded.

## 6. Embed the charts

Offer the user the [gallery](./README.md#chart-gallery) and embed their pick(s)
in their profile README (or anywhere) by raw URL:

```markdown
![usage](https://raw.githubusercontent.com/<their-username>/token-history/master/charts/day/pixel-tokens.svg)
![badge](https://raw.githubusercontent.com/<their-username>/token-history/master/charts/badge/pixel-tokens-30d-sm.svg)
```

Every style under `charts/` regenerates on each push; the URLs never change.

## Done — report back

Tell the user: how many days were backfilled, which machines/aliases are
configured, that the schedule is installed, and which chart URLs are ready to
embed.
