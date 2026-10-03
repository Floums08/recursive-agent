"""Behavioral checks for the experiment boundary, using no network or paid APIs."""
from __future__ import annotations

import copy
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from recursive_workbench import engine


def evaluation(value=0.2, *, critical=True, passed=False, split="train"):
    return {
        "suite_id": "test-suite-v1-" + split,
        "metrics": {"quality": value, "reliability": value},
        "cases": {"case-" + split: {"passed": passed, "detail": "controlled test case"}},
        "critical_pass": critical,
    }


def proposal(content="accepted", *, lesson="Validated lesson"):
    return {
        "hypothesis": "A bounded repair improves the controlled fixture.",
        "domain": "app",
        "changes": [{"path": "app/value.txt", "content": content}],
        "lesson": lesson,
    }


class EngineCase(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.workspace = self.root / "workspace"
        (self.workspace / "app").mkdir(parents=True)
        (self.workspace / "docs").mkdir()
        (self.workspace / "workflows").mkdir()
        (self.workspace / "app/value.txt").write_text("original", encoding="utf-8")
        self.config = {
            "version": 1,
            "name": "engine-tests",
            "workspace": "workspace",
            "allowed_paths": ["app/", "docs/", "workflows/"],
            "evaluator": {"kind": "builtin-demo"},
            "max_iterations": 3,
            "max_candidate_bytes": 100000,
            "min_improvement": 0.01,
            "max_regression": 0.0,
            "max_seconds": 300,
        }
        self.config_path = self.root / "project.json"
        self.write_config()

    def write_config(self):
        self.config_path.write_text(json.dumps(self.config), encoding="utf-8")

    def controlled_evaluator(self, directory, evaluator_config, split):
        content = (directory / "app/value.txt").read_text(encoding="utf-8")
        quality = {"original": 0.2, "accepted": 0.6, "rejected": 0.1}.get(content, 0.2)
        return evaluation(quality, split=split)

    def run_controlled(self, **kwargs):
        with patch.object(engine.evaluators, "evaluate", side_effect=self.controlled_evaluator):
            return engine.run(self.config_path, **kwargs)

    def test_real_demo_repairs_all_three_domains_and_preserves_source(self):
        fixture = {
            "app/pricing.json": json.dumps({"rounding": "truncate", "tax_after_discount": False}),
            "docs/handbook.md": "# Manual\n\nEjemplo inicial pendiente de completar.\n",
            "workflows/lead-routing.json": json.dumps({"deduplicate": False, "max_retries": 0, "retry_statuses": []}),
        }
        for relative, content in fixture.items():
            (self.workspace / relative).write_text(content, encoding="utf-8")
        result = engine.run(self.config_path, provider="demo")
        self.assertEqual(result["accepted"], 3)
        self.assertEqual(result["status"], "benchmark_complete")
        self.assertEqual([event["domain"] for event in result["iterations"]], ["app", "docs", "workflow"])
        for split in ("train", "holdout"):
            self.assertEqual(set(result["final"][split]["metrics"]), {"app", "docs", "workflow"})
            self.assertTrue(all(value == 1 for value in result["final"][split]["metrics"].values()))
            self.assertTrue(all(case["passed"] for case in result["final"][split]["cases"].values()))
            self.assertTrue(result["final"][split]["critical_pass"])
            self.assertGreater(engine.score(result["final"][split]), engine.score(result["baseline"][split]))
        for relative, content in fixture.items():
            self.assertEqual((self.workspace / relative).read_text(), content)
            self.assertNotEqual((Path(result["candidate_dir"]) / relative).read_text(), content)
        self.assertTrue(result["source_unchanged"])

    def test_acceptance_preserves_original_and_exports_reviewable_candidate(self):
        with patch.object(engine.providers, "make_proposal", return_value=proposal()):
            result = self.run_controlled(max_iterations=1)
        self.assertEqual(result["accepted"], 1)
        self.assertTrue(result["source_unchanged"])
        self.assertEqual((self.workspace / "app/value.txt").read_text(), "original")
        self.assertEqual((Path(result["candidate_dir"]) / "app/value.txt").read_text(), "accepted")
        report_dir = Path(result["report_path"]).parent
        self.assertIn("accepted", (report_dir / "patch.diff").read_text())
        self.assertTrue((report_dir / "proposal-1.json").is_file())
        self.assertTrue((report_dir / "report.md").is_file())
        self.assertEqual(json.loads(Path(result["report_path"]).read_text())["accepted"], 1)

    def test_only_accepted_lessons_enter_memory_and_provider_never_sees_holdout(self):
        captured = []
        def generate(name, context, options):
            captured.append(copy.deepcopy(context))
            return proposal("accepted" if len(captured) == 1 else "rejected",
                            lesson="accepted lesson" if len(captured) == 1 else "rejected lesson")
        with patch.object(engine.providers, "make_proposal", side_effect=generate):
            result = self.run_controlled(max_iterations=2)
        self.assertEqual(result["accepted"], 1)
        memories = list((self.root / ".recursive-state").glob("memory-*.json"))
        self.assertEqual(len(memories), 1)
        memory = json.loads(memories[0].read_text())
        self.assertEqual([x["lesson"] for x in memory], ["accepted lesson"])
        self.assertEqual(len(memory[0]["evidence_hash"]), 64)
        self.assertEqual(captured[0]["memory"], [])
        self.assertEqual(captured[1]["memory"][0]["lesson"], "accepted lesson")
        for context in captured:
            self.assertNotIn("holdout", context)
            self.assertNotIn("case-holdout", json.dumps(context))

    def test_rejected_candidate_does_not_replace_incumbent(self):
        with patch.object(engine.providers, "make_proposal", return_value=proposal("rejected")):
            result = self.run_controlled(max_iterations=1)
        self.assertEqual(result["accepted"], 0)
        self.assertIn("metric_regression", result["iterations"][0]["reason"])
        self.assertEqual((Path(result["candidate_dir"]) / "app/value.txt").read_text(), "original")
        self.assertEqual((Path(result["report_path"]).parent / "patch.diff").read_text(), "")

    def test_missing_candidate_metrics_are_rejected(self):
        calls = 0
        def evaluate(directory, evaluator_config, split):
            nonlocal calls
            calls += 1
            result = evaluation(split=split)
            if calls > 2:
                result["metrics"] = {}
            return result
        with patch.object(engine.providers, "make_proposal", return_value=proposal()), \
             patch.object(engine.evaluators, "evaluate", side_effect=evaluate):
            result = engine.run(self.config_path, max_iterations=1)
        self.assertEqual(result["accepted"], 0)
        self.assertEqual(result["iterations"][0]["reason"], "error_PolicyError")

    def test_baseline_evaluator_failure_blocks_provider(self):
        with patch.object(engine.evaluators, "evaluate", side_effect=RuntimeError("private evaluator output")), \
             patch.object(engine.providers, "make_proposal") as provider:
            result = engine.run(self.config_path)
        provider.assert_not_called()
        self.assertEqual(result["accepted"], 0)
        self.assertEqual(result["status"], "evaluation_failed_RuntimeError")
        self.assertNotIn("private evaluator output", Path(result["report_path"]).read_text())

    def test_provider_errors_are_bounded_and_exception_text_is_not_persisted(self):
        with patch.object(engine.providers, "make_proposal", side_effect=RuntimeError("TOP_SECRET_API_KEY")) as provider:
            result = self.run_controlled()
        self.assertEqual(provider.call_count, 2)
        self.assertEqual(result["status"], "stopped_after_rejections")
        self.assertEqual(result["accepted"], 0)
        self.assertNotIn("TOP_SECRET_API_KEY", Path(result["report_path"]).read_text())
        self.assertFalse((self.root / ".recursive-state/run.lock").exists())

    def test_iteration_override_cannot_expand_operator_budget(self):
        for count in (0, 4, True, 1.5):
            with self.subTest(count=count), self.assertRaises(engine.PolicyError):
                engine.run(self.config_path, max_iterations=count)

    def test_candidate_byte_budget_is_enforced_before_evaluation(self):
        self.config["max_candidate_bytes"] = 3
        self.write_config()
        with patch.object(engine.providers, "make_proposal", return_value=proposal("too large")), \
             patch.object(engine.evaluators, "evaluate", side_effect=self.controlled_evaluator) as evaluator:
            result = engine.run(self.config_path, max_iterations=1)
        self.assertEqual(evaluator.call_count, 2)
        self.assertEqual(result["accepted"], 0)

    def test_workspace_budget_rejects_oversized_original(self):
        self.config["max_workspace_bytes"] = 2
        self.write_config()
        with self.assertRaises(engine.PolicyError):
            engine.run(self.config_path)
        self.assertFalse((self.root / ".recursive-state/run.lock").exists())

    def test_manual_provider_honors_configured_candidate_limit_above_default(self):
        self.config["max_candidate_bytes"] = 150000
        self.write_config()
        content = "x" * 110000
        proposal_path = self.root / "proposal.json"
        proposal_path.write_text(json.dumps(proposal(content)), encoding="utf-8")

        def evaluate(directory, evaluator_config, split):
            actual = (directory / "app/value.txt").read_text(encoding="utf-8")
            return evaluation(0.6 if actual == content else 0.2, split=split)

        with patch.object(engine.evaluators, "evaluate", side_effect=evaluate):
            result = engine.run(self.config_path, provider="manual",
                                options={"proposal_file": proposal_path}, max_iterations=1)
        self.assertEqual(result["accepted"], 1)
        self.assertEqual((Path(result["candidate_dir"]) / "app/value.txt").read_text(), content)
        self.assertEqual((self.workspace / "app/value.txt").read_text(), "original")
        self.assertTrue(result["source_unchanged"])

    def test_configured_candidate_limit_reaches_provider_and_overrides_call_options(self):
        self.config["max_candidate_bytes"] = 3
        self.write_config()
        proposal_path = self.root / "proposal.json"
        proposal_path.write_text(json.dumps(proposal("too large")), encoding="utf-8")
        with patch.object(engine.providers, "make_proposal", wraps=engine.providers.make_proposal) as provider, \
             patch.object(engine.evaluators, "evaluate", side_effect=self.controlled_evaluator) as evaluator:
            result = engine.run(self.config_path, provider="manual",
                                options={"proposal_file": proposal_path, "max_candidate_bytes": 1000000},
                                max_iterations=1)
        self.assertEqual(provider.call_args.args[2]["max_candidate_bytes"], 3)
        self.assertEqual(evaluator.call_count, 2)
        self.assertEqual(result["accepted"], 0)
        self.assertEqual(result["iterations"][0]["reason"], "error_ProviderError")

    def test_expired_provider_call_cannot_promote_a_candidate(self):
        now = [0.0]
        def provider(name, context, options):
            now[0] = 301.0
            return proposal()
        with patch.object(engine.time, "monotonic", side_effect=lambda: now[0]), \
             patch.object(engine.providers, "make_proposal", side_effect=provider):
            result = self.run_controlled(max_iterations=1)
        self.assertEqual(result["accepted"], 0)
        self.assertEqual(result["iterations"][0]["reason"], "error_TimeoutError")

    def test_evaluator_returning_after_deadline_cannot_promote_a_candidate(self):
        now, calls = [0.0], [0]
        def evaluate(directory, config, split):
            calls[0] += 1
            if calls[0] == 4:
                now[0] = 301.0
            return evaluation(0.2 if calls[0] <= 2 else 0.6, split=split)
        with patch.object(engine.time, "monotonic", side_effect=lambda: now[0]), \
             patch.object(engine.providers, "make_proposal", return_value=proposal()), \
             patch.object(engine.evaluators, "evaluate", side_effect=evaluate):
            result = engine.run(self.config_path, max_iterations=1)
        self.assertEqual(result["accepted"], 0)

    def test_perfect_metrics_with_critical_failure_are_not_benchmark_complete(self):
        def evaluate(directory, config, split):
            return evaluation(1.0, critical=False, passed=False, split=split)
        with patch.object(engine.evaluators, "evaluate", side_effect=evaluate), \
             patch.object(engine.providers, "make_proposal", side_effect=RuntimeError("stop")):
            result = engine.run(self.config_path, max_iterations=1)
        self.assertNotEqual(result["status"], "benchmark_complete")
        self.assertEqual(result["accepted"], 0)

    def test_perfect_metrics_with_failed_cases_are_not_benchmark_complete(self):
        def evaluate(directory, config, split):
            return evaluation(1.0, critical=True, passed=False, split=split)
        with patch.object(engine.evaluators, "evaluate", side_effect=evaluate), \
             patch.object(engine.providers, "make_proposal", side_effect=RuntimeError("stop")):
            result = engine.run(self.config_path, max_iterations=1)
        self.assertNotEqual(result["status"], "benchmark_complete")

    def test_nested_state_runs_symlink_cannot_redirect_artifact_writes(self):
        external = self.root / "unrelated"
        external.mkdir()
        state = self.root / ".recursive-state"
        state.mkdir()
        (state / "runs").symlink_to(external, target_is_directory=True)
        with patch.object(engine.providers, "make_proposal", return_value=proposal()), \
             self.assertRaises(engine.PolicyError):
            self.run_controlled(max_iterations=1)
        self.assertEqual(list(external.iterdir()), [])

    def test_symlink_file_and_directory_roots_are_rejected(self):
        external = self.root / "outside.txt"
        external.write_text("secret")
        for location in (self.workspace / "app/link.txt", self.workspace / "app/linked-dir"):
            location.symlink_to(external if location.suffix else self.root, target_is_directory=not bool(location.suffix))
            try:
                with self.subTest(location=str(location)), self.assertRaises(engine.PolicyError):
                    engine.run(self.config_path)
            finally:
                location.unlink()

    def test_top_level_state_symlink_is_rejected(self):
        external = self.root / "other-state"
        external.mkdir()
        (self.root / ".recursive-state").symlink_to(external, target_is_directory=True)
        with self.assertRaises(engine.PolicyError):
            engine.run(self.config_path)
        self.assertEqual(list(external.iterdir()), [])

    def test_protected_files_never_enter_provider_context(self):
        (self.workspace / "app/.env").write_text("TOKEN=secret")
        (self.workspace / "app/tests").mkdir()
        (self.workspace / "app/tests/oracle.py").write_text("answer = 42")
        loaded = engine.load_config(self.config_path)[1]
        files = engine.files_at(self.workspace, loaded)
        self.assertEqual(files, {"app/value.txt": "original"})

    def test_existing_run_lock_blocks_concurrent_experiments(self):
        state = self.root / ".recursive-state"
        state.mkdir()
        (state / "run.lock").write_text("another run")
        with self.assertRaises(engine.PolicyError):
            engine.run(self.config_path)
        self.assertEqual((state / "run.lock").read_text(), "another run")


class EvaluationGateTests(unittest.TestCase):
    def setUp(self):
        self.config = {"min_improvement": 0.01, "max_regression": 0.0}

    def test_same_contract_measured_gain_is_accepted(self):
        self.assertEqual(engine.gate(evaluation(0.2), evaluation(0.4), self.config),
                         (True, "measured_improvement"))

    def test_changed_or_missing_metrics_cases_and_suite_are_rejected(self):
        for field, changed in (("suite_id", "other-suite"),
                               ("metrics", {"quality": 0.9}),
                               ("cases", {"different": {"passed": True, "detail": "different"}})):
            candidate = evaluation(0.9)
            candidate[field] = changed
            with self.subTest(field=field):
                self.assertEqual(engine.gate(evaluation(), candidate, self.config),
                                 (False, "evaluation_contract_changed"))

    def test_nonfinite_boolean_out_of_range_metrics_fail_validation(self):
        for value in (float("nan"), float("inf"), float("-inf"), True, -0.1, 1.1, "0.5", None):
            with self.subTest(value=value), self.assertRaises(engine.PolicyError):
                engine.validate_evaluation(evaluation(value))

    def test_critical_failure_cannot_be_compensated_by_score(self):
        self.assertEqual(engine.gate(evaluation(0.2), evaluation(1, critical=False), self.config),
                         (False, "critical_failure"))

    def test_passing_case_regression_cannot_be_compensated_by_score(self):
        self.assertEqual(engine.gate(evaluation(0.2, passed=True), evaluation(0.9, passed=False), self.config),
                         (False, "case_regression"))

    def test_metric_regression_cannot_be_compensated_by_other_gain(self):
        baseline, candidate = evaluation(0.4), evaluation(0.9)
        candidate["metrics"]["reliability"] = 0.39
        self.assertEqual(engine.gate(baseline, candidate, self.config), (False, "metric_regression"))

    def test_ties_and_subthreshold_gains_are_rejected(self):
        for value in (0.2, 0.2001, 0.209):
            with self.subTest(value=value):
                self.assertEqual(engine.gate(evaluation(0.2), evaluation(value), self.config),
                                 (False, "insufficient_improvement"))


class ProposalBoundaryTests(unittest.TestCase):
    config = {"allowed_paths": ["app/", "docs/", "workflows/"], "max_candidate_bytes": 1000}

    def test_paths_cannot_escape_or_edit_protected_content(self):
        paths = ["../outside", "app/../../outside", "/tmp/outside", "app\\..\\outside",
                 "app//value.txt", "app/./value.txt", "app/.env", "app/.git/config",
                 "app/tests/oracle.py", "app/credentials.json", "app/test_eval.py",
                 "app/AGENTS.md", "app/key.pem", "other/value.txt", "app/a:stream",
                 "app/a\nb.txt", "app/a\tb.txt", "app/a\x1bb.txt", "app/a\x7fb.txt"]
        for path in paths:
            value = proposal()
            value["changes"][0]["path"] = path
            with self.subTest(path=path), self.assertRaises(engine.PolicyError):
                engine.validate_proposal(value, self.config)

    def test_duplicate_and_parent_child_paths_are_rejected(self):
        for paths in (("app/a", "app/a"), ("app/a", "app/a/b")):
            value = proposal()
            value["changes"] = [{"path": p, "content": "x"} for p in paths]
            with self.subTest(paths=paths), self.assertRaises(engine.PolicyError):
                engine.validate_proposal(value, self.config)

    def test_schema_does_not_accept_commands_deletions_or_unknown_fields(self):
        invalid = [None, [], {}, {**proposal(), "command": "sh unsafe"},
                   {**proposal(), "changes": []}, {**proposal(), "domain": "shell"},
                   {**proposal(), "changes": [{"path": "app/a", "delete": True}]},
                   {**proposal(), "changes": [{"path": "app/a", "content": "nul\x00"}]}]
        for value in invalid:
            with self.subTest(value=value), self.assertRaises(engine.PolicyError):
                engine.validate_proposal(value, self.config)

    def test_multibyte_content_is_budgeted_in_utf8_bytes(self):
        value = proposal("éé")
        with self.assertRaises(engine.PolicyError):
            engine.validate_proposal(value, {**self.config, "max_candidate_bytes": 3})


if __name__ == "__main__":
    unittest.main()
