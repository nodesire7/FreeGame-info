#!/usr/bin/env python3
"""
Xbox 限免游戏数据：
- Xbox Game Pass 页面是 React SPA，HTML 抓取无法获取数据
- Xbox 100% OFF 数据由 ITAD Deals API 提供（在 itad_fetch.redistribute_itad_deals 中注入）
- 本脚本返回空列表，实际数据来自 ITAD
"""
import asyncio
import json
import os
from typing import Any, Dict, List


async def fetch_xbox() -> List[Dict[str, Any]]:
    """
    获取 Xbox 限免游戏列表。
    Xbox 免费游戏数据主要由 ITAD deals 提供（Microsoft Store 100% OFF 条目）。
    此函数返回空列表作为初始数据，ITAD 数据在 main.py 中被注入。
    """
    print("Xbox: 数据由 ITAD Deals API 提供，跳过直接抓取")
    return []


def save_json(data: List[Dict[str, Any]], path: str = "XBOX.json") -> None:
    os.makedirs(os.path.dirname(path) if os.path.dirname(path) else ".", exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)


async def main():
    import sys
    output = sys.argv[1] if len(sys.argv) > 1 else "XBOX.json"
    data = await fetch_xbox()
    save_json(data, output)
    print(f"Xbox: 完成，已写入 {output}")


if __name__ == "__main__":
    asyncio.run(main())
