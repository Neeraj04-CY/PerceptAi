import time
import json
from datetime import datetime
from typing import List, Dict, Any
from groq import Groq
from config import config

client = Groq(api_key=config.GROQ_API_KEY)

def plan_task(instruction: str) -> List[Dict]:
    """Convert plain English to executable steps using Groq"""
    response = client.chat.completions.create(
        model="llama-3.3-70b-versatile",
        messages=[{
            "role": "user",
            "content": f"""You are a computer automation planner.
            
Convert this instruction into executable steps.
Instruction: {instruction}

Return ONLY valid JSON array:
[
  {{
    "step_number": 1,
    "description": "what this step does",
    "action": "open_app|navigate_url|click|type|press|wait",
    "app": "app name if opening",
    "url": "url if navigating",
    "find": "text to find if clicking",
    "text": "text to type if typing",
    "key": "key if pressing",
    "wait": 1.0
  }}
]

Return ONLY the JSON array. Max 8 steps."""
        }],
        max_tokens=800
    )
    
    raw = response.choices[0].message.content.strip()
    raw = raw.replace("```json", "").replace("```", "").strip()
    
    try:
        return json.loads(raw)
    except:
        return []

def simulate_execution(steps: List[Dict]) -> List[Dict]:
    """
    In development: simulate execution with realistic timing.
    In production: this calls the actual PerceptAI engine on a cloud VM.
    """
    results = []
    
    for step in steps:
        start = time.time()
        time.sleep(0.5)  # Simulate execution time
        
        results.append({
            "step_number": step.get("step_number", 1),
            "description": step.get("description", ""),
            "action": step.get("action", ""),
            "status": "completed",
            "result": {"success": True},
            "timestamp": datetime.utcnow().isoformat(),
            "duration": round(time.time() - start, 2)
        })
    
    return results

def execute_task(instruction: str) -> Dict[str, Any]:
    """Full execution pipeline"""
    start_time = time.time()
    
    # Plan the task
    steps = plan_task(instruction)
    
    if not steps:
        return {
            "status": "failed",
            "steps": [],
            "error": "Could not plan task",
            "execution_time": 0
        }
    
    # Execute steps
    executed_steps = simulate_execution(steps)
    
    execution_time = round(time.time() - start_time, 2)
    
    return {
        "status": "completed",
        "steps": executed_steps,
        "execution_time": execution_time,
        "error": None
    }