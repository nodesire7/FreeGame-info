#!/usr/bin/env python3
"""
PSN 限免游戏抓取脚本：
- 使用 Playwright 获取 https://www.playstation.com/zh-hans-hk/ps-plus/whats-new/ 页面
- 基础信息（标题/链接/封面）从列表页提取
- 详情（发行商/平台/价格/发行日期/语言等）从商店页 Playwright 获取
- description 优先从列表页获取兜底的简短描述
"""
import asyncio
import json
import os
from typing import Any, Dict, List
from urllib.parse import urljoin

from bs4 import BeautifulSoup
from playwright.async_api import async_playwright

PSN_SOURCE_URL = "https://www.playstation.com/zh-hans-hk/ps-plus/whats-new/"
USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/125.0.0.0 Safari/537.36"
)


async def _fetch_listing_page() -> str:
    """使用 Playwright 获取 PSN 限免列表页 HTML"""
    async with async_playwright() as p:
        browser = await p.chromium.launch(
            headless=True,
            args=["--disable-blink-features=AutomationControlled"],
        )
        context = await browser.new_context(
            user_agent=USER_AGENT,
            viewport={"width": 1920, "height": 1080},
            locale="zh-CN",
        )
        page = await context.new_page()
        page.set_default_timeout(120_000)

        await page.goto(PSN_SOURCE_URL, wait_until="load", timeout=120_000)
        await page.wait_for_timeout(8_000)

        try:
            await page.wait_for_selector(".content-grid .box", timeout=30_000)
        except Exception:
            print("警告: 未找到 .content-grid .box 元素")

        html = await page.content()
        await browser.close()
        return html


def _parse_listing(html: str) -> List[Dict[str, Any]]:
    """从列表页 HTML 解析游戏基础信息"""
    soup = BeautifulSoup(html, "html.parser")
    base_url = "https://www.playstation.com"
    items: List[Dict[str, Any]] = []
    seen_titles: set[str] = set()

    boxes = soup.select(".content-grid .box")
    if not boxes:
        print("警告: 未找到 .content-grid .box 元素")
        return []

    for box in boxes:
        title_el = box.select_one("h3.txt-block-paragraph__title")
        if not title_el:
            continue
        title = title_el.get_text(strip=True)
        if not title or title in seen_titles:
            continue
        seen_titles.add(title)

        # 链接
        link_el = box.select_one("a.btn--cta")
        link = ""
        if link_el:
            href = link_el.get("href", "").strip()
            if href:
                if href.startswith("/"):
                    link = urljoin(base_url, href)
                elif href.startswith("http"):
                    link = href

        if not link:
            continue

        # 封面
        cover = ""
        media_block = box.select_one(".media-block")
        if media_block:
            data_src = media_block.get("data-src", "").strip()
            if data_src:
                cover = urljoin(base_url, data_src)
        if not cover:
            parent_grid = box.parent
            if parent_grid:
                adjacent_media = parent_grid.select(".imageblock .media-block")
                if adjacent_media:
                    adj_media = adjacent_media[0]
                    data_src = adj_media.get("data-src", "").strip()
                    if data_src:
                        cover = urljoin(base_url, data_src)
        if not cover:
            img_el = box.select_one("img")
            if img_el:
                src = img_el.get("src", "").strip() or img_el.get("data-src", "").strip()
                if src:
                    cover = urljoin(base_url, src)

        # 列表页简介（兜底用）
        desc_el = box.select_one("p.txt-style-base")
        description = desc_el.get_text(strip=True) if desc_el else ""

        items.append({
            "title": title,
            "link": link,
            "cover": cover,
            "description": description,
        })

    return items


