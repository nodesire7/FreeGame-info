"""Active full-game giveaways from the public GamerPower feed."""
from urllib.parse import urlsplit
from datetime import datetime
import json
import re

from bs4 import BeautifulSoup

import aiohttp


API_URL = "https://www.gamerpower.com/api/giveaways"


def _text(value):
    return value.strip() if isinstance(value, str) and value.strip() != "N/A" else ""


def giveaway_stores(game):
    platforms = game.get("platforms") or ""
    if isinstance(platforms, str):
        platforms = platforms.split(",")
    names = {str(name).strip().casefold() for name in platforms}
    return [key for key in ("steam", "gog") if key in names]


def gog_store_giveaway(game):
    if game.get("claimChannel") in ("gog", "gogBanner"):
        return True
    steps = (game.get("instructions") or "").casefold()
    return any(name in steps for name in ("gog home page", "gog homepage", "gog.com/#giveaway")) and "banner" in steps


def gog_banner_offers(html):
    node = BeautifulSoup(html, "html.parser").select_one("script#gogcom-store-state")
    if not node:
        return {}
    state = json.loads(node.get_text())
    banners = set()
    for entry in state.values():
        body = entry.get("body") if isinstance(entry, dict) else None
        if isinstance(body, dict):
            banners.update(section["sectionId"] for section in body.get("sections", [])
                           if section.get("sectionType") == "GIVEAWAY_SECTION")
    offers = {}
    for key, entry in state.items():
        if key.partition("?")[0].rsplit("/", 1)[-1] not in banners:
            continue
        info = entry["body"]["properties"]
        product = info.get("product")
        if product and info.get("endDate"):
            offers[product["title"].casefold()] = {
                "claimChannel": "gogBanner", "freeEndAt": int(datetime.fromisoformat(info["endDate"]).timestamp() * 1000),
                "storeTitle": product["title"], "poster": product.get("coverVertical"),
            }
    return offers


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
    gog_offers = [game for game in offers if "gog" in giveaway_stores(game)]
    if gog_offers:
        # 官方首页活动有单独的截止时间，零元商品目录不包含这类横幅。
        try:
            async with aiohttp.ClientSession(timeout=timeout, trust_env=True) as session:
                async with session.get("https://www.gog.com/en/") as response:
                    response.raise_for_status()
                    banners = gog_banner_offers(await response.text())
                for game in gog_offers:
                    if gog_store_giveaway(game):
                        continue
                    slug = urlsplit(game["link"]).path.strip("/")
                    if not re.fullmatch(r"[a-zA-Z0-9_-]+", slug):
                        continue
                    async with session.head(API_URL.split("/api/")[0] + "/open/" + slug,
                                            allow_redirects=False) as redirect:
                        url = redirect.headers.get("Location", "")
                        dest = urlsplit(url)
                        if dest.scheme == "https" and dest.hostname in {"gog.com", "www.gog.com"} and "/game/" in dest.path:
                            game.update(claimChannel="gog", claimUrl=url)
            for game in gog_offers:
                name = re.sub(r"\s*\(GOG\)\s*Giveaway$", "", game["title"], flags=re.I).casefold()
                game.update(banners.get(name, {}))
        except (aiohttp.ClientError, TimeoutError, KeyError, TypeError, ValueError):
            pass  # 保留活动页给出的领取步骤和日期。
    return offers
