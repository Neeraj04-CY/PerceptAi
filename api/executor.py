import time
import json
import sys
import os
import re
from datetime import datetime
from typing import List, Dict, Any
from groq import Groq
from config import config

client = Groq(api_key=config.GROQ_API_KEY)


def preprocess_instruction(instruction: str) -> str:
    now = datetime.now()
    date_str = now.strftime("%B %d, %Y")
    time_str = now.strftime("%I:%M %p")
    dt_str = f"{date_str} {time_str}"
    instruction = re.sub(r"today'?s? date and time", dt_str, instruction, flags=re.IGNORECASE)
    instruction = re.sub(r"today'?s? date", date_str, instruction, flags=re.IGNORECASE)
    instruction = re.sub(r"current date and time", dt_str, instruction, flags=re.IGNORECASE)
    instruction = re.sub(r"current time", time_str, instruction, flags=re.IGNORECASE)
    return instruction


def get_screen_context() -> str:
    core_path = os.path.join(os.path.dirname(__file__), "..", "core")
    if core_path not in sys.path:
        sys.path.insert(0, core_path)
    try:
        from perception import perceive_fast
        screen = perceive_fast()
        lines = [b["text"] for b in screen.get("text_blocks", [])[:50]]
        return "\n".join(lines)
    except:
        try:
            from perception import perceive
            screen = perceive()
            lines = [b["text"] for b in screen.get("text_blocks", [])[:50]]
            return "\n".join(lines)
        except Exception as e:
            return f"perception failed: {e}"


def plan_from_screen(instruction: str, screen_text: str, completed: List[Dict]) -> List[Dict]:
    now = datetime.now()
    completed_summary = "\n".join(
        [f"- {s['description']} [{s['action']}]: {s['status']}" for s in completed]
    ) or "Nothing completed yet"

    response = client.chat.completions.create(
        model="llama-3.3-70b-versatile",
        messages=[{
            "role": "user",
            "content": f"""You are a Windows automation agent.
Current time: {now.strftime("%B %d, %Y %I:%M %p")}

GOAL: {instruction}

Already done:
{completed_summary}

Currently visible on screen:
{screen_text}

Generate the NEXT steps to complete the goal.
Use ONLY text that is ACTUALLY VISIBLE on screen for any "find" fields.
NEVER use placeholder text like "first post title" - use exact visible text.
For date/time use actual values: {now.strftime("%B %d, %Y")} / {now.strftime("%I:%M %p")}
ALWAYS include an "app" field in EVERY step, even for click, type, press, wait, and read_screen steps.

Return ONLY valid JSON array (max 5 steps):
[
  {{
    "step_number": 1,
    "description": "what this step does",
    "action": "open_app|navigate_url|click|type|press|wait|read_screen",
    "app": "required app name for this step",
    "url": "full url",
    "find": "EXACT text visible on screen right now",
    "text": "text to type",
    "key": "key name",
    "wait": 1.0
  }}
]

Return ONLY JSON array."""
        }],
        max_tokens=800
    )
    raw = response.choices[0].message.content.strip()
    raw = raw.replace("```json", "").replace("```", "").strip()
    try:
        return json.loads(raw)
    except:
        return []


def extract_from_screen(goal: str, screen_text: str) -> str:
    response = client.chat.completions.create(
        model="llama-3.3-70b-versatile",
        messages=[{
            "role": "user",
            "content": f"""Extract specific information from screen text.

What to find: {goal}

Screen content:
{screen_text}

Return ONLY the extracted information, nothing else.
If not found, return: NOT_FOUND"""
        }],
        max_tokens=300,
    )
    return response.choices[0].message.content.strip()


def infer_target_app(instruction: str, steps: List[Dict] | None = None) -> str:
    instruction_lower = instruction.lower()
    app_aliases = [
        ("notepad", ["notepad"]),
        ("calculator", ["calculator", "calc"]),
        ("chrome", ["chrome", "google chrome", "browser"]),
        ("edge", ["edge", "microsoft edge"]),
        ("explorer", ["explorer", "file explorer"]),
    ]

    for app_name, aliases in app_aliases:
        if any(alias in instruction_lower for alias in aliases):
            return app_name

    for step in steps or []:
        app_name = str(step.get("app", "")).strip().lower()
        for canonical_name, aliases in app_aliases:
            if app_name == canonical_name or any(alias in app_name for alias in aliases):
                return canonical_name

    return ""


