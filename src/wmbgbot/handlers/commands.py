"""Command handlers for the bot."""

from __future__ import annotations

import logging

from telegram import Update
from telegram.constants import ChatType
from telegram.ext import ContextTypes

logger = logging.getLogger(__name__)


# ── /start ───────────────────────────────────────────────────────────

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Register a user or redirect to DM."""
    if update.effective_chat is None or update.effective_user is None:
        return

    if update.effective_chat.type == ChatType.PRIVATE:
        db = context.bot_data["db"]
        from wmbgbot.db.queries import upsert_user, set_dm_started

        user = upsert_user(
            db,
            update.effective_user.id,
            update.effective_user.full_name or update.effective_user.username or "Unknown",
        )
        set_dm_started(db, update.effective_user.id)
        await update.message.reply_text(
            f"Welcome, {user.display_name}! 🎲\n\n"
            "You're now registered with the Board Game Lending Bot.\n"
            "Use /help to see available commands.\n\n"
            "To add your first game, use /addgame <title> — I'll look it up on BoardGameGeek!"
        )
    else:
        await update.message.reply_text(
            "Please send /start to me in a **private message** to complete your setup.\n"
            "👉 [Open private chat](https://t.me/me)",
            parse_mode="Markdown",
        )


# ── /help ────────────────────────────────────────────────────────────

async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Show available commands."""
    is_dm = update.effective_chat is not None and update.effective_chat.type == ChatType.PRIVATE

    group_cmds = (
        "🎲 *Group Chat Commands*\n"
        "/search \\<title\\> — Search the group's game catalog\n"
        "/library — List all games in the catalog\n"
        "/mygames — Show your copies and their status\n"
        "/whohas \\<title\\> — Find who owns a specific game\n"
        "/help — Show this help message"
    )

    dm_cmds = (
        "📬 *DM Commands*\n"
        "/start — Register with the bot (required to receive request notifications)\n"
        "/addgame \\<title\\> — Add a game to the catalog (BGG lookup)\n"
        "/removegame — Remove one of your copies\n"
        "/myrequests — View your pending borrow requests (incoming & outgoing)\n"
        "/return — Mark a borrowed game as returned"
    )

    admin_cmds = (
        "🔧 *Admin Commands*\n"
        "/admin\\_edit\\_game \\<copy\\_id\\> \\<new\\_title\\> — Fix a bad title match\n"
        "/admin\\_remove\\_copy \\<copy\\_id\\> — Force-remove any copy\n"
        "/admin\\_reset\\_loan \\<loan\\_id\\> — Force-close a stuck loan\n"
        "/admin\\_list\\_users — List all registered users"
    )

    text = group_cmds
    if is_dm:
        text += "\n\n" + dm_cmds

    # Check if user is admin
    db = context.bot_data["db"]
    if update.effective_user is not None:
        from wmbgbot.db.queries import get_user

        user = get_user(db, update.effective_user.id)
        if user and user.is_admin:
            text += "\n\n" + admin_cmds

    await update.message.reply_text(text, parse_mode="Markdown")


# ── /search ──────────────────────────────────────────────────────────

