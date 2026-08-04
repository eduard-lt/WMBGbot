# WMBGbot — Implementation Plan

## Project Summary
A Telegram bot for a friend group (~10 people) to catalog who owns which board games and to request/track borrowing between friends. Runs on a Raspberry Pi 2 (Raspbian, 24/7 uptime), alongside an existing `homelab-power-manager` Python service.

---

## Tech Stack
- **Python 3** (3.9+ for Pi 2 compat)
- **`uv`** — package manager & venv tool
- **`python-telegram-bot`** v20+ (async, long polling)
- **SQLite** via `stdlib sqlite3` (lightweight, no extra deps)
- **`httpx`** or `aiohttp` — async HTTP for BGG XML API2
- **`python-dotenv`** — `.env` config loading
- **`xml.etree.ElementTree`** (stdlib) — parse BGG XML responses

---

## Directory Structure (dev repo)

```
WMBGbot/
├── .env.example              # Template for .env (token, BGG URL, etc.)
├── .gitignore                # Exclude .env, data/, __pycache__, .venv/
├── .python-version           # python version pin for uv
├── README.md
├── plan.md                   # This file
├── pyproject.toml            # uv project config + deps
├── src/
│   └── wmbgbot/
│       ├── __init__.py
│       ├── main.py           # Entry point: creates Application, registers handlers, starts polling
│       ├── config.py         # .env loading, typed config dataclass
│       ├── db/
│       │   ├── __init__.py
│       │   ├── schema.py     # CREATE TABLE statements, migration helpers
│       │   └── queries.py    # All DB query functions (async, using aiosqlite or threads)
│       ├── handlers/
│       │   ├── __init__.py
│       │   ├── commands.py   # /start, /help, /search, /library, /mygames, /whohas, /addgame, /removegame, /return, /myrequests, /borrow
│       │   ├── callbacks.py  # Inline button handlers (Accept/Decline, Borrow, Mark Returned, disambiguation pick)
│       │   └── admin.py      # /admin_edit_game, /admin_remove_copy, /admin_reset_loan, /admin_list_users
│       ├── models.py         # Simple dataclasses for User, Game, Copy, Request, Loan (no heavy ORM)
│       ├── bgg.py            # BGG API client: search() → list[candidates], fetch_game(bgg_id) → title+cover
│       └── logging_config.py # RotatingFileHandler setup
├── tests/
│   ├── __init__.py
│   ├── test_db.py
│   ├── test_bgg.py
│   └── test_handlers.py
├── deploy/
│   ├── boardgame-bot.service # systemd unit file
│   ├── deploy.sh             # Rsync/pull to Pi, restart service
│   └── cron-backup           # daily crontab entry for db backup
└── data/                     # gitignored — SQLite DB lives here in dev
```

## Pi Deployment Layout

```
/home/eduard/boardgame-bot/
├── .venv/                    # uv-managed virtualenv
├── .env                      # Production config (token, etc.)
├── src/                      # Synced from repo
├── data/
│   └── bot.db               # SQLite database (outside src, safe from redeploy)
├── backups/                  # Daily cron DB snapshots
└── bot.log                   # RotatingFileHandler output
```

---

## Implementation Phases

### Phase 1: Project Scaffold & Config (est. 0.5h) ✅ DONE
1. Initialize `uv` project: `uv init` → `pyproject.toml`
2. Add dependencies: `python-telegram-bot[job-queue]`, `python-dotenv`, `httpx`
3. Create `.env.example` with: `BOT_TOKEN`, `BGG_API_BASE_URL`, `DATABASE_PATH`, `LOG_FILE`, `LOG_LEVEL`
4. Create `config.py` — load `.env`, validate required keys, return typed config
5. Create `main.py` skeleton — `Application.builder().token(config.BOT_TOKEN).build()`, register handlers placeholder, `run_polling()`
6. Create `.gitignore` — `.env`, `data/`, `__pycache__/`, `.venv/`, `*.log`, `backups/`
7. Verify bot starts and responds to `/start` with a placeholder message

