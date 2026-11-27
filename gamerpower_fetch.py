"""Active full-game giveaways from the public GamerPower feed."""
from urllib.parse import urlsplit

import aiohttp


API_URL = "https://www.gamerpower.com/api/giveaways"


def _text(value):
    return value.strip() if isinstance(value, str) and value.strip() != "N/A" else ""


def is_steam_giveaway(game):
    platforms = game.get("platforms") or ""
    if isinstance(platforms, str):
        platforms = platforms.split(",")
    return any(str(name).strip().casefold() == "steam" for name in platforms)


async def fetch_gamerpower():
    timeout = aiohttp.ClientTimeout(total=25)
    async with aiohttp.ClientSession(timeout=timeout, trust_env=True) as session:
        async with session.get(API_URL, params={"type": "game", "sort-by": "date"}) as response:
            if response.status == 201:  # GamerPower documents this as no active giveaways.
                return []
            response.raise_for_status()
            data = await response.json()
    if not isinstance(data, list):
        raise ValueError("GamerPower returned an unexpected response")

    offers = []
    seen = set()
    for item in data:
        if item["type"] != "Game" or item["status"] != "Active":
            continue
        link = _text(item.get("gamerpower_url"))
        dest = urlsplit(link)
        title = _text(item.get("title"))
        if not title or dest.scheme != "https" or dest.hostname not in {"www.gamerpower.com", "gamerpower.com"}:
            raise ValueError("GamerPower returned an invalid event")
        if item["id"] in seen:
            continue
        seen.add(item["id"])
        offers.append({
            "id": item["id"],
            "title": title,
            "link": link,
            "platforms": _text(item.get("platforms")),
            "endDate": _text(item.get("end_date")),
            "worth": _text(item.get("worth")),
            "description": _text(item.get("description")),
            "instructions": _text(item.get("instructions")),
            "cover": _text(item.get("image")) or _text(item.get("thumbnail")),
        })
    return offers
