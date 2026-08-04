"""Tests for BGG API client."""

import pytest
from wmbgbot.bgg import search_bgg, fetch_bgg_details, BGGError


SAMPLE_SEARCH_XML = """<?xml version="1.0" encoding="utf-8"?>
<items total="2">
  <item type="boardgame" id="1234">
    <name type="primary" value="Catan"/>
    <yearpublished value="1995"/>
  </item>
  <item type="boardgame" id="5678">
    <name type="primary" value="Catan: Seafarers"/>
    <yearpublished value="1997"/>
  </item>
</items>
"""

SAMPLE_THING_XML = """<?xml version="1.0" encoding="utf-8"?>
<items>
  <item type="boardgame" id="1234">
    <thumbnail>https://example.com/thumb.jpg</thumbnail>
    <image>https://example.com/image.jpg</image>
    <name type="primary" value="Catan"/>
  </item>
</items>
"""


class MockResponse:
    def __init__(self, text, status_code=200):
        self.text = text
        self.status_code = status_code

    def raise_for_status(self):
        if self.status_code >= 400:
            raise Exception(f"HTTP {self.status_code}")


class MockClient:
    """Minimal mock httpx.AsyncClient."""
    def __init__(self, responses):
        self.responses = responses
        self.calls = []

    async def get(self, url, **kwargs):
        self.calls.append((url, kwargs))
        key = (url, kwargs.get("params", {}).get("query"))
        for pattern, resp in self.responses.items():
            if pattern in url:
                return MockResponse(resp)
        return MockResponse("", 404)

    async def __aenter__(self):
        return self

    async def __aexit__(self, *args):
        pass


@pytest.mark.asyncio
async def test_search_bgg_parses_results():
    client = MockClient({"/search": SAMPLE_SEARCH_XML})
    results = await search_bgg(client, "https://test", "Catan")
    assert len(results) == 2
    assert results[0]["bgg_id"] == 1234
    assert results[0]["name"] == "Catan"
    assert results[0]["yearpublished"] == "1995"


@pytest.mark.asyncio
async def test_search_bgg_empty():
    client = MockClient({"/search": '<items total="0"></items>'})
    results = await search_bgg(client, "https://test", "NoSuchGame")
    assert results == []


@pytest.mark.asyncio
async def test_fetch_bgg_details():
    client = MockClient({"/thing": SAMPLE_THING_XML})
    details = await fetch_bgg_details(client, "https://test", 1234)
    assert details["title"] == "Catan"
    assert details["image_url"] == "https://example.com/image.jpg"
    assert details["thumbnail_url"] == "https://example.com/thumb.jpg"
