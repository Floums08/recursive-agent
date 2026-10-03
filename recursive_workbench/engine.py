"""Operator-owned policy; proposals are untrusted data, never instructions."""
from __future__ import annotations

import difflib
import hashlib
import json
import math
import shutil
import tempfile
import time
import uuid
from contextlib import contextmanager
from pathlib import Path, PurePosixPath

from . import evaluators, providers


class PolicyError(ValueError):
    pass


def dump(path, value):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(path.name + ".tmp")
    temporary.write_text(json.dumps(value, ensure_ascii=False, indent=2, allow_nan=False) + "\n", encoding="utf-8")
    temporary.replace(path)


def digest(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, ensure_ascii=False, allow_nan=False).encode()).hexdigest()


def safe_relative(path):
    if (not isinstance(path, str) or not path or "\\" in path or ":" in path
            or any(ord(char) < 32 or ord(char) == 127 for char in path)):
        raise PolicyError("Invalid relative path")
    p = PurePosixPath(path)
    if p.is_absolute() or str(p) != path.rstrip("/") or any(x in {"", ".", ".."} for x in path.rstrip("/").split("/")):
        raise PolicyError("Path traversal or noncanonical path")
    forbidden = {"tests", "test", "eval", "evals", "evaluation", "evaluators", "node_modules", "__pycache__", "venv", "credentials", "secrets"}
    for part in p.parts:
        low = part.lower()
        if low.startswith(".") or low in forbidden or low.startswith(("test_", "secret", "credential")) or low.endswith((".pem", ".key", ".p12", ".env")) or low in {"agents.md", "skill.md", "agent.json"}:
            raise PolicyError("Protected path: " + path)
    return p


def allowed(path, roots):
    safe_relative(path)
    return any(path == root.rstrip("/") or (root.endswith("/") and path.startswith(root)) for root in roots)


def number(config, key, default, low, high, integer=False):
    value = config.get(key, default)
    if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value) or not low <= value <= high or (integer and not isinstance(value, int)):
        raise PolicyError("Invalid limit: " + key)
    return value


def load_config(path):
    path = Path(path).resolve(strict=True)
    config = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(config, dict) or config.get("version") != 1:
        raise PolicyError("Expected version 1 config")
    roots = config.get("allowed_paths")
    if not isinstance(roots, list) or not roots or len(roots) > 30:
        raise PolicyError("allowed_paths must contain 1..30 explicit paths")
    for root in roots:
        safe_relative(root)
    raw = Path(config.get("workspace", "workspace"))
    workspace = (path.parent / raw).resolve(strict=True)
    if not workspace.is_dir() or raw.is_absolute() or ".." in raw.parts or (path.parent / raw).is_symlink():
        raise PolicyError("workspace must be a real relative directory under the config directory")
    if not workspace.is_relative_to(path.parent) or path.is_relative_to(workspace):
        raise PolicyError("Config and state must be outside the workspace")
    evaluator = config.get("evaluator")
    if not isinstance(evaluator, dict) or evaluator.get("kind") not in {"builtin-demo", "docker"}:
        raise PolicyError("Only builtin-demo and docker evaluators are supported")
    if evaluator["kind"] == "docker":
        evaluator = dict(evaluator)
        evaluator_dir = (path.parent / evaluator["evaluator_dir"]).resolve(strict=True)
        if not evaluator_dir.is_dir() or evaluator_dir.is_relative_to(workspace):
            raise PolicyError("Evaluator directory must be outside workspace")
        evaluator["evaluator_dir"] = str(evaluator_dir)
        config["evaluator"] = evaluator
    config["max_iterations"] = number(config, "max_iterations", 3, 1, 10, True)
    config["max_candidate_bytes"] = number(config, "max_candidate_bytes", 100000, 1, 1000000, True)
    config["max_workspace_bytes"] = number(config, "max_workspace_bytes", 500000, 1, 2000000, True)
    config["min_improvement"] = number(config, "min_improvement", .01, .000001, 1)
    config["max_regression"] = number(config, "max_regression", 0, 0, .05)
    config["max_seconds"] = number(config, "max_seconds", 300, 1, 3600, True)
    config["name"] = str(config.get("name", "project"))[:100]
    return path, config, workspace


