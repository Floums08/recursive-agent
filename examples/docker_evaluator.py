"""Docker transport example using the same synthetic, data-only demo checks.

This is not an evaluator for arbitrary application code. To exercise it:

1. Create a trusted directory OUTSIDE the candidate workspace.
2. Copy this file there as evaluate.py.
3. Copy recursive_workbench/evaluators.py there as demo_checks.py.
4. Preload an operator-reviewed Python 3.12+ image into local Docker.
5. Configure kind=docker, evaluator_dir=<trusted directory>,
   image=<preloaded image>, command=["python", "/evaluator/evaluate.py"].

Trust is attached to the external evaluator and configuration, not the proposal.
For a real application, the operator must replace these synthetic contracts
with independently reviewed tests, reliable oracles, and a real holdout dataset.
Avoid importing untrusted candidate code into the evaluator process itself;
test it through a bounded subprocess/interface inside the isolated container.
"""

import importlib.util
import json
import os
from pathlib import Path
import sys


def main() -> int:
    trusted_path = Path(__file__).resolve().parent / "demo_checks.py"
    spec = importlib.util.spec_from_file_location("trusted_demo_checks", trusted_path)
    if spec is None or spec.loader is None:
        raise RuntimeError("Trusted demo_checks.py is missing")
    checks = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(checks)
    result = checks.evaluate(Path("/workspace"), {"kind": "builtin-demo"}, os.environ.get("RECURSIVE_SPLIT", ""))
    print(json.dumps(result, ensure_ascii=False, allow_nan=False))
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except Exception as exc:
        # Protocol errors cause a failed invocation, never a fabricated score.
        print(f"Trusted evaluation failed: {type(exc).__name__}", file=sys.stderr)
        raise SystemExit(2)
