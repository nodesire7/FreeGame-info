#!/usr/bin/env python3
"""查询 GOG 中国区当前折后免费且有付费原价的商品。"""
import asyncio
import json
import os
from decimal import Decimal
from typing import Any, Dict, List

import aiohttp

GOG_API_URL = "https://catalog.gog.com/v1/catalog"


async def fetch_gog() -> List[Dict[str, Any]]:
    params = {
        "limit": 48, "page": 1, "price": "between:0,0", "discounted": "eq:true",
        "order": "desc:discount", "productType": "in:game,pack,dlc",
        "countryCode": "CN", "locale": "zh-Hans", "currencyCode": "CNY",
    }
    result = []
    async with aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(total=30), trust_env=True) as session:
        while True:
            async with session.get(GOG_API_URL, params=params) as resp:
                resp.raise_for_status()
                data = await resp.json()
            for product in data["products"]:
                price = product["price"]
                if Decimal(price["finalMoney"]["amount"]) != 0 or Decimal(price["baseMoney"]["amount"]) <= 0:
                    continue
                result.append({
                    "id": product["id"], "title": product["title"], "link": product["storeLink"],
                    "cover": product.get("coverHorizontal") or product.get("coverVertical", ""),
                    "price": price["final"], "originalPrice": price["base"],
                    "publisher": ", ".join(product.get("publishers", [])),
                    "genres": [g["name"] for g in product.get("genres", [])],
                    "features": [f["name"] for f in product.get("features", [])],
                    "platforms": product.get("operatingSystems", []),
                    "releaseDate": product.get("releaseDate", ""), "date": "",
                    "languages": "", "description": "", "platform": "GOG", "status": "ACTIVE",
                    "region": "CN", "offerType": "giveaway", "source": "gog",
                })
            if params["page"] >= data["pages"]:
                break
            params["page"] += 1
    return result


def save_json(data: List[Dict[str, Any]], path: str = "GOG.json") -> None:
    os.makedirs(os.path.dirname(path) if os.path.dirname(path) else ".", exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)


async def main():
    import sys
    output = sys.argv[1] if len(sys.argv) > 1 else "GOG.json"
    try:
        data = await fetch_gog()
        save_json(data, output)
        print(f"\nGOG: 完成，已写入 {output}")
        for g in data:
            print(f"  - {g['title']} | {g.get('price', '?')}")
    except Exception:
        import traceback
        traceback.print_exc()
        sys.exit(1)


if __name__ == "__main__":
    asyncio.run(main())