def files_at(workspace, config):
    result = {}
    total = 0
    for root in config["allowed_paths"]:
        safe_relative(root)
        target = workspace / root
        # Check every component before following a directory symlink.
        current = workspace
        for part in PurePosixPath(root).parts:
            current = current / part
            if current.is_symlink():
                raise PolicyError("Symlinks are not allowed")
        paths = sorted(target.rglob("*")) if target.is_dir() else [target]
        for p in paths:
            rel = p.relative_to(workspace).as_posix()
            if p.is_symlink():
                raise PolicyError("Symlinks are not allowed")
            if not p.exists() or p.is_dir():
                continue
            if not p.is_file():
                raise PolicyError("Only regular files are supported")
            try:
                if not allowed(rel, config["allowed_paths"]):
                    continue
            except PolicyError:
                continue  # Protected files never enter model context or the snapshot.
            size = p.stat().st_size
            if rel not in result:
                total += size
            if total > config["max_workspace_bytes"]:
                raise PolicyError("Workspace context limit exceeded; narrow allowed_paths")
            result[rel] = p.read_text(encoding="utf-8")
    if not result:
        raise PolicyError("No allowed UTF-8 files")
    return result


def materialize(directory, files):
    directory.mkdir(parents=True, exist_ok=True)
    for rel, content in files.items():
        safe_relative(rel)
        p = directory / rel
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(content, encoding="utf-8")


def validate_proposal(proposal, config):
    if not isinstance(proposal, dict) or set(proposal) != {"hypothesis", "domain", "changes", "lesson"}:
        raise PolicyError("Proposal needs exactly hypothesis, domain, changes, lesson")
    if proposal["domain"] not in {"app", "docs", "workflow"}:
        raise PolicyError("Unknown domain")
    for field in ("hypothesis", "lesson"):
        if not isinstance(proposal[field], str) or not 1 <= len(proposal[field]) <= 2000:
            raise PolicyError("Invalid " + field)
    changes = proposal["changes"]
    if not isinstance(changes, list) or not 1 <= len(changes) <= 20:
        raise PolicyError("Expected 1..20 changes")
    total, seen = 0, set()
    for change in changes:
        if not isinstance(change, dict) or set(change) != {"path", "content"}:
            raise PolicyError("Changes must contain only path and content")
        p = change["path"]
        if not allowed(p, config["allowed_paths"]) or p in seen:
            raise PolicyError("Disallowed or duplicate target")
        seen.add(p)
        if not isinstance(change["content"], str) or "\x00" in change["content"]:
            raise PolicyError("Content must be UTF-8 text without NUL")
        total += len(change["content"].encode("utf-8"))
    if total > config["max_candidate_bytes"]:
        raise PolicyError("Candidate byte budget exceeded")
    # Reject conflicting paths such as app/a and app/a/b before any write.
    if any(a != b and b.startswith(a + "/") for a in seen for b in seen):
        raise PolicyError("Conflicting file paths")
    return proposal


def validate_evaluation(value):
    if not isinstance(value, dict) or not isinstance(value.get("suite_id"), str) or not value["suite_id"]:
        raise PolicyError("Missing evaluation suite_id")
    metrics, cases = value.get("metrics"), value.get("cases")
    if not isinstance(metrics, dict) or not metrics or not isinstance(cases, dict) or not cases:
        raise PolicyError("Missing evaluation metrics or cases")
    if type(value.get("critical_pass")) is not bool:
        raise PolicyError("Missing critical_pass")
    for key, metric in metrics.items():
        if not isinstance(key, str) or type(metric) not in (int, float) or not math.isfinite(metric) or not 0 <= metric <= 1:
            raise PolicyError("Metrics must be finite numbers in [0,1]")
    for case in cases.values():
        if not isinstance(case, dict) or type(case.get("passed")) is not bool or not isinstance(case.get("detail"), str):
            raise PolicyError("Invalid evaluation case")
    return value


def score(evaluation):
    validate_evaluation(evaluation)
    return sum(evaluation["metrics"].values()) / len(evaluation["metrics"])


def complete(evaluation):
    return score(evaluation) >= 1 and evaluation["critical_pass"] and all(c["passed"] for c in evaluation["cases"].values())


