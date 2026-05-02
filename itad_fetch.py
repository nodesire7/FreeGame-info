#!/usr/bin/env python3
"""
ITAD 抓取脚本：
- 使用官方 API: https://api.isthereanydeal.com/deals/v2 获取 100% OFF 游戏
- 使用网页 SSR 数据: https://isthereanydeal.com/bundles/ 获取 bundle / charity 列表
- 对 bundle 目标页补抓 og:image / description，补全封面与详情
"""
import asyncio
import json
import os
import re
from urllib.parse import parse_qs, unquote, urlparse
from datetime import datetime
from typing import Any, Dict, List, Optional, Tuple

import aiohttp

ITAD_API_URL = "https://api.isthereanydeal.com/deals/v2"
ITAD_BUNDLES_URL = "https://isthereanydeal.com/bundles/"
USER_AGENT = "FreeGame-info/1.0 (+https://github.com/nodesire7/FreeGame-info)"
DEFAULT_COUNTRY = os.getenv("ITAD_COUNTRY", "CN").strip().upper() or "CN"
PAGE_LIMIT = 200
BUNDLE_DETAIL_LIMIT = 24
BUNDLE_DETAIL_CONCURRENCY = 4


def _get_api_key() -> str:
    api_key = os.getenv("ITAD_API_KEY", "").strip()
    if not api_key:
        raise RuntimeError("缺少 ITAD_API_KEY 环境变量，无法调用官方 ITAD API")
    return api_key


def _parse_expiry(value: Any) -> Optional[int]:
    """将 ISO 时间或 Unix 时间解析为 Unix seconds。"""
    if not value:
        return None
    if isinstance(value, (int, float)):
        return int(value)
    try:
        return int(datetime.fromisoformat(value).timestamp())
    except (ValueError, TypeError):
        return None


def _pick_cover(assets: Dict[str, Any]) -> str:
    if not isinstance(assets, dict):
        return ""
    for key in ("banner600", "banner400", "banner300", "banner145", "boxart"):
        url = assets.get(key)
        if isinstance(url, str) and url:
            return url
    return ""


