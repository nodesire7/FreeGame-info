#!/usr/bin/env python3
"""
独立的 PSN 限免抓取脚本：
- 拉取 https://www.playstation.com/zh-hans-hk/ps-plus/whats-new/ 页面
- 解析 gdk/root gpdc-section 结构（与实例.html 一致）
- 产出 PSN.json
"""
import asyncio
import json
import os
from typing import Any, Dict, List, Optional
from urllib.parse import urljoin

import aiohttp
from bs4 import BeautifulSoup, Tag
from playwright.async_api import async_playwright

PSN_SOURCE_URL = "https://www.playstation.com/zh-hans-hk/ps-plus/whats-new/"
USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/125.0.0.0 Safari/537.36"
)


async def fetch_html() -> str:
    """优先使用 Playwright，失败回退 aiohttp"""
    # Playwright
    try:
        async with async_playwright() as p:
            browser = await p.chromium.launch(headless=True)
            context = await browser.new_context(user_agent=USER_AGENT)
            page = await context.new_page()
            await page.goto(PSN_SOURCE_URL, wait_until="networkidle", timeout=45_000)
            await page.wait_for_load_state("domcontentloaded")
            html = await page.content()
            await browser.close()
            return html
    except Exception:
        pass

    # aiohttp 回退
    async with aiohttp.ClientSession() as session:
        headers = {
            "User-Agent": USER_AGENT,
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8",
            "Accept-Language": "zh-CN,zh;q=0.9,en;q=0.8",
            "Accept-Encoding": "gzip, deflate, br",
            "Connection": "keep-alive",
            "Upgrade-Insecure-Requests": "1",
        }
        async with session.get(PSN_SOURCE_URL, headers=headers, timeout=aiohttp.ClientTimeout(total=30)) as resp:
            resp.raise_for_status()
            return await resp.text()


def _extract_image_url(box: Tag, base_url: str) -> Optional[str]:
    media = box.select_one(".media-block") or box.select_one(".imageblock") or box.select_one("img")
    candidates: List[str] = []
    if media:
        for attr in ("data-src", "data-image", "data-bg", "data-background", "data-srcset", "src"):
            val = media.get(attr)
            if val:
                candidates.append(val)
        # srcset
        srcset = media.get("srcset")
        if srcset:
            candidates.extend(srcset.split(","))
        # style url()
        style = media.get("style", "")
        if "url(" in style:
            start = style.find("url(") + 4
            end = style.find(")", start)
            if end > start:
                candidates.append(style[start:end].strip('\'" '))
    for c in candidates:
        c = c.strip()
        if not c:
            continue
        url_part = c.split(" ")[0]
        if url_part:
            return urljoin(base_url, url_part)
    return None


def parse_psn(html: str) -> List[Dict[str, Any]]:
    """
    解析 PSN 限免游戏
    根据用户提供的 JavaScript 逻辑：
    - 目标容器：.content-grid.layout__4--a
    - 游戏项：.box
    """
    soup = BeautifulSoup(html, "html.parser")
    base_url = "https://www.playstation.com"
    items: List[Dict[str, Any]] = []

    # 1. 找到包含所有游戏项的列表容器
    # 使用 .content-grid.layout__4--a 选择器（同时包含这两个类）
    list_container = soup.select_one(".content-grid.layout__4--a")
    
    if not list_container:
        # 如果找不到，尝试其他可能的容器
        list_container = soup.select_one(".content-grid.layout__4--a, .content-grid.layout__2--a")
    
    if not list_container:
        print("警告: 未找到 .content-grid.layout__4--a 容器")
        return []

    # 2. 在容器内找到所有游戏项（.box）
    boxes = list_container.select(".box")
    
    if not boxes:
        print("警告: 在容器内未找到任何 .box 元素")
        return []

    # 3. 遍历每个游戏项，提取信息
    for index, box in enumerate(boxes, start=1):
        # 提取标题（通常在 h3 或 .txt-block-paragraph__title 中）
        title_el = (
            box.select_one("h3.txt-style-medium-title") or
            box.select_one("h3.txt-block-paragraph__title") or
            box.select_one("h3") or
            box.select_one(".txt-block-paragraph__title") or
            box.find(["h1", "h2", "h3", "h4"])
        )
        title = title_el.get_text(strip=True) if title_el else ""
        
        if not title:
            # 如果没有标题，跳过这个 box（可能是图片 box）
            continue

        # 提取描述（通常在 p.txt-style-base 或 p 中）
        desc_el = (
            box.select_one("p.txt-style-base") or
            box.select_one("p.txt-block__paragraph") or
            box.select_one("p")
        )
        description = desc_el.get_text(" ", strip=True) if desc_el else ""

        # 提取链接（通常在 .btn--cta a 中）
        link_el = (
            box.select_one(".btn--cta a") or
            box.select_one(".btn--cta__btn-container a") or
            box.select_one("a[href*='/games/']") or
            box.select_one("a[href*='playstation']")
        )
        link = ""
        if link_el and link_el.get("href"):
            link = link_el.get("href").strip()
            if link:
                link = urljoin(base_url, link)

        if not link:
            # 如果没有链接，跳过
            continue

        # 提取图片（可能在当前 box 或前一个 box 中）
        image = _extract_image_url(box, base_url)
        
        # 如果当前 box 没有图片，尝试在前一个 box 中查找
        if not image and index > 1:
            prev_box = boxes[index - 2]  # index 从 1 开始，所以减 2
            image = _extract_image_url(prev_box, base_url)

        items.append(
            {
                "id": link,
                "title": title,
                "link": link,
                "image": image,
                "description": description or "PlayStation 官方暂未提供详细描述。",
                "platforms": None,
            }
        )

    return items


async def fetch_psn(output_path: Optional[str] = None) -> List[Dict[str, Any]]:
    """
    抓取 PSN 限免数据
    :param output_path: 可选，如果提供则保存到指定路径
    :return: 游戏列表
    """
    html = await fetch_html()
    items = parse_psn(html)
    
    if output_path:
        os.makedirs(os.path.dirname(output_path) if os.path.dirname(output_path) else ".", exist_ok=True)
        with open(output_path, "w", encoding="utf-8") as f:
            json.dump(items, f, ensure_ascii=False, indent=2)
        print(f"PSN 抓取完成，找到 {len(items)} 条，已写入 {output_path}")
    else:
        print(f"PSN 抓取完成，找到 {len(items)} 条")
    
    return items


async def main():
    html = await fetch_html()
    items = parse_psn(html)
    with open("PSN.json", "w", encoding="utf-8") as f:
        json.dump(items, f, ensure_ascii=False, indent=2)
    print(f"PSN 抓取完成，找到 {len(items)} 条，已写入 PSN.json")


if __name__ == "__main__":
    asyncio.run(main())

