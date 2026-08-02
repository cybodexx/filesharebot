import os
from dotenv import load_dotenv

# Load .env file if present (local dev). Render/production injects env vars directly.
load_dotenv(".env", override=False)
load_dotenv("config.env", override=False)

def str_to_bool(val: str) -> bool:
    if not val:
        return False
    return val.lower() in ("true", "1", "t", "y", "yes")

def safe_int(val, default: int = 0) -> int:
    if val is None:
        return default
    try:
        return int(val)
    except (ValueError, TypeError):
        return default

class Config:
    NAME: str = os.environ.get("APP_NAME", "vidshare.in")

    PORT: int = safe_int(os.environ.get("PORT"), 5000)
    BIND_ADDRESS: str = os.environ.get("BIND_ADDRESS", "0.0.0.0")

    DATABASE_URL: str = os.environ.get("DATABASE_URL", "")

    API_ID: int = safe_int(os.environ.get("API_ID"), 0)
    API_HASH: str = os.environ.get("API_HASH", "")
    BOT_TOKEN: str = os.environ.get("BOT_TOKEN", "")
    BIN_CHANNEL: int = safe_int(os.environ.get("BIN_CHANNEL"), 0)

    MAX_FILE_SIZE_MB: int = safe_int(os.environ.get("MAX_FILE_SIZE_MB"), 2000)
    MAX_FILE_SIZE: int = MAX_FILE_SIZE_MB * 1024 * 1024

    LINK_EXPIRY_DAYS: int = safe_int(os.environ.get("LINK_EXPIRY_DAYS"), 10)
    DELETE_AFTER_DOWNLOAD: bool = str_to_bool(os.environ.get("DELETE_AFTER_DOWNLOAD", "False"))

    # Public domain — set this to your Render service URL (no trailing slash)
    # e.g. FQDN=thunder-file-share.onrender.com
    FQDN: str = os.environ.get("FQDN", "")
    HAS_SSL: bool = str_to_bool(os.environ.get("HAS_SSL", "True"))

    @classmethod
    def get_base_url(cls) -> str:
        fqdn = os.environ.get("FQDN", "")
        if fqdn:
            protocol = "https" if cls.HAS_SSL else "http"
            return f"{protocol}://{fqdn}"
        return ""

    @classmethod
    def validate_telegram_config(cls) -> bool:
        api_id = safe_int(os.environ.get("API_ID"), 0)
        api_hash = os.environ.get("API_HASH", "")
        bot_token = os.environ.get("BOT_TOKEN", "")
        bin_channel = safe_int(os.environ.get("BIN_CHANNEL"), 0)
        return all([api_id, api_hash, bot_token, bin_channel])

    @classmethod
    def debug_config(cls):
        api_id = os.environ.get("API_ID")
        api_hash = os.environ.get("API_HASH")
        bot_token = os.environ.get("BOT_TOKEN")
        bin_channel = os.environ.get("BIN_CHANNEL")
        print(f"   [DEBUG] API_ID: {'SET' if api_id else 'NOT SET'}")
        print(f"   [DEBUG] API_HASH: {'SET' if api_hash else 'NOT SET'}")
        print(f"   [DEBUG] BOT_TOKEN: {'SET' if bot_token else 'NOT SET'}")
        print(f"   [DEBUG] BIN_CHANNEL: {'SET' if bin_channel else 'NOT SET'}")
