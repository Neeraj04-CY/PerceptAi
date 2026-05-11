import sys
import time
import os
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from core.perception import perceive_fast
from core.planner import plan_task
from core.agent import PerceptAgent
from core.os_control import get_open_windows


def separator():
    print("─" * 52)


separator()
print("  ██████╗ ███████╗██████╗  ██████╗███████╗██████╗ ")
print("  ██╔══██╗██╔════╝██╔══██╗██╔════╝██╔════╝██╔══██╗")
print("  ██████╔╝█████╗  ██████╔╝██║     █████╗  ██████╔╝")
print("  ██╔═══╝ ██╔══╝  ██╔══██╗██║     ██╔══╝  ██╔═══╝ ")
print("  ██║     ███████╗██║  ██║╚██████╗███████╗██║     ")
print("  ╚═╝     ╚══════╝╚═╝  ╚═╝ ╚═════╝╚══════╝╚═╝     ")
separator()
print("  Universal Perception Layer for AI Agents")
separator()

instruction = input("\n  → Instruction: ")

print("\n  [1/3] Scanning environment...")
open_windows = get_open_windows()
time.sleep(0.5)

print("  [2/3] Perceiving screen...")
screen = perceive_fast(force_refresh=True)
elements_found = len(screen["text_blocks"])
print(f"        {elements_found} elements detected")

context_lines = []
for block in screen["text_blocks"][:15]:
    pos = block["position"]
    context_lines.append(f"'{block['text']}' at x:{pos['x']}, y:{pos['y']}")
context = "\n".join(context_lines)

print("  [3/3] Planning with AI...")
plan = plan_task(instruction, context, open_windows)

separator()
print(f"  TASK: {plan.get('task', instruction)}")
separator()

steps = plan.get("steps", [])
for step in steps:
    print(f"  {step['step_number']}. {step['description']}")

separator()
print("  EXECUTING...")
separator()

time.sleep(1)
agent = PerceptAgent(plan["task"])
success = agent.run(steps, instruction=instruction)

separator()
if success:
    print("  ✓  TASK COMPLETED SUCCESSFULLY")
else:
    print("  ✗  TASK FAILED")
separator()