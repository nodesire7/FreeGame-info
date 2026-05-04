#!/usr/bin/env python3
"""
Xbox 限免游戏抓取脚本：
- 使用 Playwright 获取 Microsoft Store Xbox 免费游戏页面
- 基础信息从列表页提取，详情从商店页获取
"""
import asyncio
import json
import os
from typing import Any, Dict, List
from urllib.parse import urljoin
from datetime import datetime, timezone, timedelta

from bs4 import BeautifulSoup
from playwright.async_api import async_playwright

XBOX_FREE_URL = "https://www.xbox.com/zh-hk/xbox-game-pass/games"
XBOX_BASE = "https://www.xbox.com"
USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/125.0.0.0 Safari/537.36"
)

XBOX_STORE_JS = """
() => {
    const data = {};
    data.title = document.querySelector('h1[data-cy="product-title"], h1')?.innerText.trim() || '';
    data.price = document.querySelector('[data-cy="price"], .price-display')?.innerText.trim() || '';
    data.originalPrice = document.querySelector('.strikethrough, .original-price')?.innerText.trim() || '';
    data.publisher = document.querySelector('[data-cy="publisher"], .publisher-name')?.innerText.trim() || '';
    data.releaseDate = document.querySelector('[data-cy="release-date"], .release-date')?.innerText.trim() || '';
    data.description = document.querySelector('[data-cy="description"], .game-description')?.innerText.trim() || '';
    data.genres = Array.from(document.querySelectorAll('[data-cy="genre"], .genre-tag'))
        .map(el => el.innerText.trim()).filter(Boolean);
    data.features = Array.from(document.querySelectorAll('[data-cy="capability"], .capability-tag'))
        .map(el => el.innerText.trim()).filter(Boolean);
    data.cover = document.querySelector('img[data-cy="hero-image"], .hero-image img')?.src || '';
    data.platforms = Array.from(document.querySelectorAll('[data-cy="platform"], .platform-tag'))
        .map(el => el.innerText.trim()).filter(Boolean);
    if (!data.platforms.length) data.platforms = ['Xbox'];
    return data;
}
"""

XBOX_DEFAULTS = {
    "publisher": "", "releaseDate": "", "price": "",
    "originalPrice": "", "genres": [], "features": [],
    "languages": "", "cover": "", "description": "",
    "platforms": ["Xbox"],
}


async def _fetch_listing_page() -> str:
    """使用 Playwright 获取 Xbox Game Pass 游戏列表页"""
    async with async_playwright() as p:
        browser = await p.chromium.launch(
            headless=True,
            args=["--disable-blink-features=AutomationControlled"],
        )
        context = await browser.new_context(
            user_agent=USER_AGENT,
            viewport={"width": 1920, "height": 1080},
            locale="zh-HK",
        )
        page = await context.new_page()
        page.set_default_timeout(90_000)

        await page.goto(XBOX_FREE_URL, wait_until="load", timeout=90_000)
        await page.wait_for_timeout(6_000)

        # Scroll to trigger lazy loading
        for _ in range(3):
            await page.evaluate("window.scrollBy(0, 800)")
            await page.wait_for_timeout(1_000)

        html = await page.content()
        await context.close()
        await browser.close()
        return html


def _parse_listing(html: str) -> List[Dict[str, Any]]:
    """从列表页 HTML 解析游戏基础信息"""
    soup = BeautifulSoup(html, "html.parser")
    items: List[Dict[str, Any]] = []
    seen: set[str] = set()

    # Blocklist: titles/aria-labels that are navigation/UI elements, not games
    _BLOCK_PREFIXES = (
        "microsoft", "xbox", "登入", "立即加入", "取得應用程式", "下載",
        "探索", "深入了解", "瀏覽", "download", "sign in", "join",
        "get the app", "explore", "learn more", "browse",
    )
    _BLOCK_EXACT = ("", "xbox", "microsoft")

    # Only target game-specific links
    cards = soup.select('a[href*="/game/"], [class*="game-card"], [class*="GameCard"]')

    # Fallback: if no game cards found, try aria-label links but with strict filtering
    if not cards:
        cards = soup.select('a[aria-label]')

    for card in cards:
        title = ""
        link = ""

        # Try aria-label first
        aria_label = card.get("aria-label", "")
        if aria_label:
            title = aria_label.strip()

        # Try h3 or title element
        if not title:
            title_el = card.select_one("h3, .title, [class*='title']")
            if title_el:
                title = title_el.get_text(strip=True)

        if not title:
            continue

        title_lower = title.lower().strip()

        # Skip non-game entries
        if title_lower in _BLOCK_EXACT:
            continue
        if title_lower.startswith(_BLOCK_PREFIXES):
            continue
        # Skip overly long titles (usually descriptions, not game names)
        if len(title) > 100:
            continue
        # Skip entries with "app" references (download links)
        if any(kw in title_lower for kw in ("應用程式", "app", "installer", "aka.ms")):
            continue

        if title in seen:
            continue
        seen.add(title)

        # Link — only accept game detail page URLs
        href = card.get("href", "")
        if href.startswith("/") and "/game/" in href:
            link = urljoin(XBOX_BASE, href)
        elif href.startswith("http") and "/game/" in href:
            link = href

        if not link:
            continue

        # Cover image
        img = card.select_one("img")
        cover = ""
        if img:
            cover = img.get("src", "") or img.get("data-src", "") or img.get("data-lazy-src", "")
            if cover and cover.startswith("/"):
                cover = urljoin(XBOX_BASE, cover)

        # Price
        price_el = card.select_one('[class*="price"], .badge, [class*="badge"]')
        price_text = price_el.get_text(strip=True) if price_el else ""

        items.append({
            "title": title,
            "link": link,
            "cover": cover,
            "price": price_text,
            "originalPrice": "",
        })

    return items[:20]  # Cap to prevent excessive requests


