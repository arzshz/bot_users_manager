# bot_users_manager

Collects the users of **every Telegram/Bale bot on the server** into one shared
SQLite DB, and uploads that DB to a channel daily at a configurable Tehran time
(default **16:00**).

> Why a hook? Telegram doesn't let a second process poll a running bot's token,
> so each bot records its own users via a 2-line hook. This service only owns
> the shared DB and the daily upload.

## 1. Set up the manager (once)

```bash
git clone git@github.com:arzshz/bot_users_manager.git ~/bot_users_manager
cd ~/bot_users_manager
python3 -m venv .venv
.venv/bin/pip install -r requirements.txt
cp src/setting/sample.env src/setting/.env
mkdir -p data
```

Edit `src/setting/.env`:

| Variable | Meaning |
|---|---|
| `BOT_TOKEN` | Token of any bot on the target platform (admin of the channel) |
| `BACKUP_CHANNEL_ID` | Channel to upload the DB to (`@channel` or `-100…`) |
| `USERS_DB_PATH` | Absolute path of the shared DB, e.g. `/opt/bot_users_manager/data/users.sqlite` |
| `SEND_TIME` | Daily upload time, Tehran — any `HH:MM` (default `16:00`) |
| `PLATFORM` | Where the backup is sent: `telegram` (`api.telegram.org`) or `bale` (`tapi.bale.ai`) |

Run:

```bash
./runner.sh                                      # manual
sudo cp deploy/bot-users-manager.service /etc/systemd/system/
sudo sed -i "s/YOUR_USER/$(whoami)/g" /etc/systemd/system/bot-users-manager.service
sudo systemctl daemon-reload && sudo systemctl enable --now bot-users-manager
journalctl -u bot-users-manager -f
```

## 2. Hook each bot (2 lines + 1 env var)

```bash
# into the bot's own venv:
/path/to/bot/venv/bin/pip install -e /path/to/bot_users_manager
```

```python
import users_manager
users_manager.install(bot, bot_name="timereport")                            # telegram
users_manager.install(bot, bot_name="bale_timereport", platform="bale")      # bale
```

```
# in the bot's .env / systemd unit — same absolute path for every bot
USERS_DB_PATH=/opt/bot_users_manager/data/users.sqlite
```

That's it. Every message a hooked bot receives upserts the sender into the
shared DB. The hook never breaks the host bot — errors are swallowed and the
bot's own handlers always run. If `install()` can't wrap a Bale SDK build
(missing `process_new_updates`), call
`users_manager.record_message(message, bot_name="…")` in your handler instead.

## What's stored

- `users` — one row per unique user (`chat_id` is the same number across all bots)
- `bot_users` — which bots (`platform` + `bot_name`) each user has talked to

## Bale

Both platforms use the same `telebot` library — your Bale bots already run the
fork whose API defaults to `tapi.bale.ai`, so **the hook works unchanged**.

To send the daily backup to a Bale channel instead of Telegram, set in
`src/setting/.env`:

```
PLATFORM=bale
BOT_TOKEN=<bale bot token>
BACKUP_CHANNEL_ID=<bale channel>
```

`send_db.py` then points telebot at `tapi.bale.ai` (same `API_URL` override the
Bale fork uses). One platform per manager instance — run a second instance with
its own `.env`/DB if you need both telegram and bale backups.
