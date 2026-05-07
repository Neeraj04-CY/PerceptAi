import sys
import time
import os
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from core.agent import PerceptAgent

print("PerceptAI Agent Demo")
print("Open Chrome on Google homepage")
print("Switching in 5 seconds...")
time.sleep(5)

agent = PerceptAgent("Search Google for PerceptAI and open first result")

steps = [
    {
        "description": "Click the search bar",
        "action": "click",
        "find": "Search Google or type a URL",
        "wait": 0.8
    },
    {
        "description": "Type search query",
        "action": "type",
        "text": "PerceptAI autonomous screen agent",
        "wait": 0.5
    },
    {
        "description": "Press Enter to search",
        "action": "press",
        "key": "enter",
        "wait": 2.0
    }
]

success = agent.run(steps)
print(f"\nAgent Success: {success}")