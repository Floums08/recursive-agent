"""Deterministic synthetic checks and an isolated, operator-owned Docker evaluator.

``evaluate(workspace, evaluator, split)`` returns the shared evaluation protocol.
``builtin-demo`` interprets data only; it never imports/executes candidate code.

Docker configuration (resolved ``evaluator_dir`` must be absolute)::

    {"kind": "docker", "image": "python:3.12-alpine",
     "evaluator_dir": "/trusted/evaluation",
     "command": ["python", "/evaluator/evaluate.py"],
     "timeout_seconds": 30, "max_output_bytes": 1000000,
     "memory_mb": 256, "cpus": 1, "pids_limit": 64}

Preload an operator-reviewed image; images are never pulled automatically.
The evaluator gets RECURSIVE_SPLIT=train|holdout, read-only /workspace and
/evaluator, and writable ephemeral /tmp. No host environment is forwarded.
The external evaluator must emit exactly one JSON result on stdout; stderr
counts toward the same output limit. A digest-pinned image is recommended.
Docker isolation limits damage, but does not establish evaluator correctness.
"""

from __future__ import annotations

import json
import math
from pathlib import Path
import re
import subprocess
import threading
import time
import unicodedata
import uuid
from decimal import Decimal, ROUND_DOWN, ROUND_HALF_UP
from urllib.parse import unquote, urlsplit


class EvaluationError(ValueError):
    """An evaluation could not be trusted; callers must reject the candidate."""


def validate_result(result: object) -> dict:
    """Strict protocol validation, including finite scores and exact field types."""
    if not isinstance(result, dict) or set(result) != {
        "suite_id", "metrics", "cases", "critical_pass"
    }:
        raise EvaluationError("Evaluation must contain only suite_id, metrics, cases, critical_pass")
    if not isinstance(result["suite_id"], str) or not result["suite_id"].strip():
        raise EvaluationError("suite_id must be a nonempty string")
    metrics = result["metrics"]
    if not isinstance(metrics, dict) or not metrics:
        raise EvaluationError("metrics must be a nonempty object")
    for name, value in metrics.items():
        if not isinstance(name, str) or not name or type(value) not in (int, float):
            raise EvaluationError("Metric names and values have invalid types")
        if not 0 <= value <= 1 or not math.isfinite(value):
            raise EvaluationError("Metric values must be finite and between zero and one")
    if not isinstance(result["cases"], dict) or not result["cases"]:
        raise EvaluationError("cases must be a nonempty object")
    for name, case in result["cases"].items():
        if not isinstance(name, str) or not name or not isinstance(case, dict):
            raise EvaluationError("Invalid case name or object")
        if set(case) != {"passed", "detail"} or type(case["passed"]) is not bool:
            raise EvaluationError("Each case needs exactly passed (boolean) and detail (string)")
        if not isinstance(case["detail"], str):
            raise EvaluationError("Case detail must be a string")
    if type(result["critical_pass"]) is not bool:
        raise EvaluationError("critical_pass must be boolean")
    return result


def _strict_json(raw: str) -> object:
    def pairs(items: list[tuple[str, object]]) -> dict:
        result = {}
        for key, value in items:
            if key in result:
                raise EvaluationError(f"Duplicate JSON key: {key}")
            result[key] = value
        return result

    def bad_constant(value: str) -> None:
        raise EvaluationError(f"Invalid JSON constant: {value}")

    try:
        return json.loads(raw, object_pairs_hook=pairs, parse_constant=bad_constant)
    except (ValueError, RecursionError) as exc:
        raise EvaluationError(f"Invalid evaluation JSON: {exc}") from exc


def _text(workspace: Path, relative: str) -> str:
    path = workspace / relative
    for parent in [path, *path.parents]:
        if parent == workspace:
            break
        if parent.is_symlink():
            raise EvaluationError(f"Symlink is not allowed: {relative}")
    resolved = path.resolve()
    if not resolved.is_relative_to(workspace) or not resolved.is_file():
        raise EvaluationError(f"Required file missing or unsafe: {relative}")
    if resolved.stat().st_size > 1_000_000:
        raise EvaluationError(f"File exceeds evaluator limit: {relative}")
    try:
        return resolved.read_text(encoding="utf-8")
    except (OSError, UnicodeError) as exc:
        raise EvaluationError(f"Cannot read {relative}") from exc


