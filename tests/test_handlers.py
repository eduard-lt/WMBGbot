"""Tests for command and callback handlers."""

import pytest
from unittest.mock import AsyncMock, MagicMock


@pytest.mark.asyncio
async def test_start_in_group_redirects():
    """/start in a group should tell the user to DM."""
    from wmbgbot.handlers.commands import start

    update = MagicMock()
    update.effective_chat.type = "group"
    update.effective_user = MagicMock()
    update.message.reply_text = AsyncMock()

    context = MagicMock()
    context.bot_data = {"db": MagicMock()}

    await start(update, context)
    update.message.reply_text.assert_called_once()
    call_text = update.message.reply_text.call_args[0][0]
    assert "private message" in call_text.lower()


@pytest.mark.asyncio
async def test_start_in_dm_registers_user():
    """/start in DM should register user and set dm_started."""
    from wmbgbot.handlers.commands import start
    from wmbgbot.db.schema import init_db

    db = init_db(":memory:")

    update = MagicMock()
    update.effective_chat.type = "private"
    update.effective_user.id = 12345
    update.effective_user.full_name = "Test User"
    update.effective_user.username = "testuser"
    update.message.reply_text = AsyncMock()

    context = MagicMock()
    context.bot_data = {"db": db, "config": MagicMock(invite_code="secret")}
    context.args = ["secret"]

    await start(update, context)
    update.message.reply_text.assert_called_once()
    msg = update.message.reply_text.call_args[0][0]
    assert "Welcome" in msg

    from wmbgbot.db.queries import get_user
    user = get_user(db, 12345)
    assert user is not None
    assert user.display_name == "Test User"
    assert user.dm_started is True


@pytest.mark.asyncio
async def test_start_rejects_wrong_code():
    """/start with wrong invite code should reject."""
    from wmbgbot.handlers.commands import start
    from wmbgbot.db.schema import init_db

    db = init_db(":memory:")

    update = MagicMock()
    update.effective_chat.type = "private"
    update.effective_user.id = 99999
    update.effective_user.full_name = "Stranger"
    update.message.reply_text = AsyncMock()

    context = MagicMock()
    context.bot_data = {"db": db, "config": MagicMock(invite_code="secret")}
    context.args = ["wrong"]

    await start(update, context)
    msg = update.message.reply_text.call_args[0][0]
    assert "invite code" in msg.lower()

    from wmbgbot.db.queries import get_user
    assert get_user(db, 99999) is None


@pytest.mark.asyncio
async def test_set_profile():
    """/setprofile should update city and neighborhood."""
    from wmbgbot.handlers.commands import set_profile
    from wmbgbot.db.schema import init_db
    from wmbgbot.db.queries import upsert_user

    db = init_db(":memory:")
    upsert_user(db, 12345, "Test User")

    update = MagicMock()
    update.effective_chat.type = "private"
    update.effective_user.id = 12345
    update.message.reply_text = AsyncMock()

    context = MagicMock()
    context.bot_data = {"db": db}
    context.args = ["Bucharest,", "Pipera"]

    await set_profile(update, context)
    update.message.reply_text.assert_called_once()
    msg = update.message.reply_text.call_args[0][0]
    assert "Bucharest" in msg
    assert "Pipera" in msg

    from wmbgbot.db.queries import get_user
    user = get_user(db, 12345)
    assert user.city == "Bucharest"
    assert user.neighborhood == "Pipera"


@pytest.mark.asyncio
async def test_addgame():
    """/addgame should add a game directly."""
    from wmbgbot.handlers.commands import addgame
    from wmbgbot.db.schema import init_db
    from wmbgbot.db.queries import upsert_user

    db = init_db(":memory:")
    upsert_user(db, 12345, "Test User")

    update = MagicMock()
    update.effective_chat.type = "private"
    update.effective_user.id = 12345
    update.effective_user.full_name = "Test User"
    update.message.reply_text = AsyncMock()

    context = MagicMock()
    context.bot_data = {"db": db}
    context.args = ["Lost", "Ruins", "of", "Arnak"]

    await addgame(update, context)
    update.message.reply_text.assert_called_once()
    msg = update.message.reply_text.call_args[0][0]
    assert "Lost Ruins of Arnak" in msg

    from wmbgbot.db.queries import search_games
    results = search_games(db, "Arnak")
    assert len(results) == 1
    assert results[0]["title"] == "Lost Ruins of Arnak"


@pytest.mark.asyncio
async def test_search_no_results():
    """/search with no matches."""
    from wmbgbot.handlers.commands import search
    from wmbgbot.db.schema import init_db

    db = init_db(":memory:")

    update = MagicMock()
    update.effective_chat = MagicMock()
    update.effective_user = MagicMock()
    update.message.reply_text = AsyncMock()

    context = MagicMock()
    context.bot_data = {"db": db}
    context.args = ["NoSuchGame"]

    await search(update, context)
    update.message.reply_text.assert_called_once()
    assert "No games found" in update.message.reply_text.call_args[0][0]


@pytest.mark.asyncio
async def test_borrow_owner_not_dm_started():
    """Borrow request should be rejected if holder hasn't DM'd the bot."""
    from wmbgbot.handlers.callbacks import handle_borrow
    from wmbgbot.db.schema import init_db
    from wmbgbot.db.queries import upsert_user, add_game, add_copy

    db = init_db(":memory:")
    alice = upsert_user(db, 111, "Alice")  # dm_started=0
    bob = upsert_user(db, 222, "Bob")
    game_id = add_game(db, 1, "Wingspan")
    copy_id = add_copy(db, game_id, alice.id)

    query = MagicMock()
    query.data = f"borrow:{copy_id}"
    query.edit_message_text = AsyncMock()
    query.answer = AsyncMock()

    update = MagicMock()
    update.callback_query = query
    update.effective_user.id = 222

    context = MagicMock()
    context.bot_data = {"db": db}

    await handle_borrow(update, context)
    query.edit_message_text.assert_called_once()
    msg = query.edit_message_text.call_args[0][0]
    assert "hasn't set up the bot yet" in msg
