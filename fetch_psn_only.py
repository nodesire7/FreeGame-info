#!/usr/bin/env python3
"""独立抓取 PSN 免费游戏，输出 JSON。"""

import asyncio
import json
import sys

from fetch_freebies import fetch_psn


def main():
    output_file = sys.argv[1] if len(sys.argv) > 1 else "psn.json"
    data = asyncio.run(fetch_psn())
    with open(output_file, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
    print(f"[psn] 已保存到 {output_file}，共 {len(data)} 条")


if __name__ == "__main__":
    main()