def verify_post_task_state(instruction: str, steps: List[Dict]) -> Dict[str, Any]:
    core_path = os.path.join(os.path.dirname(__file__), "..", "core")
    if core_path not in sys.path:
        sys.path.insert(0, core_path)

    try:
        from os_control import get_open_windows, focus_window
    except Exception as e:
        return {
            "verified": False,
            "target_app": "",
            "required": "unknown",
            "exists": False,
            "focused": False,
            "reason": f"Verification unavailable: {e}",
            "windows": [],
        }

    target_app = infer_target_app(instruction, steps)
    windows = get_open_windows()
    has_typing = any(step.get("action") == "type" for step in steps)
    has_launch_success = any(
        step.get("action") == "open_app" and bool(step.get("result", {}).get("success"))
        for step in steps
    )
    has_ocr_evidence = any(
        step.get("action") == "read_screen"
        and bool(str(step.get("result", {}).get("extracted", "")).strip())
        for step in steps
    )

    title_aliases = {
        "notepad": ["notepad"],
        "calculator": ["calculator", "calc"],
        "chrome": ["chrome", "google chrome"],
        "edge": ["edge", "microsoft edge"],
        "explorer": ["explorer", "file explorer"],
    }
    ignored_titles = [
        "visual studio code",
        "settings",
        "program manager",
        "chatgpt",
        "claude",
        "windows input experience",
    ]

    def _match_title(app_name: str) -> str:
        aliases = title_aliases.get(app_name, [app_name])
        for window_title in windows:
            window_lower = window_title.lower()
            if any(ignored in window_lower for ignored in ignored_titles):
                continue
            if any(alias in window_lower for alias in aliases):
                return window_title
        return ""

    matched_title = _match_title(target_app) if target_app else ""
    required = "exists_and_focused" if has_typing else "exists"

    exists = bool(matched_title)
    focused = False
    focus_result = None
    reason = ""

    if target_app:
        if target_app == "chrome":
            browser_title = matched_title or next(
                (
                    window_title
                    for window_title in windows
                    if window_title.strip()
                    and not any(ignored in window_title.lower() for ignored in ignored_titles)
                ),
                "",
            )

            exists = bool(browser_title)
            if has_typing:
                focus_target = browser_title or target_app
                focus_result = focus_window(focus_target)
                focused = bool(focus_result and focus_result.get("success"))
                if exists and focused:
                    reason = f"{focus_target} browser window exists and was focusable"
                elif not exists:
                    reason = "Chrome browser verification lacked launch/OCR evidence"
                else:
                    reason = f"{focus_target} browser window found but could not be focused"
            else:
                focused = exists
                reason = (
                    f"{browser_title} browser window found after execution"
                    if exists
                    else "Chrome browser verification failed"
                )
        else:
            exists = bool(matched_title)
            if has_typing:
                focus_result = focus_window(matched_title or target_app)
                focused = bool(focus_result and focus_result.get("success"))
                if exists and focused:
                    reason = f"{matched_title or target_app} window exists and was focusable"
                elif not exists:
                    reason = f"{target_app} window not found after execution"
                else:
                    reason = f"{matched_title or target_app} window found but could not be focused"
            else:
                focused = exists
                reason = (
                    f"{matched_title or target_app} window found after execution"
                    if exists
                    else f"{target_app} window not found after execution"
                )
    else:
        reason = "Could not infer target application from instruction"

    verified = exists and ((focused and has_typing) or not has_typing)

    return {
        "verified": verified,
        "target_app": target_app,
        "required": required,
        "exists": exists,
        "focused": focused,
        "reason": reason,
        "windows": windows,
        "focus_result": focus_result,
    }


def simulate_execution(steps: List[Dict]) -> List[Dict]:
    results = []
    for step in steps:
        time.sleep(0.3)
        results.append({
            "step_number": step.get("step_number", 1),
            "description": step.get("description", ""),
            "action": step.get("action", ""),
            "status": "completed",
            "result": {"success": True},
            "timestamp": datetime.utcnow().isoformat(),
            "duration": 0.3,
        })
    return results


