#!/usr/bin/env python3
"""香港 Xbox Game Pass Ultimate 主机目录最近新增的会员游戏。"""
import asyncio
import json
import os
from typing import Any, Dict, List
from urllib.parse import urljoin

import aiohttp

# These IDs and contexts are published by Xbox's xgpcatPopulate-2025.js.
RECENT_LIST_ID = "06323672-b8c8-43cc-b0de-32d5a9834749"
CATALOG_URL = "https://catalog.gamepass.com/sigls/v3"
PRODUCTS_URL = "https://displaycatalog.mp.microsoft.com/v7.0/products"


async def fetch_xbox() -> List[Dict[str, Any]]:
    params = {
        "id": RECENT_LIST_ID, "language": "zh-hk", "market": "HK",
        "platformContext": "ConsoleGen8;ConsoleGen9", "subscriptionContext": "cfq7ttc0khs0",
    }
    async with aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(total=30), trust_env=True) as session:
        async with session.get(CATALOG_URL, params=params) as resp:
            resp.raise_for_status()
            listing = await resp.json()
        if not isinstance(listing, list) or not listing or listing[0].get("siglId") != RECENT_LIST_ID:
            raise ValueError("Xbox 最近新增目录结构异常")
        ids = list(dict.fromkeys(row["id"] for row in listing[1:]))
        indexed = {}
        for offset in range(0, len(ids), 20):
            query = {"bigIds": ",".join(ids[offset:offset + 20]), "market": "HK", "languages": "zh-HK"}
            async with session.get(PRODUCTS_URL, params=query) as resp:
                resp.raise_for_status()
                products = (await resp.json())["Products"]
            for product in products:
                indexed[product["ProductId"]] = product

    if any(product_id not in indexed for product_id in ids):
        raise ValueError("Xbox 商品详情不完整")
    result = []
    for product_id in ids:
        product = indexed[product_id]
        if product["ProductKind"] != "Game" or product["Properties"].get("IsDemo"):
            continue
        info = product["LocalizedProperties"][0]
        images = {img.get("ImagePurpose"): img.get("Uri") for img in info.get("Images", [])}
        cover = next((images[k] for k in ("Poster", "BoxArt", "TitledHeroArt") if images.get(k)), "")
        result.append({
            "id": product_id, "title": info["ProductTitle"],
            "link": f"https://www.xbox.com/zh-HK/games/store/-/{product_id}",
            "cover": urljoin("https://www.xbox.com", cover) if cover else "",
            "publisher": info.get("PublisherName", ""), "releaseDate": "", "date": "",
            "description": info.get("ShortDescription") or info.get("ProductDescription", ""),
            "price": "Game Pass Ultimate 会员可玩", "originalPrice": "", "platform": "Xbox Game Pass",
            "genres": product["Properties"].get("Categories") or [], "features": [], "platforms": ["Xbox"],
            "offerType": "subscription", "region": "HK", "status": "ACTIVE", "source": "xbox",
        })
    return result


def save_json(data: List[Dict[str, Any]], path: str = "XBOX.json") -> None:
    os.makedirs(os.path.dirname(path) if os.path.dirname(path) else ".", exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)


async def main():
    import sys
    output = sys.argv[1] if len(sys.argv) > 1 else "XBOX.json"
    data = await fetch_xbox()
    save_json(data, output)
    print(f"Xbox: 完成，已写入 {output}")


if __name__ == "__main__":
    asyncio.run(main())
