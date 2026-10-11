from datetime import datetime, timezone

from . import db as _db


def _extract_message(update):
    message = getattr(update, "message", None)
    if message is None:
        message = getattr(update, "edited_message", None)
    if message is None:
        callback_query = getattr(update, "callback_query", None)
        if callback_query is not None:
            message = getattr(callback_query, "message", None)
    return message


def _extract_user_fields(message):
    chat = getattr(message, "chat", None)
    chat_id = getattr(chat, "id", None)
    if chat_id is None:
        user = getattr(message, "from_user", None)
        chat_id = getattr(user, "id", None)
    user = getattr(message, "from_user", None)
    return (
        chat_id,
        getattr(user, "username", None),
        getattr(user, "first_name", None),
        getattr(user, "last_name", None),
    )


def record_message(
    message, bot_name: str, platform: str = "telegram", db_path=None, now=None
) -> bool:
    """Record the sender of a single message. Returns True if stored."""
    chat_id, username, first_name, last_name = _extract_user_fields(message)
    if chat_id is None:
        return False
    now_iso = (now or datetime.now(timezone.utc)).isoformat()
    _db.record_user(
        db_path,
        chat_id=chat_id,
        username=username,
        first_name=first_name,
        last_name=last_name,
        platform=platform,
        bot_name=bot_name,
        now_iso=now_iso,
    )
    return True


def install(bot, bot_name: str, platform: str = "telegram", db_path=None):
    """
    Wrap the bot's update intake so every incoming update is recorded
    before the bot's own handlers run.

    Usage in a bot project:
        import users_manager
        users_manager.install(bot, bot_name="timereport")
    """
    _db.init_db(db_path)
    if not hasattr(bot, "process_new_updates"):
        raise AttributeError(
            "bot has no process_new_updates(); use users_manager.record_message() in your handler instead"
        )

    original = bot.process_new_updates

    def process_new_updates(updates):
        try:
            for update in updates or []:
                message = _extract_message(update)
                if message is not None:
                    record_message(
                        message, bot_name=bot_name, platform=platform, db_path=db_path
                    )
        except Exception:
            pass  # recording must never break the host bot
        return original(updates)

    bot.process_new_updates = process_new_updates
    return bot
