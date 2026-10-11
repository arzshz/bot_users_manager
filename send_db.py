import os
import shutil
import signal
import tempfile
import time
from pathlib import Path
from zoneinfo import ZoneInfo

import telebot
from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.triggers.cron import CronTrigger
from dotenv import load_dotenv
from telebot import apihelper

load_dotenv(Path.cwd() / "src" / "setting" / ".env")

TEHRAN = ZoneInfo("Asia/Tehran")
PLATFORM = os.getenv("PLATFORM", "telegram").lower()
SEND_TIME = os.getenv("SEND_TIME", "16:00")
TOKEN = os.getenv("BOT_TOKEN")
CHANNEL_ID = os.getenv("BACKUP_CHANNEL_ID")
DB_PATH = Path(os.getenv("USERS_DB_PATH", Path.cwd() / "data" / "users.sqlite"))

# same override mechanism the bale telebot fork uses by default
BALE_API_URL = "https://tapi.bale.ai/bot{0}/{1}"

_TERMINATING = False


def _sigterm_handler(signum, frame):
    global _TERMINATING
    if _TERMINATING:
        return
    _TERMINATING = True
    raise KeyboardInterrupt


def configure_api(platform: str) -> str:
    """Point telebot at the right API: telegram (default) or bale."""
    if platform == "telegram":
        apihelper.API_URL = None  # telebot falls back to api.telegram.org
    elif platform == "bale":
        apihelper.API_URL = BALE_API_URL
    else:
        raise ValueError(
            f"Unknown PLATFORM {platform!r}, expected 'telegram' or 'bale'"
        )
    return platform


def parse_send_time(value: str) -> tuple[int, int]:
    try:
        hour_str, minute_str = value.split(":")
        hour, minute = int(hour_str), int(minute_str)
    except ValueError:
        raise ValueError(f"Invalid SEND_TIME {value!r}, expected HH:MM") from None
    if not (0 <= hour <= 23 and 0 <= minute <= 59):
        raise ValueError(f"Invalid SEND_TIME {value!r}: hour 0-23, minute 0-59")
    return hour, minute


def send_file(bot: telebot.TeleBot, file_path: Path):
    tmpdir = Path(tempfile.mkdtemp())
    copy = tmpdir / f"{file_path.stem}_{int(time.time())}.sqlite"
    shutil.copy2(file_path, copy)
    try:
        with open(copy, "rb") as document:
            return bot.send_document(CHANNEL_ID, document)
    finally:
        copy.unlink(missing_ok=True)
        tmpdir.rmdir()


def send_backup(bot: telebot.TeleBot):
    try:
        if not DB_PATH.exists():
            print(f"No sqlite file found at {DB_PATH}")
            return
        response = send_file(bot, DB_PATH)
        print(f"File sent: message_id={response.message_id}")
    except Exception as e:
        # never exit: runner.sh would stop the recorder along with us
        print(f"Backup failed: {e}")


def main():
    configure_api(PLATFORM)

    if not TOKEN or not CHANNEL_ID:
        print("Backup disabled: BOT_TOKEN / BACKUP_CHANNEL_ID not set.")
        while True:
            time.sleep(3600)

    hour, minute = parse_send_time(SEND_TIME)
    bot = telebot.TeleBot(TOKEN)
    scheduler = BackgroundScheduler(timezone=TEHRAN)
    scheduler.add_job(
        send_backup,
        CronTrigger(hour=hour, minute=minute, timezone=TEHRAN),
        args=[bot],
        id="daily_db_backup",
        misfire_grace_time=3600,
    )
    scheduler.start()
    print(
        f"Backup scheduled daily at {hour:02d}:{minute:02d} Tehran time ({PLATFORM} API)."
    )

    while True:
        time.sleep(3600)


if __name__ == "__main__":
    try:
        signal.signal(signal.SIGTERM, _sigterm_handler)
    except (ValueError, OSError):
        pass
    try:
        main()
    except KeyboardInterrupt:
        print("Backup process stopped.")
