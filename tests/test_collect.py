"""Collector selection and snapshot contracts; no packages or user logs needed."""

import contextlib
import datetime as dt
import importlib.util
import io
import json
from pathlib import Path
import subprocess
import tempfile
import unittest
from unittest import mock

SPEC = importlib.util.spec_from_file_location(
    "collect", Path(__file__).resolve().parents[1] / "scripts" / "collect.py")
collect = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(collect)


class CollectorTests(unittest.TestCase):
    def test_default_keeps_npx_and_configured_ccusage_spec(self):
        with mock.patch.object(collect.shutil, "which", return_value="/node/npx"):
            self.assertEqual(collect.resolve_collector({}),
                             (["/node/npx", "-y", "ccusage@latest"], "ccusage"))
            self.assertEqual(collect.resolve_collector({"ccusage": {"spec": "ccusage@20.0.20"}}),
                             (["/node/npx", "-y", "ccusage@20.0.20"], "ccusage"))

    def test_custom_executable_does_not_require_npx_or_split_its_path(self):
        path = "/tools with spaces/turbotokens"
        with mock.patch.object(collect.shutil, "which", return_value=path) as which:
            self.assertEqual(collect.resolve_collector({"collector": {"executable": path}}),
                             ([path], "turbotokens"))
        which.assert_called_once_with(path)

    def test_invalid_or_missing_executable_is_reported_before_collection(self):
        for executable in ("", 7, ["turbotokens", "daily"]):
            with self.subTest(executable=executable), contextlib.redirect_stderr(io.StringIO()):
                with self.assertRaises(SystemExit):
                    collect.resolve_collector({"collector": {"executable": executable}})
        with mock.patch.object(collect.shutil, "which", return_value=None):
            with contextlib.redirect_stderr(io.StringIO()) as stderr, self.assertRaises(SystemExit):
                collect.resolve_collector({"collector": {"executable": "missing-tool"}})
        self.assertIn("missing-tool", stderr.getvalue())

    def test_collector_section_requires_an_object(self):
        for value in (False, 0, [], None, "turbotokens"):
            with self.subTest(value=value), contextlib.redirect_stderr(io.StringIO()) as stderr:
                with self.assertRaises(SystemExit):
                    collect.resolve_collector({"collector": value})
            self.assertIn("collector must be an object", stderr.getvalue())

    def test_run_uses_argument_array_and_preserves_timeout(self):
        command = ["/tools with spaces/turbotokens"]
        args = ["claude", "daily", "--json"]
        with mock.patch.object(collect.subprocess, "run", return_value=
                               subprocess.CompletedProcess([], 0, b'{"daily": []}', b"")) as run:
            self.assertEqual(collect.run_collector(command, args), '{"daily": []}')
        run.assert_called_once_with(command + args, stdout=subprocess.PIPE,
                                    stderr=subprocess.PIPE, timeout=300)
        self.assertEqual(command, ["/tools with spaces/turbotokens"])

    def test_failure_does_not_fall_back_to_another_collector(self):
        with mock.patch.object(collect.subprocess, "run", return_value=
                               subprocess.CompletedProcess([], 3, b"", b"bad input")) as run:
            with contextlib.redirect_stderr(io.StringIO()) as stderr, self.assertRaises(SystemExit):
                collect.run_collector(["/bin/turbotokens"], ["claude", "daily"])
        self.assertEqual(run.call_count, 1)
        self.assertIn("turbotokens failed (3)", stderr.getvalue())
        self.assertIn("bad input", stderr.getvalue())

    def test_version_accepts_both_banners_and_empty_output(self):
        for output, expected in [("ccusage 20.0.20\n", "20.0.20"),
                                 ("turbotokens 1.1.2\n", "1.1.2"), ("", "unknown")]:
            with self.subTest(output=output), mock.patch.object(collect, "run_collector", return_value=output):
                self.assertEqual(collect.collector_version(["tool"]), expected)

    def test_focused_source_dates_timezone_and_cost_mode_are_preserved(self):
        command = ["turbotokens"]
        row = {"date": "2026-09-01", "totalTokens": 42}
        for source in ("claude", "codex"):
            with self.subTest(source=source), mock.patch.object(collect, "run_collector",
                    return_value=json.dumps({"daily": [row]})) as run:
                actual = collect.fetch_source(command, source, dt.date(2026, 9, 1),
                                              dt.date(2026, 9, 2), "America/Los_Angeles")
                self.assertEqual(actual, {"2026-09-01": row})
                run.assert_called_once_with(command, [source, "daily", "--json", "--since", "20260901",
                    "--until", "20260902", "--timezone", "America/Los_Angeles", "--mode", "auto"])

    def test_wrong_json_dialect_fails_instead_of_silently_returning_no_days(self):
        for payload in ["not JSON", "[]", '{}', '{"daily": {}}', '{"daily": [{"period": "2026-09-01"}]}']:
            with self.subTest(payload=payload), mock.patch.object(collect, "run_collector", return_value=payload):
                with contextlib.redirect_stderr(io.StringIO()), self.assertRaises(SystemExit):
                    collect.fetch_source(["tool"], "claude", dt.date(2026, 9, 1), dt.date(2026, 9, 1), "UTC")

    def test_empty_daily_report_is_valid(self):
        with mock.patch.object(collect, "run_collector", return_value='{"daily": []}'):
            self.assertEqual(collect.fetch_source(["tool"], "claude", dt.date(2026, 9, 1),
                                                 dt.date(2026, 9, 1), "UTC"), {})


