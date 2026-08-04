"""Handler modules for the bot."""

from wmbgbot.handlers.commands import (
    addgame,
    handle_manual_title,
    help_command,
    library,
    mygames,
    myrequests,
    removegame,
    return_game,
    search,
    start,
    whohas,
)
from wmbgbot.handlers.callbacks import (
    handle_accept,
    handle_addgame_callback,
    handle_borrow,
    handle_decline,
    handle_remove,
    handle_return,
)
from wmbgbot.handlers.admin import (
    admin_edit_game,
    admin_list_users,
    admin_remove_copy,
    admin_reset_loan,
)

__all__ = [
    # Commands
    "addgame",
    "handle_manual_title",
    "help_command",
    "library",
    "mygames",
    "myrequests",
    "removegame",
    "return_game",
    "search",
    "start",
    "whohas",
    # Callbacks
    "handle_accept",
    "handle_addgame_callback",
    "handle_borrow",
    "handle_decline",
    "handle_remove",
    "handle_return",
    # Admin
    "admin_edit_game",
    "admin_list_users",
    "admin_remove_copy",
    "admin_reset_loan",
]
