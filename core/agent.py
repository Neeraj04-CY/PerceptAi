import time
import pyautogui
from core.perception import perceive, find_element
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
        for attempt in range(self.max_retries):
            result = perceive()
            element = find_element(result, query)
            if element:
                pos = element["position"]
                if pos["x"] > 0 and pos["y"] > 0:
                    return element, result
            print(f"    Retry {attempt + 1}/{self.max_retries}: '{query}' not found")
            time.sleep(1.2)
        return None, None

    def verify_change(self, previous_text_count):
        """Re-perceive and check if screen changed"""
        time.sleep(0.8)
        result = perceive()
        new_count = len(result.get("text_blocks", []))
        changed = new_count != previous_text_count
        return changed, result

    def verify_text_present(self, expected_text):
        """Re-perceive and confirm text appears on screen"""
        time.sleep(0.6)
        result = perceive()
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

    def run(self, steps):
        print(f"\nPerceptAgent: {self.task}")
        print("=" * 52)

        for step in steps:
            step_num = step.get("step_number", "?")
            desc = step.get("description", "")
            print(f"\nStep {step_num}: {desc}")

            before_count = len(perceive().get("text_blocks", []))
            result = self.execute_step(step)

            self.steps_taken.append({
                "step": step,
                "result": result
            })

            if result and result.get("success") is False:
                print(f"    ⚠ WARNING: {result.get('error', 'Unknown error')}")

            action = step.get("action", "")
            if action not in {"wait", "type", "clear_type"}:
                changed, _ = self.verify_change(before_count)
                if not changed:
                    print("    ✗ Verification failed: no screen change detected")
                    return False

            wait_time = float(step.get("wait", 0.5))
            time.sleep(wait_time)

        print(f"\n{'=' * 52}")
        print(f"Completed {len(self.steps_taken)} steps")
        return True