### Phase 2: Database Layer (est. 1h) ✅ DONE
1. Create `db/schema.py` — `init_db(db_path)` that runs all CREATE TABLE IF NOT EXISTS statements (users, games, copies, requests, loans) exactly per spec
2. Create `models.py` — frozen dataclasses for User, Game, Copy, Request, Loan (match column names; use `from __future__ import annotations`)
3. Create `db/queries.py` — each function wraps a synchronous SQL query, to be called via `run_in_executor` or with a simple sync sqlite3 connection in a thread:
   - `upsert_user(telegram_id, display_name)` — registers or updates user
   - `set_dm_started(telegram_id)` — sets `dm_started = 1`
   - `get_user(telegram_id)` → User | None
   - `get_user_dm_started(telegram_id)` → bool
   - `search_games(query)` → list of (Game, list of (Copy, owner_display_name, borrower_display_name?))
   - `get_library()` → list of (title, owner_count)
   - `get_user_copies(owner_id)` → list of Copy + game title
   - `add_game(bgg_id, title, cover_url)` → game_id (upsert logic)
   - `add_copy(game_id, owner_id)` → copy_id
   - `remove_copy(copy_id)` — only if available
   - `get_copy(copy_id)` → Copy | None
   - `create_request(copy_id, requester_id)` → request_id
   - `resolve_request(request_id, new_status)` — sets resolved_at
   - `get_request(request_id)` → Request | None
   - `get_pending_requests_for_owner(owner_id)` → list[Request + requester info]
   - `get_pending_requests_by_requester(requester_id)` → list[Request + copy/game info]
   - `create_loan(copy_id, borrower_id)` → loan_id
   - `return_loan(loan_id)` → sets returned_at
   - `get_active_loans_for_user(telegram_id)` → list of loans (where user is borrower or owner)
   - `get_all_users()` → list[User]
   - `admin_edit_copy_game(copy_id, new_title)` — force edit
   - `admin_remove_copy(copy_id)` — force remove
   - `admin_reset_loan(loan_id)` — force close
4. Use `sqlite3.connect` with `check_same_thread=False` and a thread lock, or use `sqlite3.Connection` in a dedicated thread/executor. Keep it simple — a single-connection + thread-executor pattern is fine for ~10 users.

### Phase 3: BGG API Integration (est. 1h) ✅ DONE
1. `bgg.py`:
   - `search_bgg(query: str) -> list[dict]` — call `https://boardgamegeek.com/xmlapi2/search?query=...&type=boardgame`, parse XML, return list of `{bgg_id, name, yearpublished}`
   - `fetch_bgg_details(bgg_id: int) -> dict` — call `https://boardgamegeek.com/xmlapi2/thing?id=...`, parse XML, return `{title, thumbnail_url, image_url}`
   - Handle: no results → return empty list; API errors → retry once, then raise; rate limiting → add 2s delay between calls
   - Use `httpx.AsyncClient` for async HTTP
2. Edge case: BGG search returns 10+ results → truncate to top 8 with a "...and N more" item? (Flag to decide later)

### Phase 4: Command Handlers — Group Chat (est. 2h) ✅ DONE
All handlers in `handlers/commands.py` using `python-telegram-bot`'s `@CommandHandler` decorator pattern.

1. **`/start`** (DM only, but works in group with a redirect):
   - In DM: set `dm_started = 1`, upsert user, welcome message
   - In group: reply "Please send /start to me in a private message to complete setup."
   
2. **`/help`**: List all commands, split into "Group" and "DM" sections. Include admin commands if caller is admin.

3. **`/search <title>`**: 
   - SQL LIKE `%title%` on `games.title`
   - Group results by game_id
   - For each game: show title, each copy's owner + status (available/borrowed by X)
   - If > 5 games match, truncate with suggestion to refine search
   - Each available copy gets inline "Borrow" button (callback_data = `borrow:<copy_id>`)

4. **`/library`**:
   - List all games, grouped by title, with count of copies and count available
   - Paginate if many games? (unlikely for ~10 people but nice to have)

5. **`/mygames`**:
   - List caller's copies with status and game title
   - If copy is borrowed, show who has it
   - Inline "Remove" button per available copy

6. **`/whohas <title>`**:
   - Exact-ish match on title, show all owners and copy statuses
   - Delegates to same query as `/search` but with stricter matching

### Phase 5: Command Handlers — DM (est. 2h) ✅ DONE

1. **`/addgame <title>`**:
   - Call `search_bgg(title)`
   - If 0 results → "No matches on BoardGameGeek. Enter the title manually:" then wait for text reply → create game with no bgg_id
   - If 1 result → auto-confirm, show details, create game + copy
   - If 2–N results → inline keyboard with candidate titles, callback = `addgame:<bgg_id>:<title>`
   - On callback: fetch full details from BGG `/thing`, create game row (upsert on bgg_id), create copy for caller

