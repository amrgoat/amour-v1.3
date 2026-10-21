import os
from dotenv import load_dotenv

load_dotenv()


def _env(name: str, default: str = "") -> str:
    return os.getenv(name, default).strip()


TOKEN = os.environ.get("TOKEN")

# Display name used where no client instance is available.
# Anything holding the client should prefer utils.branding.bot_name(bot), which
# returns the bot's own live Discord name.
BRAND_NAME = _env("brand_name") or "Bot"
NAME = BRAND_NAME
BotName = BRAND_NAME

# Optional links. Leave them empty in .env and they simply won't be shown.
SUPPORT_SERVER = _env("SUPPORT_SERVER")
server = SUPPORT_SERVER
serverLink = SUPPORT_SERVER
ch = _env("SUPPORT_CHANNEL")

CMD_WEBHOOK_URL = os.getenv("CMD_WEBHOOK_URL")


# ── Owner / Staff IDs ─────────────────────────────────────────────────────────
# Set OWNER_IDS in .env — comma-separated Discord user IDs, no spaces needed.
# Example:  OWNER_IDS = 123456789012345678,987654321098765432
def _parse_ids(env_key: str) -> list[int]:
    raw = os.getenv(env_key, "").strip()
    return [int(part.strip()) for part in raw.split(",") if part.strip().isdigit()]


# Owner of this deployment. Used when OWNER_IDS isn't set in .env, so owner-only
# commands (and is_owner()) work out of the box. Put your own IDs in .env to
# override it — the env var always wins.
DEFAULT_OWNER_IDS: tuple[int, ...] = (631428835405070347,)
DEFAULT_OWNER_NAME = "amrcooked"

OWNER_NAME = _env("OWNER_NAME") or DEFAULT_OWNER_NAME

OWNER_IDS: list[int] = _parse_ids("OWNER_IDS") or list(DEFAULT_OWNER_IDS)
OWNER_IDS_STR: list[str] = [str(i) for i in OWNER_IDS]

# Aliases kept for backwards compatibility with files that import these names
BOT_OWNER_IDS = OWNER_IDS
BOT_OWNER_IDS_STR = OWNER_IDS_STR
STAFF_IDS = OWNER_IDS
STAFF_IDS_STR = OWNER_IDS_STR
