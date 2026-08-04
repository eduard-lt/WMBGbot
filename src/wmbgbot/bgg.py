"""BoardGameGeek XML API2 client."""

from __future__ import annotations

import logging
from xml.etree import ElementTree as ET

import httpx

logger = logging.getLogger(__name__)

BGG_SEARCH_URL = "/search"
BGG_THING_URL = "/thing"


class BGGError(Exception):
    """Raised when the BGG API returns an error or unexpected response."""


async def search_bgg(
    client: httpx.AsyncClient,
    base_url: str,
    query: str,
    max_results: int = 8,
) -> list[dict]:
    """Search BoardGameGeek for a game title.

    Returns a list of dicts with keys: bgg_id, name, yearpublished.
    """
    try:
        resp = await client.get(
            f"{base_url}{BGG_SEARCH_URL}",
            params={"query": query, "type": "boardgame"},
            timeout=15,
            headers={"User-Agent": "WMBGbot/0.1 (personal use bot)"},
        )
        resp.raise_for_status()
    except httpx.HTTPError as exc:
        logger.error("BGG search request failed: %s", exc)
        raise BGGError(f"Failed to search BGG: {exc}") from exc

    root = ET.fromstring(resp.text)
    items = root.findall("item")
    results: list[dict] = []

    for item in items[:max_results]:
        bgg_id = int(item.attrib["id"])
        name_el = item.find("name")
        year_el = item.find("yearpublished")
        results.append({
            "bgg_id": bgg_id,
            "name": name_el.attrib["value"] if name_el is not None else "Unknown",
            "yearpublished": year_el.attrib["value"] if year_el is not None else None,
        })

    logger.info("BGG search for '%s' returned %d results", query, len(results))
    return results


async def fetch_bgg_details(
    client: httpx.AsyncClient,
    base_url: str,
    bgg_id: int,
) -> dict:
    """Fetch detailed info for a single BGG game.

    Returns a dict with keys: title, thumbnail_url, image_url.
    """
    try:
        resp = await client.get(
            f"{base_url}{BGG_THING_URL}",
            params={"id": bgg_id},
            timeout=10,
        )
        resp.raise_for_status()
    except httpx.HTTPError as exc:
        logger.error("BGG thing request failed for id=%d: %s", bgg_id, exc)
        raise BGGError(f"Failed to fetch BGG details for id={bgg_id}: {exc}") from exc

    root = ET.fromstring(resp.text)
    item = root.find("item")

    if item is None:
        raise BGGError(f"No item found for BGG id={bgg_id}")

    name_el = item.find("name")
    title = "Unknown"
    if name_el is not None:
        # Prefer the primary name (type="primary")
        for n in item.findall("name"):
            if n.attrib.get("type") == "primary":
                title = n.attrib["value"]
                break
        else:
            title = name_el.attrib.get("value", "Unknown")

    thumbnail = item.findtext("thumbnail", None)
    image = item.findtext("image", None)

    return {
        "title": title,
        "thumbnail_url": thumbnail,
        "image_url": image,
    }
