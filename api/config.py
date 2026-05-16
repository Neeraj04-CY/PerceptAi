import os
from dotenv import load_dotenv

load_dotenv()

class Config:
    SUPABASE_URL = os.getenv("SUPABASE_URL")
    SUPABASE_KEY = os.getenv("SUPABASE_KEY")
    SUPABASE_SERVICE_KEY = os.getenv("SUPABASE_SERVICE_KEY")
    JWT_SECRET = os.getenv("JWT_SECRET", "change-this-secret")
    JWT_ALGORITHM = "HS256"
    JWT_EXPIRE_HOURS = 24 * 7  # 7 days
    GROQ_API_KEY = os.getenv("GROQ_API_KEY")
    REDIS_URL = os.getenv("REDIS_URL")
    ENVIRONMENT = os.getenv("ENVIRONMENT", "development")
    
    # Free tier limits
    FREE_MONTHLY_EXECUTIONS = 100

config = Config()