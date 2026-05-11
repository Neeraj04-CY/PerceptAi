import time
import sys
import os

sys.path.append(".")

# Test 1: Just EasyOCR
print("Testing EasyOCR speed...")
start = time.time()
import easyocr
reader = easyocr.Reader(["en"], gpu=False, verbose=False)
print(f"EasyOCR load time: {time.time() - start:.1f}s")

start = time.time()
result = reader.readtext("temp_screen.png")
print(f"EasyOCR read time: {time.time() - start:.1f}s")

# Test 2: Just Groq API
print("\nTesting Groq API speed...")
from groq import Groq
from dotenv import load_dotenv

load_dotenv()
client = Groq(api_key=os.getenv("GROQ_API_KEY"))

start = time.time()
response = client.chat.completions.create(
    model="llama-3.3-70b-versatile",
    messages=[{"role": "user", "content": "say hi"}],
    max_tokens=10,
)
print(f"Groq text API time: {time.time() - start:.1f}s")
