#!/usr/bin/env python3
"""
GOG 限免游戏抓取脚本：
- 使用 Playwright 获取 GOG 免费游戏页面
- 基础信息（标题/链接/封面/原价）从列表页提取
- 详情（发行商/平台/类型/语言等）从商店页获取
"""
import asyncio
import json
import os
from typing import Any, Dict, List
from urllib.parse import urljoin

from bs4 import BeautifulSoup
from playwright.async_api import async_playwright

GOG_FREE_URL = "https://www.gog.com/en/games?price=free&sort=popularity"
GOG_BASE = "https://www.gog.com"
USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/125.0.0.0 Safari/537.36"
)

GOG_STORE_JS = """
() => {
    const data = {};
    data.title = document.querySelector('h1.productcard-header__title')?.innerText.trim() || '';
    data.price = document.querySelector('.product-actions-price__final')?.innerText.trim() || '';
    data.originalPrice = document.querySelector('.product-actions-price__base')?.innerText.trim() || '';
    data.description = document.querySelector('.description__text')?.innerText.trim() || '';
    data.publisher = document.querySelector('.details__publisher a')?.innerText.trim() || '';
    data.releaseDate = document.querySelector('.details__release-date .details__content')?.innerText.trim() || '';
    data.genres = Array.from(document.querySelectorAll('.details__category a'))
        .map(el => el.innerText.trim()).filter(Boolean);
    data.features = Array.from(document.querySelectorAll('.details__feature .details__content'))
        .map(el => el.innerText.trim()).filter(Boolean);
    data.languages = Array.from(document.querySelectorAll('.details__languages .details__content td'))
        .map(el => el.innerText.trim()).join(', ');
    data.cover = document.querySelector('.productcard-image img')?.src || '';
    return data;
}
"""

GOG_DEFAULTS = {
    "publisher": "", "releaseDate": "", "price": "",
    "originalPrice": "", "genres": [], "features": [],
    "languages": "", "cover": "", "description": "",
}


async def _fetch_listing_page() -> str:
    """使用 Playwright 获取 GOG 免费游戏列表页"""
    async with async_playwright() as p:
        browser = await p.chromium.launch(
            headless=True,
            args=["--disable-blink-features=AutomationControlled"],
        )
        context = await browser.new_context(
            user_agent=USER_AGENT,
            viewport={"width": 1920, "height": 1080},
            locale="en-US",
        )
        page = await context.new_page()
        page.set_default_timeout(90_000)

        await page.goto(GOG_FREE_URL, wait_until="load", timeout=90_000)
        await page.wait_for_timeout(5_000)

        # Scroll to load lazy content
        await page.evaluate("window.scrollTo(0, document.body.scrollHeight)")
        await page.wait_for_timeout(2_000)

        html = await page.content()
        await context.close()
        await browser.close()
        return html


def _parse_listing(html: str) -> List[Dict[str, Any]]:
    """从列表页 HTML 解析游戏基础信息"""
    soup = BeautifulSoup(html, "html.parser")
    items: List[Dict[str, Any]] = []
    seen: set[str] = set()

    # GOG uses product tiles
    tiles = soup.select('a.product-tile, [class*="product-tile"], .game-card')
    if not tiles:
        # Fallback: try finding game links
        tiles = soup.select('a[href*="/game/"]')

    for tile in tiles:
        # Title
        title_el = (
            tile.select_one('[class*="title"]')
            or tile.select_one('h3')
            or tile.select_one('.product-title__text')
        )
        if not title_el:
            continue
        title = title_el.get_text(strip=True)
        if not title or title in seen:
            continue
        seen.add(title)

        # Link
        href = tile.get("href", "")
        if not href and tile.name == "a":
            href = tile.get("href", "")
        if not href or "javascript:" in href:
            continue
        link = urljoin(GOG_BASE, href) if href.startswith("/") else href

        # Cover image
        img = tile.select_one("img")
        cover = ""
        if img:
            cover = (
                img.get("src", "")
                or img.get("data-src", "")
                or img.get("data-original", "")
            )
            if cover and cover.startswith("/"):
                cover = urljoin(GOG_BASE, cover)

        # Price info
        price_el = tile.select_one('[class*="price"]')
        price_text = price_el.get_text(strip=True) if price_el else "Free"

        items.append({
            "title": title,
            "link": link,
            "cover": cover,
            "price": price_text if price_text else "Free",
            "originalPrice": "",
        })

    # Cap to reasonable number; GOG free page includes many permanently-free classics
    # Time-limited giveaways are rarer; ITAD Deals API is the primary GOG data source
    return items[:12]


async def _fetch_store_metadata(link: str, context) -> Dict[str, Any]:
    """使用共享 browser context 访问 GOG 商店页获取详情"""
    if not link:
        return dict(GOG_DEFAULTS)

    try:
        page = await context.new_page()
        page.set_default_timeout(60_000)

        await page.goto(link, wait_until="load", timeout=60_000)
        await page.wait_for_timeout(3_000)

        metadata = await page.evaluate(GOG_STORE_JS)
        await page.close()

        result = dict(GOG_DEFAULTS)
        result["title"] = metadata.get("title", "")
        result["publisher"] = metadata.get("publisher", "")
        result["releaseDate"] = metadata.get("releaseDate", "")
        result["price"] = metadata.get("price", "")
        result["originalPrice"] = metadata.get("originalPrice", "")
        result["genres"] = metadata.get("genres", [])
        result["features"] = metadata.get("features", [])
        result["languages"] = metadata.get("languages", "")
        result["cover"] = metadata.get("cover", "")
        result["description"] = metadata.get("description", "")
        return result
    except Exception as e:
        print(f"  ⚠️ GOG 商店页获取失败 {link}: {e}")
        return dict(GOG_DEFAULTS)


async def fetch_gog() -> List[Dict[str, Any]]:
    """获取 GOG 限免游戏列表"""
    print("GOG: 正在获取免费游戏...")
    try:
        html = await _fetch_listing_page()
    except Exception as e:
        print(f"GOG: 列表页获取失败: {e}")
        return []

    items = _parse_listing(html)
    if not items:
        print("GOG: 未找到免费游戏")
        return []

    print(f"GOG: 解析到 {len(items)} 款游戏，正在获取详情...")

    async with async_playwright() as p:
        browser = await p.chromium.launch(
            headless=True,
            args=["--disable-blink-features=AutomationControlled"],
        )
        context = await browser.new_context(
            user_agent=USER_AGENT,
            viewport={"width": 1920, "height": 1080},
            locale="en-US",
        )

        for i, item in enumerate(items):
            link = item.get("link", "")
            title_short = item["title"][:25]
            print(f"  GOG: [{i+1}/{len(items)}] {title_short}...")

            meta = await _fetch_store_metadata(link, context)

            item["publisher"] = meta.get("publisher") or "GOG"
            item["releaseDate"] = meta.get("releaseDate", "")
            item["genres"] = meta.get("genres", [])
            item["features"] = meta.get("features", [])
            item["languages"] = meta.get("languages", "")
            item["description"] = meta.get("description") or item.get("price", "")
            item["platform"] = "GOG"
            if meta.get("cover"):
                item["cover"] = meta["cover"]
            if meta.get("originalPrice"):
                item["originalPrice"] = meta["originalPrice"]
            if meta.get("price"):
                item["price"] = meta["price"]

            item["status"] = "ACTIVE"
            item["date"] = meta.get("releaseDate", "")

            await asyncio.sleep(0.3)

        await context.close()
        await browser.close()

    print(f"GOG: 完成，共 {len(items)} 款")
    return items


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
