import os
from dotenv import load_dotenv

load_dotenv("config.env")

def str_to_bool(val: str) -> bool:
    return val.lower() in ("true", "1", "t", "y", "yes")

def safe_int(val: str, default: int = 0) -> int:
    try:
        return int(val) if val else default
    except (ValueError, TypeError):
        return default

class Config:
    NAME: str = os.getenv("APP_NAME", "Thunder File Share")
    
    PORT: int = safe_int(os.getenv("PORT", "5000"), 5000)
    BIND_ADDRESS: str = os.getenv("BIND_ADDRESS", "0.0.0.0")
    
    DATABASE_URL: str = os.getenv("DATABASE_URL", "")
    
    API_ID: int = safe_int(os.getenv("API_ID", "0"), 0)
    API_HASH: str = os.getenv("API_HASH", "")
    BOT_TOKEN: str = os.getenv("BOT_TOKEN", "")
    BIN_CHANNEL: int = safe_int(os.getenv("BIN_CHANNEL", "0"), 0)
    
    MAX_FILE_SIZE_MB: int = safe_int(os.getenv("MAX_FILE_SIZE_MB", "2000"), 2000)
    MAX_FILE_SIZE: int = MAX_FILE_SIZE_MB * 1024 * 1024
    
    LINK_EXPIRY_DAYS: int = safe_int(os.getenv("LINK_EXPIRY_DAYS", "10"), 10)
    DELETE_AFTER_DOWNLOAD: bool = str_to_bool(os.getenv("DELETE_AFTER_DOWNLOAD", "False"))
    
    FQDN: str = os.getenv("FQDN", "")
    HAS_SSL: bool = str_to_bool(os.getenv("HAS_SSL", "True"))
    
    @classmethod
    def get_base_url(cls) -> str:
        if cls.FQDN:
            protocol = "https" if cls.HAS_SSL else "http"
            return f"{protocol}://{cls.FQDN}"
        return ""
    
    @classmethod
    def validate_telegram_config(cls) -> bool:
        return all([cls.API_ID, cls.API_HASH, cls.BOT_TOKEN, cls.BIN_CHANNEL])
