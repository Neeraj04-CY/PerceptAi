"""PerceptAI evaluation harness.

Runs a task suite against a runtime, scores OUTCOMES with OS-level
checkers, and writes a comparable JSON report.

    python -m evals.harness run --suite evals/suite_core.json --label unified
    python -m evals.harness run --suite evals/suite_core.json --label legacy \
        --runner "python path/to/baseline_cli.py {instruction}"
    python -m evals.harness compare evals/reports/legacy.json evals/reports/unified.json

WARNING: `run` controls the real mouse and keyboard. Run it deliberately,
on a machine you are prepared to hand over for the duration of the suite.

Metrics per task:
  outcome_success   - all checkers passed (ground truth)
  self_status       - what the runtime claimed
  self_report_honest- runtime claim agrees with ground truth
  duration_s, llm_calls, replans, healings (when the runtime exposes them)
"""
from __future__ import annotations

import argparse
import json
import shlex
import subprocess
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from evals.checkers import run_checkers

REPORTS_DIR = Path(__file__).parent / "reports"


def run_engine_task(instruction: str) -> dict:
    """Run one task in-process through the unified runtime."""
    from perceptai import AgentSession, EngineConfig

    session = AgentSession(EngineConfig.from_env())
    result = session.run(instruction)
    return result.to_dict()


def run_command_task(template: str, instruction: str) -> dict:
    """Run one task via an external command (e.g. a legacy-runtime checkout).
    The command's exit code and output are informational; scoring comes
    from checkers either way."""
    command = template.replace("{instruction}", instruction)
    t0 = time.time()
    proc = subprocess.run(shlex.split(command), capture_output=True, text=True, timeout=600)
    return {
        "status": "external",
        "duration_s": round(time.time() - t0, 2),
        "exit_code": proc.returncode,
        "metadata": {},
    }


def run_suite(suite_path: Path, label: str, runs: int, runner_cmd: str | None) -> Path:
    suite = json.loads(suite_path.read_text(encoding="utf-8"))
    tasks = suite["tasks"]
    results = []

    print(f"Suite '{suite['name']}': {len(tasks)} tasks x {runs} run(s) -> label '{label}'")
    print("This will control the real mouse and keyboard.\n")

    for task in tasks:
        for run_index in range(runs):
            print(f"[{task['id']}] run {run_index + 1}/{runs}: {task['instruction']}")
            t0 = time.time()
            error = ""
            result_dict = None
            try:
                if runner_cmd:
                    result_dict = run_command_task(runner_cmd, task["instruction"])
                else:
                    result_dict = run_engine_task(task["instruction"])
            except Exception as e:
                error = str(e)
            duration = round(time.time() - t0, 2)

            time.sleep(1.5)  # settle before observing outcome
            checks = run_checkers(task.get("checks", []), result_dict)
            outcome_success = bool(checks) and all(c.passed for c in checks)

            self_status = (result_dict or {}).get("status", "crashed" if error else "unknown")
            self_claims_success = self_status == "completed"
            metadata = (result_dict or {}).get("metadata") or {}

            record = {
                "task_id": task["id"],
                "run": run_index + 1,
                "instruction": task["instruction"],
                "outcome_success": outcome_success,
                "self_status": self_status,
                "self_report_honest": (
                    self_claims_success == outcome_success
                    if self_status not in ("external", "unknown")
                    else None
                ),
                "duration_s": (result_dict or {}).get("duration_s", duration),
                "llm_calls": metadata.get("llm_calls"),
                "replans": metadata.get("replans"),
                "healings": metadata.get("healings"),
                "checks": [{"name": c.name, "passed": c.passed, "detail": c.detail} for c in checks],
                "error": error,
            }
            results.append(record)
            mark = "PASS" if outcome_success else "FAIL"
            print(f"    -> {mark} (self: {self_status}, {record['duration_s']}s)")

            for cleanup in task.get("cleanup", []):
                subprocess.run(cleanup, shell=True, capture_output=True)
            time.sleep(1.0)

    report = {
        "label": label,
        "suite": suite["name"],
        "created_at": datetime.now(timezone.utc).isoformat(),
        "runs_per_task": runs,
        "summary": summarize(results),
        "results": results,
    }
    REPORTS_DIR.mkdir(parents=True, exist_ok=True)
    out = REPORTS_DIR / f"{label}.json"
    out.write_text(json.dumps(report, indent=2), encoding="utf-8")
    print(f"\nReport written: {out}")
    print(json.dumps(report["summary"], indent=2))
    return out


def summarize(results: list[dict]) -> dict:
    total = len(results)
    passed = sum(1 for r in results if r["outcome_success"])
    honest = [r["self_report_honest"] for r in results if r["self_report_honest"] is not None]
    durations = [r["duration_s"] for r in results if isinstance(r["duration_s"], (int, float))]
    llm = [r["llm_calls"] for r in results if isinstance(r["llm_calls"], int)]
    return {
        "tasks_run": total,
        "outcome_success_rate": round(passed / total, 3) if total else 0.0,
        "self_report_honesty": round(sum(honest) / len(honest), 3) if honest else None,
        "avg_duration_s": round(sum(durations) / len(durations), 2) if durations else None,
        "avg_llm_calls": round(sum(llm) / len(llm), 2) if llm else None,
    }


def compare(before_path: Path, after_path: Path) -> None:
    before = json.loads(before_path.read_text(encoding="utf-8"))
    after = json.loads(after_path.read_text(encoding="utf-8"))

    print(f"\n{'metric':<26}{before['label']:>14}{after['label']:>14}{'delta':>12}")
    print("-" * 66)
    for key in ("outcome_success_rate", "self_report_honesty", "avg_duration_s", "avg_llm_calls"):
        b, a = before["summary"].get(key), after["summary"].get(key)
        delta = round(a - b, 3) if isinstance(a, (int, float)) and isinstance(b, (int, float)) else "-"
        print(f"{key:<26}{str(b):>14}{str(a):>14}{str(delta):>12}")

    b_tasks = {(r["task_id"], r["run"]): r["outcome_success"] for r in before["results"]}
    print("\nPer-task changes:")
    for r in after["results"]:
        key = (r["task_id"], r["run"])
        if key in b_tasks and b_tasks[key] != r["outcome_success"]:
            direction = "FIXED" if r["outcome_success"] else "REGRESSED"
            print(f"  {direction}: {r['task_id']} (run {r['run']})")


def main() -> None:
    parser = argparse.ArgumentParser(description="PerceptAI evaluation harness")
    sub = parser.add_subparsers(dest="command", required=True)

    run_parser = sub.add_parser("run", help="run a suite (controls the real desktop!)")
    run_parser.add_argument("--suite", type=Path, default=Path("evals/suite_core.json"))
    run_parser.add_argument("--label", required=True, help="report label, e.g. 'unified' or 'legacy'")
    run_parser.add_argument("--runs", type=int, default=1)
    run_parser.add_argument("--runner", default=None,
                            help="external command template with {instruction}; default: in-process engine")

    cmp_parser = sub.add_parser("compare", help="compare two reports")
    cmp_parser.add_argument("before", type=Path)
    cmp_parser.add_argument("after", type=Path)

    args = parser.parse_args()
    if args.command == "run":
        run_suite(args.suite, args.label, args.runs, args.runner)
    else:
        compare(args.before, args.after)


if __name__ == "__main__":
    main()
