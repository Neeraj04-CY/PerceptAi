import base64
import json
import time
from pathlib import Path
from PIL import ImageGrab, Image
import numpy as np
import easyocr
from groq import Groq
from .config import get_api_key

# Absolute path for temp screenshot — works from any directory
TEMP_SCREENSHOT = str(Path(__file__).parent.parent / "temp_screen.png")

# Global instances — loaded once per session
_reader = None
_client = None
_fast_cache = {
    "timestamp": 0.0,
    "region": None,
    "result": None,
}


def get_reader():
    """Lazy load EasyOCR to avoid repeated model loads."""
    global _reader
    if _reader is None:
        print("  Loading perception engine...")
        _reader = easyocr.Reader(["en"], gpu=False, verbose=False)
        print("  Perception engine ready.")
    return _reader


def get_client():
    """Lazy load Groq client once per session."""
    global _client
    if _client is None:
        _client = Groq(api_key=get_api_key())
    return _client


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


def _prepare_ocr_image(image, max_side=960):
    """Downscale image for faster OCR while preserving aspect ratio."""
    width, height = image.size
    scale = max(width, height) / float(max_side)
    if scale <= 1:
        return image
    new_size = (int(width / scale), int(height / scale))
    return image.resize(new_size, Image.BILINEAR)


def perceive(region=None):
    screenshot = capture_screen(region)

    ocr_image = _prepare_ocr_image(screenshot)
    ocr_results = get_reader().readtext(np.array(ocr_image))

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
                "bottom_right": [int(bbox[2][0]), int(bbox[2][1])],
            },
        }
        text_blocks.append(block)
        ocr_map[text.lower().strip()] = {"x": x, "y": y}

    image_data = encode_image(TEMP_SCREENSHOT)

    response = get_client().chat.completions.create(
        model="meta-llama/llama-4-scout-17b-16e-instruct",
        messages=[
            {
                "role": "user",
                "content": [
                    {
                        "type": "image_url",
                        "image_url": {
                            "url": f"data:image/png;base64,{image_data}"
                        },
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
IMPORTANT: Use exact visible text. Return ONLY JSON.""",
                    },
                ],
            }
        ],
        max_tokens=1500,
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
        "timestamp": time.time(),
    }


def perceive_fast(region=None, force_refresh=False):
    """
    OCR-only perception. Use for simple element finding tasks.
    No Vision API call.
    """
    now = time.time()
    if (
        not force_refresh
        and _fast_cache["result"] is not None
        and _fast_cache["region"] == region
        and (now - _fast_cache["timestamp"]) < 0.8
    ):
        return _fast_cache["result"]

    screenshot = capture_screen(region)

    ocr_image = _prepare_ocr_image(screenshot)
    ocr_results = get_reader().readtext(np.array(ocr_image))

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
                "bottom_right": [int(bbox[2][0]), int(bbox[2][1])],
            },
        }
        text_blocks.append(block)
        ocr_map[text.lower().strip()] = {"x": x, "y": y}

    result = {
        "text_blocks": text_blocks,
        "vision": {"elements": [], "page_context": "unknown"},
        "screenshot_path": TEMP_SCREENSHOT,
        "timestamp": now,
        "mode": "fast",
    }

    _fast_cache["timestamp"] = now
    _fast_cache["region"] = region
    _fast_cache["result"] = result

    return result


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
                "clickable": True,
            }

    return None
