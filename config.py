import os
from pathlib import Path
from dotenv import load_dotenv

BASE_DIR = Path(__file__).resolve().parent
load_dotenv(BASE_DIR / ".env")

TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN", "").strip()

_allowed = os.getenv("ALLOWED_USER_IDS", "").strip()
ALLOWED_USER_IDS = [int(uid.strip()) for uid in _allowed.split(",") if uid.strip().isdigit()]

GEMINI_API_KEY = os.getenv("GEMINI_API_KEY", "").strip()

# Multiple Meta accounts - collect all non-empty tokens automatically
_raw_tokens = [
    os.getenv("META_ACCESS_TOKEN_1", "").strip(),
    os.getenv("META_ACCESS_TOKEN_2", "").strip(),
    os.getenv("META_ACCESS_TOKEN_3", "").strip(),
    os.getenv("META_ACCESS_TOKEN_4", "").strip(),
]
META_ACCESS_TOKENS = [t for t in _raw_tokens if t and "REPLACE_WITH" not in t]

# Legacy single-token support
META_ACCESS_TOKEN = os.getenv("META_ACCESS_TOKEN", "").strip()
if META_ACCESS_TOKEN and "EAAG..." not in META_ACCESS_TOKEN:
    if META_ACCESS_TOKEN not in META_ACCESS_TOKENS:
        META_ACCESS_TOKENS.append(META_ACCESS_TOKEN)

YOUTUBE_CLIENT_SECRETS_FILE = os.getenv("YOUTUBE_CLIENT_SECRETS_FILE", str(BASE_DIR / "client_secrets.json"))
YOUTUBE_TOKEN_FILE = os.getenv("YOUTUBE_TOKEN_FILE", str(BASE_DIR / "youtube_token.json"))

TEMP_DIR = BASE_DIR / "temp_videos"
TEMP_DIR.mkdir(parents=True, exist_ok=True)
