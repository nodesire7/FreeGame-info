#!/usr/bin/env python3
"""
ITAD 100% OFF 抓取脚本：
- 使用官方 API: https://api.isthereanydeal.com/deals/v2
- 按 cut 倒序分页拉取
- 仅保留 cut == 100 的条目
- 格式尽量兼容现有渲染层
"""
import asyncio
import json
import os
from datetime import datetime
from typing import Any, Dict, List, Optional

import aiohttp

ITAD_API_URL = "https://api.isthereanydeal.com/deals/v2"
USER_AGENT = "FreeGame-info/1.0 (+https://github.com/nodesire7/FreeGame-info)"
DEFAULT_COUNTRY = os.getenv("ITAD_COUNTRY", "CN").strip().upper() or "CN"
PAGE_LIMIT = 200


def _get_api_key() -> str:
    api_key = os.getenv("ITAD_API_KEY", "").strip()
    if not api_key:
        raise RuntimeError("缺少 ITAD_API_KEY 环境变量，无法调用官方 ITAD API")
    return api_key


def _parse_expiry(value: Optional[str]) -> Optional[int]:
    """将 ISO 时间解析为 Unix seconds。"""
    if not value:
        return None
    try:
        return int(datetime.fromisoformat(value).timestamp())
    except ValueError:
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


async def fetch_itad() -> List[Dict[str, Any]]:
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


def save_json(data: List[Dict[str, Any]], path: str = "ITAD.json") -> None:
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

        print("ITAD 100% OFF 抓取完成！")
        print(f"  已抓取: {len(data)} 个")
        print(f"  已写入: {output}")

        for i, game in enumerate(data[:10], start=1):
            print(f"  {i}. {game.get('title', 'Unknown')} ({game.get('store', '')})")

    except Exception as e:
        print(f"错误: {str(e)}")
        import traceback
        traceback.print_exc()
        sys.exit(1)


if __name__ == "__main__":
    asyncio.run(main())
