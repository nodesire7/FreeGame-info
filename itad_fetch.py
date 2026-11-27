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
from datetime import datetime, timezone
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
    """读取 ITAD v2 的 game.deal 和分页游标。"""
    result = []
    offset = 0
    while True:
        params = {
            "country": country, "limit": limit, "offset": offset, "sort": "-cut",
            "filter": '{"cut":{"min":100,"max":100}}',
        }
        async with session.get(
            ITAD_DEALS_API, params=params, headers={"ITAD-API-Key": api_key},
            timeout=aiohttp.ClientTimeout(total=30),
        ) as resp:
            resp.raise_for_status()
            data = await resp.json()
        for game in data["list"]:
            deal = game["deal"]
            price, regular = deal["price"], deal["regular"]
            if deal["cut"] != 100 or price["amount"] != 0 or regular["amount"] <= 0:
                continue
            end = deal.get("expiry")
            expiry = int(datetime.fromisoformat(end.replace("Z", "+00:00")).timestamp()) if end else None
            if expiry is not None and expiry <= datetime.now(timezone.utc).timestamp():
                continue
            shop = deal["shop"]["name"]
            assets = game.get("assets") or {}
            result.append({
                "id": game["id"], "plain": game["slug"], "title": game["title"], "store": shop,
                "cut": deal["cut"], "price": price["amount"], "priceCurrency": price["currency"],
                "regularPrice": regular["amount"], "regularCurrency": regular["currency"],
                "url": deal["url"], "voucher": deal.get("voucher"), "platforms": [platform["name"] for platform in deal.get("platforms", [])],
                "cover": assets.get("banner600") or assets.get("boxart", ""), "expiry": expiry,
                "storeFamily": _classify_store(shop), "offerType": "giveaway", "region": country,
            })
        if not data["hasMore"]:
            return result
        if data["nextOffset"] <= offset:
            raise ValueError("ITAD 分页游标异常")
        offset = data["nextOffset"]


# ============== Giveaways 页面 (Bundles) ==============


