"""Configuration loaded from .env file."""

from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

from dotenv import load_dotenv


def _find_project_root() -> Path:
    """Find the project root (where .env lives).

    Walks up from this file's location until it finds a .env file,
    pyproject.toml, or hits the filesystem root.
    """
    current = Path(__file__).resolve().parent
    for _ in range(5):
        if (current / ".env").exists() or (current / "pyproject.toml").exists():
            return current
        if current.parent == current:
            break
        current = current.parent
    # Fallback: assume we're at the repo root if launched via `uv run` or `python -m`
    return Path.cwd()


PROJECT_ROOT = _find_project_root()


@dataclass(frozen=True)
class Config:
    """Typed application configuration loaded from environment."""

    bot_token: str
    invite_code: str
    database_path: str
    log_file: str
    log_level: str

    @classmethod
    def from_env(cls) -> Config:
        load_dotenv(PROJECT_ROOT / ".env")

        token = os.getenv("BOT_TOKEN")
        if not token or token == "your_bot_token_here":
            raise ValueError("BOT_TOKEN is not set in .env file")

        return cls(
            bot_token=token,
            invite_code=os.getenv("INVITE_CODE", "change-me"),
            database_path=os.getenv("DATABASE_PATH", "data/bot.db"),
            log_file=os.getenv("LOG_FILE", "bot.log"),
            log_level=os.getenv("LOG_LEVEL", "INFO"),
        )

    @property
    def resolved_db_path(self) -> str:
        """Absolute path to the database file (relative to project root)."""
        path = Path(self.database_path)
        if not path.is_absolute():
            path = PROJECT_ROOT / path
        path.parent.mkdir(parents=True, exist_ok=True)
        return str(path)

    @property
    def resolved_log_path(self) -> str:
        """Absolute path to the log file (relative to project root)."""
        path = Path(self.log_file)
        if not path.is_absolute():
            path = PROJECT_ROOT / path
        return str(path)
