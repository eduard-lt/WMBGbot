# 🎲 WMBGbot — Where's My Board Game Bot

A Telegram bot to catalog your friend group's board game collection and manage borrowing between friends. Runs on a Raspberry Pi 2 (24/7), no public port needed.

## Features

- **Shared catalog** — everyone in the group can browse and search all games
- **BGG lookup** — add games by title; fetches canonical names and cover art from BoardGameGeek
- **Borrow/return flow** — request to borrow, owner accepts/declines in DM, either party marks returned
- **Admin tools** — force-edit titles, remove copies, reset stuck loans
- **Lightweight** — SQLite + long polling, runs comfortably on a Pi 2

## Tech Stack

| Component | Choice |
|---|---|
| Language | Python ≥3.9 |
| Bot framework | `python-telegram-bot` v20+ (async) |
| Database | SQLite (stdlib `sqlite3`) |
| BGG API | `httpx` + `xml.etree.ElementTree` |
| Package manager | `uv` |

## Commands

### Group chat (everyone sees responses)
| Command | Description |
|---|---|
| `/search <title>` | Search the catalog by title |
| `/library` | List all games in the catalog |
| `/mygames` | Show your own copies |
| `/whohas <title>` | Find who owns a specific game |
| `/help` | Show all commands |

### Private DM (required for setup and borrowing)
| Command | Description |
|---|---|
| `/start` | Register with the bot (one-time setup) |
| `/addgame <title>` | Add a game via BGG lookup |
| `/removegame` | Remove one of your copies |
| `/myrequests` | View incoming & outgoing borrow requests |
| `/return` | Mark a borrowed game as returned |

### Admin (DM or group)
| Command | Description |
|---|---|
| `/admin_list_users` | Show all registered users and their DM status |
| `/admin_edit_game <id> <title>` | Fix a bad BGG title match |
| `/admin_remove_copy <id>` | Force-remove any copy |
| `/admin_reset_loan <id>` | Force-close a stuck loan |

## How It Works

1. Each user sends `/start` in a **private DM** to register — this lets the bot DM them about requests
2. Users add their games via `/addgame` in DM — the bot looks it up on BoardGameGeek
3. Anyone in the group can `/search` and see who has what
4. To borrow: tap the inline **Borrow** button from a search result — the owner gets a DM with Accept/Decline
5. Once accepted, the game is marked as borrowed; either party can `/return` it when done

---

## Setup (Raspberry Pi)

### Prerequisites
- Raspberry Pi 2 running Raspbian
- Python 3.9+ and `uv` installed
- A Telegram bot token from [@BotFather](https://t.me/BotFather)
- Git access to this repo

### Installation

```bash
# Clone the repo
git clone https://github.com/eduard-lt/WMBGbot.git /home/eduard/boardgame-bot
cd /home/eduard/boardgame-bot

# Create and edit your .env file (add your bot token)
cp .env.example .env
nano .env

# Install dependencies
uv sync --extra dev

# Create the data directory
mkdir -p data

# Run tests to verify everything works
uv run pytest tests/ -v

# Install the systemd service
sudo cp deploy/boardgame-bot.service /etc/systemd/system/
sudo systemctl daemon-reload
sudo systemctl enable --now boardgame-bot

# Check it's running
sudo systemctl status boardgame-bot
```

### Making Yourself Admin

After you `/start` the bot in DM:

```bash
# Find your telegram_id in the logs or the DB
sqlite3 /home/eduard/boardgame-bot/data/bot.db \
  "UPDATE users SET is_admin = 1 WHERE telegram_id = <YOUR_TELEGRAM_ID>;"
```

### Database Backup

A daily cron job copies the database:

```bash
crontab -e
# Add the contents of deploy/cron-backup
```

---

## Development

```bash
git clone https://github.com/eduard-lt/WMBGbot.git
cd WMBGbot

# Create a .env (can use a test bot token)
cp .env.example .env

uv sync --extra dev
uv run pytest tests/ -v
```

### Project Structure

```
src/wmbgbot/
├── main.py              # Entry point, wires up Application
├── config.py            # .env loading
├── logging_config.py    # Rotating file handler
├── models.py            # Dataclasses (User, Game, Copy, Request, Loan)
├── bgg.py               # BoardGameGeek XML API2 client
├── db/
│   ├── schema.py        # CREATE TABLE statements
│   └── queries.py       # All SQL query functions
└── handlers/
    ├── commands.py      # /start, /search, /library, /addgame, etc.
    ├── callbacks.py     # Inline button handlers (borrow, accept, return)
    └── admin.py         # Admin-only commands
```
