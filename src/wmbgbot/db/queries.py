"""Database query functions.

All functions accept a sqlite3.Connection and are synchronous.
They should be called via run_in_executor from async handlers.
"""

from __future__ import annotations

import sqlite3
from typing import Sequence

from wmbgbot.models import Copy, Game, Loan, Request, User


# ── Users ────────────────────────────────────────────────────────────

def upsert_user(conn: sqlite3.Connection, telegram_id: int, display_name: str) -> User:
    """Insert or update a user; returns the User row."""
    conn.execute(
        """INSERT INTO users (telegram_id, display_name)
           VALUES (?, ?)
           ON CONFLICT(telegram_id) DO UPDATE SET display_name=excluded.display_name""",
        (telegram_id, display_name),
    )
    conn.commit()
    return get_user(conn, telegram_id)  # type: ignore[return-value]


def set_user_profile(
    conn: sqlite3.Connection,
    telegram_id: int,
    city: str,
    neighborhood: str,
) -> None:
    """Update a user's city and neighborhood."""
    conn.execute(
        "UPDATE users SET city = ?, neighborhood = ? WHERE telegram_id = ?",
        (city, neighborhood, telegram_id),
    )
    conn.commit()


def set_dm_started(conn: sqlite3.Connection, telegram_id: int) -> None:
    """Mark that a user has started a DM conversation with the bot."""
    conn.execute(
        "UPDATE users SET dm_started = 1 WHERE telegram_id = ?",
        (telegram_id,),
    )
    conn.commit()


def get_user(conn: sqlite3.Connection, telegram_id: int) -> User | None:
    """Get a user by Telegram ID."""
    row = conn.execute(
        "SELECT id, telegram_id, display_name, city, neighborhood, is_admin, dm_started FROM users WHERE telegram_id = ?",
        (telegram_id,),
    ).fetchone()
    if row is None:
        return None
    return User(
        id=row[0],
        telegram_id=row[1],
        display_name=row[2],
        city=row[3],
        neighborhood=row[4],
        is_admin=bool(row[5]),
        dm_started=bool(row[6]),
    )


def get_user_by_id(conn: sqlite3.Connection, user_id: int) -> User | None:
    """Get a user by internal id."""
    row = conn.execute(
        "SELECT id, telegram_id, display_name, city, neighborhood, is_admin, dm_started FROM users WHERE id = ?",
        (user_id,),
    ).fetchone()
    if row is None:
        return None
    return User(
        id=row[0],
        telegram_id=row[1],
        display_name=row[2],
        city=row[3],
        neighborhood=row[4],
        is_admin=bool(row[5]),
        dm_started=bool(row[6]),
    )


def get_all_users(conn: sqlite3.Connection) -> list[User]:
    """Get all registered users."""
    rows = conn.execute(
        "SELECT id, telegram_id, display_name, city, neighborhood, is_admin, dm_started FROM users ORDER BY display_name"
    ).fetchall()
    return [
        User(
            id=r[0],
            telegram_id=r[1],
            display_name=r[2],
            city=r[3],
            neighborhood=r[4],
            is_admin=bool(r[5]),
            dm_started=bool(r[6]),
        )
        for r in rows
    ]


# ── Games ────────────────────────────────────────────────────────────

def add_game(
    conn: sqlite3.Connection,
    bgg_id: int | None,
    title: str,
    cover_image_url: str | None = None,
) -> int:
    """Insert a game (or ignore if bgg_id already exists). Return the game id."""
    conn.execute(
        """INSERT OR IGNORE INTO games (bgg_id, title, cover_image_url)
           VALUES (?, ?, ?)""",
        (bgg_id, title, cover_image_url),
    )
    conn.commit()
    if bgg_id is not None:
        row = conn.execute("SELECT id FROM games WHERE bgg_id = ?", (bgg_id,)).fetchone()
    else:
        row = conn.execute(
            "SELECT id FROM games WHERE bgg_id IS NULL AND title = ?", (title,)
        ).fetchone()
    assert row is not None
    return row[0]


