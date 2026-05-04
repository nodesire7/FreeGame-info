#!/usr/bin/env python3
"""
GOG 限免游戏抓取脚本：
- 使用 GOG API 获取游戏列表（JSON 格式）
- 从 ITAD deals 获取 GOG 100% OFF 数据（由 itad_fetch.redistribute_itad_deals 注入）
- 本脚本作为补充：直接调用 GOG API 筛选免费游戏
"""
import asyncio
import json
import os
from typing import Any, Dict, List

import aiohttp

GOG_API_URL = "https://www.gog.com/games/ajax/filtered"
USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/125.0.0.0 Safari/537.36"
)

# GOG 实际免费游戏极少（多为限时赠送），主要数据由 ITAD deals 提供
# 此处仅作补充：从 GOG API 筛选 price.amount == 0 的游戏


def _parse_price(price_obj: Dict[str, Any]) -> str:
    """解析 GOG API 价格对象"""
    if not isinstance(price_obj, dict):
        return ""
    amount = price_obj.get("amount", "")
    currency = price_obj.get("currency", "$")
    if amount and amount != "0":
        # Not free — skip
        pass
    if not amount:
        return ""
    if currency == "USD":
        return f"${amount}"
    return f"{amount} {currency}"


def _is_free_game(product: Dict[str, Any]) -> bool:
    """判断是否为免费游戏"""
    price = product.get("price", {})
    if not isinstance(price, dict):
        return False
    # Check if price amount is 0 (free)
    base_amount = price.get("amount", "")
    final_amount = price.get("finalAmount", "") or price.get("amount", "")
    try:
        if float(base_amount) == 0 or float(final_amount) == 0:
            return True
    except (ValueError, TypeError):
        pass
    # Check if price symbol is "Free"
    if price.get("symbol", "") == "Free":
        return True
    return False


async def _fetch_gog_api(session: aiohttp.ClientSession, page: int = 1) -> List[Dict[str, Any]]:
    """从 GOG API 获取免费游戏"""
    params = {
        "mediaType": "game",
        "sort": "popularity",
        "page": page,
    }
    headers = {
        "User-Agent": USER_AGENT,
        "Accept": "application/json",
    }
    try:
        async with session.get(
            GOG_API_URL, params=params, headers=headers,
            timeout=aiohttp.ClientTimeout(total=30),
        ) as resp:
            if resp.status != 200:
                return []
            data = await resp.json()
    except Exception:
        return []

    products = data.get("products", [])
    if not isinstance(products, list):
        return []

    result: List[Dict[str, Any]] = []
    for product in products:
        if not isinstance(product, dict):
            continue

        # Only include actual free games
        if not _is_free_game(product):
            continue

        title = product.get("title", "")
        if not title:
            continue

        # Build full URL
        url_path = product.get("url", "")
        link = f"https://www.gog.com{url_path}" if url_path else ""

        # Cover image
        cover = product.get("coverHorizontal") or product.get("coverVertical") or ""
        if cover and cover.startswith("//"):
            cover = f"https:{cover}"

        # Price info
        price_obj = product.get("price", {})
        price_display = "Free"
        if isinstance(price_obj, dict):
            symbol = price_obj.get("symbol", "")
            if symbol:
                price_display = symbol

        # Publisher
        publisher = ""
        if isinstance(product.get("publisher"), str):
            publisher = product["publisher"]

        # Genres
        genres = []
        if isinstance(product.get("genres"), list):
            genres = [g.get("name", "") for g in product["genres"] if isinstance(g, dict)]

        # Platforms
        works_on = product.get("worksOn", {})
        platforms = []
        if isinstance(works_on, dict):
            if works_on.get("Windows"):
                platforms.append("Windows")
            if works_on.get("Mac"):
                platforms.append("Mac")
            if works_on.get("Linux"):
                platforms.append("Linux")

        # Release date
        release_date = ""
        if product.get("releaseDate"):
            try:
                from datetime import datetime, timezone
                ts = product["releaseDate"]
                if isinstance(ts, (int, float)) and ts > 0:
                    dt = datetime.fromtimestamp(ts, tz=timezone.utc)
                    release_date = dt.strftime("%Y-%m-%d")
            except Exception:
                pass

        result.append({
            "title": title,
            "link": link,
            "cover": cover,
            "price": price_display,
            "originalPrice": "",
            "publisher": publisher,
            "releaseDate": release_date,
            "genres": genres,
            "features": [],
            "platforms": platforms,
            "languages": "",
            "description": "",
            "platform": "GOG",
            "status": "ACTIVE",
            "date": release_date,
        })

    return result


async def fetch_gog() -> List[Dict[str, Any]]:
    """获取 GOG 限免游戏列表（GOG 免费游戏极少，主要数据来自 ITAD）"""
    print("GOG: 正在通过 API 获取免费游戏...")

    async with aiohttp.ClientSession() as session:
        all_items: List[Dict[str, Any]] = []
        # 扫描前 3 页找免费游戏（免费游戏极少，需要多翻几页）
        for page in range(1, 4):
            items = await _fetch_gog_api(session, page)
            all_items.extend(items)
            if len(items) == 0:
                break

    if not all_items:
        print("GOG: 未找到当前免费游戏（GOG 免费赠送较少见，主要数据来自 ITAD）")
        return []

    print(f"GOG: 找到 {len(all_items)} 款免费游戏")
    return all_items


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
