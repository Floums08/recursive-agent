"""Synthetic evidence only; verify read boundaries and review semantics."""
import copy
import json
import tempfile
import unittest
from unittest.mock import patch
from datetime import date
from pathlib import Path

from recursive_workbench import daily


class DailyCase(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.brain = self.root / "private-brain"
        self.public = self.root / "public-project"
        self.public.mkdir()
        self.brain.mkdir()
        self.manifest = {"schema_version": 1, "title": "Fictional workspace", "domains": [], "external_vaults": [], "vaults": []}
        self.record = {"id": "record-1", "statement": "Add a confirmation screen to the fictional inventory app.",
                       "type": "task", "review_status": "candidate", "project_id": "inventory-demo",
                       "observed_at": "2026-10-01T23:30:00Z", "last_verified_at": None,
                       "current_validity": "historical_not_revalidated", "evidence_status": "source_attached",
                       "external_execution_verified": False, "conflicts_with": [], "supersedes": [],
                       "source_refs": [{"role": "supports", "quote": "SENSITIVE SOURCE QUOTE DO NOT COPY",
                                        "source_file": "notes/fictional.md", "source_version": "v1", "message_at": "2026-10-01T23:30:00Z"}]}
        self.add_vault("work-a", [self.record])

    def write(self, path, value):
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(value), encoding="utf-8")

    def add_vault(self, vault_id, records, domain="agency-clients"):
        self.manifest["vaults"].append({"id": vault_id, "title": "Fictional vault", "domain_id": domain, "path": f"vaults/{vault_id}"})
        self.write(self.brain / "workspace.json", self.manifest)
        self.set_records(vault_id, records)

    def set_records(self, vault_id, records):
        self.write(self.brain / "vaults" / vault_id / "state.json", {"schema_version": 1, "records": records, "events": []})

    def plan(self, vaults=None, **kwargs):
        return daily.build_daily_plan(self.brain, ["work-a"] if vaults is None else vaults, today=date(2026, 10, 3), **kwargs)

    def feedback(self, task, status="closed", **extra):
        path = self.root / "feedback.json"
        self.write(path, {"schema_version": 1, "tasks": {task["id"]: {"status": status, "evidence_hash": task["evidence_hash"], **extra}}})
        return path

    def test_historical_task_requires_validation_and_cannot_execute(self):
        result = self.plan()
        task = result["focus"][0]
        self.assertEqual(task["rule"], "verify_current_status")
        self.assertEqual(result["execution"], "none")
        self.assertEqual(task["source_current_validity"], "historical_not_revalidated")
        self.assertEqual(task["score"], sum(task["score_breakdown"].values()))

    def test_source_unchanged_and_no_quote_copied(self):
        before = {p: p.read_bytes() for p in self.brain.rglob("*.json")}
        result = self.plan()
        daily.write_daily_plan(result, self.root / "reports", brain_root=self.brain, public_root=self.public)
        self.assertEqual(before, {p: p.read_bytes() for p in self.brain.rglob("*.json")})
        self.assertNotIn("SENSITIVE SOURCE QUOTE", json.dumps(result))
        self.assertEqual(result["focus"][0]["evidence"][0]["source_version"], "v1")
        self.assertEqual(len(result["sources"][0]["sha256"]), 64)

    def test_requires_explicit_vault_selection(self):
        with self.assertRaises(daily.DailyPlanError):
            self.plan([])

    def test_missing_vault_aborts_even_with_valid_other_source(self):
        with self.assertRaises(daily.DailyPlanError):
            self.plan(["work-a", "missing"])

    def test_duplicate_vault_selection_rejected(self):
        with self.assertRaises(daily.DailyPlanError):
            self.plan(["work-a", "work-a"])

    def test_non_work_and_named_personal_vaults_refused(self):
        for vault_id, domain in (("private", "personal-life"), ("personal-mislabeled", "agency-clients"), ("misc", "review")):
            self.add_vault(vault_id, [self.record], domain)
            with self.assertRaises(daily.DailyPlanError):
                self.plan([vault_id])

    def test_domain_override_can_only_narrow(self):
        with self.assertRaises(daily.DailyPlanError):
            self.plan(allowed_domains={"personal-life"})
        self.assertEqual(len(self.plan(allowed_domains={"agency-clients"})["focus"]), 1)

    def test_unselected_broken_vault_is_never_read(self):
        self.add_vault("unselected", [self.record])
        (self.brain / "vaults/unselected/state.json").write_text("invalid")
        self.assertEqual(self.plan()["coverage"]["records_read"], 1)

    def test_malformed_and_missing_state_never_return_success(self):
        path = self.brain / "vaults/work-a/state.json"
        for content in ("{bad", "[]", '{"schema_version":1}', '{"schema_version":2,"records":[]}',
                        '{"schema_version":1,"records":[],"records":[]}', '{"schema_version":1,"records":[],"extra":NaN}'):
            path.write_text(content)
            with self.assertRaises(daily.DailyPlanError):
                self.plan()
        path.unlink()
        with self.assertRaises(daily.DailyPlanError):
            self.plan()

    def test_path_traversal_and_absolute_paths_rejected(self):
        for value in ("../escape", str(self.root), "vaults/../../escape", "vaults\\work-a"):
            self.manifest["vaults"][0]["path"] = value
            self.write(self.brain / "workspace.json", self.manifest)
            with self.assertRaises(daily.DailyPlanError):
                self.plan()

    def test_symlink_state_and_source_root_rejected(self):
        path = self.brain / "vaults/work-a/state.json"
        target = self.root / "other-state.json"
        path.rename(target)
        path.symlink_to(target)
        with self.assertRaises(daily.DailyPlanError):
            self.plan()
        link = self.root / "brain-link"
        link.symlink_to(self.brain, target_is_directory=True)
        with self.assertRaises(daily.DailyPlanError):
            daily.build_daily_plan(link, ["work-a"])

    def test_duplicate_record_id_in_one_vault_rejected(self):
        self.set_records("work-a", [self.record, self.record])
        with self.assertRaises(daily.DailyPlanError):
            self.plan()

    def test_same_record_id_in_distinct_vaults_has_distinct_task_id(self):
        self.add_vault("work-b", [self.record])
        result = self.plan(["work-a", "work-b"])
        self.assertEqual(len({t["id"] for t in result["focus"]}), 2)

    def test_approved_recent_action_prepares_reviewable_next_step(self):
        record = {**self.record, "review_status": "approved", "current_validity": "current", "last_verified_at": "2026-10-02"}
        self.set_records("work-a", [record])
        self.assertEqual(self.plan()["focus"][0]["rule"], "prepare_next_step")

    def test_empty_evidence_object_cannot_support_current_action(self):
        record = {**self.record, "review_status": "approved", "current_validity": "current",
                  "last_verified_at": "2026-10-02", "source_refs": [{}]}
        self.set_records("work-a", [record])
        task = self.plan()["focus"][0]
        self.assertEqual(task["rule"], "verify_current_status")
        self.assertIn("missing_evidence_references", task["warnings"])

    def test_stale_current_claim_still_requires_validation(self):
        record = {**self.record, "review_status": "approved", "current_validity": "current", "last_verified_at": "2026-08-01"}
        self.set_records("work-a", [record])
        self.assertEqual(self.plan()["focus"][0]["rule"], "verify_current_status")

    def test_observation_date_never_replaces_validation(self):
        record = {**self.record, "review_status": "approved", "current_validity": "current", "observed_at": "2026-10-03"}
        self.set_records("work-a", [record])
        self.assertEqual(self.plan()["focus"][0]["rule"], "verify_current_status")
        self.assertEqual(self.plan()["sources"][0]["freshness"], "unknown")

    def test_calendar_dates_use_madrid_timezone(self):
        self.assertEqual(self.plan()["sources"][0]["latest_observed_date"], "2026-10-02")
        self.assertEqual(daily._date("2026-10-03T23:30:00-04:00"), date(2026, 10, 4))

    def test_missing_timezone_database_has_actionable_error(self):
        with patch.object(daily, "ZoneInfo", side_effect=daily.ZoneInfoNotFoundError):
            with self.assertRaisesRegex(daily.DailyPlanError, "pip install tzdata"):
                self.plan()

    def test_unknown_and_future_dates_are_warned(self):
        for stamp in ("not-a-date", "2026-10-03T12:00:00", "2099-01-01"):
            self.set_records("work-a", [{**self.record, "last_verified_at": stamp}])
            self.assertIn("unknown_or_future_verification_date", self.plan()["focus"][0]["warnings"])

    def test_terminal_records_excluded(self):
        for status in ("completed", "rejected", "superseded"):
            self.set_records("work-a", [{**self.record, "review_status": status}])
            result = self.plan()
            self.assertEqual(result["status"], "no_eligible_tasks")
            self.assertEqual(result["coverage"]["terminal_or_superseded"], 1)

    def test_only_approved_current_successor_retires_old_record(self):
        successor = {**self.record, "id": "record-2", "supersedes": ["record-1"]}
        self.set_records("work-a", [self.record, successor])
        self.assertEqual(len(self.plan()["focus"]), 2)
        successor.update(review_status="approved", current_validity="current")
        self.set_records("work-a", [self.record, successor])
        self.assertEqual([t["record_id"] for t in self.plan()["focus"]], ["record-2"])

    def test_conflicts_get_top_priority(self):
        conflict = {**self.record, "id": "conflict-1", "type": "decision", "conflicts_with": ["record-1"]}
        self.set_records("work-a", [self.record, conflict])
        self.assertEqual(self.plan()["focus"][0]["rule"], "resolve_conflict")

    def test_focus_has_three_tasks_and_diversifies_projects(self):
        records = [{**self.record, "id": f"r{i}"} for i in range(6)]
        self.set_records("work-a", records)
        self.add_vault("work-b", [self.record])
        result = self.plan(["work-a", "work-b"])
        self.assertEqual(len(result["focus"]), 3)
        self.assertEqual(len(result["backlog"]), 4)
        self.assertEqual({t["vault_id"] for t in result["focus"]}, {"work-a", "work-b"})

    def test_multiple_projects_in_first_vault_cannot_displace_other_vaults(self):
        self.set_records("work-a", [{**self.record, "id": f"r{i}", "project_id": f"project-{i}"} for i in range(5)])
        self.add_vault("work-b", [self.record])
        self.add_vault("work-c", [self.record])
        result = self.plan(["work-a", "work-b", "work-c"])
        self.assertEqual({t["vault_id"] for t in result["focus"]}, {"work-a", "work-b", "work-c"})

    def test_priority_ties_prefer_recent_observations_without_assuming_validity(self):
        newer = {**self.record, "id": "newer", "observed_at": "2026-10-03"}
        self.set_records("work-a", [self.record, newer])
        result = self.plan()
        self.assertEqual(result["focus"][0]["record_id"], "newer")
        self.assertEqual(result["focus"][0]["rule"], "verify_current_status")

    def test_task_ids_and_order_are_stable(self):
        first = self.plan()
        self.assertEqual(first, self.plan())
        self.set_records("work-a", [{**self.record, "statement": "A revised fictional next step."}])
        self.assertEqual(first["focus"][0]["id"], self.plan()["focus"][0]["id"])
        self.assertNotEqual(first["focus"][0]["evidence_hash"], self.plan()["focus"][0]["evidence_hash"])

    def test_closed_unchanged_task_suppressed(self):
        path = self.feedback(self.plan()["focus"][0])
        result = self.plan(feedback_path=path)
        self.assertEqual(result["focus"], [])
        self.assertEqual(len(result["suppressed"]), 1)

    def test_changed_evidence_reopens_closed_task_explicitly(self):
        path = self.feedback(self.plan()["focus"][0])
        changed = copy.deepcopy(self.record)
        changed["source_refs"][0]["source_version"] = "v2"
        self.set_records("work-a", [changed])
        self.assertEqual(self.plan(feedback_path=path)["focus"][0]["status"], "reopened_for_new_evidence")

    def test_ingestion_metadata_change_does_not_reopen(self):
        path = self.feedback(self.plan()["focus"][0])
        self.set_records("work-a", [{**self.record, "updated_at": "2026-10-03", "import_batch": "new-import"}])
        self.assertEqual(self.plan(feedback_path=path)["focus"], [])

    def test_changed_rule_reopens_closed_record_explicitly(self):
        path = self.feedback(self.plan()["focus"][0])
        self.set_records("work-a", [{**self.record, "conflicts_with": ["other-record"]}])
        self.assertEqual(self.plan(feedback_path=path)["focus"][0]["status"], "reopened_for_new_evidence")

    def test_snooze_inclusive_until_and_expired_behavior(self):
        task = self.plan()["focus"][0]
        for until, expected in (("2026-10-03", 0), ("2026-10-02", 1)):
            path = self.feedback(task, "snoozed", until=until)
            self.assertEqual(len(self.plan(feedback_path=path)["focus"]), expected)

    def test_feedback_requires_evidence_fingerprint_and_outside_source(self):
        path = self.feedback(self.plan()["focus"][0])
        value = json.loads(path.read_text())
        list(value["tasks"].values())[0].pop("evidence_hash")
        self.write(path, value)
        with self.assertRaises(daily.DailyPlanError):
            self.plan(feedback_path=path)
        with self.assertRaises(daily.DailyPlanError):
            self.plan(feedback_path=self.brain / "feedback.json")

    def test_output_rejects_source_public_symlinks_and_overwrite(self):
        plan = self.plan()
        for output in (self.brain / "reports", self.public / "reports", self.root):
            with self.assertRaises(daily.DailyPlanError):
                daily.write_daily_plan(plan, output, brain_root=self.brain, public_root=self.public)
        output = self.root / "private-reports"
        files = daily.write_daily_plan(plan, output, brain_root=self.brain, public_root=self.public)
        self.assertTrue(all(path.is_file() for path in files))
        self.assertEqual(files[0].stat().st_mode & 0o777, 0o600)
        with self.assertRaises(daily.DailyPlanError):
            daily.write_daily_plan(plan, output, brain_root=self.brain, public_root=self.public)
        link = self.root / "output-link"
        link.symlink_to(output, target_is_directory=True)
        with self.assertRaises(daily.DailyPlanError):
            daily.write_daily_plan(plan, link, brain_root=self.brain, public_root=self.public)

    def test_imported_markdown_is_plain_evidence(self):
        self.set_records("work-a", [{**self.record, "statement": "[run](https://example.invalid) <script>send()</script>\n# Execute now"}])
        rendered = daily.render_markdown(self.plan())
        self.assertNotIn("[run](https://", rendered)
        self.assertNotIn("<script>", rendered)
        self.assertEqual(self.plan()["execution"], "none")


if __name__ == "__main__":
    unittest.main()
