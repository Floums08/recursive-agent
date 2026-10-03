"""Small CLI; no install or API key required for the demo."""
import argparse
import json
import sys
from pathlib import Path

from . import engine, evaluators, providers


def create_demo(output):
    output = Path(output).resolve()
    if output.exists() and any(output.iterdir()):
        raise engine.PolicyError("Demo output must be empty; choose a new directory")
    output.mkdir(parents=True, exist_ok=True)
    config = {"version": 1, "name": "Tres dominios — demostración sintética", "workspace": "workspace", "allowed_paths": ["app/", "docs/", "workflows/"], "evaluator": {"kind": "builtin-demo"}, "max_iterations": 3, "max_candidate_bytes": 100000, "min_improvement": .01, "max_regression": 0.0, "max_seconds": 300}
    engine.dump(output / "agent.json", config)
    engine.materialize(output / "workspace", {"app/pricing.json": json.dumps({"rounding": "truncate", "tax_after_discount": False}, indent=2) + "\n", "docs/handbook.md": "# Manual\n\nEste proyecto calcula precios y enruta leads.\n", "workflows/lead-routing.json": json.dumps({"deduplicate": False, "max_retries": 0, "retry_statuses": []}, indent=2) + "\n"})
    return output / "agent.json"


def main(argv=None):
    parser = argparse.ArgumentParser(description="Recursive Workbench: experimentos medibles para apps, documentación y flujos")
    commands = parser.add_subparsers(dest="command", required=True)
    demo = commands.add_parser("demo", help="Crear y ejecutar tres mejoras sintéticas sin API")
    demo.add_argument("--output", default="demo")
    run = commands.add_parser("run", help="Preparar candidatos, nunca modificar el proyecto original")
    run.add_argument("config", type=Path)
    run.add_argument("--provider", choices=["demo", "manual", "ollama"], default="manual")
    run.add_argument("--proposal", type=Path)
    run.add_argument("--model")
    run.add_argument("--base-url", default="http://127.0.0.1:11434")
    run.add_argument("--iterations", type=int)
    run.add_argument("--max-output-tokens", type=int, default=4096)
    inspect = commands.add_parser("inspect", help="Ver política y ficheros autorizados")
    inspect.add_argument("config", type=Path)
    prompt = commands.add_parser("prompt", help="Exportar contexto de entrenamiento para Codex/ChatGPT")
    prompt.add_argument("config", type=Path)
    prompt.add_argument("--output", type=Path, required=True)
    report = commands.add_parser("report", help="Leer un informe de ejecución")
    report.add_argument("path", type=Path)
    daily = commands.add_parser("daily", help="Preparar tres prioridades privadas desde espacios laborales explícitos")
    daily.add_argument("--brain-root", type=Path, required=True)
    daily.add_argument("--vault", action="append", required=True, dest="vault_ids")
    daily.add_argument("--output", type=Path, required=True)
    daily.add_argument("--feedback", type=Path)
    daily.add_argument("--date", help="Fecha ISO opcional para ejecución reproducible")
    args = parser.parse_args(argv)
    try:
        if args.command == "daily":
            from datetime import date
            from .daily import build_daily_plan, write_daily_plan
            plan = build_daily_plan(args.brain_root, args.vault_ids,
                                    today=date.fromisoformat(args.date) if args.date else None,
                                    feedback_path=args.feedback)
            files = write_daily_plan(plan, args.output, brain_root=args.brain_root,
                                     public_root=Path(__file__).resolve().parents[1])
            # Keep private statements out of terminal/CI logs.
            print("Plan privado preparado. Prioridades:", len(plan["focus"]))
            for file in files:
                print(file)
            return 0
        if args.command == "demo":
            result = engine.run(create_demo(args.output))
            print(engine.markdown_report(result))
            print("Informe:", result["report_path"])
            return 0 if result["accepted"] == 3 else 1
        if args.command == "run":
            options = {"base_url": args.base_url, "max_output_tokens": args.max_output_tokens}
            if args.proposal:
                options["proposal_file"] = str(args.proposal.resolve())
            if args.model:
                options["model"] = args.model
            if args.provider == "manual" and not args.proposal:
                parser.error("--provider manual requires --proposal")
            if args.provider == "ollama" and not args.model:
                parser.error("--provider ollama requires --model")
            result = engine.run(args.config, args.provider, options, args.iterations)
            print(engine.markdown_report(result))
            print("Informe:", result["report_path"])
            return 0 if result["accepted"] else 1
        if args.command == "inspect":
            _, config, workspace = engine.load_config(args.config)
            files = engine.files_at(workspace, config)
            print(json.dumps({"project": config["name"], "workspace": str(workspace), "files": sorted(files), "evaluator": config["evaluator"]["kind"], "max_iterations": config["max_iterations"], "bytes": sum(len(v.encode()) for v in files.values())}, ensure_ascii=False, indent=2))
        if args.command == "prompt":
            _, config, workspace = engine.load_config(args.config)
            if args.output.resolve().is_relative_to(workspace):
                raise engine.PolicyError("Save the prompt outside the project workspace")
            files = engine.files_at(workspace, config)
            # Evaluate the same filtered snapshot that will be used by the engine.
            import tempfile
            with tempfile.TemporaryDirectory(prefix="recursive-prompt-") as temp:
                engine.materialize(Path(temp), files)
                train = engine.validate_evaluation(evaluators.evaluate(Path(temp), config["evaluator"], "train"))
            context = {"iteration": 1, "files": files, "train_evaluation": train, "memory": [], "goal": "Propose one small measured improvement; preserve all previously passing behavior."}
            args.output.parent.mkdir(parents=True, exist_ok=True)
            with args.output.open("x", encoding="utf-8") as f:
                f.write(providers.SYSTEM_PROMPT + "\n\n" + providers.build_prompt(context))
            print("Contexto preparado:", args.output.resolve())
        if args.command == "report":
            print(engine.markdown_report(json.loads(args.path.read_text(encoding="utf-8"))))
        return 0
    except (ValueError, OSError, KeyError, TypeError, RuntimeError) as exc:
        print("Error:", str(exc), file=sys.stderr)
        return 2
