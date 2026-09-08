#!/usr/bin/env python3
"""Collect local AI coding CLI token usage and persist it to this repo.

Why this exists: Claude Code deletes session transcripts older than
`cleanupPeriodDays` (default 30). ccusage reads those transcripts, so once they
are gone the numbers are gone too. This script snapshots ccusage's output into
git before that happens.

Design notes:
  - The configured collector is the source of truth (ccusage by default).
    We never parse the raw JSONL ourselves.
  - Idempotent: re-running for the same day overwrites that day's file.
  - Self-healing: each run re-collects a recall window, so a missed run (laptop
    was off) is backfilled automatically. No scheduler catch-up needed.
  - Non-destructive for old days: beyond `final_after_days`, values may only
    grow. A shrunken re-read (because transcripts were cleaned up) must never
    overwrite a correct larger value already on record.

Targets Python 3.9 (macOS system python3). Standard library only.
"""

import argparse
import datetime as dt
import json
import os
import shutil
import subprocess
import sys
import time

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DATA_DIR = os.path.join(REPO_ROOT, "data")
COST_DP = 6  # round costs on write; float sum order is not stable (~1e-13 noise)


# --------------------------------------------------------------------------- io


def log(msg):
    print("[{}] {}".format(dt.datetime.now().strftime("%H:%M:%S"), msg), flush=True)


def die(msg, code=1):
    print("ERROR: {}".format(msg), file=sys.stderr, flush=True)
    sys.exit(code)


def load_config(path):
    if not os.path.exists(path):
        die("config not found: {}\nCopy config.example.json to config.json and edit it.".format(path))
    with open(path, "r", encoding="utf-8") as fh:
        cfg = json.load(fh)
    for key in ("host", "timezone", "sources"):
        if not cfg.get(key):
            die("config is missing required key: {}".format(key))
    if "/" in cfg["host"] or cfg["host"].startswith("."):
        die("host must be a plain directory-safe alias, got: {!r}".format(cfg["host"]))
    return cfg


def read_json(path, default=None):
    if not os.path.exists(path):
        return default
    try:
        with open(path, "r", encoding="utf-8") as fh:
            return json.load(fh)
    except (ValueError, OSError):
        return default


def write_json(path, obj):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    tmp = path + ".tmp"
    with open(tmp, "w", encoding="utf-8") as fh:
        json.dump(obj, fh, indent=2, sort_keys=True, ensure_ascii=False)
        fh.write("\n")
    os.replace(tmp, path)


# ------------------------------------------------------------------------ dates


def today_in(tz_name):
    """Today's calendar date in the configured timezone.

    Uses `zoneinfo` when available (py3.9+ with tzdata), else shells out to
    `date` with TZ set, which is always correct on macOS/Linux.
    """
    try:
        from zoneinfo import ZoneInfo

        return dt.datetime.now(ZoneInfo(tz_name)).date()
    except Exception:
        env = dict(os.environ, TZ=tz_name)
        out = subprocess.check_output(["date", "+%Y-%m-%d"], env=env).decode().strip()
        return dt.date.fromisoformat(out)


def daterange(start, end):
    day = start
    while day <= end:
        yield day
        day += dt.timedelta(days=1)


# -------------------------------------------------------------------- collector


def resolve_collector(cfg):
    """Resolve one executable, or retain the existing npx ccusage invocation."""
    collector = cfg.get("collector", {})
    if not isinstance(collector, dict):
        die("collector must be an object containing an executable name or path")
    executable = collector.get("executable")
    if executable is not None:
        if not isinstance(executable, str) or not executable.strip():
            die("collector.executable must be a non-empty executable name or path")
        path = shutil.which(executable)
        if not path:
            die("collector executable not found: {}. Install it or set an absolute path.".format(executable))
        return [path], os.path.basename(executable)

    npx = shutil.which("npx")
    if not npx:
        die("npx not found on PATH. Under launchd, PATH is minimal — set "
            "EnvironmentVariables.PATH in the plist to include your node bin dir.")
    spec = (cfg.get("ccusage") or {}).get("spec", "ccusage@latest")
    return [npx, "-y", spec], "ccusage"