async def search(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Search games by title."""
    if update.effective_chat is None or update.effective_user is None:
        return

    query = " ".join(context.args) if context.args else ""
    if not query.strip():
        await update.message.reply_text("Usage: /search <title>")
        return

    db = context.bot_data["db"]
    from wmbgbot.db.queries import search_games

    results = search_games(db, query)

    if not results:
        await update.message.reply_text(f"No games found matching '{query}'.")
        return

    lines = [f"🔍 *Search results for '{query}':*", ""]
    for game in results:
        lines.append(f"*{game['title']}*")
        for copy_info in game["copies"]:
            status_icon = "✅" if copy_info["status"] == "available" else "📦"
            status_text = (
                f"available"
                if copy_info["status"] == "available"
                else f"borrowed by {copy_info['borrower_name']}"
            )
            lines.append(f"  {status_icon} {copy_info['owner_name']} — _{status_text}_")
        lines.append("")

    await update.message.reply_text("\n".join(lines), parse_mode="Markdown")


# ── /library ─────────────────────────────────────────────────────────

async def library(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """List all games in the catalog."""
    if update.effective_chat is None:
        return

    db = context.bot_data["db"]
    from wmbgbot.db.queries import get_library

    games = get_library(db)

    if not games:
        await update.message.reply_text("The game library is empty. Use /addgame in DM to add games!")
        return

    lines = ["🎲 *Game Library*", ""]
    for g in games:
        lines.append(
            f"• *{g['title']}* — {g['total_copies']} copy(s), "
            f"{g['available_copies']} available"
        )

    await update.message.reply_text("\n".join(lines), parse_mode="Markdown")


# ── /mygames ─────────────────────────────────────────────────────────

async def mygames(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """List the caller's own copies."""
    if update.effective_chat is None or update.effective_user is None:
        return

    db = context.bot_data["db"]
    from wmbgbot.db.queries import get_user, get_user_copies

    user = get_user(db, update.effective_user.id)
    if user is None:
        await update.message.reply_text("You're not registered yet. Send /start in DM first.")
        return

    copies = get_user_copies(db, user.id)

    if not copies:
        await update.message.reply_text("You haven't added any games. Use /addgame in DM!")
        return

    lines = [f"🎲 *{user.display_name}'s Games*", ""]
    for c in copies:
        icon = "✅" if c["status"] == "available" else "📦"
        extra = f" — borrowed by {c['borrower_name']}" if c["status"] == "borrowed" else ""
        lines.append(f"{icon} *{c['title']}*{extra}")

    await update.message.reply_text("\n".join(lines), parse_mode="Markdown")


# ── /whohas ──────────────────────────────────────────────────────────

async def whohas(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Find who owns a specific game (stricter search)."""
    if update.effective_chat is None:
        return

    query = " ".join(context.args) if context.args else ""
    if not query.strip():
        await update.message.reply_text("Usage: /whohas <title>")
        return

    db = context.bot_data["db"]
    from wmbgbot.db.queries import search_games

    results = search_games(db, query)

    if not results:
        await update.message.reply_text(f"No games found matching '{query}'.")
        return

    lines = [f"👥 *Who has '{query}'?*", ""]
    for game in results:
        lines.append(f"*{game['title']}*:")
        for copy_info in game["copies"]:
            status_text = "✅ available" if copy_info["status"] == "available" else f"📦 borrowed by {copy_info['borrower_name']}"
            lines.append(f"  • {copy_info['owner_name']} — {status_text}")

    await update.message.reply_text("\n".join(lines), parse_mode="Markdown")


# ── /addgame (DM only) ───────────────────────────────────────────────

async def addgame(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Add a game via BGG lookup. DM only."""
    if update.effective_chat is None or update.effective_user is None:
        return

    if update.effective_chat.type != ChatType.PRIVATE:
        await update.message.reply_text("Please use /addgame in DM to add your games.")
        return

    query = " ".join(context.args) if context.args else ""
    if not query.strip():
        await update.message.reply_text("Usage: /addgame <title>")
        return

    db = context.bot_data["db"]
    from wmbgbot.db.queries import get_user, upsert_user

    telegram_id = update.effective_user.id
    display_name = update.effective_user.full_name or update.effective_user.username or "Unknown"

    # Ensure user exists
    user = get_user(db, telegram_id)
    if user is None:
        user = upsert_user(db, telegram_id, display_name)

    # Search BGG
    from wmbgbot.bgg import search_bgg, BGGError

    bgg_client = context.bot_data["bgg_client"]
    bgg_base = context.bot_data["config"].bgg_api_base_url

    try:
        bgg_results = await search_bgg(bgg_client, bgg_base, query)
    except BGGError:
        await update.message.reply_text("❌ Couldn't reach BoardGameGeek. Try again later.")
        return

    if not bgg_results:
        await update.message.reply_text(
            f"No results on BoardGameGeek for '{query}'.\n\n"
            "You can add it manually by typing the title now:"
        )
        # Store state for next text message
        context.user_data["awaiting_manual_title"] = True
        return

    if len(bgg_results) == 1:
        # Auto-confirm the single result
        await _add_game_by_bgg_id(update, context, bgg_results[0]["bgg_id"], bgg_results[0]["name"])
        return

    # Multiple results — present inline keyboard
    from telegram import InlineKeyboardButton, InlineKeyboardMarkup

    keyboard = []
    for r in bgg_results:
        label = r["name"]
        if r.get("yearpublished"):
            label += f" ({r['yearpublished']})"
        # Truncate callback data — Telegram limit is 64 bytes
        keyboard.append([
            InlineKeyboardButton(
                label,
                callback_data=f"addgame:{r['bgg_id']}:{r['name'][:32]}"
            )
        ])

    await update.message.reply_text(
        f"Multiple matches for '{query}'. Pick the right one:",
        reply_markup=InlineKeyboardMarkup(keyboard),
    )


async def _add_game_by_bgg_id(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
    bgg_id: int,
    fallback_title: str,
) -> None:
    """Fetch BGG details, create game + copy, confirm to user."""
    if update.effective_user is None:
        return

    db = context.bot_data["db"]
    bgg_client = context.bot_data["bgg_client"]
    bgg_base = context.bot_data["config"].bgg_api_base_url

    from wmbgbot.bgg import fetch_bgg_details, BGGError
    from wmbgbot.db.queries import add_game, add_copy, get_user

    try:
        details = await fetch_bgg_details(bgg_client, bgg_base, bgg_id)
    except BGGError:
        details = {"title": fallback_title, "thumbnail_url": None, "image_url": None}

    title = details["title"]
    cover = details.get("image_url") or details.get("thumbnail_url")

    game_id = add_game(db, bgg_id, title, cover)
    user = get_user(db, update.effective_user.id)
    assert user is not None
    add_copy(db, game_id, user.id)

    msg = f"✅ Added *{title}* to your collection!"
    if cover:
        msg += f"\n\n[Cover]({cover})"

    if update.callback_query:
        await update.callback_query.edit_message_text(msg, parse_mode="Markdown")
    else:
        await update.message.reply_text(msg, parse_mode="Markdown")


# ── /removegame (DM only) ────────────────────────────────────────────

async def removegame(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """List user's copies for removal. DM only."""
    if update.effective_chat is None or update.effective_user is None:
        return

    if update.effective_chat.type != ChatType.PRIVATE:
        await update.message.reply_text("Please use /removegame in DM.")
        return

    db = context.bot_data["db"]
    from wmbgbot.db.queries import get_user, get_user_copies

    user = get_user(db, update.effective_user.id)
    if user is None:
        await update.message.reply_text("You're not registered yet. Send /start in DM first.")
        return

    copies = get_user_copies(db, user.id)
    if not copies:
        await update.message.reply_text("You have no games to remove.")
        return

    from telegram import InlineKeyboardButton, InlineKeyboardMarkup

    lines = ["🗑️ *Remove a game* — tap to remove:", ""]
    keyboard = []

    for c in copies:
        if c["status"] == "borrowed":
            lines.append(f"🔒 *{c['title']}* — currently borrowed, can't remove")
        else:
            lines.append(f"• *{c['title']}*")
            keyboard.append([
                InlineKeyboardButton(
                    f"Remove: {c['title'][:48]}",
                    callback_data=f"remove:{c['copy_id']}",
                )
            ])

    if not keyboard:
        lines.append("\nNo available copies to remove.")

    reply_markup = InlineKeyboardMarkup(keyboard) if keyboard else None
    await update.message.reply_text(
        "\n".join(lines),
        parse_mode="Markdown",
        reply_markup=reply_markup,
    )


# ── /myrequests (DM only) ────────────────────────────────────────────

async def myrequests(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Show pending requests (incoming and outgoing). DM only."""
    if update.effective_chat is None or update.effective_user is None:
        return

    if update.effective_chat.type != ChatType.PRIVATE:
        await update.message.reply_text("Please use /myrequests in DM.")
        return

    db = context.bot_data["db"]
    from wmbgbot.db.queries import (
        get_user,
        get_pending_requests_for_owner,
        get_pending_requests_by_requester,
    )

    user = get_user(db, update.effective_user.id)
    if user is None:
        await update.message.reply_text("You're not registered yet. Send /start in DM first.")
        return

    incoming = get_pending_requests_for_owner(db, user.id)
    outgoing = get_pending_requests_by_requester(db, user.id)

    if not incoming and not outgoing:
        await update.message.reply_text("You have no pending requests.")
        return

    from telegram import InlineKeyboardButton, InlineKeyboardMarkup

    lines = []
    keyboard = []

    if incoming:
        lines.append("📥 *Incoming Requests* (you own the game):")
        for r in incoming:
            lines.append(
                f"  • {r['requester_name']} wants *{r['game_title']}*"
            )
            keyboard.append([
                InlineKeyboardButton(
                    f"✅ Accept — {r['game_title'][:30]}",
                    callback_data=f"accept:{r['request_id']}",
                ),
                InlineKeyboardButton(
                    f"❌ Decline — {r['game_title'][:30]}",
                    callback_data=f"decline:{r['request_id']}",
                ),
            ])
        lines.append("")

    if outgoing:
        lines.append("📤 *Outgoing Requests* (you requested):")
        for r in outgoing:
            lines.append(f"  • *{r['game_title']}* — waiting for {r['owner_name']}")
        lines.append("")

    reply_markup = InlineKeyboardMarkup(keyboard) if keyboard else None
    await update.message.reply_text(
        "\n".join(lines),
        parse_mode="Markdown",
        reply_markup=reply_markup,
    )


# ── /return (DM only) ────────────────────────────────────────────────

async def return_game(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """List active loans for the user to mark returned. DM only."""
    if update.effective_chat is None or update.effective_user is None:
        return

    if update.effective_chat.type != ChatType.PRIVATE:
        await update.message.reply_text("Please use /return in DM.")
        return

    db = context.bot_data["db"]
    from wmbgbot.db.queries import get_user, get_active_loans_for_user

    user = get_user(db, update.effective_user.id)
    if user is None:
        await update.message.reply_text("You're not registered yet. Send /start in DM first.")
        return

    loans = get_active_loans_for_user(db, user.id)
    if not loans:
        await update.message.reply_text("You have no active loans to return.")
        return

    from telegram import InlineKeyboardButton, InlineKeyboardMarkup

    lines = ["📦 *Active Loans* — tap to mark returned:", ""]
    keyboard = []

    for loan in loans:
        is_borrower = loan["borrower_id"] == user.id
        other = loan["owner_name"] if is_borrower else loan["borrower_name"]
        role = "Borrowed from" if is_borrower else "Lent to"
        lines.append(f"• *{loan['game_title']}* — {role} {other}")
        keyboard.append([
            InlineKeyboardButton(
                f"✅ Return: {loan['game_title'][:48]}",
                callback_data=f"return:{loan['loan_id']}",
            )
        ])

    reply_markup = InlineKeyboardMarkup(keyboard)
    await update.message.reply_text(
        "\n".join(lines),
        parse_mode="Markdown",
        reply_markup=reply_markup,
    )
