#!/usr/bin/env python3
"""
ITAD 数据抓取脚本：
- Deals API：获取全平台 100% OFF 折扣游戏（需要 ITAD_API_KEY）
- Giveaways 页面：解析 giveaways 页面的 bundle/礼包数据
- 商店归类：将 deals 按平台家族分类，供渲染时再分配到对应 Tab
"""
import asyncio
import json
import os
import re
from datetime import datetime, timezone, timedelta
from typing import Any, Dict, List, Optional

import aiohttp

ITAD_DEALS_API = "https://api.isthereanydeal.com/deals/v2"
ITAD_GIVEAWAYS_URL = "https://isthereanydeal.com/giveaways/"
USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/125.0.0.0 Safari/537.36"
)

# 商店 → 平台家族映射
STORE_FAMILY = {
    "steam": "steam",
    "epicgames": "epic",
    "epic": "epic",
    "playstation": "psn",
    "psn": "psn",
    "gog": "gog",
    "xbox": "xbox",
    "microsoft": "xbox",
    "nintendo": "nintendo",
    "itchio": "itchio",
    "humble": "humble",
    "fanatical": "fanatical",
    "indiegala": "indiegala",
}


def _classify_store(store_name: str) -> str:
    """将商店名称归类到平台家族"""
    key = store_name.lower().replace(" ", "").replace("-", "")
    for k, v in STORE_FAMILY.items():
        if k in key:
            return v
    return "other"


# ============== Deals API (100% OFF) ==============


async def _fetch_itad_deals(
    session: aiohttp.ClientSession,
    api_key: str,
    country: str = "CN",
    limit: int = 200,
) -> List[Dict[str, Any]]:
    """从 ITAD Deals API 拉取 100% OFF 折扣，分页直到 cut < 100"""
    all_deals: List[Dict[str, Any]] = []
    offset = 0
    max_pages = 5

    for _ in range(max_pages):
        params = {
            "key": api_key,
            "country": country,
            "limit": limit,
            "offset": offset,
            "sort": "-cut",
        }
        try:
            async with session.get(
                ITAD_DEALS_API,
                params=params,
                timeout=aiohttp.ClientTimeout(total=30),
            ) as resp:
                if resp.status != 200:
                    break
                data = await resp.json()
        except Exception:
            break

        deals = data.get("list") if isinstance(data, dict) else []
        if not deals:
            break

        all_deals.extend(deals)
        offset += limit

        # 最后一批的 cut 值 < 100 则停止
        if deals[-1].get("cut", 0) < 100:
            break

    # 规范化 deals 字段
    result: List[Dict[str, Any]] = []
    for deal in all_deals:
        cut = deal.get("cut", 0)
        if cut < 100:
            continue

        shop_info = deal.get("shop", {})
        shop_name = shop_info.get("name", "") if isinstance(shop_info, dict) else ""
        plain = deal.get("plain", "")

        price_info = deal.get("price", {}) if isinstance(deal.get("price"), dict) else {}
        regular_info = deal.get("regular", {}) if isinstance(deal.get("regular"), dict) else {}

        result.append({
            "id": deal.get("id", plain),
            "plain": plain,
            "title": deal.get("title", ""),
            "store": shop_name,
            "cut": cut,
            "price": price_info.get("amount", 0),
            "priceCurrency": price_info.get("currency", ""),
            "regularPrice": regular_info.get("amount", 0),
            "regularCurrency": regular_info.get("currency", ""),
            "url": deal.get("urls", {}).get("game", ""),
            "platforms": deal.get("platforms", []),
            "expiry": deal.get("expiry"),
            "storeFamily": _classify_store(shop_name),
        })
    return result


# ============== Giveaways 页面 (Bundles) ==============


def _parse_giveaways_page(html_content: str) -> List[Dict[str, Any]]:
    """解析 ITAD giveaways 页面，提取 bundle 数据"""
    # 匹配 var page = [...{"bundles":[...]}]
    pattern = r'"bundles"\s*:\s*(\[[\s\S]*?\])\s*[,}]'
    match = re.search(pattern, html_content)
    if not match:
        return []

    bundles_json = match.group(1)
    try:
        bundles = json.loads(bundles_json)
    except json.JSONDecodeError:
        cleaned = re.sub(r'[,}\]]+$', '', bundles_json)
        try:
            bundles = json.loads(cleaned)
        except json.JSONDecodeError:
            return []

    if not isinstance(bundles, list):
        return []

    result: List[Dict[str, Any]] = []
    for bundle in bundles:
        if not isinstance(bundle, dict):
            continue
        title = bundle.get("title", "")
        page_info = bundle.get("page", {})
        store_name = page_info.get("name", "") if isinstance(page_info, dict) else ""
        url = bundle.get("url", "")
        expiry = bundle.get("expiry")
        counts = bundle.get("counts", {})
        game_count = counts.get("games", 0) if isinstance(counts, dict) else 0
        is_pending = bundle.get("isPending", False)
        is_mature = bundle.get("isMature", False)

        if not title or not url:
            continue

        result.append({
            "title": title,
            "store": store_name,
            "expiry": expiry,
            "gameCount": game_count,
            "url": url,
            "isPending": is_pending,
            "isMature": is_mature,
            "storeFamily": _classify_store(store_name),
        })
    return result


