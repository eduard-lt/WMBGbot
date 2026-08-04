"""Admin-only command handlers."""

from __future__ import annotations

import logging

from telegram import Update
from telegram.ext import ContextTypes

logger = logging.getLogger(__name__)


async def _check_admin(update: Update, context: ContextTypes.DEFAULT_TYPE) -> bool:
    """Return True if the effective user is an admin, else reply and return False."""
    if update.effective_user is None:
        return False

    db = context.bot_data["db"]
    from wmbgbot.db.queries import get_user

    user = get_user(db, update.effective_user.id)
    if user is None or not user.is_admin:
        if update.message:
            await update.message.reply_text("⛔ Not authorized. Admin only.")
        elif update.callback_query:
            await update.callback_query.answer("Not authorized.", show_alert=True)
        return False
    return True


# ── /admin_edit_game <copy_id> <new_title> ───────────────────────────

async def admin_edit_game(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Force-edit a copy's linked game title."""
    if not await _check_admin(update, context):
        return

    if update.message is None or not context.args:
        await update.message.reply_text(
            "Usage: /admin_edit_game <copy_id> <new_title>"
        )
        return

    if len(context.args) < 2:
        await update.message.reply_text("Please provide both copy_id and new title.")
        return

    try:
        copy_id = int(context.args[0])
    except ValueError:
        await update.message.reply_text("copy_id must be a number.")
        return

    new_title = " ".join(context.args[1:])
    db = context.bot_data["db"]

    from wmbgbot.db.queries import admin_edit_copy_game, get_copy

    copy = get_copy(db, copy_id)
    if copy is None:
        await update.message.reply_text(f"Copy {copy_id} not found.")
        return

    admin_edit_copy_game(db, copy_id, new_title)
    logger.info("Admin %d edited copy %d title to '%s'", update.effective_user.id, copy_id, new_title)
    await update.message.reply_text(f"✅ Copy {copy_id} title updated to '{new_title}'.")


# ── /admin_remove_copy <copy_id> ─────────────────────────────────────

async def admin_remove_copy(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Force-remove any copy regardless of status."""
    if not await _check_admin(update, context):
        return

    if update.message is None or not context.args:
        await update.message.reply_text("Usage: /admin_remove_copy <copy_id>")
        return

    try:
        copy_id = int(context.args[0])
    except ValueError:
        await update.message.reply_text("copy_id must be a number.")
        return

    db = context.bot_data["db"]
    from wmbgbot.db.queries import admin_remove_copy

    if admin_remove_copy(db, copy_id):
        logger.info("Admin %d force-removed copy %d", update.effective_user.id, copy_id)
        await update.message.reply_text(f"✅ Copy {copy_id} force-removed.")
    else:
        await update.message.reply_text(f"Copy {copy_id} not found.")


# ── /admin_reset_loan <loan_id> ──────────────────────────────────────

async def admin_reset_loan(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Force-close a stuck loan."""
    if not await _check_admin(update, context):
        return

    if update.message is None or not context.args:
        await update.message.reply_text("Usage: /admin_reset_loan <loan_id>")
        return

    try:
        loan_id = int(context.args[0])
    except ValueError:
        await update.message.reply_text("loan_id must be a number.")
        return

    db = context.bot_data["db"]
    from wmbgbot.db.queries import admin_reset_loan

    if admin_reset_loan(db, loan_id):
        logger.info("Admin %d force-closed loan %d", update.effective_user.id, loan_id)
        await update.message.reply_text(f"✅ Loan {loan_id} force-closed.")
    else:
        await update.message.reply_text(f"Loan {loan_id} not found or already returned.")


# ── /admin_list_users ────────────────────────────────────────────────

async def admin_list_users(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """List all registered users."""
    if not await _check_admin(update, context):
        return

    db = context.bot_data["db"]
    from wmbgbot.db.queries import get_all_users

    users = get_all_users(db)

    if not users:
        await update.message.reply_text("No registered users.")
        return

    lines = ["👥 *Registered Users*", ""]
    for u in users:
        admin_tag = " 👑" if u.is_admin else ""
        dm_tag = "" if u.dm_started else " ⚠️ no DM"
        lines.append(
            f"• {u.display_name} (id:{u.telegram_id}){admin_tag}{dm_tag}"
        )

    await update.message.reply_text("\n".join(lines), parse_mode="Markdown")
