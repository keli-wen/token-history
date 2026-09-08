"""Collector selection and snapshot contracts; no packages or user logs needed."""

import contextlib
import copy
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


def daily_row(source, zero=False):
    row = {"date": "2026-09-01", "inputTokens": 100, "outputTokens": 20,
           "cacheCreationTokens": 30, "cacheReadTokens": 40, "totalTokens": 190}
    model = {key: value for key, value in row.items() if key != "date"}
    if source == "claude":
        model.pop("totalTokens")
        model.update(modelName="claude-sonnet-4", cost=0.125)
        row.update(totalCost=0.125, modelBreakdowns=[model])
    else:
        row.update(costUSD=0.125, reasoningOutputTokens=10, models={"gpt-5": model})
        model.update(reasoningOutputTokens=10, isFallback=False)
    if zero:
        for record in (row, model):
            for key, value in record.items():
                if type(value) in (int, float):
                    record[key] = 0
    return row


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
                collect.resolve_collector({"collector": {"executable": "/missing/collector"}})
        self.assertIn("/missing/collector", stderr.getvalue())

    def test_custom_collector_rejects_names_and_relative_paths_before_resolution(self):
        for executable in ("turbotokens", "./turbotokens", "../bin/turbotokens",
                           "~/bin/turbotokens", "tools with spaces/turbotokens"):
            with self.subTest(executable=executable), \
                 mock.patch.object(collect.shutil, "which") as which, \
                 contextlib.redirect_stderr(io.StringIO()) as stderr:
                with self.assertRaises(SystemExit):
                    collect.resolve_collector({"collector": {"executable": executable}})
                which.assert_not_called()
                self.assertIn("absolute path", stderr.getvalue())

    @unittest.skipIf(collect.os.name == "nt", "POSIX scheduler environment")
    def test_absolute_collector_runs_with_minimal_scheduler_path(self):
        with tempfile.TemporaryDirectory() as root:
            directory = Path(root) / "Collector Tools"
            directory.mkdir()
            executable = directory / "custom-collector"
            executable.write_text("#!/bin/sh\nprintf '%s\\n' 'custom-collector 1.0'\n",
                                  encoding="utf-8")
            executable.chmod(0o755)
            with mock.patch.dict(collect.os.environ,
                                 {"PATH": "/usr/bin:/bin:/usr/sbin:/sbin"}):
                command, name = collect.resolve_collector(
                    {"collector": {"executable": str(executable)}})
                self.assertEqual(command, [str(executable)])
                self.assertEqual(name, "custom-collector")
                self.assertEqual(collect.collector_version(command), "1.0")

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
        for source in ("claude", "codex"):
            row = daily_row(source)
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

    def test_missing_or_invalid_metrics_are_rejected_for_both_sources(self):
        invalid = [None, True, False, "0", [], {}, -1, float("nan"), float("inf"), -float("inf"), 10 ** 400]
        for source in ("claude", "codex"):
            row = daily_row(source)
            model = row["modelBreakdowns"][0] if source == "claude" else row["models"]["gpt-5"]
            for location, record in [("row", row), ("model", model)]:
                fields = [key for key, value in record.items() if type(value) in (int, float)]
                for field in fields:
                    for value in invalid + ["missing"]:
                        candidate = copy.deepcopy(row)
                        target = candidate if location == "row" else (
                            candidate["modelBreakdowns"][0] if source == "claude" else candidate["models"]["gpt-5"])
                        if value == "missing":
                            del target[field]
                            if field == "reasoningOutputTokens":
                                continue  # The existing normalizer treats this count as optional.
                        else:
                            target[field] = value
                        with self.subTest(source=source, location=location, field=field, value=value), \
                             mock.patch.object(collect, "run_collector", return_value=json.dumps({"daily": [candidate]})), \
                             contextlib.redirect_stderr(io.StringIO()) as stderr, self.assertRaises(SystemExit):
                            collect.fetch_source(["tool"], source, dt.date(2026, 9, 1), dt.date(2026, 9, 1), "UTC")
                        self.assertIn(source, stderr.getvalue())
                        self.assertIn(field, stderr.getvalue())

    def test_invalid_model_shapes_are_rejected_before_normalization(self):
        for source, field, invalid in [
            ("claude", "modelBreakdowns", [None, {}, "", [None], [{}]]),
            ("codex", "models", [None, [], "", {"gpt-5": None}, {"gpt-5": {}}]),
        ]:
            for value in invalid + ["missing"]:
                row = daily_row(source)
                if value == "missing":
                    del row[field]
                else:
                    row[field] = value
                with self.subTest(source=source, value=value), \
                     mock.patch.object(collect, "run_collector", return_value=json.dumps({"daily": [row]})), \
                     contextlib.redirect_stderr(io.StringIO()), self.assertRaises(SystemExit):
                    collect.fetch_source(["tool"], source, dt.date(2026, 9, 1), dt.date(2026, 9, 1), "UTC")

    def test_zero_metrics_and_empty_model_containers_are_valid(self):
        for source in ("claude", "codex"):
            for with_models in (False, True):
                row = daily_row(source, zero=True)
                if not with_models:
                    row["modelBreakdowns" if source == "claude" else "models"] = [] if source == "claude" else {}
                    row.pop("reasoningOutputTokens", None)
                with self.subTest(source=source, with_models=with_models), \
                     mock.patch.object(collect, "run_collector", return_value=json.dumps({"daily": [row]})):
                    self.assertEqual(collect.fetch_source(["tool"], source, dt.date(2026, 9, 1),
                                                         dt.date(2026, 9, 1), "UTC"), {row["date"]: row})

    def test_invalid_dates_model_names_and_fallback_flags_are_rejected(self):
        cases = []
        for date in ("", "2026-02-30", "20260901", "../2026-09-01"):
            row = daily_row("claude")
            row["date"] = date
            cases.append(("claude", row))
        for name in (None, "", True, 42):
            row = daily_row("claude")
            row["modelBreakdowns"][0]["modelName"] = name
            cases.append(("claude", row))
        for flag in (None, "false", 0, 1):
            row = daily_row("codex")
            row["models"]["gpt-5"]["isFallback"] = flag
            cases.append(("codex", row))
        row = daily_row("codex")
        row["models"][""] = row["models"].pop("gpt-5")
        cases.append(("codex", row))
        for source, row in cases:
            with self.subTest(source=source, row=row), \
                 mock.patch.object(collect, "run_collector", return_value=json.dumps({"daily": [row]})), \
                 contextlib.redirect_stderr(io.StringIO()), self.assertRaises(SystemExit):
                collect.fetch_source(["tool"], source, dt.date(2026, 9, 1), dt.date(2026, 9, 1), "UTC")