def run_collector(command, args, timeout=300):
    cmd = command + args
    proc = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, timeout=timeout)
    if proc.returncode != 0:
        die("{} failed ({}): {}\n{}".format(
            os.path.basename(command[0]), proc.returncode, " ".join(args),
            proc.stderr.decode(errors="replace")[:2000]))
    return proc.stdout.decode(errors="replace")


def collector_version(command):
    """Recorded in every data file so a future discontinuity in the series can
    be traced to an upstream change (v15 -> v20 shifted output tokens by ~38%)."""
    lines = run_collector(command, ["--version"], timeout=180).strip().splitlines()
    line = lines[-1].strip() if lines else ""
    return line.split()[-1] if line else "unknown"


def fetch_source(command, source, since, until, tz_name):
    """Return {date: raw ccusage daily record} for one source."""
    raw = run_collector(command, [
        source, "daily", "--json",
        "--since", since.strftime("%Y%m%d"),
        "--until", until.strftime("%Y%m%d"),
        "--timezone", tz_name,
        "--mode", "auto",
    ])
    try:
        payload = json.loads(raw)
    except ValueError:
        die("collector {} returned non-JSON output".format(source))
    if not isinstance(payload, dict) or not isinstance(payload.get("daily"), list):
        die("collector {} JSON is missing the daily array".format(source))
    rows = payload["daily"]
    if any(not isinstance(r, dict) or not isinstance(r.get("date"), str) for r in rows):
        die("collector {} daily rows must use the per-source date field".format(source))
    return {r["date"]: r for r in rows}


# -------------------------------------------------------------------- normalize


def _num(value):
    return value if isinstance(value, (int, float)) else 0


def _round_cost(value):
    return round(float(value), COST_DP)


def normalize_claude(rec):
    """ccusage `claude daily` record -> our schema.

    Claude gives per-model cost but no per-model total; we derive the total.
    """
    models = {}
    for m in rec.get("modelBreakdowns") or []:
        name = m.get("modelName")
        if not name:
            continue
        entry = {
            "input": _num(m.get("inputTokens")),
            "output": _num(m.get("outputTokens")),
            "cacheCreation": _num(m.get("cacheCreationTokens")),
            "cacheRead": _num(m.get("cacheReadTokens")),
            "costUSD": _round_cost(_num(m.get("cost"))),
        }
        entry["total"] = entry["input"] + entry["output"] + entry["cacheCreation"] + entry["cacheRead"]
        models[name] = entry
    return {
        "input": _num(rec.get("inputTokens")),
        "output": _num(rec.get("outputTokens")),
        "cacheCreation": _num(rec.get("cacheCreationTokens")),
        "cacheRead": _num(rec.get("cacheReadTokens")),
        "total": _num(rec.get("totalTokens")),
        "costUSD": _round_cost(_num(rec.get("totalCost"))),
        "models": models,
    }


def normalize_codex(rec):
    """ccusage `codex daily` record -> our schema.

    Codex differs from Claude: `models` is a dict, cost lives under `costUSD`,
    there is a `reasoningOutputTokens` field, and per-model cost is NOT provided
    (so model entries carry no costUSD).
    """
    models = {}
    for name, m in (rec.get("models") or {}).items():
        entry = {
            "input": _num(m.get("inputTokens")),
            "output": _num(m.get("outputTokens")),
            "cacheCreation": _num(m.get("cacheCreationTokens")),
            "cacheRead": _num(m.get("cacheReadTokens")),
            "total": _num(m.get("totalTokens")),
        }
        if m.get("reasoningOutputTokens") is not None:
            entry["reasoningOutput"] = _num(m.get("reasoningOutputTokens"))
        if m.get("isFallback"):
            # ccusage could not identify the model and guessed. Keep the flag so
            # a weird-looking model name in the chart is explainable later.
            entry["modelNameIsFallback"] = True
        models[name] = entry
    out = {
        "input": _num(rec.get("inputTokens")),
        "output": _num(rec.get("outputTokens")),
        "cacheCreation": _num(rec.get("cacheCreationTokens")),
        "cacheRead": _num(rec.get("cacheReadTokens")),
        "total": _num(rec.get("totalTokens")),
        "costUSD": _round_cost(_num(rec.get("costUSD"))),
        "models": models,
    }
    if rec.get("reasoningOutputTokens") is not None:
        out["reasoningOutput"] = _num(rec.get("reasoningOutputTokens"))
    return out


