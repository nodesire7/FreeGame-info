#!/usr/bin/env python3
"""
统一调度：调用独立的 EPIC / PSN / Steam 抓取并合并为 snapshot.json
"""
import asyncio
import json
import os
import sys
from datetime import datetime, timezone

from fetch_freebies import fetch_epic, fetch_psn, fetch_steam


async def fetch_all(psn_html_path: str | None = None) -> dict:
    epic, steam, psn = await asyncio.gather(
        fetch_epic(),
        fetch_steam(),
        fetch_psn(psn_html_path),
    )
    return {
        "fetchedAt": datetime.now(timezone.utc).isoformat(),
        "epic": epic,
        "steam": steam,
        "psn": psn,
    }


def main():
    output_file = sys.argv[1] if len(sys.argv) > 1 else "snapshot.json"
    output_dir = os.path.dirname(os.path.abspath(output_file)) or os.getcwd()
    psn_html_path = os.path.join(output_dir, "psn.html")

    snapshot = asyncio.run(fetch_all(psn_html_path))

    with open(output_file, "w", encoding="utf-8") as f:
        json.dump(snapshot, f, ensure_ascii=False, indent=2)

    print(f"数据已保存到 {output_file}")
    print(f"Epic: {len(snapshot['epic'].get('now', []))} 正在免费, {len(snapshot['epic'].get('upcoming', []))} 即将免费")
    print(f"Steam: {len(snapshot['steam'])} 条")
    print(f"PSN: {len(snapshot['psn'])} 条")


if __name__ == "__main__":
    main()