async def _fetch_itad_giveaways(session: aiohttp.ClientSession) -> List[Dict[str, Any]]:
    """抓取 ITAD Giveaways 页面"""
    headers = {
        "User-Agent": USER_AGENT,
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
        "Accept-Language": "en-US,en;q=0.9",
    }
    try:
        async with session.get(
            ITAD_GIVEAWAYS_URL,
            headers=headers,
            timeout=aiohttp.ClientTimeout(total=30),
        ) as resp:
            if resp.status != 200:
                return []
            html_content = await resp.text()
    except Exception:
        return []

    return _parse_giveaways_page(html_content)


# ============== 主入口 ==============


async def fetch_itad(
    api_key: Optional[str] = None,
    country: str = "CN",
) -> Dict[str, Any]:
    """
    获取 ITAD 全平台数据
    返回: {"deals": [...], "bundles": [...]}
    """
    itad_key = api_key or os.getenv("ITAD_API_KEY", "")

    async with aiohttp.ClientSession() as session:
        deals: List[Dict[str, Any]] = []
        bundles: List[Dict[str, Any]] = []

        # Deals API
        if itad_key:
            try:
                deals = await _fetch_itad_deals(session, itad_key, country)
            except Exception as e:
                print(f"  ⚠️ ITAD Deals API 失败: {e}")

        # Giveaways (bundles)
        try:
            bundles = await _fetch_itad_giveaways(session)
        except Exception as e:
            print(f"  ⚠️ ITAD Giveaways 失败: {e}")

    return {"deals": deals, "bundles": bundles}


def redistribute_itad_deals(
    itad_data: Dict[str, Any],
    epic_data: Optional[Dict[str, Any]] = None,
    steam_data: Optional[List[Dict[str, Any]]] = None,
) -> List[Dict[str, Any]]:
    """
    将 ITAD deals 中属于 Epic/Steam/PSN 的条目合并到对应平台数据中。
    返回仅保留"其他商店"和 bundles 的 ITAD 数据。
    """
    deals = itad_data.get("deals", [])
    bundles = itad_data.get("bundles", [])

    main_platforms = {"epic", "steam", "psn"}
    redistributed_deals: List[Dict[str, Any]] = []
    leftover_deals: List[Dict[str, Any]] = []

    for deal in deals:
        family = deal.get("storeFamily", "other")
        if family in main_platforms:
            redistributed_deals.append(deal)
        else:
            leftover_deals.append(deal)

    # 将 redistributed_deals 注入到对应平台数据
    if epic_data is not None and isinstance(epic_data, dict):
        epic_extra = [d for d in redistributed_deals if d.get("storeFamily") == "epic"]
        if epic_extra:
            for d in epic_extra:
                normalized = {
                    "title": d["title"],
                    "link": d.get("url", ""),
                    "cover": "",
                    "originalPriceDesc": f"{d.get('regularPrice', 0)} {d.get('regularCurrency', '')}".strip(),
                    "publisher": d.get("store", ""),
                    "creator": "",
                    "description": f"ITAD 来源：{d['store']} 100% OFF",
                    "isFreeNow": True,
                    "freeStartAt": None,
                    "freeEndAt": d.get("expiry"),
                    "source": "itad",
                }
                if "now" not in epic_data:
                    epic_data["now"] = []
                epic_data["now"].append(normalized)

    if steam_data is not None and isinstance(steam_data, list):
        steam_extra = [d for d in redistributed_deals if d.get("storeFamily") == "steam"]
        for d in steam_extra:
            normalized = {
                "title": d["title"],
                "id": d.get("url", d.get("plain", "")),
                "link": d.get("url", f"https://store.steampowered.com/app/{d.get('plain', '')}/"),
                "image": "",
                "platforms": d.get("platforms", []),
                "discountText": "100% OFF",
                "originalPrice": f"{d.get('regularPrice', 0)} {d.get('regularCurrency', '')}".strip(),
                "finalPrice": "0",
                "shortDescription": f"ITAD 来源：{d['store']} 100% OFF",
                "source": "itad",
            }
            steam_data.append(normalized)

    return leftover_deals + bundles


def save_json(data: Dict[str, Any], path: str = "ITAD.json") -> None:
    """保存数据到 JSON 文件"""
    os.makedirs(os.path.dirname(path) if os.path.dirname(path) else ".", exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)


async def main():
    import sys
    output = sys.argv[1] if len(sys.argv) > 1 else "ITAD.json"
    try:
        data = await fetch_itad()
        save_json(data, output)

        deal_count = len(data.get("deals", []))
        bundle_count = len(data.get("bundles", []))
        print(f"ITAD 抓取完成！")
        print(f"  100% OFF deals: {deal_count} 个")
        print(f"  Bundles/Giveaways: {bundle_count} 个")
        print(f"  已写入: {output}")

    except Exception as e:
        print(f"错误: {str(e)}")
        import traceback
        traceback.print_exc()
        sys.exit(1)


if __name__ == "__main__":
    asyncio.run(main())