def _load_config(workspace: Path, path: str, domain: str) -> dict:
    data = _strict_json(_text(workspace, path))
    if not isinstance(data, dict):
        raise EvaluationError(f"{path} must contain a JSON object")
    if domain == "app":
        if set(data) != {"rounding", "tax_after_discount"}:
            raise EvaluationError("Pricing requires rounding and tax_after_discount")
        if data["rounding"] not in ("truncate", "half_up") or type(data["tax_after_discount"]) is not bool:
            raise EvaluationError("Invalid pricing configuration")
    else:
        if set(data) != {"deduplicate", "max_retries", "retry_statuses"}:
            raise EvaluationError("Workflow requires deduplicate, max_retries, retry_statuses")
        if type(data["deduplicate"]) is not bool or type(data["max_retries"]) is not int:
            raise EvaluationError("Invalid workflow configuration types")
        if not 0 <= data["max_retries"] <= 10:
            raise EvaluationError("max_retries must be between 0 and 10")
        statuses = data["retry_statuses"]
        if not isinstance(statuses, list) or any(type(x) is not int or not 100 <= x <= 599 for x in statuses):
            raise EvaluationError("retry_statuses must be HTTP status integers")
        if len(statuses) != len(set(statuses)):
            raise EvaluationError("retry_statuses cannot contain duplicates")
    return data


def _price(config: dict, subtotal: str, discount: str, tax: str) -> str:
    base, disc, rate = map(Decimal, (subtotal, discount, tax))
    discounted = base * (Decimal(1) - disc)
    taxable = discounted if config["tax_after_discount"] else base
    rounding = ROUND_HALF_UP if config["rounding"] == "half_up" else ROUND_DOWN
    return str((discounted + taxable * rate).quantize(Decimal("0.01"), rounding=rounding))


def _replay(config: dict, events: list[tuple[str, list[int]]]) -> dict:
    """Replay deliveries; successful event IDs are persisted for idempotency.

    max_retries excludes the first attempt. Terminal statuses must stop; exhausted
    transient errors must fail, and failed attempts must not mark an ID delivered.
    """
    successful = set()
    deliveries, attempts, failed, skipped = [], 0, 0, 0
    for event_id, responses in events:
        if config["deduplicate"] and event_id in successful:
            skipped += 1
            continue
        delivered = False
        for attempt in range(config["max_retries"] + 1):
            status = responses[min(attempt, len(responses) - 1)]
            attempts += 1
            if 200 <= status <= 299:
                deliveries.append(event_id)
                successful.add(event_id)
                delivered = True
                break
            if status not in config["retry_statuses"]:
                break
        if not delivered:
            failed += 1
    return {"delivered": deliveries, "attempts": attempts, "failed": failed, "skipped": skipped}


def _normalize(value: str) -> str:
    return "".join(c for c in unicodedata.normalize("NFKD", value.lower()) if not unicodedata.combining(c))


def _sections(text: str) -> dict[str, str]:
    sections = {}
    matches = list(re.finditer(r"(?m)^#{1,6}\s+([^\n]+)$", text))
    for index, match in enumerate(matches):
        end = matches[index + 1].start() if index + 1 < len(matches) else len(text)
        sections[_normalize(match.group(1)).strip()] = text[match.end():end].strip()
    return sections


def _local_links(workspace: Path, text: str) -> tuple[set[str], list[str]]:
    valid, invalid = set(), []
    for target in re.findall(r"(?<!!)\[[^\]]+\]\(([^)\s]+)\)", text):
        parsed = urlsplit(target.strip("<>"))
        if parsed.scheme or parsed.netloc or not parsed.path:
            continue  # External links are not fetched or asserted by this suite.
        value = unquote(parsed.path)
        path = workspace / "docs" / value
        resolved = path.resolve()
        if not resolved.is_relative_to(workspace) or not resolved.is_file():
            invalid.append(target)
            continue
        relative = str(resolved.relative_to(workspace))
        try:
            _text(workspace, relative)
        except EvaluationError:
            invalid.append(target)
        else:
            valid.add(relative)
    return valid, invalid


