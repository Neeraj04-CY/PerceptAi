import json
from groq import Groq
from .config import get_api_key


def plan_task(instruction, screen_context, open_windows=None):
    """
    Takes plain English instruction.
    Returns executable steps including OS-level actions.
    """
    windows_context = ""
    if open_windows:
        windows_context = f"\nCurrently open windows: {', '.join(open_windows[:10])}"

    prompt = f"""You are a computer automation planner for Windows.

Current screen elements:
{screen_context}
{windows_context}

User instruction: {instruction}

Return ONLY valid JSON with this exact structure:
{{
  "task": "overall task description",
  "steps": [
    {{
      "step_number": 1,
      "description": "what this step does",
      "action": "open_app|navigate_url|focus_window|click|type|press|wait",
      "app": "app name (for open_app)",
      "url": "full url (for navigate_url)",
      "window": "window title keyword (for focus_window)",
      "find": "exact text to find on screen (for click)",
      "text": "text to type (for type)",
      "key": "key name (for press)",
      "wait": 1.0
    }}
  ]
}}

Available actions:
- open_app: Opens an application (chrome, notepad, calculator)
- navigate_url: Opens a URL in browser
- focus_window: Brings existing window to front
- click: Clicks element found by text on screen
- type: Types text into focused element
- press: Presses keyboard key or hotkey combo (enter, tab, escape, ctrl+s, alt+d)
- wait: Waits specified seconds

Rules:
- Always open or focus the right app FIRST before clicking anything
- Use navigate_url to go to websites instead of clicking address bar
- For Save/Save As dialogs, prefer hotkeys: press ctrl+s, then press alt+d to focus address bar, type full path (e.g. %USERPROFILE%\Desktop), press enter
- Keep steps simple and atomic
- Maximum 10 steps

Return ONLY JSON. No markdown. No explanation."""

    client = Groq(api_key=get_api_key())
    response = client.chat.completions.create(
        model="llama-3.3-70b-versatile",
        messages=[{"role": "user", "content": prompt}],
        max_tokens=1000,
    )

    raw = response.choices[0].message.content.strip()
    raw = raw.replace("```json", "").replace("```", "").strip()

    try:
        return json.loads(raw)
    except json.JSONDecodeError:
        return {"task": instruction, "steps": [], "error": raw}