def search_games(conn: sqlite3.Connection, query: str) -> list[dict]:
    """Fuzzy search games by title.

    Returns a list of dicts: {game_id, title, bgg_id, cover_image_url, copies: [{copy_id, owner_name, owner_id, status, borrower_name}]}
    """
    like = f"%{query}%"
    rows = conn.execute(
        """SELECT g.id, g.bgg_id, g.title, g.cover_image_url,
                  c.id AS copy_id, c.owner_id, c.status,
                  u.display_name AS owner_name,
                  u.city AS owner_city,
                  u.neighborhood AS owner_neighborhood,
                  l.borrower_id,
                  ub.display_name AS borrower_name
           FROM games g
           JOIN copies c ON c.game_id = g.id
           JOIN users u ON u.id = c.owner_id
           LEFT JOIN loans l ON l.copy_id = c.id AND l.returned_at IS NULL
           LEFT JOIN users ub ON ub.id = l.borrower_id
           WHERE g.title LIKE ?
           ORDER BY g.title""",
        (like,),
    ).fetchall()

    # Group by game
    games: dict[int, dict] = {}
    for r in rows:
        game_id = r[0]
        if game_id not in games:
            games[game_id] = {
                "game_id": game_id,
                "bgg_id": r[1],
                "title": r[2],
                "cover_image_url": r[3],
                "copies": [],
            }
        games[game_id]["copies"].append({
            "copy_id": r[4],
            "owner_id": r[5],
            "status": r[6],
            "owner_name": r[7],
            "city": r[8],
            "neighborhood": r[9],
            "borrower_name": r[11] if r[6] == "borrowed" else None,
        })

    return list(games.values())


def get_library(conn: sqlite3.Connection) -> list[dict]:
    """List all games grouped by title with owner counts."""
    rows = conn.execute(
        """SELECT g.id, g.title, COUNT(c.id) AS total_copies,
                  SUM(CASE WHEN c.status = 'available' THEN 1 ELSE 0 END) AS available_copies
           FROM games g
           JOIN copies c ON c.game_id = g.id
           GROUP BY g.id
           ORDER BY g.title"""
    ).fetchall()
    return [
        {
            "game_id": r[0],
            "title": r[1],
            "total_copies": r[2],
            "available_copies": r[3],
        }
        for r in rows
    ]


def get_library_full(conn: sqlite3.Connection) -> list[dict]:
    """Like get_library but returns one row per unique game (no copies detail)."""
    return get_library(conn)


def get_game_copies_detail(conn: sqlite3.Connection, game_id: int) -> list[dict]:
    """Get all copies of a game with owner and borrower details."""
    rows = conn.execute(
        """SELECT c.id AS copy_id, c.owner_id, c.status,
                  uo.display_name AS owner_name,
                  uo.city, uo.neighborhood,
                  l.borrower_id,
                  ub.display_name AS borrower_name,
                  g.title
           FROM copies c
           JOIN users uo ON uo.id = c.owner_id
           JOIN games g ON g.id = c.game_id
           LEFT JOIN loans l ON l.copy_id = c.id AND l.returned_at IS NULL
           LEFT JOIN users ub ON ub.id = l.borrower_id
           WHERE c.game_id = ?
           ORDER BY c.status DESC, uo.display_name""",
        (game_id,),
    ).fetchall()
    return [
        {
            "copy_id": r[0],
            "owner_id": r[1],
            "status": r[2],
            "owner_name": r[3],
            "city": r[4],
            "neighborhood": r[5],
            "borrower_id": r[6],
            "borrower_name": r[7],
            "title": r[8],
        }
        for r in rows
    ]


# ── Copies ───────────────────────────────────────────────────────────

def add_copy(conn: sqlite3.Connection, game_id: int, owner_id: int) -> int:
    """Add a copy of a game for an owner. Returns the copy id."""
    cur = conn.execute(
        "INSERT INTO copies (game_id, owner_id) VALUES (?, ?)",
        (game_id, owner_id),
    )
    conn.commit()
    return cur.lastrowid


def get_copy(conn: sqlite3.Connection, copy_id: int) -> Copy | None:
    """Get a copy by id."""
    row = conn.execute(
        "SELECT id, game_id, owner_id, status, added_at FROM copies WHERE id = ?",
        (copy_id,),
    ).fetchone()
    if row is None:
        return None
    return Copy(id=row[0], game_id=row[1], owner_id=row[2], status=row[3], added_at=row[4])


