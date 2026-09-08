"""Optional contract check against an already-installed turbotokens binary.

TOKEN_HISTORY_TEST_TURBOTOKENS=/absolute/path/turbotokens python3 -m unittest discover -s tests -v
The fixtures and every write stay inside a temporary directory.
"""

import contextlib
import datetime as dt
import io
import json
import os
from pathlib import Path
import subprocess
import tempfile
import unittest
from unittest import mock

from test_collect import collect

BINARY = os.environ.get("TOKEN_HISTORY_TEST_TURBOTOKENS")
CCUSAGE_BINARY = os.environ.get("TOKEN_HISTORY_TEST_CCUSAGE")


@unittest.skipUnless(BINARY, "set TOKEN_HISTORY_TEST_TURBOTOKENS to run the installed-binary contract")
class TurbotokensContractTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        self.binary = str(Path(BINARY).resolve())
        claude_home = self.root / "home/.claude"
        codex_home = self.root / "home/.codex"
        claude_log = claude_home / "projects/synthetic/session.jsonl"
        codex_log = codex_home / "sessions/2026/09/01/rollout-synthetic.jsonl"
        claude_log.parent.mkdir(parents=True)
        codex_log.parent.mkdir(parents=True)
        stamps = ["2026-09-01T23:30:00.000Z", "2026-09-02T00:30:00.000Z"]
        claude_rows = [{
            "timestamp": stamp, "type": "assistant", "sessionId": "synthetic-claude",
            "requestId": "req-" + str(i), "costUSD": 0.125 * i,
            "message": {"id": "msg-" + str(i), "model": "claude-sonnet-4-20250514",
                "role": "assistant", "usage": {"input_tokens": 100 * i, "output_tokens": 20 * i,
                    "cache_creation_input_tokens": 30 * i, "cache_read_input_tokens": 40 * i}}
        } for i, stamp in enumerate(stamps, 1)]
        codex_rows = [
            {"timestamp": "2026-09-01T23:00:00.000Z", "type": "session_meta",
             "payload": {"id": "synthetic-codex", "cwd": "/synthetic/project"}},
            {"timestamp": "2026-09-01T23:00:01.000Z", "type": "turn_context", "payload": {"model": "gpt-5"}},
        ]
        for stamp, counts in zip(stamps, [(200, 60, 50, 10, 250), (300, 80, 80, 15, 380)]):
            codex_rows.append({"timestamp": stamp, "type": "event_msg", "payload": {
                "type": "token_count", "info": {"total_token_usage": dict(zip(
                    ["input_tokens", "cached_input_tokens", "output_tokens", "reasoning_output_tokens", "total_tokens"],
                    counts))}}})
        for path, rows in [(claude_log, claude_rows), (codex_log, codex_rows)]:
            path.write_text("".join(json.dumps(row, separators=(",", ":")) + "\n" for row in rows))
        # Isolate config and make pricing deterministic without network access.
        pricing_config = json.dumps({"defaults": {
            "offline": True, "pricingOverrides": {"gpt-5": {
                "inputCostPerToken": 0.00000125, "outputCostPerToken": 0.00001,
                "cacheReadInputTokenCost": 0.000000125}}}})
        for name in ("turbotokens.json", "ccusage.json"):
            (claude_home / name).write_text(pricing_config)
        env = {"HOME": str(self.root / "home"), "PATH": os.defpath, "TZ": "UTC",
               "XDG_CONFIG_HOME": str(self.root / "home/.config"),
               "XDG_CACHE_HOME": str(self.root / "home/.cache"),
               "CLAUDE_CONFIG_DIR": str(claude_home), "CODEX_HOME": str(codex_home)}
        real_run = subprocess.run
        patcher = mock.patch.object(collect.subprocess, "run", side_effect=lambda *args, **kwargs:
                                    real_run(*args, cwd=str(self.root), env=env, **kwargs))
        patcher.start()
        self.addCleanup(patcher.stop)

    def fetch(self, source, timezone="UTC", end=2):
        rows = collect.fetch_source([self.binary], source, dt.date(2026, 9, 1),
                                    dt.date(2026, 9, end), timezone)
        return {date: collect.NORMALIZERS[source](row) for date, row in rows.items()}

    def test_claude_counts_models_costs_and_inclusive_dates(self):
        rows = self.fetch("claude")
        self.assertEqual(sorted(rows), ["2026-09-01", "2026-09-02"])
        for i, date in enumerate(sorted(rows), 1):
            counts = {"input": 100 * i, "output": 20 * i, "cacheCreation": 30 * i,
                      "cacheRead": 40 * i, "total": 190 * i, "costUSD": 0.125 * i}
            self.assertEqual(rows[date], dict(counts, models={"claude-sonnet-4-20250514": counts}))
        self.assertEqual(self.fetch("claude", end=1), {"2026-09-01": rows["2026-09-01"]})

    def test_codex_cumulative_deltas_cached_input_and_reasoning(self):
        rows = self.fetch("codex")
        self.assertEqual(sorted(rows), ["2026-09-01", "2026-09-02"])
        for date, values, cost in [("2026-09-01", (140, 50, 60, 10, 250), 0.000683),
                                  ("2026-09-02", (80, 30, 20, 5, 130), 0.000403)]:
            counts = dict(zip(["input", "output", "cacheRead", "reasoningOutput", "total"], values))
            counts["cacheCreation"] = 0
            self.assertEqual(rows[date], dict(counts, costUSD=cost, models={"gpt-5": counts}))
        self.assertEqual(self.fetch("codex", end=1), {"2026-09-01": rows["2026-09-01"]})

    def test_timezone_combines_the_same_two_events_without_losing_tokens(self):
        for source, total in [("claude", 570), ("codex", 380)]:
            with self.subTest(source=source):
                rows = self.fetch(source, "America/Los_Angeles", end=1)
                self.assertEqual(list(rows), ["2026-09-01"])
                self.assertEqual(rows["2026-09-01"]["total"], total)

    @unittest.skipUnless(CCUSAGE_BINARY, "set TOKEN_HISTORY_TEST_CCUSAGE to compare installed collectors")
    def test_normalized_daily_records_match_ccusage(self):
        for source in ("claude", "codex"):
            for timezone in ("UTC", "America/Los_Angeles"):
                for end in (1, 2):
                    with self.subTest(source=source, timezone=timezone, end=end):
                        rows = collect.fetch_source([str(Path(CCUSAGE_BINARY).resolve())], source,
                                                    dt.date(2026, 9, 1), dt.date(2026, 9, end), timezone)
                        expected = {date: collect.NORMALIZERS[source](row) for date, row in rows.items()}
                        self.assertEqual(self.fetch(source, timezone, end), expected)

    def test_full_collection_records_real_binary_identity(self):
        config = self.root / "config.json"
        config.write_text(json.dumps({"host": "synthetic", "timezone": "UTC", "sources": ["claude", "codex"],
                                      "collector": {"executable": self.binary}}))
        argv = ["collect.py", "--config", str(config), "--since", "2026-09-01", "--until", "2026-09-02", "--no-git"]
        with mock.patch.object(collect, "DATA_DIR", str(self.root / "data")), \
             mock.patch.object(collect.sys, "argv", argv), contextlib.redirect_stdout(io.StringIO()):
            collect.main()
        for filename in ["2026-09-01.json", "2026-09-02.json", "_meta.json"]:
            record = json.loads((self.root / "data/synthetic" / filename).read_text())
            self.assertEqual(record["collector"]["name"], "turbotokens")
            self.assertEqual(record["collector"]["version"], collect.collector_version([self.binary]))
            self.assertNotIn("ccusageVersion", record)
            self.assertNotIn(str(self.root), json.dumps(record))


if __name__ == "__main__":
    unittest.main()