2. **`/removegame`**:
   - List caller's copies with inline "Remove" buttons (callback = `remove:<copy_id>`)
   - On callback: validate copy is available and caller is owner; remove if valid; error msg if borrowed

3. **`/borrow`** (implied via inline button from `/search`, but also a DM command? The spec says "Triggered from a /search result's inline Borrow button" — so this is purely callback-driven):
   - `handlers/callbacks.py`: `handle_borrow(update, context)` 
   - Look up `copy_id` from callback data
   - Validate: copy exists, is available, requester ≠ owner, owner has `dm_started = 1`
   - If owner hasn't set up DM → tell requester
   - Create `requests` row (status = pending)
   - DM the owner: "▶ [Requester] wants to borrow [Game Title]" with Accept / Decline buttons
   - Confirm to requester: "Request sent to [Owner]"
   - Edge case: requester already has a pending request for this same copy → reject duplicate

4. **`/myrequests`**:
   - "Outgoing requests": pending requests made by caller, grouped by game
   - "Incoming requests": pending requests for caller's copies, with Accept/Decline buttons inline
   - If no requests: "You have no pending requests."

5. **`/return`**:
   - List active loans where caller is borrower OR owner
   - Each loan shows: game title, other party name, borrowed date
   - Inline "Mark Returned" button per loan (callback = `return:<loan_id>`)
   - On callback: set `returned_at`, flip `copies.status` to 'available', notify other party

### Phase 6: Callback Handlers (Inline Keyboard) (est. 1.5h) ✅ DONE
All in `handlers/callbacks.py` using `@CallbackQueryHandler` with pattern matching.

1. **`borrow:<copy_id>`** → handle_borrow (see Phase 5.3)
2. **`accept:<request_id>`** / **`decline:<request_id>`**:
   - Validate: only the copy owner can act (check `telegram_id` against `copies.owner_id` at callback time)
   - On accept: create `loans` row, set `copies.status = 'borrowed'`, notify requester
   - On decline: just update request status, notify requester
   - Edit the original DM message to show resolved state (remove buttons)
3. **`addgame:<bgg_id>:<escaped_title>`** → create game + copy, confirm to user
4. **`remove:<copy_id>`** → validate ownership and availability, remove, confirm
5. **`return:<loan_id>`** → validate caller is borrower or owner, mark returned, notify other party
6. **Guard**: all callbacks must refresh user record to ensure `display_name` is current

### Phase 7: Admin Commands (est. 0.75h) ✅ DONE
All in `handlers/admin.py`. Each checks `users.is_admin` before proceeding.

1. **`/admin_edit_game <copy_id> <new_title>`**:
   - Force-update the game title for a copy
   - Log the action
2. **`/admin_remove_copy <copy_id>`**:
   - Force-remove regardless of borrowed status
   - If borrowed, also close the active loan first
   - Confirm with inline button? (Yes/No) Maybe just DO it with a "Done" reply
3. **`/admin_reset_loan <loan_id>`**:
   - Set `returned_at`, flip copy to available
   - Log the action
4. **`/admin_list_users`**:
   - List all users: display_name, telegram_id, is_admin, dm_started
   - Highlight who still needs to DM the bot

### Phase 8: Logging & Error Handling (est. 0.75h) ✅ DONE
1. `logging_config.py`:
   - `RotatingFileHandler` — max 5MB per file, keep 3 backups
   - Log format: `%(asctime)s - %(name)s - %(levelname)s - %(message)s`
   - Log to file AND console (for systemd journal)
2. Global error handler in `main.py`:
   - Catch unhandled updates, log full traceback, reply "Something went wrong" to user
3. Add structured logging for: borrow requests created, loans created, returns, admin actions
4. Ensure all BGG API calls have timeout (10s), retry once on failure, log errors

### Phase 9: Testing (est. 1.5h) ✅ DONE (13 tests passing)
1. `tests/test_db.py` — test all query functions with in-memory SQLite
2. `tests/test_bgg.py` — mock HTTP responses, test parsing
3. `tests/test_handlers.py` — use `python-telegram-bot`'s test framework (`Application`, `CallbackContext` mocks)
4. Integration test: end-to-end flow (add game → search → borrow → accept → return) using in-memory DB

