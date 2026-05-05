# PerceptAI

An AI-powered perception core that captures your screen, extracts text via OCR, and analyzes UI elements using a vision language model.

## Usage

1. **Install requirements**
   ```bash
   cd perceptai
   pip install -r requirements.txt
   ```

2. **Create your `.env` file**
   ```bash
   cp .env .env.local   # or just edit .env directly
   ```
   Set your Groq API key inside `.env`:
   ```
   GROQ_API_KEY=your_actual_key_here
   ```
   > ⚠️ **Warning:** Never commit `.env` to version control. It is listed in `.gitignore` to protect your secrets.

3. **Run the demo**
   ```bash
   cd examples
   python basic_demo.py
   ```

## Structure

```
perceptai/
├── core/
│   ├── __init__.py
│   ├── perception.py   # Screen capture, OCR, and vision analysis
│   └── action.py       # Mouse/keyboard automation helpers
├── examples/
│   └── basic_demo.py   # Quick demo: perceive your screen
├── requirements.txt
└── .env                # API keys (never commit this)
```
