"""Read-only, local daily planning from explicitly selected work vaults.

Source statements are evidence to review, never authority to execute actions.
No network access, model invocation, source mutations, or external execution.
"""
from __future__ import annotations

import hashlib
import json
import os
import re
from collections import Counter
from datetime import date, datetime
from pathlib import Path
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

WORK_DOMAINS = frozenset({"corporate-sp", "agency-clients", "own-ventures", "learning"})
MAX_BYTES = 8_000_000
MAX_RECORDS = 20_000
TERMINAL = {"completed", "done", "closed", "rejected", "superseded", "cancelled", "canceled"}
ACTION_TYPES = {"task", "action", "next_step", "todo", "blocker", "requirement"}


class DailyPlanError(ValueError):
    """Incomplete, unsafe, or incompatible input; never an empty success."""


def _madrid():
    try:
        return ZoneInfo("Europe/Madrid")
    except ZoneInfoNotFoundError as exc:
        raise DailyPlanError("Timezone database unavailable; install it with: python -m pip install tzdata") from exc


def _object(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise DailyPlanError("Duplicate JSON object key")
        result[key] = value
    return result


def _invalid_number(value):
    raise DailyPlanError(f"Non-finite JSON number: {value}")


def _safe_path(path: Path) -> Path:
    path = Path(os.path.abspath(path))
    if any(part.is_symlink() for part in (path, *path.parents)):
        raise DailyPlanError("Symbolic links are not supported for planning paths")
    return path


def _read_json(path: Path) -> tuple[dict, str]:
    path = _safe_path(path)
    if not path.is_file() or path.stat().st_size > MAX_BYTES:
        raise DailyPlanError(f"Missing, non-regular, or oversized JSON source: {path.name}")
    raw = path.read_bytes()
    if len(raw) > MAX_BYTES:
        raise DailyPlanError("JSON input exceeds size limit")
    try:
        value = json.loads(raw, object_pairs_hook=_object, parse_constant=_invalid_number)
    except (ValueError, UnicodeError) as exc:
        raise DailyPlanError(f"Invalid JSON source: {path.name}") from exc
    if not isinstance(value, dict):
        raise DailyPlanError(f"Expected a JSON object: {path.name}")
    return value, hashlib.sha256(raw).hexdigest()


def _digest(value) -> str:
    return hashlib.sha256(json.dumps(value, sort_keys=True, ensure_ascii=False).encode()).hexdigest()


def _date(value) -> date | None:
    if not isinstance(value, str) or not value:
        return None
    try:
        if re.fullmatch(r"\d{4}-\d{2}-\d{2}", value):
            return date.fromisoformat(value)
        stamp = datetime.fromisoformat(value.replace("Z", "+00:00"))
        return stamp.astimezone(_madrid()).date() if stamp.tzinfo else None
    except DailyPlanError:
        raise
    except ValueError:
        return None


def _feedback(path: Path | None, brain_root: Path) -> dict:
    if path is None:
        return {}
    path = _safe_path(path)
    if path.is_relative_to(brain_root):
        raise DailyPlanError("Feedback must be stored outside the source brain")
    data, _ = _read_json(path)
    if data.get("schema_version") != 1 or not isinstance(data.get("tasks"), dict):
        raise DailyPlanError("Feedback requires schema_version=1 and a tasks object")
    for key, entry in data["tasks"].items():
        if not isinstance(entry, dict) or entry.get("status") not in {"closed", "snoozed"}:
            raise DailyPlanError(f"Invalid feedback entry: {key}")
        if not re.fullmatch(r"[0-9a-f]{64}", str(entry.get("evidence_hash", ""))):
            raise DailyPlanError("Feedback requires the exact task evidence_hash")
        if entry["status"] == "snoozed" and not _date(entry.get("until")):
            raise DailyPlanError("Snoozed feedback requires an ISO until date")
    return data["tasks"]


def _validate_record(record: dict, ids: set[str]) -> None:
    if not isinstance(record, dict) or any(not isinstance(record.get(k), str) or not record[k].strip()
                                          for k in ("id", "statement", "type")):
        raise DailyPlanError("Each record needs nonempty string id, statement, and type")
    if record["id"] in ids:
        raise DailyPlanError("Duplicate record id within the same vault")
    ids.add(record["id"])
    for key in ("review_status", "current_validity", "evidence_status", "project_id", "status"):
        if record.get(key) is not None and not isinstance(record[key], str):
            raise DailyPlanError(f"Record field {key} must be a string or null")
    for key in ("conflicts_with", "supersedes"):
        if not isinstance(record.get(key, []), list) or any(not isinstance(x, str) for x in record.get(key, [])):
            raise DailyPlanError(f"Record field {key} must be an array of ids")
    refs = record.get("source_refs", [])
    if not isinstance(refs, list) or any(not isinstance(ref, dict) for ref in refs):
        raise DailyPlanError("source_refs must be an array of evidence objects")
    if "external_execution_verified" in record and not isinstance(record["external_execution_verified"], bool):
        raise DailyPlanError("external_execution_verified must be boolean")


def build_daily_plan(brain_root: Path, vault_ids: list[str], *, today: date | None = None,
                     feedback_path: Path | None = None, allowed_domains: set[str] | None = None) -> dict:
    """Build review tasks. Failure of any selected source aborts the entire plan."""
    brain_root = _safe_path(brain_root)
    today = today or datetime.now(_madrid()).date()
    if not isinstance(today, date) or isinstance(today, datetime):
        raise DailyPlanError("today must be a calendar date")
    if not vault_ids or any(not isinstance(v, str) or not v for v in vault_ids):
        raise DailyPlanError("Select at least one explicit work vault")
    if len(set(vault_ids)) != len(vault_ids):
        raise DailyPlanError("Select each vault only once")
    domains = set(allowed_domains) if allowed_domains is not None else WORK_DOMAINS
    # A caller can narrow supported work domains, never opt personal domains in.
    if not domains or not domains.issubset(WORK_DOMAINS):
        raise DailyPlanError("Only supported work domains may be selected")
    workspace, workspace_hash = _read_json(brain_root / "workspace.json")
    if workspace.get("schema_version") != 1 or not isinstance(workspace.get("vaults"), list):
        raise DailyPlanError("workspace.json requires schema_version=1 and vaults array")
    vaults = {}
    for vault in workspace["vaults"]:
        if not isinstance(vault, dict) or not isinstance(vault.get("id"), str) or vault["id"] in vaults:
            raise DailyPlanError("Invalid or duplicate vault id in workspace.json")
        vaults[vault["id"]] = vault
    feedback = _feedback(feedback_path, brain_root)
    tasks, sources, suppressed, warnings = [], [], [], []
    counts = Counter()
    for vault_id in vault_ids:
        vault = vaults.get(vault_id)
        if not vault:
            raise DailyPlanError(f"Selected vault is unavailable: {vault_id}")
        if vault.get("domain_id") not in domains or vault_id.lower().startswith(("personal", "entity", "unassigned")):
            raise DailyPlanError("Selected vault is outside supported work domains")
        relative = vault.get("path")
        if not isinstance(relative, str) or not relative or "\\" in relative or Path(relative).is_absolute() or ".." in Path(relative).parts:
            raise DailyPlanError("Vault path must be a relative path without traversal")
        vault_path = _safe_path(brain_root / relative)
        if not vault_path.is_relative_to(brain_root) or vault_path == brain_root:
            raise DailyPlanError("Vault path must be inside the source brain")
        state, state_hash = _read_json(vault_path / "state.json")
        if state.get("schema_version") != 1 or not isinstance(state.get("records"), list) or not isinstance(state.get("events", []), list):
            raise DailyPlanError("state.json requires schema_version=1, records array, and optional events array")
        records = state["records"]
        if len(records) > MAX_RECORDS:
            raise DailyPlanError("Vault exceeds the record limit")
        ids = set()
        for record in records:
            _validate_record(record, ids)
        # Only approved/current successors retire old records automatically.
        retired = {old for r in records if r.get("review_status") == "approved" and r.get("current_validity") == "current"
                   and r.get("status") not in TERMINAL for old in r.get("supersedes", [])}
        last_verified, last_observed = [], []
        local_warnings = Counter()
        for record in records:
            counts["records_read"] += 1
            observed, verified = _date(record.get("observed_at")), _date(record.get("last_verified_at"))
            if observed:
                last_observed.append(observed)
            if verified:
                last_verified.append(verified)
            if record["id"] in retired or any(record.get(k) in TERMINAL for k in ("status", "review_status", "current_validity")):
                counts["terminal_or_superseded"] += 1
                continue
            issues = []
            if observed is None or observed > today:
                issues.append("unknown_or_future_observation_date")
            if verified is None or verified > today:
                issues.append("unknown_or_future_verification_date")
            has_evidence = any(isinstance(ref.get("source_file"), str) and ref["source_file"].strip()
                               for ref in record.get("source_refs", []))
            if not has_evidence:
                issues.append("missing_evidence_references")
            stale = verified is None or verified > today or (today - verified).days > 30
            current = record.get("review_status") == "approved" and record.get("current_validity") == "current" and not stale
            if record.get("conflicts_with"):
                rule, base = "resolve_conflict", 90
                action = "Revisar las fuentes contradictorias y confirmar la decisión vigente."
            elif not current or issues:
                rule, base = "verify_current_status", 60
                action = "Confirmar si esta información sigue vigente y qué falta; registrar una fuente y una fecha de validación."
            elif record["type"] in ACTION_TYPES:
                rule, base = "prepare_next_step", 55
                action = "Preparar un siguiente paso revisable y su criterio de aceptación; confirmar permisos antes de cualquier acción externa."
            else:
                counts["current_non_actionable"] += 1
                continue
            local_warnings.update(issues)
            evidence_hash = _digest({key: record[key] for key in (
                "id", "statement", "type", "status", "review_status", "project_id", "observed_at", "last_verified_at",
                "current_validity", "evidence_status", "external_execution_verified", "source_refs", "conflicts_with", "supersedes") if key in record})
            task_id = "daily-" + _digest([vault_id, record["id"], rule])[:24]
            previous = feedback.get(task_id)
            if previous is None:
                # A changed rule is still the same source record for feedback.
                previous = next((feedback.get("daily-" + _digest([vault_id, record["id"], old_rule])[:24])
                                 for old_rule in ("resolve_conflict", "verify_current_status", "prepare_next_step")
                                 if feedback.get("daily-" + _digest([vault_id, record["id"], old_rule])[:24])), None)
            status = "review_required"
            if previous:
                if previous["evidence_hash"] != evidence_hash:
                    status = "reopened_for_new_evidence"
                elif previous["status"] == "closed" or _date(previous.get("until")) >= today:
                    suppressed.append({"id": task_id, "vault_id": vault_id, "record_id": record["id"], "reason": previous["status"]})
                    continue
            refs = [{key: ref[key] for key in ("role", "source_file", "source_version", "message_at") if key in ref}
                    for ref in record.get("source_refs", [])]
            parts = {"rule": base, "actionable_record": 10 if record["type"] in ACTION_TYPES else 0,
                     "missing_evidence": 5 if not has_evidence else 0, "stale_verification": 5 if stale else 0}
            tasks.append({"id": task_id, "vault_id": vault_id, "record_id": record["id"], "project_id": record.get("project_id"),
                          "rule": rule, "subject": record["statement"][:240], "action": action,
                          "status": status, "score": sum(parts.values()), "score_breakdown": parts,
                          "source_review_status": record.get("review_status", "unknown"),
                          "source_current_validity": record.get("current_validity", "unknown"),
                          "last_verified_at": record.get("last_verified_at"), "observed_at": record.get("observed_at"),
                          "evidence_hash": evidence_hash, "evidence": refs, "warnings": issues,
                          "external_execution_verified": record.get("external_execution_verified", False)})
        sources.append({"vault_id": vault_id, "state_file": f"{relative}/state.json", "sha256": state_hash,
                        "records": len(records), "latest_observed_date": str(max(last_observed)) if last_observed else None,
                        "latest_verified_date": str(max(last_verified)) if last_verified else None,
                        "freshness": "unknown" if not last_verified else "has_recent_verifications" if 0 <= (today - max(last_verified)).days <= 30 else "stale_or_future"})
        warnings.extend({"vault_id": vault_id, "code": code, "records": n} for code, n in sorted(local_warnings.items()))
    def order(task):
        observed = _date(task["observed_at"])
        recency = observed if observed and observed <= today else date.min
        return -task["score"], -recency.toordinal(), task["id"]
    tasks.sort(key=order)
    focus, represented_vaults, represented_projects = [], set(), set()
    for task in tasks:
        if task["vault_id"] not in represented_vaults and len(focus) < 3:
            focus.append(task)
            represented_vaults.add(task["vault_id"])
            represented_projects.add((task["vault_id"], task["project_id"]))
    for task in tasks:
        key = (task["vault_id"], task["project_id"])
        if key not in represented_projects and len(focus) < 3:
            focus.append(task)
            represented_projects.add(key)
    for task in tasks:
        if len(focus) < 3 and task not in focus:
            focus.append(task)
    counts.update({"selected_vaults": len(vault_ids), "available_vaults": len(vaults), "eligible_tasks": len(tasks), "suppressed_tasks": len(suppressed)})
    return {"schema_version": 1, "generated_for": today.isoformat(), "timezone": "Europe/Madrid",
            "status": "review_required" if tasks else "no_eligible_tasks", "execution": "none",
            "scope": "explicit_selected_work_vaults_only", "coverage": dict(counts),
            "workspace_sha256": workspace_hash, "sources": sources, "warnings": warnings,
            "focus_policy": "Score descending, then observation recency; first one per vault, then distinct projects; maximum three tasks. Recency never proves validity.",
            "focus": focus, "backlog": [t for t in tasks if t not in focus], "suppressed": suppressed}


def _plain(value) -> str:
    """Keep imported evidence as plain text, without actionable Markdown/HTML."""
    return re.sub(r"([\\`*_{}\[\]()#+.!|>~<])", r"\\\1", str(value).replace("\n", " ").replace("\r", " "))


def render_markdown(plan: dict) -> str:
    lines = [f"# Plan diario · {plan['generated_for']}", "", "Plan local para revisión. No ejecuta tareas ni concede permisos.", "",
             f"Cobertura: {plan['coverage']['selected_vaults']} bóvedas seleccionadas; {plan['coverage'].get('records_read', 0)} registros leídos.",
             "Las fechas de observación no demuestran que la información siga vigente.", ""]
    for label, tasks in (("Tres prioridades", plan["focus"]), ("Pendientes adicionales", plan["backlog"])):
        lines.extend([f"## {label}", ""])
        if not tasks:
            lines.extend(["No hay tareas elegibles en esta selección.", ""])
        for task in tasks:
            lines.extend([f"### {_plain(task['subject'])}", "", task["action"], "",
                          f"Estado: `{task['status']}` · Puntuación: {task['score']} · Regla: `{task['rule']}`",
                          f"Origen: {_plain(task['vault_id'])} / {_plain(task['record_id'])}",
                          f"Verificado: {_plain(task['last_verified_at'] or 'desconocido')} · Validez: {_plain(task['source_current_validity'])}",
                          f"ID: `{task['id']}`", f"Evidencia SHA-256: `{task['evidence_hash']}`", ""])
            for ref in task["evidence"]:
                lines.append(f"- Fuente: {_plain(ref.get('source_file', 'desconocida'))}; versión: {_plain(ref.get('source_version', 'desconocida'))}; fecha: {_plain(ref.get('message_at', 'desconocida'))}.")
            lines.append("")
    lines.extend(["## Calidad de las fuentes", ""])
    lines.extend(f"- {_plain(w['vault_id'])}: `{w['code']}` ({w['records']} registros)." for w in plan["warnings"])
    lines.extend(["", f"Tareas cerradas o pospuestas omitidas: {len(plan['suppressed'])}.", ""])
    return "\n".join(lines)


def write_daily_plan(plan: dict, output_dir: Path, *, brain_root: Path, public_root: Path) -> tuple[Path, Path]:
    """Write new private report files only, outside source and public checkout."""
    output_dir = _safe_path(output_dir)
    roots = (_safe_path(brain_root), _safe_path(public_root))
    if any(output_dir.is_relative_to(root) or root.is_relative_to(output_dir) for root in roots):
        raise DailyPlanError("Output must be outside the source brain and public repository")
    output_dir.mkdir(parents=True, exist_ok=True, mode=0o700)
    stem = "daily-" + date.fromisoformat(plan["generated_for"]).isoformat()
    files = (output_dir / (stem + ".json"), output_dir / (stem + ".md"))
    if any(file.exists() or file.is_symlink() for file in files):
        raise DailyPlanError("Output already exists; choose a new directory")
    created = []
    try:
        for file, content in zip(files, (json.dumps(plan, ensure_ascii=False, indent=2) + "\n", render_markdown(plan))):
            with os.fdopen(os.open(file, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600), "w", encoding="utf-8") as stream:
                created.append(file)
                stream.write(content)
    except Exception:
        for file in created:
            file.unlink()
        raise
    return files