def _builtin(workspace: Path, split: str) -> dict:
    cases, metrics = {}, {}

    def case(domain: str, name: str, passed: bool, detail: str) -> None:
        cases[f"{split}.{domain}.{name}"] = {"passed": bool(passed), "detail": detail}

    pricing_cases = {
        "train": [("plain", "10.00", "0", "0", "10.00"),
                  ("half_cent", "0.05", "0", "0.10", "0.06"),
                  ("discount_tax", "100.00", "0.10", "0.21", "108.90")],
        "holdout": [("zero", "0", "0.20", "0.21", "0.00"),
                    ("round_up", "19.99", "0", "0.21", "24.19"),
                    ("discount_fraction", "79.95", "0.15", "0.20", "81.55"),
                    ("full_discount", "42.00", "1", "0.21", "0.00")],
    }[split]
    try:
        pricing = _load_config(workspace, "app/pricing.json", "app")
        pricing_error = None
    except (EvaluationError, OSError) as exc:
        pricing_error = str(exc)
        pricing = {}
    for name, subtotal, discount, tax, expected in pricing_cases:
        actual = _price(pricing, subtotal, discount, tax) if not pricing_error else None
        case("app", name, actual == expected, pricing_error or f"Expected {expected}; received {actual}")

    workflow_cases = {
        "train": [
            ("duplicate", [("A", [200]), ("A", [200])], {"delivered": ["A"], "attempts": 1, "failed": 0, "skipped": 1}),
            ("transient", [("B", [503, 200])], {"delivered": ["B"], "attempts": 2, "failed": 0, "skipped": 0}),
            ("terminal", [("C", [400, 200])], {"delivered": [], "attempts": 1, "failed": 1, "skipped": 0}),
        ],
        "holdout": [
            ("rate_limit", [("D", [429, 503, 200])], {"delivered": ["D"], "attempts": 3, "failed": 0, "skipped": 0}),
            ("distinct_events", [("E", [201]), ("F", [200]), ("E", [200])], {"delivered": ["E", "F"], "attempts": 2, "failed": 0, "skipped": 1}),
            ("auth_terminal", [("G", [401, 200])], {"delivered": [], "attempts": 1, "failed": 1, "skipped": 0}),
            ("retry_exhaustion", [("H", [503])], {"delivered": [], "attempts": 3, "failed": 1, "skipped": 0}),
            ("redelivery_after_failure", [("I", [400]), ("I", [200])], {"delivered": ["I"], "attempts": 2, "failed": 1, "skipped": 0}),
        ],
    }[split]
    try:
        workflow = _load_config(workspace, "workflows/lead-routing.json", "workflow")
        workflow_error = None
    except (EvaluationError, OSError) as exc:
        workflow_error = str(exc)
        workflow = {}
    for name, events, expected in workflow_cases:
        actual = _replay(workflow, events) if not workflow_error else None
        case("workflow", name, actual == expected, workflow_error or f"Expected {expected}; received {actual}")

    try:
        handbook = _text(workspace, "docs/handbook.md")
        doc_error = None
    except (EvaluationError, OSError) as exc:
        handbook, doc_error = "", str(exc)
    sections = _sections(handbook)
    local_links, broken_links = _local_links(workspace, handbook)
    normalized = _normalize(handbook)
    if split == "train":
        required = {"objetivo", "uso", "recuperacion", "validacion"}
        case("docs", "structure", len(handbook) >= 200 and required <= set(sections),
             doc_error or "Need >=200 characters and headings Objetivo, Uso, Recuperación, Validación")
        case("docs", "source_links", {"app/pricing.json", "workflows/lead-routing.json"} <= local_links and not broken_links,
             "Link both local pricing and workflow JSON; all local links must resolve inside the workspace")
        fields = {"rounding", "tax_after_discount", "deduplicate", "max_retries", "retry_statuses"}
        case("docs", "configuration", all(field in handbook for field in fields),
             "Explain rounding, tax_after_discount, deduplicate, max_retries and retry_statuses")
        for title in ("recuperacion", "validacion"):
            section = sections.get(title, "")
            case("docs", title, len(section) >= 60 and bool(re.search(r"(?m)^\s*(?:[-*]|\d+\.)\s+\S", section)),
                 f"{title} needs >=60 characters and at least one concrete checklist step")
    else:
        case("docs", "pricing_contract", "half_up" in handbook and "descuento" in normalized and "impuesto" in normalized,
             "Document half_up rounding and discount/tax behavior")
        case("docs", "retry_contract", "400" in handbook and "503" in handbook and "max_retries" in handbook,
             "Document terminal 400, transient 503 and the retry limit")
        case("docs", "idempotency_contract", "event_id" in handbook and "duplic" in normalized,
             "Document duplicate-event behavior using event_id")
        case("docs", "link_integrity", len(local_links) >= 2 and not broken_links,
             "Operational documentation must retain two existing local references without broken links")
    for domain in ("app", "docs", "workflow"):
        selected = [value["passed"] for key, value in cases.items() if key.startswith(f"{split}.{domain}.")]
        metrics[domain] = sum(selected) / len(selected)
    # Functional defects are represented as failures/scores, so they can be repaired.
    # Malformed configs are critical failures: no promotion until they are valid.
    result = {"suite_id": f"recursive-workbench-demo-v1:{split}", "metrics": metrics,
              "cases": cases, "critical_pass": not (pricing_error or workflow_error)}
    return validate_result(result)


