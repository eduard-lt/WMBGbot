"""Command handlers for the bot."""

from __future__ import annotations

import logging

from telegram import CallbackQuery, Message, Update
from telegram.constants import ChatType
from telegram.ext import ContextTypes

logger = logging.getLogger(__name__)


# ── /start ───────────────────────────────────────────────────────────

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Register a user. Requires invite code: /start <code>"""
    if update.effective_chat is None or update.effective_user is None:
        return

    if update.effective_chat.type != ChatType.PRIVATE:
        await update.message.reply_text(
            "Please send /start to me in a **private message** to complete your setup."
        )
        return

    db = context.bot_data["db"]
    config = context.bot_data["config"]
    from wmbgbot.db.queries import get_user, upsert_user, set_dm_started

    telegram_id = update.effective_user.id

    # Already registered? Just show welcome back
    existing = get_user(db, telegram_id)
    if existing is not None:
        set_dm_started(db, telegram_id)
        await update.message.reply_text(
            f"Welcome back, {existing.display_name}! 🎲\n\n"
            "You're already registered. Use /menu to see what you can do.",
            parse_mode="Markdown",
        )
        return

    # New user — validate invite code
    code = " ".join(context.args) if context.args else ""
    expected = config.invite_code

    if not code or code != expected:
        await update.message.reply_text(
            "🔐 To join this board game group, you need an invite code.\n\n"
            "Use `/start <code>` with the code shared by the group admin."
        )
        return

    # Register
    display_name = update.effective_user.full_name or update.effective_user.username or "Unknown"
    upsert_user(db, telegram_id, display_name)
    set_dm_started(db, telegram_id)

    await update.message.reply_text(
        f"Welcome, {display_name}! 🎲\n\n"
        "Let's set up your profile. Use /setprofile <city>, <neighborhood>\n"
        "Example: `/setprofile Bucharest, Pipera`\n\n"
        "Then use /menu to see what you can do!",
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
        await update.message.reply_text("Please provide at least a city.")
        return

    set_user_profile(db, update.effective_user.id, city, neighborhood)

    await update.message.reply_text(
        f"✅ Profile updated: {city}" + (f", {neighborhood}" if neighborhood else ""),
    )


# ── /menu (DM) ───────────────────────────────────────────────────────

async def menu(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Show main action buttons."""
    if update.effective_chat is None:
        return

    from telegram import InlineKeyboardButton, InlineKeyboardMarkup

    if update.effective_chat.type == ChatType.PRIVATE:
        keyboard = [
            [InlineKeyboardButton("➕ Add a game", callback_data="menu:addgame")],
            [InlineKeyboardButton("🗑️ Remove a game", callback_data="menu:removegame")],
            [InlineKeyboardButton("📋 My requests", callback_data="menu:myrequests")],
            [InlineKeyboardButton("📦 Return a game", callback_data="menu:return")],
            [InlineKeyboardButton("📍 Set my location", callback_data="menu:setprofile")],
        ]
        text = "🎲 *Menu* — what would you like to do?"
    else:
        keyboard = [
            [InlineKeyboardButton("🔍 Search games", switch_inline_query_current_chat="")],
            [InlineKeyboardButton("📚 Library", callback_data="menu:library")],
            [InlineKeyboardButton("👥 Who has?", callback_data="menu:whohas")],
        ]
        text = "🎲 *Menu* — what would you like to do?"

    await update.message.reply_text(
        text,
        parse_mode="Markdown",
        reply_markup=InlineKeyboardMarkup(keyboard),
    )


# ── /help ────────────────────────────────────────────────────────────

