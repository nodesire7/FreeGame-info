#!/usr/bin/env python3
"""从香港 PlayStation Plus 官方每月游戏栏目读取会员权益。"""
import asyncio
import json
import os
from typing import Any, Dict, List
from urllib.parse import urljoin

from bs4 import BeautifulSoup
import aiohttp

PSN_SOURCE_URL = "https://www.playstation.com/zh-hans-hk/ps-plus/whats-new/"
USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/125.0.0.0 Safari/537.36"
)


def _parse_listing(html: str) -> List[Dict[str, Any]]:
    soup = BeautifulSoup(html, "html.parser")
    section = soup.select_one("#monthly-games")
    if section is None:
        raise ValueError("PS Plus 官网缺少每月游戏栏目")
    # The heading and game grid live in separate CMS sections.
    items = []
    for element in section.select_one("h2").find_all_next(["h2", "h3"]):
        if element.name == "h2":
            break
        box = element.find_parent(class_="box")
        if box is None:
            continue
        cta = box.select_one("a.btn--cta[href]")
        if cta is None:
            continue
        image = box.select_one(".media-block[data-src]")
        desc = box.select_one("p")
        items.append({
            "title": element.get_text(strip=True), "link": urljoin(PSN_SOURCE_URL, cta["href"]),
            "cover": urljoin(PSN_SOURCE_URL, image["data-src"]) if image else "",
            "description": desc.get_text(" ", strip=True) if desc else "",
            "platform": "PS Plus", "region": "HK", "offerType": "subscription",
            "price": "PS Plus 会员领取", "source": "psn", "status": "ACTIVE",
            "publisher": "", "releaseDate": "", "date": "", "originalPrice": "",
            "currency": "", "features": [], "supportedLanguages": "",
        })
    if not items:
        raise ValueError("PS Plus 每月游戏栏目未解析到商品")
    return items


async def fetch_psn() -> List[Dict[str, Any]]:
    headers = {"User-Agent": USER_AGENT}
    async with aiohttp.ClientSession(headers=headers, timeout=aiohttp.ClientTimeout(total=30), trust_env=True) as session:
        async with session.get(PSN_SOURCE_URL) as resp:
            resp.raise_for_status()
            items = _parse_listing(await resp.text())

        async def enrich(item):
            try:
                async with session.get(item["link"]) as resp:
                    resp.raise_for_status()
                    page = BeautifulSoup(await resp.text(), "html.parser")
            except (aiohttp.ClientError, asyncio.TimeoutError) as error:
                print(f"PS Plus 商品详情未更新 {item['title']}: {type(error).__name__}")
                return
            for field, key in (("publisher", "publisher"), ("releaseDate", "releaseDate"), ("supportedLanguages", "subtitles")):
                value = page.select_one(f'dd[data-qa$="#{key}-value"]')
                if value:
                    item[field] = value.get_text(" ", strip=True)
            systems = page.select_one('dd[data-qa$="#platform-value"]')
            if systems:
                item["platforms"] = [name.strip() for name in systems.get_text(strip=True).split(",")]

        await asyncio.gather(*(enrich(item) for item in items))
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
