import os
import json
from groq import Groq
from dotenv import load_dotenv

load_dotenv()
client = Groq(api_key=os.getenv("GROQ_API_KEY"))


def diagnose_failure(failed_step, screen_context, error_info):
    """
    When a step fails, understand why and suggest recovery.
    Returns a recovery plan.
    """
    prompt = f"""You are an AI agent debugger for Windows automation.

A step in an automation task just failed.

Failed step:
{json.dumps(failed_step, indent=2)}

Error info: {error_info}

Current screen elements:
{screen_context}

Diagnose what went wrong and return ONLY valid JSON:
{{
  "diagnosis": "what went wrong in one sentence",
  "failure_type": "element_not_found|app_not_open|wrong_screen|timeout|other",
  "recovery_steps": [
    {{
      "step_number": 1,
      "description": "what to do to recover",
      "action": "open_app|navigate_url|focus_window|click|type|press|wait",
      "app": "",
      "url": "",
      "window": "",
      "find": "",
      "text": "",
      "key": "",
      "wait": 1.0
    }}
  ],
  "confidence": 0.8
}}

Return ONLY JSON. No explanation."""

    response = client.chat.completions.create(
        model="llama-3.3-70b-versatile",
        messages=[{"role": "user", "content": prompt}],
        max_tokens=800,
    )

    raw = response.choices[0].message.content.strip()
    raw = raw.replace("```json", "").replace("```", "").strip()

    try:
        return json.loads(raw)
    except json.JSONDecodeError:
        return {
            "diagnosis": "Unknown failure",
            "failure_type": "other",
            "recovery_steps": [],
            "confidence": 0.0,
        }