NORMALIZERS = {"claude": normalize_claude, "codex": normalize_codex}


# ------------------------------------------------------------------------ merge


def merge_max(old, new):
    """Recursively keep the larger value for every numeric leaf.

    Used for days older than `final_after_days`. Rationale: once Claude Code has
    cleaned up part of a day's transcripts, a fresh read produces a SMALLER
    number. Overwriting would silently corrupt a correct record — and unlike a
    missing day, a shrunken day is invisible. So old days may only grow.
    """
    if isinstance(old, dict) and isinstance(new, dict):
        merged = dict(old)
        for key, value in new.items():
            merged[key] = merge_max(old[key], value) if key in old else value
        return merged
    if isinstance(old, (int, float)) and isinstance(new, (int, float)):
        return max(old, new)
    return new if new is not None else old


# -------------------------------------------------------------------------- git


def git(args, check=True):
    proc = subprocess.run(["git", "-C", REPO_ROOT] + args,
                          stdout=subprocess.PIPE, stderr=subprocess.STDOUT)
    if check and proc.returncode != 0:
        die("git {} failed:\n{}".format(" ".join(args), proc.stdout.decode(errors="replace")))
    return proc.returncode, proc.stdout.decode(errors="replace")


def git_sync(cfg, message):
    gcfg = cfg.get("git") or {}
    if not gcfg.get("enabled", True):
        log("git disabled in config, skipping commit/push")
        return
    if not os.path.isdir(os.path.join(REPO_ROOT, ".git")):
        log("not a git repo yet, skipping commit/push")
        return

    git(["add", "-A", "data"])
    rc, _ = git(["diff", "--cached", "--quiet"], check=False)
    if rc == 0:
        log("no data changes, nothing to commit")
        return
    git(["commit", "-m", message])
    log("committed: {}".format(message))

    remote = gcfg.get("remote", "origin")
    branch = gcfg.get("branch", "main")
    rc, _ = git(["remote", "get-url", remote], check=False)
    if rc != 0:
        log("remote {!r} not configured, commit stays local".format(remote))
        return

    retries = int(gcfg.get("push_retries", 5))
    for attempt in range(1, retries + 1):
        git(["pull", "--rebase", remote, branch], check=False)
        rc, out = git(["push", remote, "HEAD:" + branch], check=False)
        if rc == 0:
            log("pushed to {}/{}".format(remote, branch))
            return
        wait = 2 ** attempt
        log("push failed (attempt {}/{}), retrying in {}s".format(attempt, retries, wait))
        if attempt < retries:
            time.sleep(wait)
    # Not fatal: the local commit IS the queue. The next run rebases and
    # re-pushes everything that is ahead of origin.
    log("WARNING: push failed after {} attempts; {} commit(s) queued locally".format(
        retries, git(["rev-list", "--count", "@{u}..HEAD"], check=False)[1].strip() or "?"))


# -------------------------------------------------------------------------- run


def decide_window(cfg, meta, today, args):
    if args.since:
        start = dt.date.fromisoformat(args.since)
        return start, (dt.date.fromisoformat(args.until) if args.until else today)

    rc = cfg.get("recall") or {}
    min_days = int(rc.get("min_days", 3))
    max_days = int(rc.get("max_days", 21))
    slack = int(rc.get("slack_days", 2))

    last_run = (meta or {}).get("last_success_date")
    if not last_run:
        # First run on this host: take everything ccusage still has.
        return None, today

    gap = (today - dt.date.fromisoformat(last_run)).days
    span = max(min_days, min(max_days, gap + slack))
    return today - dt.timedelta(days=span - 1), today


