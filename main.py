#!/usr/bin/env python3
"""
主调度：调用各独立 fetcher（epic_fetch / psn_fetch / steam），合并为 snapshot.json，并生成 HTML
"""
import asyncio
import json
import os
import sys
from datetime import datetime, timezone
from typing import Any, Dict, List

# 导入各个独立的 fetcher
from epic_fetch import fetch_epic
from psn_fetch import fetch_psn
from steam_fetch import fetch_steam
from render_html import render_html


async def fetch_all(output_dir: str = "site") -> Dict[str, Any]:
    """抓取所有平台的限免数据"""
    print("开始抓取限免数据...")
    
    os.makedirs(output_dir, exist_ok=True)
    
    # 定义各平台的输出路径
    epic_path = os.path.join(output_dir, "EPIC.json")
    psn_path = os.path.join(output_dir, "PSN.json")
    steam_path = os.path.join(output_dir, "STEAM.json")
    
    # 并行抓取各平台数据
    results = {}
    
    # Epic
    try:
        epic_data = await fetch_epic()
        results["epic"] = epic_data
        print("[OK] EPIC 抓取完成")
    except Exception as e:
        print(f"[FAIL] EPIC 抓取失败: {e}")
        results["epic"] = {"now": [], "upcoming": []}
    
    # PSN
    try:
        psn_data = await fetch_psn(psn_path)
        results["psn"] = psn_data
        print("[OK] PSN 抓取完成")
    except Exception as e:
        print(f"[FAIL] PSN 抓取失败: {e}")
        results["psn"] = []
    
    # Steam
    try:
        steam_data = await fetch_steam(steam_path)
        results["steam"] = steam_data
        print("[OK] STEAM 抓取完成")
    except Exception as e:
        print(f"[FAIL] STEAM 抓取失败: {e}")
        results["steam"] = []
    
    # 保存各平台的独立 JSON
    epic_data = results.get("epic", {"now": [], "upcoming": []})
    with open(epic_path, "w", encoding="utf-8") as f:
        json.dump(epic_data, f, ensure_ascii=False, indent=2)
    
    steam_data = results.get("steam", [])
    with open(steam_path, "w", encoding="utf-8") as f:
        json.dump(steam_data, f, ensure_ascii=False, indent=2)
    
    # PSN 已经在 fetch_psn 中保存了
    
    # 合并为 snapshot.json
    snapshot = {
        "fetchedAt": datetime.now(timezone.utc).isoformat(),
        "epic": epic_data,
        "steam": steam_data,
        "psn": results.get("psn", []),
        "sources": {
            "epic": "https://store-site-backend-static-ipv4.ak.epicgames.com/freeGamesPromotions",
            "steam": "https://store.steampowered.com/search/?maxprice=free&specials=1&ndl=1?cc=cn&l=schinese",
            "psn": "https://www.playstation.com/zh-hans-hk/ps-plus/whats-new/",
        },
    }
    
    snapshot_path = os.path.join(output_dir, "snapshot.json")
    with open(snapshot_path, "w", encoding="utf-8") as f:
        json.dump(snapshot, f, ensure_ascii=False, indent=2)
    
    return snapshot


def main():
    """主函数"""
    output_dir = sys.argv[1] if len(sys.argv) > 1 else "site"
    
    # 创建 archive 文件夹用于保存历史文件
    archive_dir = os.path.join(output_dir, "archive")
    os.makedirs(archive_dir, exist_ok=True)
    
    # 生成时间戳（格式：YYYYMMDDHHmmss）
    timestamp = datetime.now(timezone.utc).strftime("%Y%m%d%H%M%S")
    
    snapshot = asyncio.run(fetch_all(output_dir))
    
    print(f"\n数据已保存到 {output_dir}/snapshot.json")
    print(f"Epic: {len(snapshot['epic'].get('now', []))} 正在免费, {len(snapshot['epic'].get('upcoming', []))} 即将免费")
    print(f"Steam: {len(snapshot['steam'])} 条")
    print(f"PSN: {len(snapshot['psn'])} 条")
    
    # 保存带时间戳的 JSON 到 archive 文件夹
    archive_json_filename = f"{timestamp}白嫖信息.json"
    archive_json_path = os.path.join(archive_dir, archive_json_filename)
    with open(archive_json_path, "w", encoding="utf-8") as f:
        json.dump(snapshot, f, ensure_ascii=False, indent=2)
    print(f"\n历史 JSON 已保存到 {archive_json_path}")
    
    # 生成 HTML
    snapshot_path = os.path.join(output_dir, "snapshot.json")
    template_path = "epic-freebies.html.template"
    html_output_path = os.path.join(output_dir, "index.html")
    
    if os.path.exists(template_path):
        try:
            html_content = render_html(snapshot, template_path, timestamp=timestamp)
            with open(html_output_path, "w", encoding="utf-8") as f:
                f.write(html_content)
            print(f"\nHTML 已生成到 {html_output_path}")
        except Exception as e:
            print(f"\n生成 HTML 失败: {e}")
            import traceback
            traceback.print_exc()
    else:
        print(f"\n警告: 找不到模板文件 {template_path}，跳过 HTML 生成")
    
    # 生成带时间戳的图片文件名
    archive_image_filename = f"{timestamp}白嫖信息.webp"
    archive_image_path = os.path.join(archive_dir, archive_image_filename)
    
    # 复制 logo.png 到 site 目录
    if os.path.exists("logo.png"):
        import shutil
        logo_dest = os.path.join(output_dir, "logo.png")
        shutil.copy2("logo.png", logo_dest)
        print(f"\nLogo 已复制到 {logo_dest}")
    
    # 生成图片（使用时间戳文件名）
    try:
        from generate_image import generate_webp_from_html
        generate_webp_from_html(html_output_path, archive_image_path, 1200)
        print(f"\n历史图片已生成到 {archive_image_path}")
    except Exception as e:
        print(f"\n生成历史图片失败: {e}")
        import traceback
        traceback.print_exc()
    
    return timestamp, archive_image_path


if __name__ == "__main__":
    main()