def _number(config: dict, key: str, default: float, minimum: float, maximum: float, integer: bool = False):
    value = config.get(key, default)
    if type(value) not in (int, float) or not minimum <= value <= maximum or not math.isfinite(value):
        raise EvaluationError(f"{key} must be between {minimum} and {maximum}")
    if integer and type(value) is not int:
        raise EvaluationError(f"{key} must be an integer")
    return value


def _docker_arguments(workspace: Path, evaluator: dict, split: str, name: str) -> tuple[list[str], float, int]:
    allowed = {"kind", "image", "evaluator_dir", "command", "timeout_seconds", "max_output_bytes", "memory_mb", "cpus", "pids_limit"}
    if set(evaluator) - allowed:
        raise EvaluationError(f"Unknown Docker evaluator fields: {sorted(set(evaluator) - allowed)}")
    source = evaluator.get("evaluator_dir")
    if not isinstance(source, str) or not Path(source).is_absolute():
        raise EvaluationError("evaluator_dir must be an absolute, operator-resolved path")
    trusted = Path(source)
    if trusted.is_symlink() or not trusted.is_dir():
        raise EvaluationError("evaluator_dir must be an existing nonsymlink directory")
    trusted = trusted.resolve()
    if trusted.is_relative_to(workspace) or workspace.is_relative_to(trusted):
        raise EvaluationError("Trusted evaluator must be outside, and not contain, the candidate workspace")
    if any(',' in str(path) or '\n' in str(path) for path in (workspace, trusted)):
        raise EvaluationError("Mount paths cannot contain commas or newlines")
    image = evaluator.get("image")
    if not isinstance(image, str) or not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9._/@:+-]{0,250}", image):
        raise EvaluationError("A valid, explicitly configured Docker image is required")
    command = evaluator.get("command")
    if not isinstance(command, list) or not command or any(not isinstance(arg, str) or not arg or '\x00' in arg for arg in command):
        raise EvaluationError("command must be a nonempty argv array")
    if len(command) > 64 or sum(len(arg) for arg in command) > 16384:
        raise EvaluationError("Evaluator command is too large")
    timeout = _number(evaluator, "timeout_seconds", 30, 1, 300)
    maximum = _number(evaluator, "max_output_bytes", 1_000_000, 1024, 4_000_000, True)
    memory = _number(evaluator, "memory_mb", 256, 64, 2048, True)
    cpus = _number(evaluator, "cpus", 1, 0.1, 4)
    pids = _number(evaluator, "pids_limit", 64, 8, 256, True)
    argv = ["docker", "run", "--rm", "--pull", "never", "--name", name,
            "--network", "none", "--read-only", "--cap-drop", "ALL",
            "--security-opt", "no-new-privileges", "--user", "65534:65534",
            "--pids-limit", str(pids), "--memory", f"{memory}m", "--memory-swap", f"{memory}m",
            "--cpus", str(cpus), "--ulimit", "nofile=256:256", "--log-driver", "none",
            "--tmpfs", "/tmp:rw,noexec,nosuid,size=16m",
            "--mount", f"type=bind,src={workspace},dst=/workspace,readonly",
            "--mount", f"type=bind,src={trusted},dst=/evaluator,readonly",
            "--workdir", "/workspace", "--env", f"RECURSIVE_SPLIT={split}",
            "--env", "PYTHONDONTWRITEBYTECODE=1", image, *command]
    return argv, timeout, maximum