def main():
    ap = argparse.ArgumentParser(description="Snapshot coding-agent usage into this repo.")
    ap.add_argument("--config", default=os.path.join(REPO_ROOT, "config.json"))
    ap.add_argument("--since", help="YYYY-MM-DD, overrides the recall window")
    ap.add_argument("--until", help="YYYY-MM-DD, defaults to today")
    ap.add_argument("--all", action="store_true", help="collect everything ccusage still has")
    ap.add_argument("--dry-run", action="store_true", help="do not write files or touch git")
    ap.add_argument("--no-git", action="store_true", help="write files but skip commit/push")
    args = ap.parse_args()

    cfg = load_config(args.config)
    host = cfg["host"]
    tz_name = cfg["timezone"]
    command, collector_name = resolve_collector(cfg)
    final_after = int((cfg.get("recall") or {}).get("final_after_days", 7))

    today = today_in(tz_name)
    host_dir = os.path.join(DATA_DIR, host)
    meta_path = os.path.join(host_dir, "_meta.json")
    meta = read_json(meta_path, default={}) or {}

    if args.all:
        start, end = None, today
    else:
        start, end = decide_window(cfg, meta, today, args)

    version = collector_version(command)
    # Keep the existing schema for default runs. Custom collectors publish only
    # the executable's basename, never a potentially identifying local path.
    provenance = ({"collector": {"name": collector_name, "version": version}}
                  if (cfg.get("collector") or {}).get("executable") is not None
                  else {"ccusageVersion": version})
    log("{} {} | host={} | tz={} | window={}..{}".format(
        collector_name, version, host, tz_name, start.isoformat() if start else "(all)", end.isoformat()))

    # A very early sentinel means "whatever ccusage still knows about".
    fetch_start = start or dt.date(2000, 1, 1)

    per_source = {}
    for source in cfg["sources"]:
        if source not in NORMALIZERS:
            die("unsupported source {!r} (known: {})".format(source, ", ".join(sorted(NORMALIZERS))))
        rows = fetch_source(command, source, fetch_start, end, tz_name)
        per_source[source] = rows
        log("  {}: {} day(s) returned".format(source, len(rows)))

    all_dates = sorted({d for rows in per_source.values() for d in rows})
    if start is not None:
        all_dates = [d for d in all_dates if start.isoformat() <= d <= end.isoformat()]
    if not all_dates:
        log("no usage data in window, nothing to do")
        return

    now_iso = dt.datetime.now(dt.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    written = skipped = 0

    for date_str in all_dates:
        sources = {}
        for source, rows in per_source.items():
            if date_str in rows:
                sources[source] = NORMALIZERS[source](rows[date_str])
        if not sources:
            continue

        day = dt.date.fromisoformat(date_str)
        record = {
            "date": date_str,
            "host": host,
            "timezone": tz_name,
            "status": "partial" if day == today else "final",
            "collectedAt": now_iso,
            **provenance,
            "sources": sources,
        }

        path = os.path.join(host_dir, date_str + ".json")
        existing = read_json(path)
        if existing and (today - day).days > final_after:
            # Old day: values may only grow. Metadata still refreshes.
            merged_sources = merge_max(existing.get("sources") or {}, sources)
            if merged_sources == (existing.get("sources") or {}):
                skipped += 1
                continue
            record["sources"] = merged_sources
            record["status"] = existing.get("status", "final")

        if args.dry_run:
            log("  would write {}".format(os.path.relpath(path, REPO_ROOT)))
        else:
            write_json(path, record)
        written += 1

    log("{} day(s) written, {} unchanged old day(s) skipped".format(written, skipped))

    if args.dry_run:
        log("dry run, not updating _meta.json or git")
        return

    # Switching collectors must not leave the previous collector's identity on
    # the metadata for this successful read. Historical day files keep theirs.
    meta.pop("ccusageVersion", None)
    meta.pop("collector", None)
    meta.update({
        "host": host,
        "timezone": tz_name,
        "last_success_date": today.isoformat(),
        "last_success_at": now_iso,
        **provenance,
        "earliest_date": min([meta["earliest_date"]] + all_dates) if meta.get("earliest_date") else all_dates[0],
        "latest_date": max([meta.get("latest_date", "")] + all_dates),
    })
    write_json(meta_path, meta)

    if not args.no_git:
        git_sync(cfg, "data({}): {} .. {}".format(host, all_dates[0], all_dates[-1]))


if __name__ == "__main__":
    main()
