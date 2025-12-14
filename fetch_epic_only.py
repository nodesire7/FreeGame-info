#!/usr/bin/env python3
import asyncio
import json
import sys

from fetch_freebies import fetch_epic


def main():
    output = sys.argv[1] if len(sys.argv) > 1 else "epic.json"
    data = asyncio.run(fetch_epic())
    with open(output, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
    print(f"Epic 数据已保存到 {output}，当前免费 {len(data['now'])}，即将免费 {len(data['upcoming'])}")


if __name__ == "__main__":
    main()