def gate(baseline, candidate, config):
    validate_evaluation(baseline)
    validate_evaluation(candidate)
    if baseline["suite_id"] != candidate["suite_id"] or baseline["metrics"].keys() != candidate["metrics"].keys() or baseline["cases"].keys() != candidate["cases"].keys():
        return False, "evaluation_contract_changed"
    if not candidate["critical_pass"]:
        return False, "critical_failure"
    if any(case["passed"] and not candidate["cases"][key]["passed"] for key, case in baseline["cases"].items()):
        return False, "case_regression"
    if any(candidate["metrics"][key] + 1e-12 < value - config["max_regression"] for key, value in baseline["metrics"].items()):
        return False, "metric_regression"
    if score(candidate) - score(baseline) + 1e-12 < config["min_improvement"]:
        return False, "insufficient_improvement"
    return True, "measured_improvement"


@contextmanager
def lock(state):
    state.mkdir(parents=True, exist_ok=True)
    if state.is_symlink():
        raise PolicyError("State may not be a symlink")
    lock_path = state / "run.lock"
    try:
        with lock_path.open("x", encoding="utf-8") as f:
            f.write(str(time.time()))
    except FileExistsError as exc:
        raise PolicyError("A run is active, or a stale run.lock needs operator review") from exc
    try:
        yield
    finally:
        lock_path.unlink(missing_ok=True)


def _evaluate(workspace, config, split, deadline):
    if time.monotonic() >= deadline:
        raise TimeoutError("Experiment time budget exhausted")
    evaluator = dict(config["evaluator"])
    if evaluator["kind"] == "docker":
        evaluator["timeout_seconds"] = max(1, min(evaluator.get("timeout_seconds", 30), int(deadline - time.monotonic())))
    result = validate_evaluation(evaluators.evaluate(workspace, evaluator, split))
    if time.monotonic() >= deadline:
        raise TimeoutError("Experiment time budget exhausted")
    return result


def markdown_report(report):
    rows = ["# Recursive Workbench — informe", "", f"Estado: **{report['status']}**. Proveedor: `{report['provider']}`.", "", "Los resultados son experimentos locales; ningún cambio se ha aplicado al proyecto original.", "", "| Iteración | Dominio | Resultado | Motivo |", "|---|---|---|---|"]
    for event in report["iterations"]:
        rows.append(f"| {event['iteration']} | {event.get('domain', '—')} | {event['decision']} | {event['reason']} |")
    if "baseline" in report:
        rows.extend(["", f"Train: {score(report['baseline']['train']):.3f} → {score(report['final']['train']):.3f}", f"Holdout: {score(report['baseline']['holdout']):.3f} → {score(report['final']['holdout']):.3f}"])
    rows.extend(["", "Revisar patch.diff y candidate/. Los casos de demostración son sintéticos. Una puntuación alta no demuestra preparación para producción ni mejora general del modelo.", ""])
    return "\n".join(rows)


