"""PerceptAI interactive CLI.

A thin consumer of the engine's canonical event stream — all execution
logic lives in the perceptai package.

WARNING: running a task controls the real mouse and keyboard.
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from perceptai import AgentSession, EventType


def separator():
    print("-" * 52)


def render(event):
    p = event.payload
    if event.type == EventType.TASK_STARTED:
        separator()
        print(f"  TASK: {p['instruction']}")
        separator()
    elif event.type == EventType.PLAN_CREATED:
        for i, step in enumerate(p["steps"], 1):
            print(f"  {i}. {step['description']} [{step['action']}]")
        separator()
    elif event.type == EventType.STEP_STARTED:
        print(f"  Step {p['step_number']}: {p['description']} [{p['action']}]")
    elif event.type == EventType.STEP_COMPLETED:
        mark = "ok" if p["status"] in ("completed", "healed") else "FAILED"
        line = f"      -> {mark} ({p['duration_s']}s)"
        if p.get("error"):
            line += f" {p['error']}"
        if (p.get("data") or {}).get("extracted"):
            line += f" | extracted: {p['data']['extracted'][:80]}"
        print(line)
    elif event.type == EventType.REPLANNED:
        print(f"  Replanned: {p['count']} new steps ({p['reason']})")
    elif event.type == EventType.HEALING_STARTED:
        print(f"  Healing attempt {p['attempt']}...")
    elif event.type == EventType.HEALING_RESULT and p.get("diagnosis"):
        print(f"      diagnosis: {p['diagnosis']}")
    elif event.type == EventType.VERIFICATION:
        print(f"  Verification: verified={p['verified']} confidence={p['confidence']}")
    elif event.type == EventType.LOG:
        print(f"  {p['message']}")


def main():
    separator()
    print("  PerceptAI - Universal Perception Layer for AI Agents")
    separator()
    instruction = input("\n  Instruction: ").strip()
    if not instruction:
        print("  Nothing to do.")
        return

    session = AgentSession()
    session.events.subscribe(render)
    result = session.run(instruction)

    separator()
    print(f"  STATUS: {result.status.value.upper()}  ({result.duration_s}s, "
          f"{len(result.steps)} steps, {result.metadata.get('llm_calls', 0)} LLM calls)")
    print(f"  {result.summary}")
    for finding in result.findings:
        print(f"  Finding: {finding.label} = {finding.value[:100]}")
    if result.errors:
        for error in result.errors:
            print(f"  Error: {error}")
    separator()


if __name__ == "__main__":
    main()