### Phase 10: Deployment (est. 1h)
1. `deploy/boardgame-bot.service`:
   ```ini
   [Unit]
   Description=Board Game Lending Bot
   After=network-online.target
   Wants=network-online.target

   [Service]
   Type=simple
   User=eduard
   WorkingDirectory=/home/eduard/boardgame-bot
   EnvironmentFile=/home/eduard/boardgame-bot/.env
   ExecStart=/home/eduard/boardgame-bot/.venv/bin/python -m wmbgbot.main
   Restart=on-failure
   RestartSec=5
   StandardOutput=journal
   StandardError=journal

   [Install]
   WantedBy=multi-user.target
   ```
2. `deploy/deploy.sh`:
   - `rsync -avz --exclude '.venv' --exclude 'data' --exclude '.env' --exclude '__pycache__' --exclude '.git' ./ pi@<pi-host>:/home/eduard/boardgame-bot/`
   - `ssh pi@<pi-host> 'cd /home/eduard/boardgame-bot && uv sync && sudo systemctl restart boardgame-bot'`
3. `deploy/cron-backup`:
   - `0 3 * * * cp /home/eduard/boardgame-bot/data/bot.db /home/eduard/boardgame-bot/backups/bot_$(date +\%Y\%m\%d).db`
4. First-run setup on Pi:
   - `mkdir -p /home/eduard/boardgame-bot/{data,backups}`
   - Create `.env` from `.env.example`
   - `uv sync`
   - `sudo systemctl enable --now boardgame-bot.service`

---

## Acceptance Criteria Checklist

- [ ] A user who hasn't DM'd the bot gets a clear message when someone tries to borrow their game
- [ ] `/addgame` with no BGG match falls back to free-text title entry
- [ ] `/search` and `/library` group multiple copies of same title under one entry with all owners listed
- [ ] Borrowed copies are rejected for new borrow requests with a clear message
- [ ] Only the copy owner can Accept/Decline (validated at callback time via telegram_id)
- [ ] Both borrower and owner can mark a loan returned; the other party is notified
- [ ] `/removegame` refuses to remove a currently-borrowed copy
- [ ] Admin commands reject non-admins with "not authorized"
- [ ] Bot runs under systemd with `Restart=on-failure`
- [ ] SQLite DB lives in `data/` (outside src), safe from redeploys
- [ ] `.env` holds all secrets — nothing hardcoded
- [ ] Log rotation configured — won't fill the 22GB disk

---

## Open Design Decisions

| # | Question | Default Decision | Notes |
|---|---|---|---|
| 1 | BGG disambiguation: truncate to how many results? | Top 8 + "too many matches" | Easy to change; 8 fits a Telegram inline keyboard comfortably |
| 2 | Should `/mygames` show pending incoming requests inline? | No — keep `/mygames` informative only, `/myrequests` is for actions | Clean separation of concerns |
| 3 | `/removegame` — confirm with inline button or just do it? | Inline confirm button (Yes/No) | Prevents accidents; single tap to remove is risky |
| 4 | Should loans track who initiated the return? | No — not needed for v1 | Add `returned_by` column in v2 if social disputes arise |
| 5 | Should the bot work in multiple groups? | Out of scope for v1 | All users share one catalog; group_id not stored |
| 6 | How to handle BGG API rate limiting? | 2s delay between calls, max 5 retries | BGG is slow anyway; long polling bot won't notice |

---

## Time Estimate Summary

| Phase | Est. Hours |
|---|---|
| 1. Scaffold & Config | 0.5 |
| 2. Database Layer | 1.0 |
| 3. BGG API | 1.0 |
| 4. Group Chat Handlers | 2.0 |
| 5. DM Handlers | 2.0 |
| 6. Callback Handlers | 1.5 |
| 7. Admin Commands | 0.75 |
| 8. Logging & Errors | 0.75 |
| 9. Testing | 1.5 |
| 10. Deployment | 1.0 |
| **Total** | **~12h** |

---

## Dependencies (`pyproject.toml`)

```toml
[project]
name = "wmbgbot"
version = "0.1.0"
description = "Telegram bot for board game lending among friends"
requires-python = ">=3.9"
dependencies = [
    "python-telegram-bot[job-queue]>=20.0,<22.0",
    "python-dotenv>=1.0",
    "httpx>=0.25",
]

[project.optional-dependencies]
dev = [
    "pytest>=8.0",
    "pytest-asyncio>=0.23",
    "pytest-mock>=3.12",
]
```