def _parse_giveaways_page(html_content: str) -> List[Dict[str, Any]]:
    """解析 ITAD giveaways 页面，提取 bundle 数据"""
    marker = re.search(r"\bvar\s+page\s*=\s*", html_content)
    if not marker:
        raise ValueError("ITAD 页面缺少数据")
    page, _ = json.JSONDecoder().raw_decode(html_content[marker.end():])
    bundles = page[1]["bundles"]
    if not isinstance(bundles, list):
        raise ValueError("ITAD 组合包格式异常")

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

        if not title or not url or (expiry and expiry <= datetime.now(timezone.utc).timestamp()):
            continue

        result.append({
            "title": title,
            "store": store_name,
            "expiry": expiry,
            "gameCount": game_count,
            "offerType": "bundle",
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
    async with session.get(ITAD_GIVEAWAYS_URL, headers=headers, timeout=aiohttp.ClientTimeout(total=30)) as resp:
        resp.raise_for_status()
        html_content = await resp.text()
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

    errors = {}
    async with aiohttp.ClientSession(trust_env=True) as session:
        deals: List[Dict[str, Any]] = []
        bundles: List[Dict[str, Any]] = []

        # Deals API
        if itad_key:
            try:
                deals = await _fetch_itad_deals(session, itad_key, country)
            except Exception as e:
                errors["deals"] = type(e).__name__
                print(f"ITAD Deals API 请求失败: {type(e).__name__}")
        else:
            errors["deals"] = "ITAD_API_KEY 未配置"

        # Giveaways (bundles)
        try:
            bundles = await _fetch_itad_giveaways(session)
            # 尝试为 bundle 提取 og:image 封面
            if bundles:
                try:
                    await _enrich_bundle_covers(session, bundles)
                except Exception as e:
                    print(f"  ⚠️ ITAD bundle 封面提取失败: {e}")
        except Exception as e:
            errors["bundles"] = type(e).__name__
            print(f"ITAD 组合包请求失败: {type(e).__name__}")

    return {"deals": deals, "bundles": bundles, "errors": errors}


def _format_itad_price(d: Dict[str, Any]) -> str:
    """格式化 ITAD deal 价格为字符串"""
    price = d.get("regularPrice", 0)
    currency = d.get("regularCurrency", "")
    if price and currency:
        return f"{price} {currency}".strip()
    elif price:
        return str(price)
    return ""


def redistribute_itad_deals(
    itad_data: Dict[str, Any],
    epic_data: Optional[Dict[str, Any]] = None,
    steam_data: Optional[List[Dict[str, Any]]] = None,
    psn_data: Optional[List[Dict[str, Any]]] = None,
    gog_data: Optional[List[Dict[str, Any]]] = None,
    xbox_data: Optional[List[Dict[str, Any]]] = None,
) -> List[Dict[str, Any]]:
    """
    将 ITAD deals 中属于 Epic/Steam/PSN/GOG/Xbox 的条目合并到对应平台数据中。
    返回仅保留"其他商店"和 bundles 的 ITAD 数据（扁平列表，供渲染层统一展示）。
    """
    deals = itad_data.get("deals", [])
    bundles = itad_data.get("bundles", [])

    targets = {
        "epic": epic_data.setdefault("now", []) if epic_data is not None else None,
        "steam": steam_data, "psn": psn_data, "gog": gog_data, "xbox": xbox_data,
    }
    leftover_deals = []
    for deal in deals:
        family = deal.get("storeFamily")
        target = targets.get(family)
        if target is None:
            leftover_deals.append(deal)
            continue
        title = deal["title"]
        if any(row.get("title", "").strip().casefold() == title.strip().casefold()
               and row.get("offerType") != "subscription" for row in target):
            continue
        expiry = deal.get("expiry")
        regular_price = _format_itad_price(deal)
        row = {
            "id": deal.get("id") or deal["url"], "title": title, "link": deal["url"],
            "cover": deal.get("cover", ""), "originalPrice": regular_price, "price": "免费",
            "description": f"{deal['store']} 限时免费", "platforms": deal.get("platforms", []),
            "freeEndAt": expiry * 1000 if expiry else None, "expiry": expiry, "status": "ACTIVE",
            "date": "", "source": "itad", "offerType": "giveaway", "region": deal.get("region", ""),
        }
        if deal.get("voucher"):
            row["description"] += f"，结算时使用优惠码 {deal['voucher']}"
        if family == "epic":
            row.update(originalPriceDesc=regular_price, isFreeNow=True, freeStartAt=None, publisher="", creator="")
        elif family == "steam":
            row.update(image=row["cover"], discountText="-100%", finalPrice="0", shortDescription=row["description"])
        else:
            row.update(platform={"psn": "PlayStation Store", "gog": "GOG", "xbox": "Microsoft Store"}[family],
                       publisher="", releaseDate="", genres=[], features=[], languages="")
            if family == "psn":
                row["image"] = row["cover"]
        target.append(row)

    return leftover_deals + bundles


async def _enrich_bundle_covers(
    session: aiohttp.ClientSession,
    bundles: List[Dict[str, Any]],
) -> None:
    """为 bundle 从目标页面提取 og:image 封面（并发最多 4 个）"""
    import asyncio
    import re

    semaphore = asyncio.Semaphore(4)

    async def _fetch_og_image(bundle: Dict[str, Any]) -> None:
        url = bundle.get("url", "")
        if not url or bundle.get("cover"):
            return
        async with semaphore:
            try:
                async with session.get(
                    url,
                    timeout=aiohttp.ClientTimeout(total=15),
                    headers={"User-Agent": USER_AGENT, "Accept": "text/html"},
                    allow_redirects=True,
                ) as resp:
                    if resp.status != 200:
                        return
                    # 只读前 64KB 找 og:image
                    html = ""
                    chunk_count = 0
                    async for chunk in resp.content.iter_chunked(8192):
                        html += chunk.decode("utf-8", errors="ignore")
                        chunk_count += 1
                        if chunk_count >= 8 or "og:image" in html:
                            break
            except Exception:
                return

            # 提取 og:image content
            m = re.search(r'<meta\s+property="og:image"\s+content="([^"]+)"', html)
            if not m:
                m = re.search(r'<meta\s+content="([^"]+)"\s+property="og:image"', html)
            if m:
                bundle["cover"] = m.group(1)

    await asyncio.gather(*[_fetch_og_image(b) for b in bundles])


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
