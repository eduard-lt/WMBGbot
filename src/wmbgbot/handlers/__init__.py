"""Handler modules for the bot."""

from wmbgbot.handlers.commands import (
    addgame,
    handle_game_detail,
    handle_manual_title,
    handle_menu_callback,
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
from wmbgbot.handlers.callbacks import (
    handle_accept,
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
    "addgame",
    "handle_game_detail",
    "handle_manual_title",
    "handle_menu_callback",
    "help_command",
    "library",
    "menu",
    "mygames",
    "myrequests",
    "removegame",
    "return_game",
    "search",
    "set_profile",
    "start",
    "whohas",
    "handle_accept",
    "handle_borrow",
    "handle_decline",
    "handle_remove",
    "handle_return",
    "admin_edit_game",
    "admin_list_users",
    "admin_remove_copy",
    "admin_reset_loan",
]
