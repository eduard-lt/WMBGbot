from wmbgbot.db.schema import SCHEMA_SQL, init_db


def test_init_db_creates_tables():
    """Verify init_db creates all expected tables."""
    conn = init_db(":memory:")
    tables = conn.execute(
        "SELECT name FROM sqlite_master WHERE type='table' ORDER BY name"
    ).fetchall()
    table_names = [t[0] for t in tables]
    for expected in ["users", "games", "copies", "requests", "loans"]:
        assert expected in table_names, f"Table {expected} missing"
    conn.close()


def test_upsert_user():
    """Test user creation and update."""
    conn = init_db(":memory:")
    from wmbgbot.db.queries import upsert_user, get_user

    user = upsert_user(conn, 123456, "Alice")
    assert user.telegram_id == 123456
    assert user.display_name == "Alice"
    assert user.dm_started is False

    # Update display name
    user2 = upsert_user(conn, 123456, "Alice Updated")
    assert user2.display_name == "Alice Updated"
    assert user2.id == user.id  # same row

    conn.close()


def test_set_dm_started():
    """Test dm_started flag."""
    conn = init_db(":memory:")
    from wmbgbot.db.queries import upsert_user, get_user, set_dm_started

    upsert_user(conn, 123, "Bob")
    set_dm_started(conn, 123)
    user = get_user(conn, 123)
    assert user.dm_started is True
    conn.close()


def test_add_and_search_games():
    """Test adding games and searching."""
    conn = init_db(":memory:")
    from wmbgbot.db.queries import add_game, add_copy, upsert_user, search_games

    user = upsert_user(conn, 123, "Alice")
    game_id = add_game(conn, 42, "Catan")
    add_copy(conn, game_id, user.id)

    results = search_games(conn, "Catan")
    assert len(results) == 1
    assert results[0]["title"] == "Catan"
    assert len(results[0]["copies"]) == 1
    assert results[0]["copies"][0]["owner_name"] == "Alice"
    assert results[0]["copies"][0]["status"] == "available"

    # No match
    assert search_games(conn, "Monopoly") == []
    conn.close()


def test_borrow_flow():
    """Test the full borrow → accept → return flow."""
    conn = init_db(":memory:")
    from wmbgbot.db.queries import (
        upsert_user,
        set_dm_started,
        add_game,
        add_copy,
        get_copy,
        create_request,
        create_loan,
        set_copy_status,
        return_loan,
        resolve_request,
        has_pending_request,
    )

    alice = upsert_user(conn, 111, "Alice")
    set_dm_started(conn, 111)
    bob = upsert_user(conn, 222, "Bob")
    set_dm_started(conn, 222)

    game_id = add_game(conn, 1, "Wingspan")
    copy_id = add_copy(conn, game_id, alice.id)

    # Alice's copy starts available
    copy = get_copy(conn, copy_id)
    assert copy.status == "available"

    # Bob requests
    assert not has_pending_request(conn, copy_id, bob.id)
    req_id = create_request(conn, copy_id, bob.id)
    assert has_pending_request(conn, copy_id, bob.id)

    # Alice accepts
    resolve_request(conn, req_id, "accepted")
    create_loan(conn, copy_id, bob.id)
    set_copy_status(conn, copy_id, "borrowed")

    copy = get_copy(conn, copy_id)
    assert copy.status == "borrowed"

    # Bob returns
    assert return_loan(conn, 1)
    set_copy_status(conn, copy_id, "available")
    copy = get_copy(conn, copy_id)
    assert copy.status == "available"

    conn.close()


def test_remove_copy_only_when_available():
    """Test that remove_copy only works on available copies."""
    conn = init_db(":memory:")
    from wmbgbot.db.queries import upsert_user, add_game, add_copy, remove_copy, set_copy_status

    user = upsert_user(conn, 123, "Alice")
    game_id = add_game(conn, 1, "Catan")
    copy_id = add_copy(conn, game_id, user.id)

    # Remove while available
    assert remove_copy(conn, copy_id) is True

    # Add again, mark borrowed, try removing
    copy_id2 = add_copy(conn, game_id, user.id)
    set_copy_status(conn, copy_id2, "borrowed")
    assert remove_copy(conn, copy_id2) is False  # can't remove borrowed

    conn.close()