async def _fetch_store_metadata(link: str) -> Dict[str, Any]:
    """
    使用 Playwright 访问商店页，通过执行 JS 提取：
    - title, publisher, releaseDate, price, originalPrice, currency
    - features (兼容性说明等)
    """
    defaults = {
        "publisher": "", "platform": "", "releaseDate": "",
        "price": "", "originalPrice": "", "currency": "",
        "features": [], "supportedLanguages": "",
    }
    if not link:
        return defaults

    js_code = """
() => {
    const results = {};
    results.title = document.querySelector('h1[data-qa*="name"], h1.game-title')?.innerText.trim() || '';
    results.publisher = document.querySelector('div[data-qa*="publisher"], .publisher')?.innerText.trim() || '';
    results.releaseDate = document.querySelector('dd[data-qa*="release-date-value"], .release-date')?.innerText.replace('已发布', '').trim() || '';

    const scripts = document.querySelectorAll('script[type="application/json"]');
    let priceFound = false;

    scripts.forEach(script => {
        try {
            const content = JSON.parse(script.textContent);
            const cache = content.cache || {};
            for (let key in cache) {
                const item = cache[key];
                if (item.price && item.price.basePriceValue !== undefined && !priceFound) {
                    results.price = item.price.discountedPrice || '';
                    results.originalPrice = item.price.basePrice || '';
                    results.currency = item.price.currencyCode || '';
                    priceFound = true;
                }
                if (item.__typename === 'Sku' && item.name && item.name.includes('版')) {
                    results.supportedLanguages = item.name;
                }
            }
        } catch (e) {}
    });

    const notices = Array.from(document.querySelectorAll('[data-qa*="notice"]'))
        .map(el => el.innerText.trim())
        .filter(text => text.length > 0);
    results.features = [...new Set(notices)];

    return results;
}
"""

    try:
        async with async_playwright() as p:
            browser = await p.chromium.launch(
                headless=True,
                args=["--disable-blink-features=AutomationControlled"],
            )
            context = await browser.new_context(
                user_agent=USER_AGENT,
                viewport={"width": 1920, "height": 1080},
                locale="zh-CN",
            )
            page = await context.new_page()
            page.set_default_timeout(60_000)

            await page.goto(link, wait_until="load", timeout=60_000)
            await page.wait_for_timeout(5_000)

            metadata = await page.evaluate(js_code)
            await browser.close()

            result = dict(defaults)
            result["publisher"] = metadata.get("publisher", "")
            result["releaseDate"] = metadata.get("releaseDate", "")
            result["price"] = metadata.get("price", "")
            result["originalPrice"] = metadata.get("originalPrice", "")
            result["currency"] = metadata.get("currency", "")
            result["features"] = metadata.get("features", [])
            result["supportedLanguages"] = metadata.get("supportedLanguages", "")
            return result
    except Exception as e:
        print(f"  ⚠️ 商店页元数据获取失败 {link}: {e}")
        return defaults


async def fetch_psn() -> List[Dict[str, Any]]:
    """获取 PSN 限免游戏列表"""
    print("PSN: 正在抓取限免列表页...")
    html = await _fetch_listing_page()
    items = _parse_listing(html)

    if not items:
        print("PSN: 未找到任何游戏")
        return []

    print(f"PSN: 解析到 {len(items)} 款游戏，正在获取商店页元数据...")

    for i, item in enumerate(items):
        link = item.get("link", "")
        title_short = item["title"][:20]
        print(f"  PSN: [{i+1}/{len(items)}] {title_short}...")

        metadata = await _fetch_store_metadata(link)

        # 优先用列表页简介，其次用发行商+平台拼接
        description = item.get("description", "")
        if not description and (metadata["publisher"] or metadata["releaseDate"]):
            parts = []
            if metadata["publisher"]:
                parts.append(f"发行商：{metadata['publisher']}")
            if metadata["releaseDate"]:
                parts.append(f"发行日期：{metadata['releaseDate']}")
            if metadata["supportedLanguages"]:
                parts.append(f"版本：{metadata['supportedLanguages']}")
            description = " | ".join(parts)

        item["description"] = description
        item["publisher"] = metadata["publisher"]
        item["releaseDate"] = metadata["releaseDate"]
        item["price"] = metadata["price"]
        item["originalPrice"] = metadata["originalPrice"]
        item["currency"] = metadata["currency"]
        item["features"] = metadata["features"]
        item["platform"] = "PS Plus"
        item["originalPrice2"] = "会员免费"
        item["date"] = "本月有效"
        item["status"] = "ACTIVE"

        await asyncio.sleep(0.3)

    print(f"PSN: 完成，共 {len(items)} 款")
    return items


def save_json(data: List[Dict[str, Any]], path: str = "PSN.json") -> None:
    os.makedirs(os.path.dirname(path) if os.path.dirname(path) else ".", exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)


async def main():
    import sys
    output = sys.argv[1] if len(sys.argv) > 1 else "PSN.json"
    try:
        data = await fetch_psn()
        save_json(data, output)
        print(f"\nPSN: 抓取完成，{len(data)} 款，已写入 {output}")
        for g in data:
            print(f"  - {g['title']} | {g.get('publisher','?')} | {g.get('price','?')}")
    except Exception:
        import traceback
        traceback.print_exc()
        sys.exit(1)


if __name__ == "__main__":
    asyncio.run(main())
