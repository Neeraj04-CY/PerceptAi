"""Perception benchmark: measures the Universal Perception Layer against
the LIVE screen.

Read-only — it takes screenshots and walks UIA trees, it never moves the
mouse or types. Still, it observes whatever is on the user's screen, so
run it deliberately:

    python -m evals.perception_bench --snapshots 3 --label baseline
    python -m evals.perception_bench --snapshots 3 --mode full   # + vision LLM

Reports per provider: availability, latency, observation volume, failures;
for fusion: raw observations vs fused elements (dedupe), confidence
distribution and interactive-element coverage. Writes JSON next to the
task-suite reports so runs are comparable over time.
"""
from __future__ import annotations

import argparse
import json
import statistics
import time
from datetime import datetime, timezone
from pathlib import Path

REPORTS_DIR = Path(__file__).parent / "reports"


def run_bench(snapshots: int, mode: str, label: str) -> dict:
    from perceptai import AgentSession

    session = AgentSession()
    world_model = session.world

    runs = []
    for i in range(snapshots):
        t0 = time.time()
        world = world_model.snapshot(mode=mode, force_refresh=True)
        total_ms = round((time.time() - t0) * 1000, 1)
        raw_observations = sum(r.observations for r in world.providers)
        runs.append(
            {
                "total_ms": total_ms,
                "providers": [
                    {"name": r.name, "ok": r.ok, "observations": r.observations,
                     "latency_ms": r.latency_ms, "error": r.error}
                    for r in world.providers
                ],
                "raw_observations": raw_observations,
                "fused_elements": len(world.elements),
                "interactive_elements": len(world.interactive_elements),
                "windows": len(world.windows),
                "focused_window": world.focused_window,
                "confidence": world.confidence,
                "confidence_histogram": _histogram([e.confidence for e in world.elements]),
            }
        )
        print(f"snapshot {i + 1}/{snapshots}: {total_ms}ms, "
              f"{raw_observations} observations -> {len(world.elements)} elements, "
              f"confidence {world.confidence}")
        time.sleep(0.5)

    provider_names = sorted({p["name"] for run in runs for p in run["providers"]})
    provider_summary = {}
    for name in provider_names:
        entries = [p for run in runs for p in run["providers"] if p["name"] == name]
        latencies = [p["latency_ms"] for p in entries]
        provider_summary[name] = {
            "runs": len(entries),
            "failures": sum(1 for p in entries if not p["ok"]),
            "avg_observations": round(statistics.mean(p["observations"] for p in entries), 1),
            "latency_ms_mean": round(statistics.mean(latencies), 1),
            "latency_ms_max": round(max(latencies), 1),
            "errors": sorted({p["error"] for p in entries if p["error"]}),
        }

    raw_total = sum(r["raw_observations"] for r in runs)
    fused_total = sum(r["fused_elements"] for r in runs)
    report = {
        "label": label,
        "mode": mode,
        "created_at": datetime.now(timezone.utc).isoformat(),
        "snapshots": len(runs),
        "total_ms_mean": round(statistics.mean(r["total_ms"] for r in runs), 1),
        "dedupe_ratio": round(1 - fused_total / raw_total, 3) if raw_total else 0.0,
        "confidence_mean": round(statistics.mean(r["confidence"] for r in runs), 3),
        "providers": provider_summary,
        "runs": runs,
        "session_stats": world_model.stats(),
    }
    return report


def _histogram(values: list[float]) -> dict:
    buckets = {"0.0-0.5": 0, "0.5-0.7": 0, "0.7-0.9": 0, "0.9-1.0": 0}
    for v in values:
        if v < 0.5:
            buckets["0.0-0.5"] += 1
        elif v < 0.7:
            buckets["0.5-0.7"] += 1
        elif v < 0.9:
            buckets["0.7-0.9"] += 1
        else:
            buckets["0.9-1.0"] += 1
    return buckets


def main() -> None:
    parser = argparse.ArgumentParser(description="Benchmark the perception layer (read-only).")
    parser.add_argument("--snapshots", type=int, default=3)
    parser.add_argument("--mode", choices=("fast", "full"), default="fast")
    parser.add_argument("--label", default="")
    args = parser.parse_args()

    label = args.label or datetime.now().strftime("%Y%m%d-%H%M%S")
    report = run_bench(args.snapshots, args.mode, label)

    REPORTS_DIR.mkdir(exist_ok=True)
    out = REPORTS_DIR / f"perception_{label}.json"
    out.write_text(json.dumps(report, indent=2))

    print("\n=== Perception benchmark ===")
    print(f"mode={report['mode']}  snapshots={report['snapshots']}  "
          f"mean total {report['total_ms_mean']}ms")
    print(f"dedupe ratio {report['dedupe_ratio']}  "
          f"mean confidence {report['confidence_mean']}")
    for name, p in report["providers"].items():
        status = "OK" if p["failures"] == 0 else f"{p['failures']} failure(s)"
        print(f"  {name:<16} {p['latency_ms_mean']:>7.1f}ms avg  "
              f"{p['avg_observations']:>6.1f} obs  {status}")
        for err in p["errors"]:
            print(f"    error: {err}")
    print(f"report: {out}")


if __name__ == "__main__":
    main()
