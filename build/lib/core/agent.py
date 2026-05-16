import time
import pyautogui
from core.perception import perceive, perceive_fast, find_element
from core.action import click, type_text, clear_and_type
from core.os_control import (
    open_app, focus_window, navigate_to_url, get_screen_size
)


class PerceptAgent:
    def __init__(self, task_description):
        self.task = task_description
        self.steps_taken = []
        self.max_retries = 3

    def perceive_and_find(self, query):
        """
        Try fast OCR perception first.
        Fall back to full vision only if needed.
        """
        for attempt in range(self.max_retries):
            result = perceive_fast()
            element = find_element(result, query)

            if element:
                pos = element["position"]
                if pos["x"] > 0 and pos["y"] > 0:
                    return element, result

            if attempt == 1:
                print("    Fast mode failed, trying full vision...")
                result = perceive()
                element = find_element(result, query)
                if element:
                    pos = element["position"]
                    if pos["x"] > 0 and pos["y"] > 0:
                        return element, result

            print(f"    Retry {attempt + 1}/{self.max_retries}: '{query}' not found")
            time.sleep(1)

        return None, None

    def verify_change(self, previous_text_count):
        """Re-perceive and check if screen changed"""
        time.sleep(0.8)
        result = perceive_fast(force_refresh=True)
        new_count = len(result.get("text_blocks", []))
        changed = new_count != previous_text_count
        return changed, result

    def verify_text_present(self, expected_text):
        """Re-perceive and confirm text appears on screen"""
        time.sleep(0.6)
        result = perceive_fast(force_refresh=True)
        found = find_element(result, expected_text)
        return found is not None, result

    def execute_step(self, step):
        action = step["action"]

        if action == "open_app":
            app = step.get("app", "")
            print(f"    Opening {app}...")
            result = open_app(app)
            time.sleep(2.5)
            return result

        elif action == "navigate_url":
            url = step.get("url", "")
            print(f"    Navigating to {url}...")
            result = navigate_to_url(url)
            time.sleep(2.5)
            return result

        elif action == "focus_window":
            window = step.get("window", "")
            print(f"    Focusing: {window}...")
            result = focus_window(window)
            time.sleep(0.8)
            return result

        elif action == "click":
            query = step.get("find", "")
            element, perception = self.perceive_and_find(query)

            if element:
                pos = element["position"]
                conf = element.get("confidence", 0)
                print(f"    Clicking '{query}' at x:{pos['x']}, y:{pos['y']} (conf:{conf})")
                result = click(pos["x"], pos["y"])
                time.sleep(0.5)
                return result
            else:
                # Smart fallback — click center of screen
                screen = get_screen_size()
                cx, cy = screen["width"] // 2, screen["height"] // 2
                print(f"    '{query}' not found — clicking screen center")
                return click(cx, cy)

        elif action == "type":
            text = step.get("text", "")
            print(f"    Typing: '{text}'")
            return type_text(text)

        elif action == "clear_type":
            text = step.get("text", "")
            print(f"    Clear and type: '{text}'")
            return clear_and_type(text)

        elif action == "press":
            key = step.get("key", "")
            print(f"    Pressing: '{key}'")
            if "+" in key:
                pyautogui.hotkey(*key.split("+"))
            else:
                pyautogui.press(key)
            return {"success": True, "key": key}

        elif action == "wait":
            wait_time = float(step.get("wait", 1.0))
            print(f"    Waiting {wait_time}s...")
            time.sleep(wait_time)
            return {"success": True}

        elif action == "scroll":
            direction = step.get("direction", "down")
            screen = get_screen_size()
            cx, cy = screen["width"] // 2, screen["height"] // 2
            from core.action import scroll
            return scroll(cx, cy, direction)

        return {"success": False, "error": f"Unknown action: {action}"}

    def run(self, steps, instruction=""):
        import time as _time
        from core.healer import diagnose_failure
        from core.memory import (
            remember_interface, remember_task,
            recall_element,
        )

        print(f"\nPerceptAgent: {self.task}")
        print("=" * 52)

        start_time = _time.time()
        current_steps = steps.copy()
        step_index = 0
        max_healing_attempts = 2

        while step_index < len(current_steps):
            step = current_steps[step_index]
            step_num = step.get("step_number", step_index + 1)
            desc = step.get("description", "")
            print(f"\nStep {step_num}: {desc}")

            result = self.execute_step(step)

            self.steps_taken.append({
                "step": step,
                "result": result,
            })

            failed = (
                result and
                result.get("success") is False
            )

            if failed:
                print(f"    ⚠ Step failed: {result.get('error', 'unknown')}")

                healing_attempt = 0
                healed = False

                while healing_attempt < max_healing_attempts:
                    print(f"    🔄 Healing attempt {healing_attempt + 1}...")

                    current_screen = perceive_fast(force_refresh=True)

                    context_lines = []
                    for block in current_screen["text_blocks"][:15]:
                        pos = block["position"]
                        context_lines.append(
                            f"'{block['text']}' at x:{pos['x']}, y:{pos['y']}"
                        )
                    context = "\n".join(context_lines)

                    recovery = diagnose_failure(
                        step,
                        context,
                        result.get("error", "step failed"),
                    )

                    print(f"    Diagnosis: {recovery.get('diagnosis')}")

                    recovery_steps = recovery.get("recovery_steps", [])

                    if recovery_steps and recovery.get("confidence", 0) > 0.5:
                        recovery_success = True
                        for r_step in recovery_steps:
                            r_result = self.execute_step(r_step)
                            if r_result and r_result.get("success") is False:
                                recovery_success = False
                                break

                        if recovery_success:
                            print("    ✓ Healed successfully")
                            healed = True
                            break

                    healing_attempt += 1
                    _time.sleep(1)

                if not healed:
                    print(f"    ✗ Could not heal step {step_num}. Continuing...")

            if result and result.get("success") is not False:
                try:
                    screen = perceive_fast()
                    app_context = screen.get("vision", {}).get("page_context", "unknown")
                    elements = [
                        {
                            "text": block.get("text", ""),
                            "type": "text",
                            "position": block.get("position", {}),
                            "confidence": block.get("confidence", 0.0),
                        }
                        for block in screen.get("text_blocks", [])
                    ]
                    if elements:
                        remember_interface(app_context, elements)
                except Exception:
                    pass

            wait_time = float(step.get("wait", 0.5))
            _time.sleep(wait_time)
            step_index += 1

        execution_time = _time.time() - start_time
        success = True

        if instruction:
            remember_task(
                instruction,
                steps,
                success,
                execution_time,
            )

        print(f"\n{'=' * 52}")
        print(f"Completed {len(self.steps_taken)} steps in {execution_time:.1f}s")
        return True