"""Simple dataclasses mirroring the database schema."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class User:
    id: int
    telegram_id: int
    display_name: str
    city: str = ""
    neighborhood: str = ""
    is_admin: bool = False
    dm_started: bool = False


@dataclass(frozen=True)
class Game:
    id: int
    bgg_id: int | None
    title: str
    cover_image_url: str | None = None


@dataclass(frozen=True)
class Copy:
    id: int
    game_id: int
    owner_id: int
    status: str  # 'available' | 'borrowed'
    added_at: str = ""


@dataclass(frozen=True)
class Request:
    id: int
    copy_id: int
    requester_id: int
    status: str  # 'pending' | 'accepted' | 'declined' | 'cancelled'
    created_at: str = ""
    resolved_at: str | None = None


@dataclass(frozen=True)
class Loan:
    id: int
    copy_id: int
    borrower_id: int
    borrowed_at: str = ""
    returned_at: str | None = None
