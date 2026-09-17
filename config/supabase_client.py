import os
import dotenv
from supabase import create_client, Client

dotenv.load_dotenv(override=True)

SUPABASE_URL = os.getenv("SUPABASE_URL", "")
SUPABASE_KEY = os.getenv("SUPABASE_KEY", "")

supabase: Client | None = None

if SUPABASE_URL and SUPABASE_KEY:
    try:
        supabase = create_client(SUPABASE_URL, SUPABASE_KEY)
    except Exception as e:
        import logging
        logging.getLogger(__name__).warning(f"Failed to initialize Supabase client: {e}")

def get_supabase() -> Client | None:
    return supabase
