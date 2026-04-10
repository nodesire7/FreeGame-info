#!/usr/bin/env python3
"""
PSN 限免游戏抓取脚本：
- 抓取 https://www.playstation.com/zh-hans-hk/ps-plus/whats-new/ 页面
- 使用 Playwright 获取页面 HTML + 动态渲染描述
- 从 PSN 商店页提取真实描述（subtitle / mainTitle / paragraphs）
- 格式：title, description, link, cover, status
"""
import asyncio
import json
import os
import re
from typing import Any, Dict, List, Optional
from urllib.parse import urljoin, urlparse

import aiohttp
from bs4 import BeautifulSoup
from playwright.async_api import async_playwright

PSN_SOURCE_URL = "https://www.playstation.com/zh-hans-hk/ps-plus/whats-new/"
USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/125.0.0.0 Safari/537.36"
)


async def _fetch_listing_html() -> str:
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

        await page.goto(PSN_SOURCE_URL, wait_until="domcontentloaded", timeout=120_000)
        await page.wait_for_load_state("networkidle")
        await page.wait_for_timeout(5_000)

        try:
            await page.wait_for_selector(".content-grid .box", timeout=30_000)
        except Exception:
            print("警告: 未找到 .content-grid .box 元素")

        html = await page.content()
        await browser.close()
        return html


def _parse_listing(html: str) -> List[Dict[str, Any]]:
    """解析 PSN 限免列表页，提取游戏卡片基础信息"""
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

        # 提取链接
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

        # 提取封面
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

        items.append({
            "title": title,
            "link": link,
            "cover": cover,
        })

    return items


async def _fetch_store_description(link: str) -> str:
    """
    使用 Playwright 访问 PSN 商店页，提取动态加载的描述：
    - subtitle (.txt-block-title__subtitle)
    - mainTitle (.txt-block-title__title)
    - paragraphs (.txt-block__paragraph p.txt-style-base)
    """
    if not link:
        return ""

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

            await page.goto(link, wait_until="domcontentloaded", timeout=60_000)
            await page.wait_for_load_state("networkidle")
            await page.wait_for_timeout(5_000)

            # 提取 subtitle
            subtitle = await page.eval_on_selector(
                ".txt-block-title__subtitle", "el => el ? el.innerText.trim() : ''"
            ) or ""

            # 提取 mainTitle
            main_title = await page.eval_on_selector(
                ".txt-block-title__title", "el => el ? el.innerText.trim() : ''"
            ) or ""

            # 提取所有段落
            paragraphs = await page.eval_on_selector_all(
                ".txt-block__paragraph p.txt-style-base",
                "els => els.map(el => el.innerText.trim()).filter(t => t)"
            ) or []

            description_parts = []
            if subtitle:
                description_parts.append(subtitle)
            if main_title:
                description_parts.append(main_title)
            if paragraphs:
                description_parts.extend(paragraphs)

            await browser.close()
            return "\n\n".join(description_parts)
    except Exception as e:
        print(f"  ⚠️ 获取描述失败 {link}: {e}")
        return ""


async def fetch_psn() -> List[Dict[str, Any]]:
    """
    获取 PSN 限免游戏列表，包含从商店页提取的真实描述
    """
    print("PSN: 正在抓取限免列表页...")
    html = await _fetch_listing_html()
    items = _parse_listing(html)

    if not items:
        print("PSN: 未找到任何游戏")
        return []

    print(f"PSN: 解析到 {len(items)} 款游戏，正在从商店页获取描述...")

    # 批量获取每个游戏的商店页描述
    for i, item in enumerate(items):
        link = item.get("link", "")
        if link:
            print(f"  PSN: [{i+1}/{len(items)}] 获取描述 {item['title'][:20]}...")
            description = await _fetch_store_description(link)
            item["description"] = description
            item["platform"] = "PSN"
            item["originalPrice"] = "会员免费"
            item["date"] = "本月有效"
            item["status"] = "ACTIVE"
            await asyncio.sleep(0.5)  # 避免请求过快
        else:
            item["description"] = ""
            item["platform"] = "PSN"
            item["originalPrice"] = "会员免费"
            item["date"] = "本月有效"
            item["status"] = "ACTIVE"

    print(f"PSN: 描述获取完成")
    return items


def save_json(data: List[Dict[str, Any]], path: str = "PSN.json") -> None:
    """保存数据到 JSON 文件"""
    os.makedirs(os.path.dirname(path) if os.path.dirname(path) else ".", exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)


async def main():
    """主函数"""
    import sys
    output = sys.argv[1] if len(sys.argv) > 1 else "PSN.json"
    try:
        data = await fetch_psn()
        save_json(data, output)
        print(f"PSN: 抓取完成，找到 {len(data)} 款，已写入 {output}")
        for i, game in enumerate(data, 1):
            desc_preview = (game.get("description") or "无描述")[:40]
            print(f"  {i}. {game.get('title')} - {desc_preview}...")
    except Exception as e:
        print(f"错误: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)


if __name__ == "__main__":
    asyncio.run(main())
