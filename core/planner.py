import os
import json
from groq import Groq
from dotenv import load_dotenv

load_dotenv()
client = Groq(api_key=os.getenv("GROQ_API_KEY"))

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
- press: Presses keyboard key (enter, tab, escape, ctrl+c)
- wait: Waits specified seconds

Rules:
- Always open or focus the right app FIRST before clicking anything
- Use navigate_url to go to websites instead of clicking address bar
- Keep steps simple and atomic
- Maximum 10 steps

Return ONLY JSON. No markdown. No explanation."""

    response = client.chat.completions.create(
        model="llama-3.3-70b-versatile",
        messages=[{"role": "user", "content": prompt}],
        max_tokens=1000
    )
    
    raw = response.choices[0].message.content.strip()
    raw = raw.replace("```json", "").replace("```", "").strip()
    
    try:
        return json.loads(raw)
    except json.JSONDecodeError:
        return {"task": instruction, "steps": [], "error": raw}