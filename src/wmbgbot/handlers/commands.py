"""Command handlers for the bot."""

from __future__ import annotations

import logging

from telegram import Update
from telegram.constants import ChatType
from telegram.ext import ContextTypes

logger = logging.getLogger(__name__)


# ── /start ───────────────────────────────────────────────────────────

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Register a user. In DM: welcomes and prompts for profile setup."""
    if update.effective_chat is None or update.effective_user is None:
        return

    if update.effective_chat.type != ChatType.PRIVATE:
        await update.message.reply_text(
            "Please send /start to me in a **private message** to complete your setup."
        )
        return

    db = context.bot_data["db"]
    from wmbgbot.db.queries import upsert_user, set_dm_started

    telegram_id = update.effective_user.id
    display_name = update.effective_user.full_name or update.effective_user.username or "Unknown"

    upsert_user(db, telegram_id, display_name)
    set_dm_started(db, telegram_id)

    await update.message.reply_text(
        f"Welcome, {display_name}! 🎲\n\n"
        "Let's set up your profile. Use /setprofile <city>, <neighborhood>\n"
        "Example: `/setprofile Bucharest, Pipera`\n\n"
        "Then add your games with /addgame <title>.\n"
        "Use /help to see all commands.",
        parse_mode="Markdown",
    )


# ── /setprofile ──────────────────────────────────────────────────────

async def set_profile(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Set city and neighborhood for the user."""
    if update.effective_chat is None or update.effective_user is None:
        return

    if update.effective_chat.type != ChatType.PRIVATE:
        await update.message.reply_text("Please use /setprofile in DM.")
        return

    db = context.bot_data["db"]
    from wmbgbot.db.queries import get_user, set_user_profile

    user = get_user(db, update.effective_user.id)
    if user is None:
        await update.message.reply_text("Send /start first to register.")
        return

    args = context.args
    if not args:
        await update.message.reply_text(
            "Usage: /setprofile <city>, <neighborhood>\n"
            "Example: `/setprofile Bucharest, Pipera`"
        )
        return

    joined = " ".join(args)
    parts = [p.strip() for p in joined.split(",", 1)]
    city = parts[0] if len(parts) > 0 else ""
    neighborhood = parts[1] if len(parts) > 1 else ""

    if not city:
        await update.message.reply_text(
            "Please provide at least a city. Example: `/setprofile Bucharest, Pipera`"
        )
        return

    set_user_profile(db, update.effective_user.id, city, neighborhood)

    await update.message.reply_text(
        f"✅ Profile updated: {city}" + (f", {neighborhood}" if neighborhood else ""),
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
        "/whohas \\<title\\> — Find who currently has a game\n"
        "/help — Show this help message"
    )

    dm_cmds = (
        "📬 *DM Commands*\n"
        "/start — Register with the bot\n"
        "/setprofile \\<city\\>\\, \\<neighborhood\\> — Set your location\n"
        "/addgame \\<title\\> — Add a game to your collection\n"
        "/removegame — Remove one of your copies\n"
        "/myrequests — View your pending borrow requests\n"
        "/return — Mark a borrowed game as returned"
    )

    admin_cmds = (
        "🔧 *Admin Commands*\n"
        "/admin\\_edit\\_game \\<copy\\_id\\> \\<new\\_title\\> — Fix a bad title\n"
        "/admin\\_remove\\_copy \\<copy\\_id\\> — Force-remove any copy\n"
        "/admin\\_reset\\_loan \\<loan\\_id\\> — Force-close a stuck loan\n"
        "/admin\\_list\\_users — List all registered users"
    )

    text = group_cmds
    if is_dm:
        text += "\n\n" + dm_cmds

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
                "available"
                if copy_info["status"] == "available"
                else f"held by {copy_info['borrower_name']}"
            )
            owner = copy_info["owner_name"]
            location = _format_location(copy_info.get("city"), copy_info.get("neighborhood"))
            lines.append(f"  {status_icon} {owner}{location} — _{status_text}_")
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
        extra = f" — held by {c['borrower_name']}" if c["status"] == "borrowed" else ""
        lines.append(f"{icon} *{c['title']}*{extra}")

    await update.message.reply_text("\n".join(lines), parse_mode="Markdown")


# ── /whohas ──────────────────────────────────────────────────────────

async def whohas(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Find who currently has a specific game."""
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
            owner = copy_info["owner_name"]
            location = _format_location(copy_info.get("city"), copy_info.get("neighborhood"))
            if copy_info["status"] == "available":
                lines.append(f"  ✅ {owner}{location} — available")
            else:
                lines.append(f"  📦 {copy_info['borrower_name']} — currently holding (owner: {owner}{location})")

    await update.message.reply_text("\n".join(lines), parse_mode="Markdown")


def _format_location(city: str | None, neighborhood: str | None) -> str:
    if not city:
        return ""
    parts = [city]
    if neighborhood:
        parts.append(neighborhood)
    return f" 📍({', '.join(parts)})"


# ── /addgame (DM only) ───────────────────────────────────────────────

async def addgame(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Add a game directly by title. DM only."""
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
    from wmbgbot.db.queries import get_user, upsert_user, add_game, add_copy

    telegram_id = update.effective_user.id
    display_name = update.effective_user.full_name or update.effective_user.username or "Unknown"

    user = get_user(db, telegram_id)
    if user is None:
        user = upsert_user(db, telegram_id, display_name)

    game_id = add_game(db, None, query, None)
    add_copy(db, game_id, user.id)

    await update.message.reply_text(f"✅ Added *{query}* to your collection!", parse_mode="Markdown")


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
            lines.append(f"🔒 *{c['title']}* — currently out, can't remove")
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
        "\n".join(lines), parse_mode="Markdown", reply_markup=reply_markup,
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
        lines.append("📥 *Incoming Requests* (they want a game you hold):")
        for r in incoming:
            lines.append(f"  • {r['requester_name']} wants *{r['game_title']}*")
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
        "\n".join(lines), parse_mode="Markdown", reply_markup=reply_markup,
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
        "\n".join(lines), parse_mode="Markdown", reply_markup=reply_markup,
    )


# ── Manual text handler (DM) ─────────────────────────────────────────

async def handle_manual_title(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handle free-text in DM — currently does nothing unless awaiting_manual_title."""
    if update.message is None or update.message.text is None:
        return
    if update.effective_chat.type != ChatType.PRIVATE:
        return
    if not context.user_data.get("awaiting_manual_title"):
        return

    text = update.message.text.strip()
    if text.startswith("/"):
        return

    if text.lower() == "/cancel":
        context.user_data.pop("awaiting_manual_title", None)
        await update.message.reply_text("Canceled.")
        return

    db = context.bot_data["db"]
    from wmbgbot.db.queries import get_user, add_game, add_copy

    user = get_user(db, update.effective_user.id)
    if user is None:
        await update.message.reply_text("You're not registered yet. Send /start in DM first.")
        return

    game_id = add_game(db, None, text, None)
    add_copy(db, game_id, user.id)

    context.user_data.pop("awaiting_manual_title", None)
    await update.message.reply_text(f"✅ Added *{text}* to your collection!", parse_mode="Markdown")