class SnapshotTests(unittest.TestCase):
    def run_collection(self, root, custom=False, dry_run=False):
        cfg = {"host": "test-host", "timezone": "UTC", "sources": ["claude", "codex"]}
        if custom:
            cfg["collector"] = {"executable": "/private/local/path/turbotokens"}
        config = root / "config.json"
        config.write_text(json.dumps(cfg))
        claude = {"inputTokens": 100, "outputTokens": 20, "cacheCreationTokens": 30,
                  "cacheReadTokens": 40, "totalTokens": 190, "totalCost": 0.125,
                  "modelBreakdowns": [{"modelName": "claude-sonnet-4", "inputTokens": 100,
                     "outputTokens": 20, "cacheCreationTokens": 30, "cacheReadTokens": 40, "cost": 0.125}]}
        codex = {"inputTokens": 200, "outputTokens": 50, "cacheReadTokens": 60,
                 "totalTokens": 250, "costUSD": 0.25, "reasoningOutputTokens": 10,
                 "models": {"gpt-5": {"inputTokens": 200, "outputTokens": 50,
                     "cacheReadTokens": 60, "totalTokens": 250, "reasoningOutputTokens": 10}}}
        def fetch(_command, source, *_args):
            return {"2026-09-01": claude if source == "claude" else codex}
        argv = ["collect.py", "--config", str(config), "--since", "2026-09-01", "--until", "2026-09-01", "--no-git"]
        if dry_run:
            argv.append("--dry-run")
        with mock.patch.object(collect, "DATA_DIR", str(root / "data")), \
             mock.patch.object(collect.shutil, "which", side_effect=lambda name: name), \
             mock.patch.object(collect, "collector_version", return_value="1.1.2" if custom else "20.0.20"), \
             mock.patch.object(collect, "fetch_source", side_effect=fetch), \
             mock.patch.object(collect, "today_in", return_value=dt.date(2026, 9, 2)), \
             mock.patch.object(collect, "git_sync") as sync, \
             mock.patch.object(collect.sys, "argv", argv), contextlib.redirect_stdout(io.StringIO()):
            collect.main()
        sync.assert_not_called()

    def test_custom_metadata_and_both_source_normalizers(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            self.run_collection(root, custom=True)
            day = json.loads((root / "data/test-host/2026-09-01.json").read_text())
            meta = json.loads((root / "data/test-host/_meta.json").read_text())
        for record in (day, meta):
            self.assertEqual(record["collector"], {"name": "turbotokens", "version": "1.1.2"})
            self.assertNotIn("ccusageVersion", record)
            self.assertNotIn("/private", json.dumps(record))
        self.assertEqual(day["sources"]["claude"], {
            "input": 100, "output": 20, "cacheCreation": 30, "cacheRead": 40,
            "total": 190, "costUSD": 0.125, "models": {"claude-sonnet-4": {
                "input": 100, "output": 20, "cacheCreation": 30, "cacheRead": 40,
                "total": 190, "costUSD": 0.125}}})
        self.assertEqual(day["sources"]["codex"], {
            "input": 200, "output": 50, "cacheCreation": 0, "cacheRead": 60,
            "total": 250, "costUSD": 0.25, "reasoningOutput": 10, "models": {"gpt-5": {
                "input": 200, "output": 50, "cacheCreation": 0, "cacheRead": 60,
                "total": 250, "reasoningOutput": 10}}})

    def test_default_metadata_is_unchanged_and_switching_clears_stale_identity(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            for custom in (False, True, False):
                self.run_collection(root, custom=custom)
                for name in ("2026-09-01.json", "_meta.json"):
                    record = json.loads((root / "data/test-host" / name).read_text())
                    if custom:
                        self.assertNotIn("ccusageVersion", record)
                        self.assertEqual(record["collector"]["name"], "turbotokens")
                    else:
                        self.assertEqual(record["ccusageVersion"], "20.0.20")
                        self.assertNotIn("collector", record)

    def test_dry_run_creates_no_snapshot_files(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            self.run_collection(root, custom=True, dry_run=True)
            self.assertFalse((root / "data").exists())

    def test_renderer_receives_identical_data_with_custom_provenance(self):
        spec = importlib.util.spec_from_file_location(
            "render", Path(__file__).resolve().parents[1] / "scripts" / "render.py")
        render = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(render)
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            with mock.patch.object(render, "DATA_DIR", str(root / "data")):
                self.run_collection(root)
                expected = render.load_days()
                self.run_collection(root, custom=True)
                self.assertEqual(render.load_days(), expected)
                self.assertEqual(expected["2026-09-01"]["claude"]["total"], 190)
                self.assertEqual(expected["2026-09-01"]["codex"]["total"], 250)


if __name__ == "__main__":
    unittest.main()