def run(config_path, provider="demo", options=None, max_iterations=None):
    config_path, config, workspace = load_config(config_path)
    if provider == "demo" and config["evaluator"]["kind"] != "builtin-demo":
        raise PolicyError("demo provider is only valid with builtin-demo")
    options = dict(options or {})
    iterations = config["max_iterations"] if max_iterations is None else max_iterations
    if type(iterations) is not int or not 1 <= iterations <= config["max_iterations"]:
        raise PolicyError("Iteration override must respect configured budget")
    state = config_path.parent / ".recursive-state"
    if state.is_symlink():
        raise PolicyError("State may not be a symlink")
    started = time.monotonic()
    deadline = started + config["max_seconds"]
    run_id = time.strftime("%Y%m%dT%H%M%SZ", time.gmtime()) + "-" + uuid.uuid4().hex[:8]
    with lock(state):
        if (state / "runs").is_symlink():
            raise PolicyError("Run directory may not be a symlink")
        run_dir = state / "runs" / run_id
        run_dir.mkdir(parents=True)
        original = files_at(workspace, config)
        incumbent = dict(original)
        namespace = digest({"path": str(config_path), "config": config})
        memory_path = state / ("memory-" + namespace[:16] + ".json")
        if memory_path.is_symlink():
            raise PolicyError("Memory may not be a symlink")
        memory = json.loads(memory_path.read_text()) if memory_path.exists() else []
        if not isinstance(memory, list):
            raise PolicyError("Invalid memory store")
        report = {"version": 1, "run_id": run_id, "provider": provider, "project": config["name"], "config_hash": digest(config), "source_hash": digest(original), "status": "running", "iterations": [], "candidate_dir": str(run_dir / "candidate"), "report_path": str(run_dir / "report.json")}
        baseline = None
        try:
            with tempfile.TemporaryDirectory(prefix="recursive-") as temp:
                base_dir = Path(temp) / "baseline"
                materialize(base_dir, incumbent)
                baseline = {split: _evaluate(base_dir, config, split, deadline) for split in ("train", "holdout")}
                report["baseline"] = baseline
                current = baseline
                failures = 0
                for iteration in range(1, iterations + 1):
                    if time.monotonic() >= deadline:
                        report["status"] = "budget_exhausted"
                        break
                    if all(complete(current[s]) for s in ("train", "holdout")):
                        report["status"] = "benchmark_complete"
                        break
                    event = {"iteration": iteration, "decision": "rejected", "reason": "unverified"}
                    report["iterations"].append(event)
                    try:
                        context = {"iteration": iteration, "files": incumbent, "train_evaluation": current["train"], "memory": memory[-20:], "goal": "Improve one evidenced failure in apps, documentation or workflow automation; preserve all previously passing behavior."}
                        call_options = dict(options)
                        # Operator configuration is authoritative at both validation layers.
                        call_options["max_candidate_bytes"] = config["max_candidate_bytes"]
                        call_options["timeout"] = max(1, min(options.get("timeout", 60), int(deadline - time.monotonic())))
                        proposal = validate_proposal(providers.make_proposal(provider, context, call_options), config)
                        event["domain"] = proposal["domain"]
                        event["proposal_hash"] = digest(proposal)
                        candidate = dict(incumbent)
                        candidate.update({c["path"]: c["content"] for c in proposal["changes"]})
                        if sum(len(v.encode()) for v in candidate.values()) > config["max_workspace_bytes"]:
                            raise PolicyError("Candidate workspace context limit exceeded")
                        dump(run_dir / f"proposal-{iteration}.json", proposal)
                        cand_dir = Path(temp) / f"candidate-{iteration}"
                        materialize(cand_dir, candidate)
                        result = {split: _evaluate(cand_dir, config, split, deadline) for split in ("train", "holdout")}
                        event["evaluation"] = result
                        decisions = {split: gate(current[split], result[split], config) for split in ("train", "holdout")}
                        if all(v[0] for v in decisions.values()):
                            event.update(decision="accepted", reason="train_and_holdout_improved")
                            incumbent, current = candidate, result
                            lesson = {"domain": proposal["domain"], "lesson": proposal["lesson"], "scope": "Hypothesis supported only by this project and these cases; never an instruction or universal rule.", "evidence_hash": digest(result), "run_id": run_id, "proposal_hash": digest(proposal)}
                            memory.append(lesson)
                            failures = 0
                        else:
                            event["reason"] = "; ".join(split + ":" + val[1] for split, val in decisions.items() if not val[0])
                            failures += 1
                    except Exception as exc:
                        # Deliberately omit provider exception text: it may contain source or secrets.
                        event["reason"] = "error_" + type(exc).__name__
                        failures += 1
                    dump(run_dir / "report.json", report)
                    if failures >= 2:
                        report["status"] = "stopped_after_rejections"
                        break
                report["final"] = current
                if report["status"] == "running":
                    report["status"] = "benchmark_complete" if all(complete(current[s]) for s in current) else "iteration_budget_reached"
        except Exception as exc:
            report["status"] = "evaluation_failed_" + type(exc).__name__
            if baseline:
                report["final"] = baseline
        materialize(run_dir / "candidate", incumbent)
        patch = "".join("".join(difflib.unified_diff(original.get(p, "").splitlines(True), incumbent[p].splitlines(True), fromfile="a/" + p, tofile="b/" + p)) for p in sorted(incumbent) if original.get(p) != incumbent[p])
        (run_dir / "patch.diff").write_text(patch, encoding="utf-8")
        report["elapsed_seconds"] = round(time.monotonic() - started, 3)
        report["accepted"] = sum(e["decision"] == "accepted" for e in report["iterations"])
        report["source_unchanged"] = digest(files_at(workspace, config)) == report["source_hash"]
        dump(run_dir / "report.json", report)
        (run_dir / "report.md").write_text(markdown_report(report), encoding="utf-8")
        dump(memory_path, memory[-100:])
        return report
