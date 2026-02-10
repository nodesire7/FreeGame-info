#!/usr/bin/env python3
"""
PSN 限免游戏抓取脚本：
- 抓取 https://www.playstation.com/zh-hans-hk/ps-plus/whats-new/ 页面
- 使用 Playwright 获取完整渲染的页面
- 返回简化的 JSON 格式（与用户提供的新 JS 逻辑一致）
- 格式：title, description, link, cover, status
"""
import asyncio
import json
import os
from typing import Any, Dict, List, Optional
from urllib.parse import urljoin

from playwright.async_api import async_playwright

PSN_SOURCE_URL = "https://www.playstation.com/zh-hans-hk/ps-plus/whats-new/"
USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/125.0.0.0 Safari/537.36"
)


async def fetch_html() -> str:
    """
    使用 Playwright 获取页面 HTML
    """
    try:
        async with async_playwright() as p:
            browser = await p.chromium.launch(headless=True)
            context = await browser.new_context(
                user_agent=USER_AGENT,
                viewport={"width": 1920, "height": 1080},
                locale="zh-CN",
            )
            page = await context.new_page()
            
            # 设置页面导航超时
            page.set_default_timeout(120_000)
            
            # 使用更宽松的等待策略
            await page.goto(PSN_SOURCE_URL, wait_until="domcontentloaded", timeout=120_000)
            await page.wait_for_load_state("domcontentloaded")
            
            # 等待页面内容加载
            await page.wait_for_timeout(10_000)
            
            # 尝试等待关键元素加载
            try:
                await page.wait_for_selector('.content-grid .box', timeout=30_000)
            except Exception:
                print("警告: 未找到 .content-grid .box 元素，继续尝试...")
            
            html = await page.content()
            await browser.close()
            return html
    
    except Exception as e:
        print(f"Playwright 获取失败: {str(e)}")
        raise


def parse_psn(html: str) -> List[Dict[str, Any]]:
    """
    解析 PSN 限免游戏
    根据用户提供的 JavaScript 逻辑：
    - 目标容器：.content-grid .box
    - 提取字段：title, description, link, cover, status
    """
    from bs4 import BeautifulSoup
    
    soup = BeautifulSoup(html, "html.parser")
    base_url = "https://www.playstation.com"
    items: List[Dict[str, Any]] = []
    seen_titles: set[str] = set()

    # 1. 找到所有游戏卡片区域
    boxes = soup.select('.content-grid .box')
    
    if not boxes:
        print("警告: 未找到 .content-grid .box 元素")
        return []

    # 2. 遍历每个 box
    for box in boxes:
        # 提取标题
        title_el = box.select_one('h3.txt-block-paragraph__title')
        if not title_el:
            continue
        
        title = title_el.get_text(strip=True)
        if not title:
            continue
        
        # 去重
        if title in seen_titles:
            continue
        seen_titles.add(title)

        # 提取描述
        desc_el = box.select_one('p.txt-style-base')
        description = desc_el.get_text(strip=True) if desc_el else ""

        # 提取链接
        link_el = box.select_one('a.btn--cta')
        link = ""
        if link_el:
            href = link_el.get('href', '').strip()
            if href:
                if href.startswith('/'):
                    link = urljoin(base_url, href)
                elif href.startswith('http'):
                    link = href
        
        if not link:
            continue

        # 提取封面图
        # 匹配 JS 逻辑：
        # 1. 优先使用 media-block 的 data-src（当前 box 内）
        # 2. 如果没有，查找相邻 box 的 .imageblock .media-block
        cover = ""
        
        # 情况1: 当前 box 内的 media-block
        media_block = box.select_one('.media-block')
        if media_block:
            data_src = media_block.get('data-src', '').strip()
            if data_src:
                cover = urljoin(base_url, data_src)
        
        # 情况2: 查找相邻 box 的 .imageblock .media-block（如果情况1没找到）
        if not cover:
            parent_grid = box.parent  # 获取父级容器
            if parent_grid:
                # 在父级内查找相邻的 .imageblock .media-block
                adjacent_media = parent_grid.select('.imageblock .media-block')
                if adjacent_media:
                    # 取第一个匹配的元素
                    adj_media = adjacent_media[0]
                    data_src = adj_media.get('data-src', '').strip()
                    if data_src:
                        cover = urljoin(base_url, data_src)
        
        # 兜底: 如果都没有 data-src，尝试从 img 标签获取
        if not cover:
            img_el = box.select_one('img')
            if img_el:
                src = img_el.get('src', '').strip() or img_el.get('data-src', '').strip()
                if src:
                    cover = urljoin(base_url, src)

        items.append({
            "platform": "PSN",
            "title": title,
            "description": description,
            "originalPrice": "会员免费",
            "date": "本月有效",
            "link": link,
            "cover": cover,
            "status": "ACTIVE"
        })

    return items


async def fetch_psn() -> List[Dict[str, Any]]:
    """
    获取 PSN 限免游戏列表
    """
    html = await fetch_html()
    items = parse_psn(html)
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
        
        print(f"PSN 抓取完成！")
        print(f"  找到 {len(data)} 款限免游戏")
        print(f"  已写入: {output}")
        
        # 打印游戏列表
        for i, game in enumerate(data, start=1):
            print(f"  {i}. {game.get('title', 'Unknown')}")
        
    except Exception as e:
        print(f"错误: {str(e)}")
        sys.exit(1)


if __name__ == "__main__":
    asyncio.run(main())
