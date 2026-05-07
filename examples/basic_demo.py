import sys
import time
import os
# Ensure project root is on sys.path regardless of cwd
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from core.perception import perceive, find_element
from core.action import click, type_text

print("PerceptAI - Chrome Test")
print("=" * 40)
print("Switch to Chrome NOW! 3 seconds...")
time.sleep(3)

result = perceive()

print("\nALL TEXT FOUND ON SCREEN:")
for block in result["text_blocks"]:
    pos = block["position"]
    print(f"  '{block['text']}' → x:{pos['x']}, y:{pos['y']} (conf: {block['confidence']})")

print("\nSEARCHING FOR CHROME ELEMENTS...")

# Things that should exist on Google homepage
targets = [
    "Google",
    "Search Google or type a URL", 
    "Youtube",
    "Gmail",
    "Images",
    "Search"
]

for query in targets:
    found = find_element(result, query)
    if found:
        pos = found["position"]
        print(f"  ✓ FOUND '{query}' at x:{pos['x']}, y:{pos['y']}")
    else:
        print(f"  ✗ MISSED '{query}'")

# Now actually search something on Google
print("\nATTEMPTING: Click search bar and search for PerceptAI...")

search_bar = find_element(result, "Search Google or type a URL")
if not search_bar:
    search_bar = find_element(result, "Search")

if search_bar:
    pos = search_bar["position"]
    print(f"Found search bar at x:{pos['x']}, y:{pos['y']}")
    
    click(pos['x'], pos['y'])
    time.sleep(0.5)
    
    type_text("PerceptAI autonomous agent")
    time.sleep(0.3)
    
    import pyautogui
    pyautogui.press('enter')
    
    print("Search executed successfully!")
else:
    print("Search bar not found — printing all text for debugging")
    for block in result["text_blocks"]:
        print(f"  '{block['text']}'")

print("\nChrome test complete.")
