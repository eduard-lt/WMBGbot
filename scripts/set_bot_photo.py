"""One-shot script to set the bot's profile picture from WMBG.png.

Usage:
    uv run python scripts/set_bot_photo.py
    # or:
    .venv/bin/python scripts/set_bot_photo.py
"""

from __future__ import annotations

import asyncio
import sys
from pathlib import Path

from wmbgbot.config import Config, PROJECT_ROOT

# The image is at the repo root
IMAGE_PATH = PROJECT_ROOT / "WMBG.png"


async def main() -> None:
    config = Config.from_env()

    if not IMAGE_PATH.exists():
        print(f"Error: {IMAGE_PATH} not found", file=sys.stderr)
        sys.exit(1)

    from telegram import Bot

    async with Bot(config.bot_token) as bot:
        photo_data = IMAGE_PATH.read_bytes()
        success = await bot.set_my_photo(photo=photo_data)
        if success:
            print(f"✅ Bot profile photo set from {IMAGE_PATH}")
        else:
            print("❌ Failed to set bot profile photo", file=sys.stderr)
            sys.exit(1)


if __name__ == "__main__":
    asyncio.run(main())
