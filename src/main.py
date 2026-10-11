import os
import signal
import sys
import time
from pathlib import Path

from dotenv import load_dotenv

sys.path.insert(0, str(Path.cwd()))

from users_manager import db
from utils.log import get_logger

load_dotenv(Path.cwd() / "src" / "setting" / ".env")

log = get_logger("main")

PLATFORM = os.getenv("PLATFORM", "telegram").lower()
DB_PATH = os.getenv("USERS_DB_PATH", str(Path.cwd() / "data" / "users.sqlite"))
HEARTBEAT_SECONDS = int(os.getenv("HEARTBEAT_SECONDS", "3600"))

_TERMINATING = False


def _sigterm_handler(signum, frame):
    global _TERMINATING
    if _TERMINATING:
        return
    _TERMINATING = True
    raise KeyboardInterrupt


def main():
    if PLATFORM not in ("telegram", "bale"):
        log.error("Unknown PLATFORM %r - expected 'telegram' or 'bale'.", PLATFORM)
        sys.exit(1)

    db.init_db(DB_PATH)
    log.info("Database ready at %s (platform=%s)", DB_PATH, PLATFORM)

    if PLATFORM == "bale":
        log.info("Bale platform: daily sender uploads via tapi.bale.ai.")

    while True:
        try:
            total = db.count_users(DB_PATH)
            per_bot = db.count_bot_users(DB_PATH)
            log.info("heartbeat: %s unique users across %s bot(s)", total, len(per_bot))
            for (platform, bot_name), count in per_bot.items():
                log.info("heartbeat:   %s/%s: %s user(s)", platform, bot_name, count)
        except Exception as e:
            log.error("heartbeat failed: %s", e)

        time.sleep(HEARTBEAT_SECONDS)


if __name__ == "__main__":
    try:
        signal.signal(signal.SIGTERM, _sigterm_handler)
    except (ValueError, OSError):
        pass
    try:
        main()
    except KeyboardInterrupt:
        print("Manager process stopped.")
