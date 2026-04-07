#!/usr/bin/env python3
"""
ITAD Giveaways 抓取脚本：
- 抓取 https://isthereanydeal.com/giveaways/ 页面
- 解析页面嵌入的 JavaScript 数据（window.page 变量）
- 返回简化的 JSON 格式
- 格式：title, store, expiry, gameCount, url, isPending, isMature
"""
import asyncio
import json
import os
import re
from datetime import datetime, timezone, timedelta
from typing import Any, Dict, List, Optional

import aiohttp

ITAD_GIVEAWAYS_URL = "https://isthereanydeal.com/giveaways/"
USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/125.0.0.0 Safari/537.36"
)


def parse_giveaways_page(html_content: str) -> List[Dict[str, Any]]:
    """
    解析 ITAD giveaways 页面
    数据嵌入在 window.page 变量中，格式类似：
    var page = ["Specials/GiveawayListPage",{"bundles":[...]}]
    """
    # 方法1: 尝试匹配 var page = [...{"bundles":[...]}]
    pattern1 = r'var\s+page\s*=\s*\[[\s\S]*?"bundles"\s*:\s*(\[[\s\S]*?\])\s*[,}]'
    match = re.search(pattern1, html_content)

    if not match:
        # 方法2: 直接搜索 bundles 数组
        pattern2 = r'"bundles"\s*:\s*(\[[\s\S]*?\])\s*[,}]'
        match = re.search(pattern2, html_content)

    if not match:
        return []

    bundles_json = match.group(1)

    # 清理 JSON（移除尾部可能多余的字符）
    # 尝试解析
    try:
        bundles = json.loads(bundles_json)
    except json.JSONDecodeError:
        # 尝试修复常见的 JSON 解析问题
        # 可能尾部有多余的 ,}] 字符
        cleaned = re.sub(r'[,}\]]+$', '', bundles_json)
        try:
            bundles = json.loads(cleaned)
        except json.JSONDecodeError:
            return []

    if not isinstance(bundles, list):
        return []

    result: List[Dict[str, Any]] = []
    for bundle in bundles:
        if not isinstance(bundle, dict):
            continue

        title = bundle.get("title", "")
        page_info = bundle.get("page", {})
        store_name = page_info.get("name", "") if isinstance(page_info, dict) else ""
        url = bundle.get("url", "")
        expiry = bundle.get("expiry")
        counts = bundle.get("counts", {})
        game_count = counts.get("games", 0) if isinstance(counts, dict) else 0
        is_pending = bundle.get("isPending", False)
        is_mature = bundle.get("isMature", False)

        if not title or not url:
            continue

        result.append({
            "title": title,
            "store": store_name,
            "expiry": expiry,
            "gameCount": game_count,
            "url": url,
            "isPending": is_pending,
            "isMature": is_mature,
        })

    return result


async def fetch_itad() -> List[Dict[str, Any]]:
    """
    获取 ITAD Giveaways 列表
    """
    async with aiohttp.ClientSession() as session:
        headers = {
            "User-Agent": USER_AGENT,
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
            "Accept-Language": "en-US,en;q=0.9",
            "Connection": "keep-alive",
        }
        try:
            async with session.get(
                ITAD_GIVEAWAYS_URL,
                headers=headers,
                timeout=aiohttp.ClientTimeout(total=30)
            ) as resp:
                if resp.status != 200:
                    raise RuntimeError(f"ITAD 返回状态码 {resp.status}")
                html_content = await resp.text()

        except asyncio.TimeoutError:
            raise RuntimeError("ITAD 请求超时")
        except aiohttp.ClientError as e:
            raise RuntimeError(f"ITAD 请求失败: {str(e)}")

    items = parse_giveaways_page(html_content)
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

        active_count = len([g for g in data if not g.get("isPending", False)])
        pending_count = len([g for g in data if g.get("isPending", False)])

        print(f"ITAD Giveaways 抓取完成！")
        print(f"  有效 giveaway: {active_count} 个")
        print(f"  待生效: {pending_count} 个")
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
