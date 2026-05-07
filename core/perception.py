import os
import base64
import json
import time
from pathlib import Path
from PIL import ImageGrab
import easyocr
from groq import Groq
from dotenv import load_dotenv

load_dotenv()

# Absolute path for temp screenshot — works from any directory
TEMP_SCREENSHOT = str(Path(__file__).parent.parent / "temp_screen.png")

reader = easyocr.Reader(['en'], gpu=False)
client = Groq(api_key=os.getenv("GROQ_API_KEY"))


def capture_screen(region=None):
    screenshot = ImageGrab.grab(bbox=region)
    screenshot.save(TEMP_SCREENSHOT)
    return screenshot


def encode_image(image_path):
    with open(image_path, "rb") as f:
        return base64.b64encode(f.read()).decode("utf-8")


def get_element_center(bbox):
    top_left = bbox[0]
    bottom_right = bbox[2]
    x = int((top_left[0] + bottom_right[0]) / 2)
    y = int((top_left[1] + bottom_right[1]) / 2)
    return x, y


def perceive(region=None):
    capture_screen(region)

    ocr_results = reader.readtext(TEMP_SCREENSHOT)
    
    text_blocks = []
    ocr_map = {}
    
    for result in ocr_results:
        bbox, text, confidence = result
        x, y = get_element_center(bbox)
        block = {
            "text": text,
            "confidence": round(confidence, 3),
            "position": {"x": x, "y": y},
            "bounds": {
                "top_left": [int(bbox[0][0]), int(bbox[0][1])],
                "bottom_right": [int(bbox[2][0]), int(bbox[2][1])]
            }
        }
        text_blocks.append(block)
        ocr_map[text.lower().strip()] = {"x": x, "y": y}

    image_data = encode_image(TEMP_SCREENSHOT)

    response = client.chat.completions.create(
        model="meta-llama/llama-4-scout-17b-16e-instruct",
        messages=[
            {
                "role": "user",
                "content": [
                    {
                        "type": "image_url",
                        "image_url": {
                            "url": f"data:image/png;base64,{image_data}"
                        }
                    },
                    {
                        "type": "text",
                                                "text": """Analyze this screenshot. Return ONLY valid JSON:
{
  "elements": [
    {
      "id": "el_001",
      "type": "button|input|dropdown|text|image|icon|table|link|menu",
      "text": "exact visible text of this element",
      "clickable": true,
      "description": "what this element does"
    }
  ],
  "page_context": "what app or page is this",
  "primary_action": "main thing user can do here"
}
IMPORTANT: Use exact visible text. Return ONLY JSON."""
                    }
                ]
            }
        ],
        max_tokens=1500
    )

    raw = response.choices[0].message.content.strip()
    raw = raw.replace("```json", "").replace("```", "").strip()

    try:
        vision_data = json.loads(raw)
    except json.JSONDecodeError:
        vision_data = {"elements": [], "raw_response": raw}

    # Merge OCR coordinates into vision elements
    if "elements" in vision_data:
        for element in vision_data["elements"]:
            element_text = element.get("text", "").lower().strip()
            
            # Direct match
            if element_text in ocr_map:
                element["position"] = ocr_map[element_text]
                element["confidence"] = next(
                    (
                        block["confidence"]
                        for block in text_blocks
                        if block["text"].lower().strip() == element_text
                    ),
                    0.0,
                )
            else:
                # Partial match
                for ocr_text, pos in ocr_map.items():
                    if element_text in ocr_text or ocr_text in element_text:
                        element["position"] = pos
                        element["confidence"] = next(
                            (
                                block["confidence"]
                                for block in text_blocks
                                if block["text"].lower().strip() == ocr_text
                            ),
                            0.0,
                        )
                        break
                else:
                    element["position"] = {"x": -1, "y": -1}
                    element["confidence"] = 0.0

    return {
        "text_blocks": text_blocks,
        "vision": vision_data,
        "screenshot_path": TEMP_SCREENSHOT,
        "timestamp": time.time()
    }


def find_element(perception_result, query):
    """Find a specific element by text or description"""
    query_lower = query.lower()
    elements = perception_result.get("vision", {}).get("elements", [])
    
    for element in elements:
        text = element.get("text", "").lower()
        desc = element.get("description", "").lower()
        if query_lower in text or query_lower in desc:
            return element
    
    # Also search text blocks
    for block in perception_result.get("text_blocks", []):
        if query_lower in block["text"].lower():
            return {
                "text": block["text"],
                "position": block["position"],
                "confidence": block.get("confidence", 0.0),
                "type": "text",
                "clickable": True
            }
    
    return None
