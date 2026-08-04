"""Inline callback query handlers."""

from __future__ import annotations

import logging

from telegram import Update
from telegram.ext import ContextTypes

logger = logging.getLogger(__name__)


# ── Borrow callback ──────────────────────────────────────────────────

async def handle_borrow(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handle 'Borrow' button from search results.

    Request goes to the current holder: the owner if available,
    or the current borrower if already on loan.
    """
    query = update.callback_query
    if query is None or update.effective_user is None:
        return

    await query.answer()

    data = query.data
    if not data or not data.startswith("borrow:"):
        return

    copy_id = int(data.split(":")[1])
    db = context.bot_data["db"]

    from wmbgbot.db.queries import (
        get_copy,
        get_user,
        get_user_by_id,
        has_pending_request,
        create_request,
    )

    requester = get_user(db, update.effective_user.id)
    if requester is None:
        await query.edit_message_text("You're not registered. Send /start in DM first.")
        return

    copy = get_copy(db, copy_id)
    if copy is None:
        await query.edit_message_text("This copy no longer exists.")
        return

    if copy.owner_id == requester.id:
        await query.edit_message_text("You can't borrow your own game!")
        return

    # Determine the current holder
    if copy.status == "available":
        holder = get_user_by_id(db, copy.owner_id)
        holder_label = "the owner"
    else:
        loan_row = db.execute(
            "SELECT borrower_id FROM loans WHERE copy_id = ? AND returned_at IS NULL",
            (copy_id,),
        ).fetchone()
        if loan_row is None:
            await query.edit_message_text("This copy is in an unexpected state.")
            return
        holder = get_user_by_id(db, loan_row[0])
        holder_label = "the current holder"

    if holder is None:
        await query.edit_message_text("Couldn't find the holder's account.")
        return

    if holder.id == requester.id:
        await query.edit_message_text("You already have this game!")
        return

    if not holder.dm_started:
        await query.edit_message_text(
            f"❌ {holder.display_name} hasn't set up the bot yet — "
            "they need to send /start in DM before they can receive borrow requests."
        )
        return

    if has_pending_request(db, copy_id, requester.id):
        await query.edit_message_text("You already have a pending request for this game.")
        return

    game_row = db.execute(
        "SELECT title FROM games WHERE id = ?", (copy.game_id,)
    ).fetchone()
    game_title = game_row[0] if game_row else "Unknown game"

    request_id = create_request(db, copy_id, requester.id)

    from telegram import InlineKeyboardButton, InlineKeyboardMarkup

    try:
        await context.bot.send_message(
            chat_id=holder.telegram_id,
            text=(
                f"📬 *Borrow Request*\n\n"
                f"{requester.display_name} wants to borrow *{game_title}* from you "
                f"({holder_label})."
            ),
            parse_mode="Markdown",
            reply_markup=InlineKeyboardMarkup([
                [
                    InlineKeyboardButton("✅ Accept", callback_data=f"accept:{request_id}"),
                    InlineKeyboardButton("❌ Decline", callback_data=f"decline:{request_id}"),
                ]
            ]),
        )
    except Exception as exc:
        logger.error("Failed to DM holder %d: %s", holder.telegram_id, exc)
        await query.edit_message_text("❌ Couldn't reach the holder via DM. They may have blocked the bot.")
        return

    await query.edit_message_text(
        f"📤 Request sent to *{holder.display_name}* for *{game_title}*. "
        "You'll be notified when they respond.",
        parse_mode="Markdown",
    )


# ── Accept / Decline callbacks ───────────────────────────────────────

async def handle_accept(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    await _handle_request_resolution(update, context, accepted=True)


async def handle_decline(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    await _handle_request_resolution(update, context, accepted=False)


async def _handle_request_resolution(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
    *,
    accepted: bool,
) -> None:
    query = update.callback_query
    if query is None or update.effective_user is None:
        return

    await query.answer()

    data = query.data or ""
    request_id = int(data.split(":")[1])

    db = context.bot_data["db"]
    from wmbgbot.db.queries import (
        get_request,
        get_copy,
        get_user,
        get_user_by_id,
        resolve_request,
        create_loan,
        set_copy_status,
        return_active_loan_for_copy,
    )

    request = get_request(db, request_id)
    if request is None:
        await query.edit_message_text("This request no longer exists.")
        return

    if request.status != "pending":
        await query.edit_message_text(f"This request was already {request.status}.")
        return

    copy = get_copy(db, request.copy_id)
    if copy is None:
        await query.edit_message_text("The game copy no longer exists.")
        return

    # Validate: only the current holder can act
    if copy.status == "available":
        holder_id = copy.owner_id
    else:
        loan_row = db.execute(
            "SELECT borrower_id FROM loans WHERE copy_id = ? AND returned_at IS NULL",
            (copy.id,),
        ).fetchone()
        holder_id = loan_row[0] if loan_row else copy.owner_id

    actor = get_user(db, update.effective_user.id)
    if actor is None or actor.id != holder_id:
        await query.answer("Only the current holder can accept/decline this request.", show_alert=True)
        return

    new_status = "accepted" if accepted else "declined"
    resolve_request(db, request_id, new_status)

    requester = get_user_by_id(db, request.requester_id)
    game_row = db.execute("SELECT title FROM games WHERE id = ?", (copy.game_id,)).fetchone()
    game_title = game_row[0] if game_row else "Unknown game"

    if requester:
        action = "accepted ✅" if accepted else "declined ❌"
        try:
            await context.bot.send_message(
                chat_id=requester.telegram_id,
                text=f"Your request to borrow *{game_title}* was *{action}*.",
                parse_mode="Markdown",
            )
        except Exception as exc:
            logger.error("Failed to notify requester %d: %s", requester.telegram_id, exc)

    if accepted:
        # Close any existing active loan (the previous holder is lending it onward)
        return_active_loan_for_copy(db, request.copy_id)
        # Create new loan and mark borrowed
        create_loan(db, request.copy_id, request.requester_id)
        set_copy_status(db, request.copy_id, "borrowed")

    await query.edit_message_text(
        f"Request from {requester.display_name if requester else 'Unknown'} for "
        f"*{game_title}* — *{new_status}*.",
        parse_mode="Markdown",
    )


# ── Remove callback ──────────────────────────────────────────────────

async def handle_remove(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handle 'Remove' button from /removegame."""
    query = update.callback_query
    if query is None or update.effective_user is None:
        return

    await query.answer()

    copy_id = int((query.data or "").split(":")[1])
    db = context.bot_data["db"]

    from wmbgbot.db.queries import get_copy, get_user, remove_copy

    user = get_user(db, update.effective_user.id)
    copy = get_copy(db, copy_id)

    if copy is None:
        await query.edit_message_text("This copy no longer exists.")
        return

    if user is None or copy.owner_id != user.id:
        await query.answer("You can only remove your own games.", show_alert=True)
        return

    if copy.status != "available":
        await query.edit_message_text("Can't remove a game that's currently out.")
        return

    if remove_copy(db, copy_id):
        await query.edit_message_text("🗑️ Game removed from your collection.")
    else:
        await query.edit_message_text("Couldn't remove the game.")


# ── Return callback ──────────────────────────────────────────────────

async def handle_return(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handle 'Mark Returned' button from /return.

    Returns the game to the original owner.
    """
    query = update.callback_query
    if query is None or update.effective_user is None:
        return

    await query.answer()

    loan_id = int((query.data or "").split(":")[1])
    db = context.bot_data["db"]

    from wmbgbot.db.queries import (
        get_loan,
        get_copy,
        get_user,
        get_user_by_id,
        return_loan,
        set_copy_status,
    )

    user = get_user(db, update.effective_user.id)
    loan = get_loan(db, loan_id)

    if loan is None:
        await query.edit_message_text("This loan no longer exists.")
        return

    if loan.returned_at is not None:
        await query.edit_message_text("This loan was already returned.")
        return

    copy = get_copy(db, loan.copy_id)
    if copy is None:
        await query.edit_message_text("The game copy no longer exists.")
        return

    # Caller must be borrower or original owner
    if user is None or (user.id != loan.borrower_id and user.id != copy.owner_id):
        await query.answer("Only the borrower or owner can mark this returned.", show_alert=True)
        return

    return_loan(db, loan_id)
    set_copy_status(db, loan.copy_id, "available")

    game_row = db.execute("SELECT title FROM games WHERE id = ?", (copy.game_id,)).fetchone()
    game_title = game_row[0] if game_row else "Unknown game"

    # Notify the other party
    other_id = loan.borrower_id if user.id == copy.owner_id else copy.owner_id
    other = get_user_by_id(db, other_id)

    if other:
        try:
            await context.bot.send_message(
                chat_id=other.telegram_id,
                text=f"📦 *{game_title}* has been marked as returned by {user.display_name}.",
                parse_mode="Markdown",
            )
        except Exception as exc:
            logger.error("Failed to notify other party %d: %s", other.telegram_id, exc)

    await query.edit_message_text(f"✅ *{game_title}* marked as returned!", parse_mode="Markdown")
