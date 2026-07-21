from loguru import logger
import os
import sys

# ── Log level from environment (DEBUG in dev, INFO in prod) ──────────────────
LOG_LEVEL = os.getenv("LOG_LEVEL", "INFO").upper()

os.makedirs("app/logs", exist_ok=True)

# ── Remove default stderr sink (stops DEBUG spam in console) ─────────────────
logger.remove()

# ── Console sink — only WARNING and above in production ──────────────────────
logger.add(
    sys.stderr,
    level="WARNING" if LOG_LEVEL == "INFO" else LOG_LEVEL,
    format="{time:HH:mm:ss} | <level>{level}</level> | {message}",
    colorize=True,
)

# ── File sink — full INFO+ logs with rotation ────────────────────────────────
logger.add(
    "app/logs/remoteio.log",
    rotation="10 MB",
    retention="7 days",
    level=LOG_LEVEL,
    format="{time:YYYY-MM-DD HH:mm:ss} | {level} | {name}:{function}:{line} | {message}",
    encoding="utf-8",
)

logger.info(f"Logger initialized | level={LOG_LEVEL}")