def execute_task(instruction: str) -> Dict[str, Any]:
    core_path = os.path.join(os.path.dirname(__file__), "..", "core")
    if core_path not in sys.path:
        sys.path.insert(0, core_path)

    instruction = preprocess_instruction(instruction)
    start_time = time.time()

    try:
        from agent import PerceptAgent
    except Exception as e:
        return {
            "status": "failed",
            "steps": [],
            "error": f"Engine load failed: {e}",
            "execution_time": 0,
        }

    agent = PerceptAgent(instruction)
    executed_steps = []
    last_extracted = ""
    max_steps = 12
    step_count = 0

    screen = get_screen_context()
    steps = plan_from_screen(instruction, screen, [])

    if not steps:
        return {
            "status": "failed",
            "steps": [],
            "error": "Could not plan task",
            "execution_time": 0,
        }

    step_index = 0

    while step_index < len(steps) and step_count < max_steps:
        step = steps[step_index]
        step_start = time.time()
        action = step.get("action", "")
        description = step.get("description", "")
        step_count += 1

        print(f"  Step {step_count}: [{action}] {description}")

        if action == "read_screen":
            time.sleep(1.0)
            screen_text = get_screen_context()
            goal = step.get("find", instruction)
            extracted = extract_from_screen(goal, screen_text)
            if extracted != "NOT_FOUND":
                last_extracted = extracted
                print(f"  Extracted: {last_extracted[:120]}")
            executed_steps.append({
                "step_number": len(executed_steps) + 1,
                "description": f"Read screen: {last_extracted[:80] or 'scanning...'}",
                "action": "read_screen",
                "status": "completed",
                "result": {"success": True, "extracted": last_extracted},
                "timestamp": datetime.utcnow().isoformat(),
                "duration": round(time.time() - step_start, 2),
            })
            step_index += 1
            continue

        if action == "wait":
            wait_time = float(step.get("wait", 1.0))
            time.sleep(wait_time)
            executed_steps.append({
                "step_number": len(executed_steps) + 1,
                "description": description,
                "action": "wait",
                "status": "completed",
                "result": {"success": True},
                "timestamp": datetime.utcnow().isoformat(),
                "duration": round(time.time() - step_start, 2),
            })
            step_index += 1
            continue

        if action == "type":
            text = step.get("text", "")
            text_lower = text.lower()
            is_placeholder = (
                not text or
                text in ["{{extract}}", "{extract}", "$extract", "extracted_text"] or
                "placeholder" in text_lower or
                "title" in text_lower and len(text) < 20 or
                "content" in text_lower and len(text) < 20
            )
            if is_placeholder and last_extracted:
                step = {**step, "text": last_extracted}
                print(f"  Injecting extracted: {last_extracted[:80]}")

        try:
            result = agent.execute_step(step)
        except Exception as e:
            result = {"success": False, "error": str(e)}
            print(f"  Step error: {e}")

        success = result and result.get("success") is not False

        executed_steps.append({
            "step_number": len(executed_steps) + 1,
            "description": description,
            "action": action,
            "status": "completed" if success else "failed",
            "result": result or {"success": True},
            "timestamp": datetime.utcnow().isoformat(),
            "duration": round(time.time() - step_start, 2),
        })

        if action in ("navigate_url", "open_app") and success:
            nav_wait = float(step.get("wait", 2.5))
            print(f"  Waiting {nav_wait}s then re-perceiving...")
            time.sleep(nav_wait)

            fresh_screen = get_screen_context()
            remaining_goal_steps = steps[step_index + 1:]

            if remaining_goal_steps:
                print("  Replanning from live screen...")
                new_steps = plan_from_screen(
                    instruction,
                    fresh_screen,
                    executed_steps,
                )
                if new_steps:
                    steps = steps[:step_index + 1] + new_steps
                    print(f"  New plan: {len(new_steps)} steps from screen")

        time.sleep(0.2)
        step_index += 1

    execution_time = round(time.time() - start_time, 2)
    all_ok = all(s["status"] == "completed" for s in executed_steps)
    verification = verify_post_task_state(instruction, executed_steps)
    if not all_ok:
        final_status = "failed"
    elif verification["verified"]:
        final_status = "completed"
    else:
        final_status = "unverified"

    print(
        "  Verification: "
        f"target={verification['target_app'] or 'unknown'} "
        f"exists={verification['exists']} "
        f"focused={verification['focused']} "
        f"status={final_status}"
    )

    return {
        "status": final_status,
        "steps": executed_steps,
        "execution_time": execution_time,
        "error": None if final_status == "completed" else verification["reason"],
        "verification": verification,
    }