def _bounded_docker(argv: list[str], timeout: float, maximum: int, name: str) -> str:
    """Drain both pipes with one shared limit; remove the container on any abort."""
    try:
        process = subprocess.Popen(argv, stdin=subprocess.DEVNULL, stdout=subprocess.PIPE, stderr=subprocess.PIPE, shell=False)
    except OSError as exc:
        raise EvaluationError("Docker could not start; install/start Docker and preload the trusted image") from exc
    buffers = {"stdout": bytearray(), "stderr": bytearray()}
    overflow = threading.Event()
    lock = threading.Lock()
    total = 0

    def drain(stream, key: str) -> None:
        nonlocal total
        try:
            while True:
                chunk = stream.read(4096)
                if not chunk:
                    return
                with lock:
                    remaining = max(0, maximum - total)
                    buffers[key].extend(chunk[:remaining])
                    total += len(chunk)
                    if total > maximum:
                        overflow.set()
        finally:
            stream.close()

    threads = [threading.Thread(target=drain, args=(getattr(process, key), key), daemon=True)
               for key in ("stdout", "stderr")]
    for thread in threads:
        thread.start()
    error = None
    deadline = time.monotonic() + timeout
    try:
        while process.poll() is None:
            if overflow.is_set():
                error = "Docker evaluator exceeded output limit"
                break
            if time.monotonic() >= deadline:
                error = "Docker evaluator timed out"
                break
            try:
                process.wait(timeout=min(0.05, max(0.001, deadline - time.monotonic())))
            except subprocess.TimeoutExpired:
                pass
    finally:
        if process.poll() is None:
            error = error or "Docker evaluator interrupted"
            process.kill()
            try:
                process.wait(timeout=3)
            except subprocess.TimeoutExpired:
                pass
        # Killing the client alone does not stop its container.
        if error:
            try:
                subprocess.run(["docker", "rm", "--force", name], stdin=subprocess.DEVNULL,
                               stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, timeout=5, check=False)
            except (OSError, subprocess.TimeoutExpired):
                pass
        for thread in threads:
            thread.join(timeout=1)
    if overflow.is_set():
        raise EvaluationError("Docker evaluator exceeded output limit")
    if error:
        raise EvaluationError(error)
    if any(thread.is_alive() for thread in threads):
        raise EvaluationError("Docker evaluator output streams did not close")
    if process.returncode != 0:
        # Do not echo untrusted stderr, which may include secrets or control codes.
        raise EvaluationError(f"Docker evaluator exited with status {process.returncode}")
    try:
        return bytes(buffers["stdout"]).decode("utf-8")
    except UnicodeError as exc:
        raise EvaluationError("Docker evaluator stdout must be UTF-8 JSON") from exc


def evaluate(workspace: Path, evaluator: dict, split: str) -> dict:
    if split not in {"train", "holdout"}:
        raise EvaluationError("split must be train or holdout")
    workspace = Path(workspace)
    if workspace.is_symlink() or not workspace.is_dir():
        raise EvaluationError("workspace must be a nonsymlink directory")
    workspace = workspace.resolve()
    if not isinstance(evaluator, dict):
        raise EvaluationError("evaluator must be an object")
    if evaluator.get("kind") == "builtin-demo":
        if set(evaluator) != {"kind"}:
            raise EvaluationError("builtin-demo accepts only kind")
        return _builtin(workspace, split)
    if evaluator.get("kind") == "docker":
        name = "recursive-eval-" + uuid.uuid4().hex
        argv, timeout, maximum = _docker_arguments(workspace, evaluator, split, name)
        raw = _bounded_docker(argv, timeout, maximum, name)
        return validate_result(_strict_json(raw))
    raise EvaluationError("Unknown evaluator kind; use builtin-demo or docker")
