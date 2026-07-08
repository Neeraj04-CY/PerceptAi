import os
from pathlib import Path
from dotenv import load_dotenv

env_path = Path(__file__).resolve().parent / ".env"
load_dotenv(env_path)

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
    # Secrets vault encryption key; falls back to JWT_SECRET so a single
    # secret works out of the box. Set separately in production.
    SECRETS_KEY = os.getenv("SECRETS_KEY") or os.getenv("JWT_SECRET", "change-this-secret")
    # Server secret used to derive per-runner work-order signing keys. Falls
    # back to SECRETS_KEY out of the box; set separately in production.
    RUNNER_SIGNING_KEY = os.getenv("RUNNER_SIGNING_KEY") or os.getenv("SECRETS_KEY") \
        or os.getenv("JWT_SECRET", "change-this-secret")
    # Lease a runner holds on a claimed session; renewed by heartbeat. A run
    # whose runner stops heartbeating past this is reclaimed (see runners.py).
    RUNNER_LEASE_SECONDS = int(os.getenv("RUNNER_LEASE_SECONDS", "90"))
    # Max times a session may be claimed before it is dead-lettered instead of
    # requeued — bounds retries so a run never bounces between broken runners.
    RUNNER_MAX_ATTEMPTS = int(os.getenv("RUNNER_MAX_ATTEMPTS", "3"))
    # Scheduled workflows execute on THIS host's desktop. Off by default;
    # enable only on a machine dedicated to running automations.
    ENABLE_SCHEDULER = os.getenv("ENABLE_SCHEDULER", "false").lower() in ("1", "true", "yes")
    
    # Free tier limits
    FREE_MONTHLY_EXECUTIONS = 100

config = Config()