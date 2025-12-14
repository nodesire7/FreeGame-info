#!/usr/bin/env python3
import asyncio
import json
import sys

from fetch_freebies import fetch_psn


def main():
    output = sys.argv[1] if len(sys.argv) > 1 else "psn.json"
    data = asyncio.run(fetch_psn())
    with open(output, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
    print(f"PSN 数据已保存到 {output}，共 {len(data)} 条")


if __name__ == "__main__":
    main()