async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Show available commands."""
    is_dm = update.effective_chat is not None and update.effective_chat.type == ChatType.PRIVATE

    group_cmds = (
        "🎲 *Group Commands*\n"
        "/menu — Main menu with buttons\n"
        "/search \\<title\\> — Search the catalog\n"
        "/library — Browse all games\n"
        "/mygames — Show your copies\n"
        "/whohas \\<title\\> — Find who has a game\n"
        "/help — Show this help"
    )

    dm_cmds = (
        "📬 *DM Commands*\n"
        "/menu — Main menu with buttons\n"
        "/start — Register with the bot\n"
        "/setprofile \\<city\\>\\, \\<neighborhood\\> — Set your location\n"
        "/addgame — Add a game to your collection\n"
        "/removegame — Remove one of your copies\n"
        "/myrequests — View pending borrow requests\n"
        "/return — Mark a borrowed game as returned"
    )

    text = group_cmds
    if is_dm:
        text += "\n\n" + dm_cmds

    db = context.bot_data["db"]
    if update.effective_user is not None:
        from wmbgbot.db.queries import get_user
        user = get_user(db, update.effective_user.id)
        if user and user.is_admin:
            text += (
                "\n\n🔧 *Admin Commands*\n"
                "/admin\\_list\\_users — List all users\n"
                "/admin\\_edit\\_game \\<id\\> \\<title\\> — Fix a title\n"
                "/admin\\_remove\\_copy \\<id\\> — Force-remove a copy\n"
                "/admin\\_reset\\_loan \\<id\\> — Force-close a loan"
            )

    await update.message.reply_text(text, parse_mode="Markdown")


# ── /menu callback handler ───────────────────────────────────────────

async def handle_menu_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handle menu button presses."""
    query = update.callback_query
    if query is None:
        return

    await query.answer()
    data = (query.data or "").split(":", 1)[1] if ":" in (query.data or "") else ""

    if data == "addgame":
        await _prompt_addgame(query, context)
    elif data == "removegame":
        await _show_remove_list(query, context)
    elif data == "myrequests":
        await _show_myrequests(query, context)
    elif data == "return":
        await _show_return_list(query, context)
    elif data == "setprofile":
        await query.edit_message_text(
            "Use /setprofile <city>, <neighborhood>\n"
            "Example: `/setprofile Bucharest, Pipera`",
            parse_mode="Markdown",
        )
    elif data == "library":
        await _show_library(query, context)
    elif data == "whohas":
        await query.edit_message_text(
            "Use /whohas <title> to find who has a specific game."
        )


# ── /addgame (DM only) ───────────────────────────────────────────────

