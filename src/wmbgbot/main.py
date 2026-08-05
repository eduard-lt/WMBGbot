"""WMBGbot entry point — builds and runs the Telegram bot."""

from __future__ import annotations

import logging

from telegram.ext import (
    Application,
    CallbackQueryHandler,
    CommandHandler,
    ContextTypes,
    MessageHandler,
    filters,
)

from wmbgbot.config import Config
from wmbgbot.db import init_db
from wmbgbot.handlers import (
    addgame,
    admin_edit_game,
    admin_list_users,
    admin_remove_copy,
    admin_reset_loan,
    handle_accept,
    handle_borrow,
    handle_decline,
    handle_game_detail,
    handle_manual_title,
    handle_menu_callback,
    handle_remove,
    handle_return,
    help_command,
    library,
    menu,
    mygames,
    myrequests,
    removegame,
    return_game,
    search,
    set_profile,
    start,
    whohas,
)
from wmbgbot.logging_config import setup_logging

logger = logging.getLogger(__name__)


def main() -> None:
    """Build the Application and start polling."""
    config = Config.from_env()
    setup_logging(config)

    logger.info("Starting WMBGbot...")

    # Initialize database
    db = init_db(config.resolved_db_path)
    logger.info("Database initialized at %s", config.resolved_db_path)

    # Build the bot Application
    app = (
        Application.builder()
        .token(config.bot_token)
        .build()
    )

    # Store shared resources in bot_data
    app.bot_data["db"] = db
    app.bot_data["config"] = config

    # ── Register command handlers ──────────────────────────────────
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("menu", menu))
    app.add_handler(CommandHandler("help", help_command))
    app.add_handler(CommandHandler("search", search))
    app.add_handler(CommandHandler("library", library))
    app.add_handler(CommandHandler("mygames", mygames))
    app.add_handler(CommandHandler("whohas", whohas))
    app.add_handler(CommandHandler("addgame", addgame))
    app.add_handler(CommandHandler("removegame", removegame))
    app.add_handler(CommandHandler("myrequests", myrequests))
    app.add_handler(CommandHandler("return", return_game))
    app.add_handler(CommandHandler("setprofile", set_profile))

    # Text handler in group=1 so commands fire first
    app.add_handler(MessageHandler(filters.TEXT & filters.ChatType.PRIVATE, handle_manual_title), group=1)

    # Admin commands
    app.add_handler(CommandHandler("admin_edit_game", admin_edit_game))
    app.add_handler(CommandHandler("admin_remove_copy", admin_remove_copy))
    app.add_handler(CommandHandler("admin_reset_loan", admin_reset_loan))
    app.add_handler(CommandHandler("admin_list_users", admin_list_users))

    # ── Register callback handlers ─────────────────────────────────
    app.add_handler(CallbackQueryHandler(handle_borrow, pattern=r"^borrow:"))
    app.add_handler(CallbackQueryHandler(handle_accept, pattern=r"^accept:"))
    app.add_handler(CallbackQueryHandler(handle_decline, pattern=r"^decline:"))
    app.add_handler(CallbackQueryHandler(handle_remove, pattern=r"^remove:"))
    app.add_handler(CallbackQueryHandler(handle_return, pattern=r"^return:"))
    app.add_handler(CallbackQueryHandler(handle_menu_callback, pattern=r"^menu:"))
    app.add_handler(CallbackQueryHandler(handle_game_detail, pattern=r"^game:"))

    # ── Error handler ──────────────────────────────────────────────
    async def error_handler(update: object, context: ContextTypes.DEFAULT_TYPE) -> None:
        logger.error("Unhandled error: %s", context.error, exc_info=context.error)

    app.add_error_handler(error_handler)

    # ── Register bot commands for Telegram's auto-complete menu ────
    import asyncio as _asyncio
    from telegram import BotCommand
    from telegram import BotCommandScopeAllGroupChats as GroupScope
    from telegram import BotCommandScopeAllPrivateChats as DMScope

    group_commands = [
        BotCommand("menu", "Main menu with buttons"),
        BotCommand("search", "Search the game catalog by title"),
        BotCommand("library", "List all games in the catalog"),
        BotCommand("mygames", "Show your own copies"),
        BotCommand("whohas", "Find who currently has a game"),
        BotCommand("help", "Show all commands"),
    ]

    dm_commands = group_commands + [
        BotCommand("start", "Register with the bot"),
        BotCommand("setprofile", "Set your city and neighborhood"),
        BotCommand("addgame", "Add a game to your collection"),
        BotCommand("removegame", "Remove one of your copies"),
        BotCommand("myrequests", "View pending borrow requests"),
        BotCommand("return", "Mark a borrowed game as returned"),
    ]

    loop = _asyncio.get_event_loop()
    loop.run_until_complete(app.bot.set_my_commands(
        commands=group_commands, scope=GroupScope(),
    ))
    loop.run_until_complete(app.bot.set_my_commands(
        commands=dm_commands, scope=DMScope(),
    ))
    logger.info("Bot commands registered with Telegram")

    # ── Start polling ──────────────────────────────────────────────
    logger.info("Bot is running. Press Ctrl+C to stop.")
    app.run_polling(allowed_updates=["message", "callback_query"])


if __name__ == "__main__":
    import asyncio

    # Python 3.12+ requires an explicit event loop for run_polling
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    try:
        main()
    finally:
        loop.close()