def _normalize_item(item: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    deal = item.get("deal")
    if not isinstance(deal, dict):
        return None

    cut = deal.get("cut")
    if cut != 100:
        return None

    shop = deal.get("shop") or {}
    price = deal.get("price") or {}
    regular = deal.get("regular") or {}

    return {
        "id": item.get("id") or item.get("slug") or item.get("title"),
        "title": item.get("title", ""),
        "store": shop.get("name", "ITAD"),
        "storeFamily": _classify_store(shop.get("name", ""), shop.get("id")),
        "expiry": _parse_expiry(deal.get("expiry")),
        "gameCount": 1,
        "url": deal.get("url", ""),
        "isPending": False,
        "isMature": bool(item.get("mature", False)),
        "cover": _pick_cover(item.get("assets") or {}),
        "type": item.get("type") or "game",
        "cut": cut,
        "currentPrice": price.get("amount"),
        "currentCurrency": price.get("currency"),
        "regularPrice": regular.get("amount"),
        "regularCurrency": regular.get("currency"),
        "flag": deal.get("flag", ""),
        "shopId": shop.get("id"),
        "drm": [x.get("name", "") for x in (deal.get("drm") or []) if isinstance(x, dict)],
        "platforms": [x.get("name", "") for x in (deal.get("platforms") or []) if isinstance(x, dict)],
    }


def _classify_store(store_name: str, shop_id: Any = None) -> str:
    name = (store_name or "").strip().lower()
    if "steam" in name:
        return "Steam"
    if "epic" in name:
        return "Epic"
    if "playstation" in name or "psn" in name:
        return "PlayStation"
    if "gog" in name:
        return "GOG"
    if "xbox" in name or "microsoft" in name:
        return "Xbox"
    if "nintendo" in name:
        return "Nintendo"
    if shop_id == 61:
        return "Steam"
    return "Other"


def _unwrap_affiliate_url(url: str) -> str:
    if not url:
        return ""
    parsed = urlparse(url)
    query = parse_qs(parsed.query)
    for key in ("u", "url", "target"):
        if key in query and query[key]:
            return unquote(query[key][0])
    return url


def _clean_text(value: str) -> str:
    return re.sub(r"\s+", " ", (value or "")).strip()


def _pick_meta_image(html: str) -> str:
    patterns = [
        r'<meta[^>]+property=["\']og:image["\'][^>]+content=["\']([^"\']+)["\']',
        r'<meta[^>]+name=["\']twitter:image["\'][^>]+content=["\']([^"\']+)["\']',
        r'<meta[^>]+content=["\']([^"\']+)["\'][^>]+property=["\']og:image["\']',
    ]
    for pattern in patterns:
        match = re.search(pattern, html, re.IGNORECASE)
        if match:
            return match.group(1).strip()
    return ""


def _pick_meta_description(html: str) -> str:
    patterns = [
        r'<meta[^>]+property=["\']og:description["\'][^>]+content=["\']([^"\']+)["\']',
        r'<meta[^>]+name=["\']description["\'][^>]+content=["\']([^"\']+)["\']',
        r'<meta[^>]+content=["\']([^"\']+)["\'][^>]+name=["\']description["\']',
    ]
    for pattern in patterns:
        match = re.search(pattern, html, re.IGNORECASE)
        if match:
            return _clean_text(match.group(1))
    return ""


def _extract_bundles_payload(html: str) -> List[Dict[str, Any]]:
    match = re.search(r"var\s+page\s*=\s*(\[[\s\S]*?\]);", html)
    if not match:
        raise RuntimeError("未能从 ITAD bundles 页面提取 SSR 数据")

    payload = json.loads(match.group(1))
    if not isinstance(payload, list) or len(payload) < 2 or not isinstance(payload[1], dict):
        raise RuntimeError("ITAD bundles SSR 数据结构不符合预期")

    data = payload[1]
    merged: List[Dict[str, Any]] = []
    for key in ("expiring", "updated", "pending"):
        items = data.get(key) or []
        if isinstance(items, list):
            merged.extend([item for item in items if isinstance(item, dict)])
    return merged


def _normalize_bundle(item: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    title = item.get("title")
    url = item.get("url")
    page = item.get("page") or {}
    counts = item.get("counts") or {}
    if not title or not url:
        return None

    details = _clean_text(item.get("details") or item.get("note") or "")
    return {
        "id": item.get("id") or url or title,
        "title": title,
        "store": page.get("name", "Bundle"),
        "storeFamily": "Bundle",
        "url": url,
        "sourceUrl": _unwrap_affiliate_url(url),
        "expiry": _parse_expiry(item.get("expiry")),
        "publishedAt": _parse_expiry(item.get("publish")),
        "isPending": bool(item.get("isPending", False)),
        "isMature": bool(item.get("isMature", False)),
        "gameCount": counts.get("games") or 0,
        "mediaCount": counts.get("media") or 0,
        "details": details,
        "description": details,
        "cover": _pick_cover(item.get("assets") or {}),
        "shopId": page.get("shopId"),
    }


async def _enrich_bundle_details(
    session: aiohttp.ClientSession, bundle: Dict[str, Any], semaphore: asyncio.Semaphore
) -> Dict[str, Any]:
    target_url = bundle.get("sourceUrl") or bundle.get("url")
    if not target_url:
        return bundle

    async with semaphore:
        try:
            async with session.get(target_url, allow_redirects=True) as resp:
                if resp.status != 200:
                    return bundle
                html = await resp.text()
        except Exception:
            return bundle

    cover = bundle.get("cover") or _pick_meta_image(html)
    description = bundle.get("description") or _pick_meta_description(html)
    bundle["cover"] = cover
    bundle["description"] = description or bundle.get("details") or ""
    return bundle


async def fetch_itad_deals() -> List[Dict[str, Any]]:
    """
    获取 ITAD 100% OFF 列表。

    说明：
    - 通过 sort=-cut 将 100% off 项排在最前面
    - 分页抓取，直到当前页已不再出现 100% off 条目
    """
    api_key = _get_api_key()
    headers = {"User-Agent": USER_AGENT}
    params = {
        "key": api_key,
        "country": DEFAULT_COUNTRY,
        "limit": PAGE_LIMIT,
        "sort": "-cut",
    }

    items: List[Dict[str, Any]] = []
    offset = 0

    async with aiohttp.ClientSession(headers=headers, timeout=aiohttp.ClientTimeout(total=30)) as session:
        while True:
            query = dict(params)
            query["offset"] = offset

            try:
                async with session.get(ITAD_API_URL, params=query) as resp:
                    if resp.status != 200:
                        text = await resp.text()
                        raise RuntimeError(f"ITAD API 返回状态码 {resp.status}: {text[:200]}")
                    payload = await resp.json()
            except asyncio.TimeoutError:
                raise RuntimeError("ITAD API 请求超时")
            except aiohttp.ClientError as e:
                raise RuntimeError(f"ITAD API 请求失败: {str(e)}")

            page_items = payload.get("list") or []
            if not isinstance(page_items, list) or not page_items:
                break

            normalized_page = []
            saw_lower_cut = False
            for raw in page_items:
                if not isinstance(raw, dict):
                    continue
                normalized = _normalize_item(raw)
                if normalized:
                    if normalized.get("title") and normalized.get("url"):
                        normalized_page.append(normalized)
                else:
                    deal = raw.get("deal") or {}
                    if isinstance(deal, dict) and isinstance(deal.get("cut"), int) and deal.get("cut", 0) < 100:
                        saw_lower_cut = True

            items.extend(normalized_page)

            if saw_lower_cut:
                break
            if not payload.get("hasMore"):
                break

            next_offset = payload.get("nextOffset")
            if not isinstance(next_offset, int) or next_offset <= offset:
                break
            offset = next_offset

    return items


async def fetch_itad_bundles() -> List[Dict[str, Any]]:
    headers = {"User-Agent": USER_AGENT}
    timeout = aiohttp.ClientTimeout(total=30)

    async with aiohttp.ClientSession(headers=headers, timeout=timeout) as session:
        try:
            async with session.get(ITAD_BUNDLES_URL) as resp:
                if resp.status != 200:
                    text = await resp.text()
                    raise RuntimeError(f"ITAD bundles 页面返回状态码 {resp.status}: {text[:200]}")
                html = await resp.text()
        except asyncio.TimeoutError:
            raise RuntimeError("ITAD bundles 页面请求超时")
        except aiohttp.ClientError as e:
            raise RuntimeError(f"ITAD bundles 页面请求失败: {str(e)}")

        raw_items = _extract_bundles_payload(html)
        bundles = [item for item in (_normalize_bundle(raw) for raw in raw_items) if item]

        # 仅对前若干条补抓封面和详情，控制时延。
        semaphore = asyncio.Semaphore(BUNDLE_DETAIL_CONCURRENCY)
        tasks = [
            _enrich_bundle_details(session, bundle, semaphore)
            for bundle in bundles[:BUNDLE_DETAIL_LIMIT]
        ]
        if tasks:
            enriched = await asyncio.gather(*tasks)
            bundles[: len(enriched)] = enriched
        bundles.sort(
            key=lambda item: (
                0 if item.get("cover") else 1,
                0 if item.get("description") else 1,
                item.get("expiry") or 2**31,
            )
        )
        return bundles


async def fetch_itad() -> Dict[str, List[Dict[str, Any]]]:
    deals: List[Dict[str, Any]] = []
    bundles: List[Dict[str, Any]] = []
    errors: List[str] = []

    try:
        deals = await fetch_itad_deals()
    except Exception as e:
        errors.append(f"deals: {e}")

    try:
        bundles = await fetch_itad_bundles()
    except Exception as e:
        errors.append(f"bundles: {e}")

    if not deals and not bundles and errors:
        raise RuntimeError(" ; ".join(errors))

    return {
        "deals": deals,
        "bundles": bundles,
    }


def save_json(data: Dict[str, List[Dict[str, Any]]], path: str = "ITAD.json") -> None:
    """保存数据到 JSON 文件"""
    os.makedirs(os.path.dirname(path) if os.path.dirname(path) else ".", exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)


async def main():
    """主函数"""
    import sys

    output = sys.argv[1] if len(sys.argv) > 1 else "ITAD.json"

    try:
        data = await fetch_itad()
        save_json(data, output)

        deals = data.get("deals", [])
        bundles = data.get("bundles", [])
        print("ITAD 数据抓取完成！")
        print(f"  100% OFF: {len(deals)} 个")
        print(f"  Bundles: {len(bundles)} 个")
        print(f"  已写入: {output}")

        for i, game in enumerate(deals[:5], start=1):
            print(f"  [DEAL {i}] {game.get('title', 'Unknown')} ({game.get('store', '')})")
        for i, bundle in enumerate(bundles[:5], start=1):
            print(f"  [BUNDLE {i}] {bundle.get('title', 'Unknown')} ({bundle.get('store', '')})")

    except Exception as e:
        print(f"错误: {str(e)}")
        import traceback
        traceback.print_exc()
        sys.exit(1)


if __name__ == "__main__":
    asyncio.run(main())