async def addgame(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Prompt to add a game. With args: adds directly. Without: prompts for title."""
    if update.effective_chat is None or update.effective_user is None:
        return

    if update.effective_chat.type != ChatType.PRIVATE:
        await update.message.reply_text("Please use /addgame in DM.")
        return

    args = " ".join(context.args) if context.args else ""

    if args.strip():
        # Direct add with args
        await _do_add_game(update.effective_user.id, args.strip(), update.message, context)
    else:
        # Prompt for title
        await _prompt_addgame(update.message, context)


async def _prompt_addgame(target: Message | CallbackQuery, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Ask user to type the game title."""
    context.user_data["awaiting_game_title"] = True
    if isinstance(target, Message):
        await target.reply_text("🎲 What game do you want to add? Just type the title:")
    else:
        await target.edit_message_text("🎲 What game do you want to add? Just type the title:")


async def _do_add_game(
    telegram_id: int,
    title: str,
    target,
    context: ContextTypes.DEFAULT_TYPE,
) -> None:
    """Add a game to the user's collection."""
    db = context.bot_data["db"]
    from wmbgbot.db.queries import get_user, upsert_user, add_game, add_copy

    # Get display name from wherever we can
    display_name = "User"
    from_user = getattr(target, 'from_user', None)
    eff_user = getattr(target, 'effective_user', None)
    user_obj = eff_user or from_user
    if user_obj:
        display_name = user_obj.full_name or user_obj.username or "Unknown"

    user = get_user(db, telegram_id)
    if user is None:
        user = upsert_user(db, telegram_id, display_name)

    game_id = add_game(db, None, title, None)
    add_copy(db, game_id, user.id)

    text = f"✅ Added *{title}* to your collection!"

    # Message has reply_text, CallbackQuery has edit_message_text
    if hasattr(target, 'reply_text'):
        await target.reply_text(text, parse_mode="Markdown")
    else:
        await target.edit_message_text(text, parse_mode="Markdown")


# ── /removegame (DM only) ────────────────────────────────────────────

async def removegame(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """List user's copies for removal. DM only."""
    if update.effective_chat is None or update.effective_user is None:
        return
    if update.effective_chat.type != ChatType.PRIVATE:
        await update.message.reply_text("Please use /removegame in DM.")
        return
    await _show_remove_list(update.message, context)


async def _show_remove_list(
    target: Message | CallbackQuery,
    context: ContextTypes.DEFAULT_TYPE,
) -> None:
    if target.from_user is None:
        return

    db = context.bot_data["db"]
    from wmbgbot.db.queries import get_user, get_user_copies
    from telegram import InlineKeyboardButton, InlineKeyboardMarkup

    user = get_user(db, target.from_user.id)
    if user is None:
        await _reply(target, "You're not registered yet. Send /start in DM first.")
        return

    copies = get_user_copies(db, user.id)
    if not copies:
        await _reply(target, "You have no games to remove.")
        return

    lines = ["🗑️ *Remove a game*:"]
    keyboard = []
    for c in copies:
        if c["status"] == "borrowed":
            lines.append(f"🔒 *{c['title']}* — currently out")
        else:
            keyboard.append([
                InlineKeyboardButton(
                    f"🗑️ {c['title'][:50]}",
                    callback_data=f"remove:{c['copy_id']}",
                )
            ])

    if not keyboard:
        lines.append("\nNo available copies to remove.")

    reply_markup = InlineKeyboardMarkup(keyboard) if keyboard else None
    await _reply(target, "\n".join(lines), parse_mode="Markdown", reply_markup=reply_markup)


# ── /library ─────────────────────────────────────────────────────────

async def library(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """List all games as buttons. Works in group or DM."""
    if update.effective_chat is None or update.effective_user is None:
        return
    await _show_library(update.message, context)


async def _show_library(
    target: Message | CallbackQuery,
    context: ContextTypes.DEFAULT_TYPE,
) -> None:
    db = context.bot_data["db"]
    from wmbgbot.db.queries import get_library_full
    from telegram import InlineKeyboardButton, InlineKeyboardMarkup

    games = get_library_full(db)

    if not games:
        await _reply(target, "The game library is empty. Use /addgame in DM to add games!")
        return

    # Build button rows: 2 per row
    keyboard = []
    row = []
    for g in games:
        avail = g["available_copies"]
        total = g["total_copies"]
        label = f"{g['title'][:40]} ({avail}/{total})"
        row.append(InlineKeyboardButton(label, callback_data=f"game:{g['game_id']}"))
        if len(row) == 2:
            keyboard.append(row)
            row = []
    if row:
        keyboard.append(row)

    text = "📚 *Game Library* — tap a game for details:"
    await _reply(target, text, parse_mode="Markdown", reply_markup=InlineKeyboardMarkup(keyboard))


# ── Game detail callback ─────────────────────────────────────────────

async def handle_game_detail(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Show detail view for a game: all copies, owners, status, location, borrow button."""
    query = update.callback_query
    if query is None or update.effective_user is None:
        return

    await query.answer()

    game_id = int((query.data or "").split(":")[1])
    db = context.bot_data["db"]

    from wmbgbot.db.queries import get_game_copies_detail
    from telegram import InlineKeyboardButton, InlineKeyboardMarkup

    copies = get_game_copies_detail(db, game_id)

    if not copies:
        await query.edit_message_text("No copies of this game found.")
        return

    title = copies[0]["title"]
    lines = [f"🎲 *{title}*", ""]
    keyboard = []

    for c in copies:
        owner = c["owner_name"]
        city = c.get("city", "")
        neighborhood = c.get("neighborhood", "")
        loc = f"📍 {city}" if city else ""
        if neighborhood:
            loc += f", {neighborhood}"

        if c["status"] == "available":
            lines.append(f"✅ Owned by {owner} {loc}")
            keyboard.append([
                InlineKeyboardButton(
                    f"📬 Request from {owner}",
                    callback_data=f"borrow:{c['copy_id']}",
                )
            ])
        else:
            holder = c["borrower_name"] or "?"
            lines.append(f"📦 Owned by {owner} {loc}\n   → Currently with *{holder}*")
            if c["borrower_id"] != update.effective_user.id:
                keyboard.append([
                    InlineKeyboardButton(
                        f"📬 Request from {holder}",
                        callback_data=f"borrow:{c['copy_id']}",
                    )
                ])

    # "Back to library" button
    keyboard.append([
        InlineKeyboardButton("◀️ Back to library", callback_data="menu:library")
    ])

    await query.edit_message_text(
        "\n".join(lines),
        parse_mode="Markdown",
        reply_markup=InlineKeyboardMarkup(keyboard),
    )


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
    from telegram import InlineKeyboardButton, InlineKeyboardMarkup

    results = search_games(db, query)

    if not results:
        await update.message.reply_text(f"No games found matching '{query}'.")
        return

    # Build buttons for each game found
    keyboard = []
    for game in results:
        label = game["title"][:50]
        keyboard.append([
            InlineKeyboardButton(label, callback_data=f"game:{game['game_id']}")
        ])

    await update.message.reply_text(
        f"🔍 *Results for '{query}':*",
        parse_mode="Markdown",
        reply_markup=InlineKeyboardMarkup(keyboard),
    )


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
    from telegram import InlineKeyboardButton, InlineKeyboardMarkup

    results = search_games(db, query)

    if not results:
        await update.message.reply_text(f"No games found matching '{query}'.")
        return

    # Show first match's detail view directly
    game_id = results[0]["game_id"]
    # Build a fake callback query to reuse handle_game_detail
    # Instead, show summary
    lines = [f"👥 *Who has '{query}'?*", ""]
    for game in results[:3]:  # max 3 games
        lines.append(f"*{game['title']}*:")
        for c in game["copies"]:
            owner = c["owner_name"]
            loc = _format_location(c.get("city"), c.get("neighborhood"))
            if c["status"] == "available":
                lines.append(f"  ✅ {owner}{loc} — available")
            else:
                lines.append(f"  📦 {c['borrower_name']} — holding (owner: {owner}{loc})")

    keyboard = []
    for game in results[:3]:
        keyboard.append([
            InlineKeyboardButton(
                f"Details: {game['title'][:40]}",
                callback_data=f"game:{game['game_id']}",
            )
        ])

    await update.message.reply_text(
        "\n".join(lines),
        parse_mode="Markdown",
        reply_markup=InlineKeyboardMarkup(keyboard) if keyboard else None,
    )


# ── /mygames ─────────────────────────────────────────────────────────

async def mygames(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """List the caller's own copies."""
    if update.effective_chat is None or update.effective_user is None:
        return

    db = context.bot_data["db"]
    from wmbgbot.db.queries import get_user, get_user_copies
    from telegram import InlineKeyboardButton, InlineKeyboardMarkup

    user = get_user(db, update.effective_user.id)
    if user is None:
        await update.message.reply_text("You're not registered yet. Send /start in DM first.")
        return

    copies = get_user_copies(db, user.id)
    if not copies:
        await update.message.reply_text("You haven't added any games. Use /addgame in DM!")
        return

    lines = [f"🎲 *{user.display_name}'s Games*"]
    keyboard = []
    for c in copies:
        icon = "✅" if c["status"] == "available" else "📦"
        extra = f" — held by {c['borrower_name']}" if c["status"] == "borrowed" else ""
        lines.append(f"{icon} *{c['title']}*{extra}")
        keyboard.append([
            InlineKeyboardButton(
                f"{'✅' if c['status'] == 'available' else '📦'} {c['title'][:45]}",
                callback_data=f"game:{c['game_id']}",
            )
        ])

    await update.message.reply_text(
        "\n".join(lines),
        parse_mode="Markdown",
        reply_markup=InlineKeyboardMarkup(keyboard) if keyboard else None,
    )


# ── /myrequests (DM only) ────────────────────────────────────────────

async def myrequests(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Show pending requests. DM only."""
    if update.effective_chat is None or update.effective_user is None:
        return
    if update.effective_chat.type != ChatType.PRIVATE:
        await update.message.reply_text("Please use /myrequests in DM.")
        return
    await _show_myrequests(update.message, context)


async def _show_myrequests(
    target: Message | CallbackQuery,
    context: ContextTypes.DEFAULT_TYPE,
) -> None:
    if target.from_user is None:
        return

    db = context.bot_data["db"]
    from wmbgbot.db.queries import (
        get_user,
        get_pending_requests_for_owner,
        get_pending_requests_by_requester,
    )
    from telegram import InlineKeyboardButton, InlineKeyboardMarkup

    user = get_user(db, target.from_user.id)
    if user is None:
        await _reply(target, "You're not registered yet. Send /start in DM first.")
        return

    incoming = get_pending_requests_for_owner(db, user.id)
    outgoing = get_pending_requests_by_requester(db, user.id)

    if not incoming and not outgoing:
        await _reply(target, "You have no pending requests.")
        return

    lines = []
    keyboard = []

    if incoming:
        lines.append("📥 *Incoming Requests*:")
        for r in incoming:
            lines.append(f"  • {r['requester_name']} wants *{r['game_title']}*")
            keyboard.append([
                InlineKeyboardButton(f"✅ {r['game_title'][:30]}", callback_data=f"accept:{r['request_id']}"),
                InlineKeyboardButton("❌ Decline", callback_data=f"decline:{r['request_id']}"),
            ])
        lines.append("")

    if outgoing:
        lines.append("📤 *Outgoing Requests*:")
        for r in outgoing:
            lines.append(f"  • *{r['game_title']}* — waiting for {r['owner_name']}")
        lines.append("")

    await _reply(target, "\n".join(lines), parse_mode="Markdown", reply_markup=InlineKeyboardMarkup(keyboard) if keyboard else None)


# ── /return (DM only) ────────────────────────────────────────────────

async def return_game(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """List active loans. DM only."""
    if update.effective_chat is None or update.effective_user is None:
        return
    if update.effective_chat.type != ChatType.PRIVATE:
        await update.message.reply_text("Please use /return in DM.")
        return
    await _show_return_list(update.message, context)


async def _show_return_list(
    target: Message | CallbackQuery,
    context: ContextTypes.DEFAULT_TYPE,
) -> None:
    if target.from_user is None:
        return

    db = context.bot_data["db"]
    from wmbgbot.db.queries import get_user, get_active_loans_for_user
    from telegram import InlineKeyboardButton, InlineKeyboardMarkup

    user = get_user(db, target.from_user.id)
    if user is None:
        await _reply(target, "You're not registered yet. Send /start in DM first.")
        return

    loans = get_active_loans_for_user(db, user.id)
    if not loans:
        await _reply(target, "You have no active loans.")
        return

    lines = ["📦 *Active Loans* — tap to mark returned:"]
    keyboard = []
    for loan in loans:
        is_borrower = loan["borrower_id"] == user.id
        other = loan["owner_name"] if is_borrower else loan["borrower_name"]
        role = "From" if is_borrower else "To"
        lines.append(f"• *{loan['game_title']}* — {role} {other}")
        keyboard.append([
            InlineKeyboardButton(f"✅ {loan['game_title'][:48]}", callback_data=f"return:{loan['loan_id']}")
        ])

    await _reply(target, "\n".join(lines), parse_mode="Markdown", reply_markup=InlineKeyboardMarkup(keyboard))


# ── Manual text handler (DM) ─────────────────────────────────────────

async def handle_manual_title(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handle free-text in DM for addgame prompt or manual title fallback."""
    if update.message is None or update.message.text is None:
        return
    if update.effective_chat is None or update.effective_chat.type != ChatType.PRIVATE:
        return
    if update.effective_user is None:
        return

    text = update.message.text.strip()
    if text.startswith("/"):
        return

    # Check if we're waiting for a game title
    if context.user_data.get("awaiting_game_title"):
        context.user_data.pop("awaiting_game_title", None)
        await _do_add_game(update.effective_user.id, text, update, context)
        return

    # Legacy manual title flow
    if context.user_data.get("awaiting_manual_title"):
        context.user_data.pop("awaiting_manual_title", None)
        await _do_add_game(update.effective_user.id, text, update, context)
        return


# ── Helpers ──────────────────────────────────────────────────────────

def _format_location(city: str | None, neighborhood: str | None) -> str:
    if not city:
        return ""
    parts = [city]
    if neighborhood:
        parts.append(neighborhood)
    return f" 📍({', '.join(parts)})"


async def _reply(
    target: Message | CallbackQuery,
    text: str,
    **kwargs,
) -> None:
    """Reply to either a message or callback query."""
    if isinstance(target, CallbackQuery):
        await target.edit_message_text(text, **kwargs)
    else:
        await target.reply_text(text, **kwargs)
