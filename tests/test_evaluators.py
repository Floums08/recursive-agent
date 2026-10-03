"""Synthetic scoring checks plus mocked Docker transport/security checks.

These tests do NOT claim that a real Docker daemon/image was exercised.
"""

import io
import json
from pathlib import Path
import subprocess
import tempfile
import unittest
from unittest.mock import patch

from recursive_workbench.evaluators import EvaluationError, evaluate, validate_result


HANDBOOK = """# Manual de operación
## Objetivo
Preparar precios con impuestos y un flujo de entrega de eventos verificable.
## Uso
El [precio](../app/pricing.json) configura rounding=half_up y
tax_after_discount=true: aplicar el descuento antes del impuesto.
El [flujo](../workflows/lead-routing.json) usa deduplicate=true, max_retries=2
y retry_statuses=[429,500,502,503,504]. El event_id identifica duplicados.
## Recuperación
- Tras un 503 transitorio, reintentar hasta dos veces; ante un 400 terminal,
  corregir los datos antes de volver a entregar. Conservar event_id en un duplicado.
## Validación
- Verificar que 100 con descuento del 10% e impuesto del 21% produce 108.90.
  Entregar dos veces el mismo event_id y comprobar una única operación.
"""


class EvaluatorTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.workspace = self.root / "workspace"
        for directory in ("app", "docs", "workflows"):
            (self.workspace / directory).mkdir(parents=True)
        self.write("app/pricing.json", {"rounding": "truncate", "tax_after_discount": False})
        self.write("workflows/lead-routing.json", {"deduplicate": False, "max_retries": 0, "retry_statuses": []})
        (self.workspace / "docs/handbook.md").write_text("# Manual\n", encoding="utf-8")

    def write(self, relative, value):
        (self.workspace / relative).write_text(json.dumps(value), encoding="utf-8")

    def repaired(self):
        self.write("app/pricing.json", {"rounding": "half_up", "tax_after_discount": True})
        self.write("workflows/lead-routing.json", {"deduplicate": True, "max_retries": 2, "retry_statuses": [429, 500, 502, 503, 504]})
        (self.workspace / "docs/handbook.md").write_text(HANDBOOK, encoding="utf-8")

    def score(self, split="train"):
        return evaluate(self.workspace, {"kind": "builtin-demo"}, split)

    def test_repairs_improve_both_splits_without_case_regressions(self):
        baseline = {split: self.score(split) for split in ("train", "holdout")}
        self.repaired()
        for split in ("train", "holdout"):
            result = self.score(split)
            self.assertEqual(result["metrics"], {"app": 1, "docs": 1, "workflow": 1})
            self.assertEqual(set(result["cases"]), set(baseline[split]["cases"]))
            self.assertEqual(result["suite_id"], baseline[split]["suite_id"])
            for name, case in baseline[split]["cases"].items():
                if case["passed"]:
                    self.assertTrue(result["cases"][name]["passed"])
            self.assertTrue(result["critical_pass"])

    def test_holdout_has_distinct_cases_and_retry_exhaustion(self):
        self.repaired()
        train, holdout = self.score(), self.score("holdout")
        self.assertFalse(set(train["cases"]) & set(holdout["cases"]))
        self.write("workflows/lead-routing.json", {"deduplicate": True, "max_retries": 1, "retry_statuses": [429, 503]})
        self.assertEqual(self.score()["metrics"]["workflow"], 1)
        self.assertLess(self.score("holdout")["metrics"]["workflow"], 1)

    def test_retrying_terminal_errors_is_a_visible_regression(self):
        self.repaired()
        self.write("workflows/lead-routing.json", {"deduplicate": True, "max_retries": 2, "retry_statuses": [400, 401, 429, 503]})
        self.assertFalse(self.score()["cases"]["train.workflow.terminal"]["passed"])
        self.assertFalse(self.score("holdout")["cases"]["holdout.workflow.auth_terminal"]["passed"])

    def test_heading_stuffing_and_broken_links_do_not_pass(self):
        self.repaired()
        (self.workspace / "docs/handbook.md").write_text(
            "# Objetivo\n# Uso\n# Recuperación\n# Validación\n" + "x" * 250, encoding="utf-8")
        self.assertLess(self.score()["metrics"]["docs"], 0.5)
        (self.workspace / "docs/handbook.md").write_text(HANDBOOK + "\n[bad](../../outside.txt)", encoding="utf-8")
        self.assertFalse(self.score()["cases"]["train.docs.source_links"]["passed"])

    def test_bad_json_and_types_are_visible_critical_failures(self):
        (self.workspace / "app/pricing.json").write_text('{"rounding":"half_up","rounding":"truncate"}', encoding="utf-8")
        result = self.score()
        self.assertFalse(result["critical_pass"])
        self.assertEqual(result["metrics"]["app"], 0)
        self.write("workflows/lead-routing.json", {"deduplicate": True, "max_retries": True, "retry_statuses": []})
        self.assertEqual(self.score()["metrics"]["workflow"], 0)

    def test_candidate_python_is_never_executed(self):
        self.repaired()
        (self.workspace / "app/__init__.py").write_text("raise RuntimeError('candidate executed')", encoding="utf-8")
        self.assertEqual(self.score()["metrics"]["app"], 1)

    def test_symlink_source_is_a_failure(self):
        target = self.root / "secret.json"
        target.write_text('{"rounding":"half_up","tax_after_discount":true}')
        (self.workspace / "app/pricing.json").unlink()
        (self.workspace / "app/pricing.json").symlink_to(target)
        self.assertFalse(self.score()["critical_pass"])

    def test_protocol_rejects_nan_boolean_score_and_unexpected_fields(self):
        good = self.score()
        for bad_value in (float("nan"), float("inf"), -0.1, 1.1, True, "1"):
            bad = dict(good, metrics={"app": bad_value})
            with self.assertRaises(EvaluationError):
                validate_result(bad)
        with self.assertRaises(EvaluationError):
            validate_result(dict(good, extra=True))
        with self.assertRaises(EvaluationError):
            validate_result(dict(good, cases={"one": {"passed": 1, "detail": "bad"}}))

    def docker_config(self):
        trusted = self.root / "trusted"
        trusted.mkdir(exist_ok=True)
        return {"kind": "docker", "image": "python:3.12-alpine", "evaluator_dir": str(trusted),
                "command": ["python", "/evaluator/evaluate.py"]}

    def test_docker_argv_enforces_isolation_mocked(self):
        config = self.docker_config()
        expected = self.score()
        with patch("recursive_workbench.evaluators._bounded_docker", return_value=json.dumps(expected)) as runner:
            result = evaluate(self.workspace, config, "train")
        self.assertEqual(result, expected)
        argv, timeout, maximum, name = runner.call_args.args
        for token in ("--read-only", "--cap-drop", "ALL", "no-new-privileges", "--pids-limit", "--cpus", "--memory", "--memory-swap"):
            self.assertIn(token, argv)
        self.assertEqual(argv[argv.index("--network") + 1], "none")
        self.assertEqual(argv[argv.index("--pull") + 1], "never")
        self.assertEqual(argv[argv.index("--user") + 1], "65534:65534")
        self.assertIn("RECURSIVE_SPLIT=train", argv)
        mounts = [argv[i + 1] for i, arg in enumerate(argv) if arg == "--mount"]
        self.assertEqual(len(mounts), 2)
        self.assertTrue(all(mount.endswith(",readonly") for mount in mounts))
        self.assertEqual(argv[-3:], [config["image"], "python", "/evaluator/evaluate.py"])

    def test_docker_refuses_evaluator_overlap_and_unknown_flags(self):
        config = self.docker_config()
        for location in (self.workspace, self.workspace / "app", self.root):
            with self.assertRaises(EvaluationError):
                evaluate(self.workspace, dict(config, evaluator_dir=str(location)), "train")
        with self.assertRaises(EvaluationError):
            evaluate(self.workspace, dict(config, privileged=True), "train")

    def test_docker_rejects_logs_and_duplicate_json_keys_mocked(self):
        config = self.docker_config()
        good = json.dumps(self.score())
        for raw in ("log\n" + good, good + good, '{"suite_id":"a","suite_id":"b"}', good.replace('"app":', '"app":NaN,"bad":', 1)):
            with patch("recursive_workbench.evaluators._bounded_docker", return_value=raw):
                with self.assertRaises(EvaluationError):
                    evaluate(self.workspace, config, "train")

    def test_docker_output_limit_real_pipe_logic_mocked_process(self):
        config = dict(self.docker_config(), max_output_bytes=1024)

        class FakeProcess:
            stdout = io.BytesIO(b"X" * 2048)
            stderr = io.BytesIO(b"")
            returncode = 0

            def poll(self):
                return self.returncode

        with patch("recursive_workbench.evaluators.subprocess.Popen", return_value=FakeProcess()) as create:
            with self.assertRaisesRegex(EvaluationError, "output limit"):
                evaluate(self.workspace, config, "train")
        self.assertFalse(create.call_args.kwargs["shell"])

    def test_docker_timeout_removes_container_mocked_process(self):
        config = self.docker_config()

        class FakeProcess:
            stdout = io.BytesIO(b"")
            stderr = io.BytesIO(b"")
            returncode = None

            def poll(self):
                return self.returncode

            def kill(self):
                self.returncode = -9

            def wait(self, timeout):
                if self.returncode is None:
                    raise subprocess.TimeoutExpired("docker", timeout)
                return self.returncode

        with patch("recursive_workbench.evaluators.subprocess.Popen", return_value=FakeProcess()), \
                patch("recursive_workbench.evaluators.time.monotonic", side_effect=[0, 31]), \
                patch("recursive_workbench.evaluators.subprocess.run") as cleanup:
            with self.assertRaisesRegex(EvaluationError, "timed out"):
                evaluate(self.workspace, config, "train")
        self.assertEqual(cleanup.call_args.args[0][:3], ["docker", "rm", "--force"])


if __name__ == "__main__":
    unittest.main()
