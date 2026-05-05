import os
import base64
import json
from PIL import ImageGrab, Image
import easyocr
from groq import Groq
from dotenv import load_dotenv

load_dotenv()

reader = easyocr.Reader(['en'], gpu=False)
client = Groq(api_key=os.getenv("GROQ_API_KEY"))

def capture_screen(region=None):
    screenshot = ImageGrab.grab(bbox=region)
    screenshot.save("temp_screen.png")
    return screenshot

def encode_image(image_path):
    with open(image_path, "rb") as f:
        return base64.b64encode(f.read()).decode("utf-8")

def perceive(region=None):
    capture_screen(region)
    
    ocr_results = reader.readtext("temp_screen.png")
    text_blocks = [
        {
            "text": result[1],
            "confidence": round(result[2], 3),
            "position": {
                "top_left": result[0][0],
                "bottom_right": result[0][2]
            }
        }
        for result in ocr_results
    ]

    image_data = encode_image("temp_screen.png")
    
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
                        "text": """Analyze this screenshot and return ONLY valid JSON with this structure:
{
  "elements": [
    {
      "id": "el_001",
      "type": "button|input|dropdown|text|image|icon|table|link",
      "text": "visible text if any",
      "position": {"x": 0, "y": 0},
      "clickable": true,
      "description": "what this element does"
    }
  ],
  "page_context": "what app or page is this",
  "primary_action": "what is the main thing a user can do here"
}
Return ONLY the JSON. No explanation."""
                    }
                ]
            }
        ],
        max_tokens=1500
    )

    raw = response.choices[0].message.content.strip()
    
    try:
        vision_data = json.loads(raw)
    except json.JSONDecodeError:
        vision_data = {"elements": [], "raw_response": raw}

    return {
        "text_blocks": text_blocks,
        "vision": vision_data,
        "screenshot_path": "temp_screen.png"
    }
