#!/usr/bin/env python3
"""独立抓取 Epic 免费游戏，输出 now/upcoming JSON。"""

import asyncio
import json
import sys

from fetch_freebies import fetch_epic


def main():
    output_file = sys.argv[1] if len(sys.argv) > 1 else "epic.json"
    data = asyncio.run(fetch_epic())
    with open(output_file, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
    print(f"[epic] 已保存到 {output_file}，当前免费 {len(data.get('now', []))} 条，即将免费 {len(data.get('upcoming', []))} 条")


if __name__ == "__main__":
    main()