class SnapshotTests(unittest.TestCase):
    def run_collection(self, root, custom=False, dry_run=False, payloads=None):
        cfg = {"host": "test-host", "timezone": "UTC", "sources": ["claude", "codex"]}
        if custom:
            cfg["collector"] = {"executable": "/private/local/path/turbotokens"}
        config = root / "config.json"
        config.write_text(json.dumps(cfg))
        claude = {"date": "2026-09-01", "inputTokens": 100, "outputTokens": 20, "cacheCreationTokens": 30,
                  "cacheReadTokens": 40, "totalTokens": 190, "totalCost": 0.125,
                  "modelBreakdowns": [{"modelName": "claude-sonnet-4", "inputTokens": 100,
                     "outputTokens": 20, "cacheCreationTokens": 30, "cacheReadTokens": 40, "cost": 0.125}]}
        codex = {"date": "2026-09-01", "inputTokens": 200, "outputTokens": 50, "cacheCreationTokens": 0, "cacheReadTokens": 60,
                 "totalTokens": 250, "costUSD": 0.25, "reasoningOutputTokens": 10,
                 "models": {"gpt-5": {"inputTokens": 200, "outputTokens": 50,
                     "cacheCreationTokens": 0, "cacheReadTokens": 60, "totalTokens": 250, "reasoningOutputTokens": 10}}}
        if payloads is None:
            payloads = {"claude": {"daily": [claude]}, "codex": {"daily": [codex]}}
        def run(_command, args, **_kwargs):
            return json.dumps(payloads[args[0]])
        argv = ["collect.py", "--config", str(config), "--since", "2026-09-01", "--until", "2026-09-01", "--no-git"]
        if dry_run:
            argv.append("--dry-run")
        with mock.patch.object(collect, "DATA_DIR", str(root / "data")), \
             mock.patch.object(collect.shutil, "which", side_effect=lambda name: name), \
             mock.patch.object(collect, "collector_version", return_value="1.1.2" if custom else "20.0.20"), \
             mock.patch.object(collect, "run_collector", side_effect=run), \
             mock.patch.object(collect, "today_in", return_value=dt.date(2026, 9, 2)), \
             mock.patch.object(collect, "git_sync") as sync, \
             mock.patch.object(collect.sys, "argv", argv), contextlib.redirect_stdout(io.StringIO()):
            collect.main()
        sync.assert_not_called()

    def test_incompatible_backend_preserves_existing_snapshots_and_metadata(self):
        for bad_source in ("claude", "codex"):
            with self.subTest(source=bad_source), tempfile.TemporaryDirectory() as tmp:
                root = Path(tmp)
                self.run_collection(root, custom=True)
                host = root / "data/test-host"
                before = {path.name: path.read_bytes() for path in host.iterdir()}
                payloads = {source: {"daily": [daily_row(source)]} for source in ("claude", "codex")}
                # A valid first row/source must not be written before all later rows validate.
                payloads[bad_source]["daily"].append({"date": "2026-09-01", "tokens": 999})
                with mock.patch.object(collect, "write_json", wraps=collect.write_json) as write, \
                     contextlib.redirect_stderr(io.StringIO()), self.assertRaises(SystemExit):
                    self.run_collection(root, custom=True, payloads=payloads)
                write.assert_not_called()
                self.assertEqual({path.name: path.read_bytes() for path in host.iterdir()}, before)

    def test_genuine_zero_usage_can_replace_a_recent_snapshot(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            self.run_collection(root, custom=True)
            self.run_collection(root, custom=True, payloads={
                source: {"daily": [daily_row(source, zero=True)]} for source in ("claude", "codex")})
            record = json.loads((root / "data/test-host/2026-09-01.json").read_text())
            for source in ("claude", "codex"):
                self.assertEqual(record["sources"][source]["total"], 0)
                self.assertEqual(record["sources"][source]["costUSD"], 0)

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
