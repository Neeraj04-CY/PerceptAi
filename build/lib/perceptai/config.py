import os
from dotenv import load_dotenv

load_dotenv()


def get_api_key():
    key = os.getenv("GROQ_API_KEY")
    if not key:
        raise EnvironmentError(
            "\n\nPerceptAI needs a Groq API key.\n"
            "Get one free at: https://console.groq.com\n"
            "Then set it: export GROQ_API_KEY=your_key\n"
            "Or create a .env file with: GROQ_API_KEY=your_key\n"
        )
    return key
