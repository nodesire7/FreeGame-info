#!/usr/bin/env python3
"""
独立的 Steam 限免抓取脚本：
- 拉取 https://store.steampowered.com/search/?maxprice=free&specials=1&ndl=1?cc=cn&l=schinese
- 解析搜索结果页面
- 产出 STEAM.json
"""
import asyncio
import json
import os
from typing import Any, Dict, List, Optional

import aiohttp
from bs4 import BeautifulSoup
from playwright.async_api import async_playwright, TimeoutError as PlaywrightTimeoutError

STEAM_FREEBIES_URL = "https://store.steampowered.com/search/?maxprice=free&specials=1&ndl=1?cc=cn&l=schinese"
USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/125.0.0.0 Safari/537.36"
)

PLATFORM_LABELS = {
    "win": "Windows",
    "mac": "macOS",
    "linux": "Linux",
}


async def fetch_html() -> str:
    """使用 Playwright 抓取 Steam 页面 HTML"""
    try:
        async with async_playwright() as playwright:
            browser = await playwright.chromium.launch(
                headless=True,
                args=[
                    "--disable-blink-features=AutomationControlled",
                    "--disable-dev-shm-usage",
                    "--disable-gpu",
                ],
            )
            context = None
            try:
                context = await browser.new_context(
                    user_agent=USER_AGENT,
                    viewport={"width": 1280, "height": 720},
                    device_scale_factor=1,
                    is_mobile=False,
                    java_script_enabled=True,
                )
                await context.add_init_script(
                    "Object.defineProperty(navigator, 'webdriver', { get: () => undefined });"
                )
                page = await context.new_page()
                await page.goto(STEAM_FREEBIES_URL, wait_until="networkidle", timeout=45_000)
                await page.wait_for_load_state("domcontentloaded")
                await page.wait_for_selector("#search_resultsRows", timeout=45_000)
                await page.wait_for_timeout(1_500)
                html_content = await page.content()
                return html_content
            finally:
                if context is not None:
                    await context.close()
                await browser.close()
    except PlaywrightTimeoutError:
        # 回退到 aiohttp
        async with aiohttp.ClientSession() as session:
            headers = {
                "User-Agent": USER_AGENT,
                "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8",
                "Accept-Language": "zh-CN,zh;q=0.9,en;q=0.8",
                "Accept-Encoding": "gzip, deflate, br",
                "Connection": "keep-alive",
                "Upgrade-Insecure-Requests": "1",
            }
            async with session.get(STEAM_FREEBIES_URL, headers=headers, timeout=aiohttp.ClientTimeout(total=30)) as resp:
                resp.raise_for_status()
                return await resp.text()


def parse_steam_freebies(html_content: str) -> List[Dict[str, Any]]:
    """解析 Steam 限免 HTML"""
    soup = BeautifulSoup(html_content, "html.parser")
    rows_container = soup.select_one("#search_resultsRows")
    if rows_container is None:
        return []

    items: List[Dict[str, Any]] = []

    for row in rows_container.select("a.search_result_row"):
        title_el = row.select_one(".title")
        link = row.get("href", "").strip()
        if not title_el or not link:
            continue

        title = title_el.get_text(strip=True)
        if not title:
            continue

        image_el = row.select_one(".search_capsule img")
        image = image_el.get("src").strip() if image_el and image_el.get("src") else None

        release_el = row.select_one(".search_released")
        release_date = release_el.get_text(strip=True) if release_el else None

        discount_el = row.select_one(".discount_block .discount_pct")
        discount_text = discount_el.get_text(strip=True) if discount_el else None

        original_price_el = row.select_one(".discount_block .discount_original_price")
        final_price_el = row.select_one(".discount_block .discount_final_price")
        original_price = (
            original_price_el.get_text(strip=True) if original_price_el else None
        )
        final_price = final_price_el.get_text(strip=True) if final_price_el else None

        review_el = row.select_one(".search_review_summary")
        review_summary_raw = review_el.get("data-tooltip-html") if review_el else None
        review_summary = (
            BeautifulSoup(review_summary_raw, "html.parser").get_text(" ", strip=True)
            if review_summary_raw
            else None
        )

        platform_spans = row.select(".search_platforms .platform_img")
        platforms: List[str] = []
        for span in platform_spans:
            classes = span.get("class", [])
            for class_name in classes:
                if class_name in PLATFORM_LABELS:
                    label = PLATFORM_LABELS[class_name]
                    if label not in platforms:
                        platforms.append(label)

        items.append(
            {
                "id": link or title,
                "title": title,
                "link": link,
                "image": image,
                "releaseDate": release_date,
                "platforms": platforms,
                "discountText": discount_text,
                "originalPrice": original_price,
                "finalPrice": final_price,
                "reviewSummary": review_summary,
            }
        )

    return items


async def fetch_steam(output_path: Optional[str] = None) -> List[Dict[str, Any]]:
    """
    抓取 Steam 限免数据
    :param output_path: 可选，如果提供则保存到指定路径
    :return: 游戏列表
    """
    try:
        html_content = await fetch_html()
        items = parse_steam_freebies(html_content)
        
        if output_path:
            os.makedirs(os.path.dirname(output_path) if os.path.dirname(output_path) else ".", exist_ok=True)
            with open(output_path, "w", encoding="utf-8") as f:
                json.dump(items, f, ensure_ascii=False, indent=2)
            print(f"Steam 抓取完成，找到 {len(items)} 条，已写入 {output_path}")
        else:
            print(f"Steam 抓取完成，找到 {len(items)} 条")
        
        return items
    except PlaywrightTimeoutError as e:
        print(f"Timeout fetching Steam page: {e}")
        return []
    except Exception as e:
        print(f"Failed to fetch Steam freebies: {e}")
        import traceback
        traceback.print_exc()
        return []


async def main():
    html = await fetch_html()
    items = parse_steam_freebies(html)
    with open("STEAM.json", "w", encoding="utf-8") as f:
        json.dump(items, f, ensure_ascii=False, indent=2)
    print(f"Steam 抓取完成，找到 {len(items)} 条，已写入 STEAM.json")


if __name__ == "__main__":
    asyncio.run(main())

