import sys
import json
sys.path.append("..")

from core.perception import perceive
from core.action import click

print("PerceptAI - First Perception Test")
print("=" * 40)
print("Capturing your screen in 3 seconds...")

import time
time.sleep(3)

result = perceive()

print("\nTEXT FOUND ON SCREEN:")
for block in result["text_blocks"][:10]:
    print(f"  '{block['text']}' (confidence: {block['confidence']})")

print("\nVISION ANALYSIS:")
print(json.dumps(result["vision"], indent=2))

print("\nFirst perception complete.")
