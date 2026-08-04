# BGG XML API2 — Notes & Learnings

## Key Facts

- **BGG's API is XML-based**, not JSON. All responses must be parsed with an XML parser.
- **Root URL**: `https://boardgamegeek.com/xmlapi2/` (no `www` subdomain — BGG explicitly warns against it)
- **Rate limiting**: BGG throttles aggressively. Leave **5 seconds** between requests, or you'll get 500/503 errors.
- **Auth**: BGG documentation says registration/authorization is required. This may be why requests from the Pi are failing.

## Mental Model

```
                         BoardGameGeek
                              │
                ┌─────────────┼─────────────┐
                │             │             │
              SEARCH         THING       COLLECTION
                │             │             │
          "find Wingspan"  "give me      "give me
                            Wingspan      someone's
                            details"      collection"
                │             │             │
                ▼             ▼             ▼
             Game ID      Game details    Games owned
              266192
```

## The Two-Step Workflow

### Step 1 — Search by name → get BGG ID

```
GET /xmlapi2/search?query=Wingspan&type=boardgame
```

Returns XML with matching items, each containing `id` and `name`:

```xml
<items>
    <item type="boardgame" id="266192">
        <name type="primary" value="Wingspan"/>
        <yearpublished value="2019"/>
    </item>
</items>
```

### Step 2 — Get full details by ID

```
GET /xmlapi2/thing?id=266192&stats=1
```

Returns full game metadata: name, year, players, playing time, images, ratings, etc.

**Tip**: You can request up to 20 IDs in one call:
```
GET /xmlapi2/thing?id=1,2,3,4
```

## Endpoints We Use

| Endpoint | Purpose |
|---|---|
| `/xmlapi2/search?query=X&type=boardgame` | Find games by name |
| `/xmlapi2/thing?id=N&stats=1` | Get game details by BGG ID |

## Architecture Decision

**WMBGbot is NOT a BGG bot.** It's a board-game collection/borrowing system that uses BGG only as a source of game metadata.

- **WMBGbot database** is authoritative for: who owns what, who borrowed what, loan status
- **BGG** provides: game title, cover image, player count, year, rating (nice-to-have metadata)

This means the bot works fine **without BGG** — games can be added with free-text titles. The BGG lookup is an enhancement, not a dependency.

## Why BGG Might Fail

1. **Auth (401 Unauthorized)** — Confirmed on 2026-08-04: BGG's XML API2 now requires authentication. Requests without a valid API token return HTTP 401. This is the current reason our Pi can't reach BGG — TLS/DNS/connectivity all work fine, but the API rejects unauthenticated calls.
2. **Network**: Pi behind NAT/Tailscale may not reach `boardgamegeek.com`
3. **Throttling**: Too many requests too fast → 500/503
4. **User-Agent**: BGG blocks requests without one (we set `WMBGbot/0.1`)

### Debugging on the Pi

```bash
# Test DNS
nslookup boardgamegeek.com

# Test HTTPS connectivity
curl -v -H "User-Agent: WMBGbot/0.1" \
  "https://boardgamegeek.com/xmlapi2/search?query=Catan&type=boardgame" \
  2>&1 | head -50

# Check the bot's error log
cat /home/eduard/boardgame-bot/bot.log | grep -i bgg
```

## Fallback Strategy

When BGG is unreachable, the bot falls back to **manual title entry**:

1. User types `/addgame Monopoly (Milka Edition)`
2. BGG call fails → bot prompts: "Adding *Monopoly (Milka Edition)* directly. Type the exact title or /cancel"
3. User types the title → game is saved with `bgg_id = NULL` and the user-provided title
4. Bot works exactly the same — just without cover art or BGG metadata

## References

- Official docs: https://boardgamegeek.com/wiki/page/BGG_XML_API2
- Using the API: https://boardgamegeek.com/wiki/page/Using_the_XML_API
- XML API terms of use: https://boardgamegeek.com/wiki/page/XML_API_Terms_of_Use