async def _fetch_store_metadata(link: str, context) -> Dict[str, Any]:
    """使用共享 browser context 访问 Xbox 商店页获取详情"""
    if not link:
        return dict(XBOX_DEFAULTS)

    try:
        page = await context.new_page()
        page.set_default_timeout(60_000)

        await page.goto(link, wait_until="load", timeout=60_000)
        await page.wait_for_timeout(4_000)

        metadata = await page.evaluate(XBOX_STORE_JS)
        await page.close()

        result = dict(XBOX_DEFAULTS)
        result["title"] = metadata.get("title", "")
        result["publisher"] = metadata.get("publisher", "")
        result["releaseDate"] = metadata.get("releaseDate", "")
        result["price"] = metadata.get("price", "")
        result["originalPrice"] = metadata.get("originalPrice", "")
        result["genres"] = metadata.get("genres", [])
        result["features"] = metadata.get("features", [])
        result["cover"] = metadata.get("cover", "")
        result["description"] = metadata.get("description", "")
        result["platforms"] = metadata.get("platforms", ["Xbox"])
        return result
    except Exception as e:
        print(f"  ⚠️ Xbox 商店页获取失败 {link}: {e}")
        return dict(XBOX_DEFAULTS)


async def fetch_xbox() -> List[Dict[str, Any]]:
    """获取 Xbox 限免游戏列表"""
    print("Xbox: 正在获取 Game Pass 免费游戏...")
    try:
        html = await _fetch_listing_page()
    except Exception as e:
        print(f"Xbox: 列表页获取失败: {e}")
        return []

    items = _parse_listing(html)
    if not items:
        print("Xbox: 未找到游戏")
        return []

    print(f"Xbox: 解析到 {len(items)} 款游戏，正在获取详情...")

    async with async_playwright() as p:
        browser = await p.chromium.launch(
            headless=True,
            args=["--disable-blink-features=AutomationControlled"],
        )
        context = await browser.new_context(
            user_agent=USER_AGENT,
            viewport={"width": 1920, "height": 1080},
            locale="zh-HK",
        )

        for i, item in enumerate(items):
            link = item.get("link", "")
            title_short = item["title"][:25]
            print(f"  Xbox: [{i+1}/{len(items)}] {title_short}...")

            meta = await _fetch_store_metadata(link, context)

            item["publisher"] = meta.get("publisher") or "Microsoft"
            item["releaseDate"] = meta.get("releaseDate", "")
            item["genres"] = meta.get("genres", [])
            item["features"] = meta.get("features", [])
            item["description"] = meta.get("description") or item.get("price", "")
            item["platform"] = "Xbox Game Pass"
            item["platforms"] = meta.get("platforms", ["Xbox"])
            if meta.get("cover"):
                item["cover"] = meta["cover"]
            if meta.get("originalPrice"):
                item["originalPrice"] = meta["originalPrice"]
            if meta.get("price"):
                item["price"] = meta["price"]

            if not item.get("price") or item["price"] in ("Free", "免费", "HK$0.00"):
                item["price"] = "Game Pass 免费"

            item["status"] = "ACTIVE"
            item["date"] = meta.get("releaseDate", "")

            await asyncio.sleep(0.3)

        await context.close()
        await browser.close()

    print(f"Xbox: 完成，共 {len(items)} 款")
    return items


def save_json(data: List[Dict[str, Any]], path: str = "XBOX.json") -> None:
    os.makedirs(os.path.dirname(path) if os.path.dirname(path) else ".", exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)


async def main():
    import sys
    output = sys.argv[1] if len(sys.argv) > 1 else "XBOX.json"
    try:
        data = await fetch_xbox()
        save_json(data, output)
        print(f"\nXbox: 完成，已写入 {output}")
        for g in data:
            print(f"  - {g['title']} | {g.get('price', '?')}")
    except Exception:
        import traceback
        traceback.print_exc()
        sys.exit(1)


if __name__ == "__main__":
    asyncio.run(main())