def get_user_copies(conn: sqlite3.Connection, owner_id: int) -> list[dict]:
    """Get all copies owned by a user, with game info."""
    rows = conn.execute(
        """SELECT c.id, c.game_id, c.owner_id, c.status, c.added_at,
                  g.title, g.cover_image_url,
                  ub.display_name AS borrower_name
           FROM copies c
           JOIN games g ON g.id = c.game_id
           LEFT JOIN loans l ON l.copy_id = c.id AND l.returned_at IS NULL
           LEFT JOIN users ub ON ub.id = l.borrower_id
           WHERE c.owner_id = ?
           ORDER BY g.title""",
        (owner_id,),
    ).fetchall()
    return [
        {
            "copy_id": r[0],
            "game_id": r[1],
            "owner_id": r[2],
            "status": r[3],
            "added_at": r[4],
            "title": r[5],
            "cover_image_url": r[6],
            "borrower_name": r[7],
        }
        for r in rows
    ]


def remove_copy(conn: sqlite3.Connection, copy_id: int) -> bool:
    """Remove a copy if it's available. Returns True on success."""
    cur = conn.execute(
        "DELETE FROM copies WHERE id = ? AND status = 'available'",
        (copy_id,),
    )
    conn.commit()
    return cur.rowcount > 0


def set_copy_status(conn: sqlite3.Connection, copy_id: int, status: str) -> None:
    """Update a copy's status."""
    conn.execute("UPDATE copies SET status = ? WHERE id = ?", (status, copy_id))
    conn.commit()


# ── Requests ─────────────────────────────────────────────────────────

def create_request(conn: sqlite3.Connection, copy_id: int, requester_id: int) -> int:
    """Create a pending borrow request. Returns request id."""
    cur = conn.execute(
        "INSERT INTO requests (copy_id, requester_id) VALUES (?, ?)",
        (copy_id, requester_id),
    )
    conn.commit()
    return cur.lastrowid


def resolve_request(conn: sqlite3.Connection, request_id: int, status: str) -> None:
    """Resolve a request (accept/decline/cancel)."""
    conn.execute(
        "UPDATE requests SET status = ?, resolved_at = CURRENT_TIMESTAMP WHERE id = ?",
        (status, request_id),
    )
    conn.commit()


def get_request(conn: sqlite3.Connection, request_id: int) -> Request | None:
    """Get a request by id."""
    row = conn.execute(
        "SELECT id, copy_id, requester_id, status, created_at, resolved_at FROM requests WHERE id = ?",
        (request_id,),
    ).fetchone()
    if row is None:
        return None
    return Request(
        id=row[0],
        copy_id=row[1],
        requester_id=row[2],
        status=row[3],
        created_at=row[4],
        resolved_at=row[5],
    )


def get_pending_requests_for_owner(conn: sqlite3.Connection, owner_id: int) -> list[dict]:
    """Get pending requests for copies owned by a user."""
    rows = conn.execute(
        """SELECT r.id, r.copy_id, r.requester_id, r.status, r.created_at,
                  u.display_name AS requester_name,
                  g.title AS game_title
           FROM requests r
           JOIN copies c ON c.id = r.copy_id
           JOIN users u ON u.id = r.requester_id
           JOIN games g ON g.id = c.game_id
           WHERE c.owner_id = ? AND r.status = 'pending'
           ORDER BY r.created_at DESC""",
        (owner_id,),
    ).fetchall()
    return [
        {
            "request_id": r[0],
            "copy_id": r[1],
            "requester_id": r[2],
            "status": r[3],
            "created_at": r[4],
            "requester_name": r[5],
            "game_title": r[6],
        }
        for r in rows
    ]


def get_pending_requests_by_requester(conn: sqlite3.Connection, requester_id: int) -> list[dict]:
    """Get pending requests made by a user."""
    rows = conn.execute(
        """SELECT r.id, r.copy_id, r.requester_id, r.status, r.created_at,
                  u.display_name AS owner_name,
                  g.title AS game_title
           FROM requests r
           JOIN copies c ON c.id = r.copy_id
           JOIN users u ON u.id = c.owner_id
           JOIN games g ON g.id = c.game_id
           WHERE r.requester_id = ? AND r.status = 'pending'
           ORDER BY r.created_at DESC""",
        (requester_id,),
    ).fetchall()
    return [
        {
            "request_id": r[0],
            "copy_id": r[1],
            "requester_id": r[2],
            "status": r[3],
            "created_at": r[4],
            "owner_name": r[5],
            "game_title": r[6],
        }
        for r in rows
    ]


def has_pending_request(conn: sqlite3.Connection, copy_id: int, requester_id: int) -> bool:
    """Check if a user already has a pending request for a specific copy."""
    row = conn.execute(
        "SELECT 1 FROM requests WHERE copy_id = ? AND requester_id = ? AND status = 'pending'",
        (copy_id, requester_id),
    ).fetchone()
    return row is not None


