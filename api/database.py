from supabase import create_client, Client
from config import config

_client: Client = None
_service_client: Client = None

def get_db() -> Client:
    global _client
    if _client is None:
        _client = create_client(config.SUPABASE_URL, config.SUPABASE_KEY)
    return _client

def get_service_db() -> Client:
    global _service_client
    if _service_client is None:
        _service_client = create_client(
            config.SUPABASE_URL,
            config.SUPABASE_SERVICE_KEY
        )
    return _service_client