def execute_task_stream(instruction: str):
    """
    Generator version of execute_task.
    Yields step dicts as they complete instead of returning all at once.
    Used by the SSE streaming endpoint.
    """
    core_path = os.path.join(os.path.dirname(__file__), "..", "core")
    if core_path not in sys.path:
        sys.path.insert(0, core_path)

    instruction = preprocess_instruction(instruction)
    start_time = time.time()

    yield {
        "type": "session_start",
        "instruction": instruction,
        "timestamp": datetime.utcnow().isoformat(),
    }

    try:
        from agent import PerceptAgent
    except Exception as e:
        yield {"type": "error", "message": f"Engine load failed: {e}"}
        return

    screen = get_screen_context()
    steps = plan_from_screen(instruction, screen, [])

    if not steps:
        yield {"type": "error", "message": "Could not plan task"}
        return

    yield {
        "type": "plan",
        "steps": [
            {
                "step_number": i + 1,
                "description": s.get("description", ""),
                "action": s.get("action", ""),
                "status": "pending",
            }
            for i, s in enumerate(steps)
        ],
    }

    agent = PerceptAgent(instruction)
    executed_steps = []
    last_extracted = ""
    max_steps = 12
    step_count = 0
    step_index = 0

    while step_index < len(steps) and step_count < max_steps:
        step = steps[step_index]
        step_start = time.time()
        action = step.get("action", "")
        description = step.get("description", "")
        step_count += 1

        yield {
            "type": "step_start",
            "step_number": step_count,
            "description": description,
            "action": action,
        }

        if action == "read_screen":
            time.sleep(1.0)
            screen_text = get_screen_context()
            goal = step.get("find", instruction)
            extracted = extract_from_screen(goal, screen_text)
            if extracted != "NOT_FOUND":
                last_extracted = extracted

            duration = round(time.time() - step_start, 2)
            step_result = {
                "step_number": len(executed_steps) + 1,
                "description": f"Read screen: {last_extracted[:80] or 'scanning...'}",
                "action": "read_screen",
                "status": "completed",
                "result": {"success": True, "extracted": last_extracted},
                "timestamp": datetime.utcnow().isoformat(),
                "duration": duration,
            }
            executed_steps.append(step_result)
            yield {"type": "step_complete", "step": step_result}
            step_index += 1
            continue

        if action == "wait":
            wait_time = float(step.get("wait", 1.0))
            time.sleep(wait_time)
            duration = round(time.time() - step_start, 2)
            step_result = {
                "step_number": len(executed_steps) + 1,
                "description": description,
                "action": "wait",
                "status": "completed",
                "result": {"success": True},
                "timestamp": datetime.utcnow().isoformat(),
                "duration": duration,
            }
            executed_steps.append(step_result)
            yield {"type": "step_complete", "step": step_result}
            step_index += 1
            continue

        if action == "type":
            text = step.get("text", "")
            text_lower = text.lower()
            is_placeholder = (
                not text or
                text in ["{{extract}}", "{extract}", "$extract", "extracted_text"] or
                "placeholder" in text_lower or
                "title" in text_lower and len(text) < 20 or
                "content" in text_lower and len(text) < 20
            )
            if is_placeholder and last_extracted:
                step = {**step, "text": last_extracted}

        try:
            result = agent.execute_step(step)
        except Exception as e:
            result = {"success": False, "error": str(e)}

        success = result and result.get("success") is not False
        duration = round(time.time() - step_start, 2)

        step_result = {
            "step_number": len(executed_steps) + 1,
            "description": description,
            "action": action,
            "status": "completed" if success else "failed",
            "result": result or {"success": True},
            "timestamp": datetime.utcnow().isoformat(),
            "duration": duration,
        }
        executed_steps.append(step_result)
        yield {"type": "step_complete", "step": step_result}

        if action in ("navigate_url", "open_app") and success:
            nav_wait = float(step.get("wait", 2.5))
            yield {"type": "log", "message": f"Waiting {nav_wait}s for load..."}
            time.sleep(nav_wait)

            fresh_screen = get_screen_context()
            remaining = steps[step_index + 1:]
            if remaining:
                new_steps = plan_from_screen(instruction, fresh_screen, executed_steps)
                if new_steps:
                    steps = steps[:step_index + 1] + new_steps
                    yield {
                        "type": "replan",
                        "message": f"Replanned {len(new_steps)} steps from screen",
                    }

        time.sleep(0.2)
        step_index += 1

    execution_time = round(time.time() - start_time, 2)
    all_ok = all(s["status"] == "completed" for s in executed_steps)
    verification = verify_post_task_state(instruction, executed_steps)
    if not all_ok:
        final_status = "failed"
    elif verification["verified"]:
        final_status = "completed"
    else:
        final_status = "unverified"

    print(
        "  Verification: "
        f"target={verification['target_app'] or 'unknown'} "
        f"exists={verification['exists']} "
        f"focused={verification['focused']} "
        f"status={final_status}"
    )

    yield {
        "type": "complete",
        "status": final_status,
        "execution_time": execution_time,
        "total_steps": len(executed_steps),
        "verification": verification,
    }