# ── Loans ────────────────────────────────────────────────────────────

def create_loan(conn: sqlite3.Connection, copy_id: int, borrower_id: int) -> int:
    """Create a loan record. Returns loan id."""
    cur = conn.execute(
        "INSERT INTO loans (copy_id, borrower_id) VALUES (?, ?)",
        (copy_id, borrower_id),
    )
    conn.commit()
    return cur.lastrowid


def return_loan(conn: sqlite3.Connection, loan_id: int) -> bool:
    """Mark a loan as returned. Returns True on success."""
    cur = conn.execute(
        "UPDATE loans SET returned_at = CURRENT_TIMESTAMP WHERE id = ? AND returned_at IS NULL",
        (loan_id,),
    )
    conn.commit()
    return cur.rowcount > 0


def return_active_loan_for_copy(conn: sqlite3.Connection, copy_id: int) -> bool:
    """Close the active (unreturned) loan for a copy, if any."""
    cur = conn.execute(
        "UPDATE loans SET returned_at = CURRENT_TIMESTAMP WHERE copy_id = ? AND returned_at IS NULL",
        (copy_id,),
    )
    conn.commit()
    return cur.rowcount > 0


def get_loan(conn: sqlite3.Connection, loan_id: int) -> Loan | None:
    """Get a loan by id."""
    row = conn.execute(
        "SELECT id, copy_id, borrower_id, borrowed_at, returned_at FROM loans WHERE id = ?",
        (loan_id,),
    ).fetchone()
    if row is None:
        return None
    return Loan(
        id=row[0],
        copy_id=row[1],
        borrower_id=row[2],
        borrowed_at=row[3],
        returned_at=row[4],
    )


def get_active_loans_for_user(conn: sqlite3.Connection, user_id: int) -> list[dict]:
    """Get all active loans where user is borrower or owner."""
    rows = conn.execute(
        """SELECT l.id, l.copy_id, l.borrower_id, l.borrowed_at,
                  g.title AS game_title,
                  ub.display_name AS borrower_name,
                  uo.display_name AS owner_name,
                  c.owner_id
           FROM loans l
           JOIN copies c ON c.id = l.copy_id
           JOIN games g ON g.id = c.game_id
           JOIN users ub ON ub.id = l.borrower_id
           JOIN users uo ON uo.id = c.owner_id
           WHERE l.returned_at IS NULL
             AND (l.borrower_id = ? OR c.owner_id = ?)
           ORDER BY l.borrowed_at DESC""",
        (user_id, user_id),
    ).fetchall()
    return [
        {
            "loan_id": r[0],
            "copy_id": r[1],
            "borrower_id": r[2],
            "borrowed_at": r[3],
            "game_title": r[4],
            "borrower_name": r[5],
            "owner_name": r[6],
            "owner_id": r[7],
        }
        for r in rows
    ]


# ── Admin ────────────────────────────────────────────────────────────

def admin_edit_copy_game(conn: sqlite3.Connection, copy_id: int, new_title: str) -> None:
    """Force-edit a copy's linked game title."""
    conn.execute(
        """UPDATE games SET title = ?
           WHERE id = (SELECT game_id FROM copies WHERE id = ?)""",
        (new_title, copy_id),
    )
    conn.commit()


def admin_remove_copy(conn: sqlite3.Connection, copy_id: int) -> bool:
    """Force-remove any copy. Closes active loans first. Returns True on success."""
    conn.execute(
        "UPDATE loans SET returned_at = CURRENT_TIMESTAMP WHERE copy_id = ? AND returned_at IS NULL",
        (copy_id,),
    )
    cur = conn.execute("DELETE FROM copies WHERE id = ?", (copy_id,))
    conn.commit()
    return cur.rowcount > 0


def admin_reset_loan(conn: sqlite3.Connection, loan_id: int) -> bool:
    """Force-close a loan (sets returned_at, flips copy to available)."""
    row = conn.execute(
        "SELECT copy_id FROM loans WHERE id = ? AND returned_at IS NULL",
        (loan_id,),
    ).fetchone()
    if row is None:
        return False
    copy_id = row[0]
    conn.execute(
        "UPDATE loans SET returned_at = CURRENT_TIMESTAMP WHERE id = ?",
        (loan_id,),
    )
    conn.execute("UPDATE copies SET status = 'available' WHERE id = ?", (copy_id,))
    conn.commit()
    return True
