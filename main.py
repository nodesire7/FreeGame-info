#!/usr/bin/env python3
"""
主调度：调用各独立 fetcher（epic_fetch / psn_fetch / steam），生成静态页面，并将历史写入 SQLite（date.db）。
"""
import asyncio
import hashlib
import json
import os
import shutil
import sys
from argparse import ArgumentParser
from datetime import datetime, timezone, timedelta
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

# 导入各个独立的 fetcher
from epic_fetch import fetch_epic
from psn_fetch import fetch_psn
from steam_fetch import fetch_steam
from render_html import render_html, render_history_page
from history_db import open_db, get_latest_meta, insert_record, list_snapshots


async def fetch_all(output_dir: str = "site") -> Dict[str, Any]:
    """抓取所有平台的限免数据"""
    print("开始抓取限免数据...")
    
    os.makedirs(output_dir, exist_ok=True)

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
        psn_data = await fetch_psn(None)
        results["psn"] = psn_data
        print("[OK] PSN 抓取完成")
    except Exception as e:
        print(f"[FAIL] PSN 抓取失败: {e}")
        results["psn"] = []
    
    # Steam
    try:
        steam_data = await fetch_steam(None)
        results["steam"] = steam_data
        print("[OK] STEAM 抓取完成")
    except Exception as e:
        print(f"[FAIL] STEAM 抓取失败: {e}")
        results["steam"] = []

    epic_data = results.get("epic", {"now": [], "upcoming": []})
    steam_data = results.get("steam", [])

    # 合并为 snapshot（不落地 JSON 文件；历史数据写入 SQLite）
    # 使用中国时区（UTC+8）
    china_tz = timezone(timedelta(hours=8))
    snapshot = {
        "fetchedAt": datetime.now(china_tz).isoformat(),
        "epic": epic_data,
        "steam": steam_data,
        "psn": results.get("psn", []),
        "sources": {
            "epic": "https://store-site-backend-static-ipv4.ak.epicgames.com/freeGamesPromotions",
            "steam": "https://store.steampowered.com/search/?maxprice=free&specials=1&ndl=1?cc=cn&l=schinese",
            "psn": "https://www.playstation.com/zh-hans-hk/ps-plus/whats-new/",
        },
    }
    return snapshot


def _china_tz() -> timezone:
    return timezone(timedelta(hours=8))


def _timestamp_cn() -> str:
    return datetime.now(_china_tz()).strftime("%Y%m%d%H%M%S")


def _canonicalize_for_hash(snapshot: Dict[str, Any]) -> Dict[str, Any]:
    """
    用于“是否变更”的去重：只保留决定性字段，避免 fetchedAt/描述变动导致重复记录。
    """
    epic = snapshot.get("epic") or {}
    steam = snapshot.get("steam") or []
    psn = snapshot.get("psn") or []

    def pick_epic(item: Dict[str, Any]) -> Dict[str, Any]:
        return {
            "id": item.get("id"),
            "title": item.get("title"),
            "link": item.get("link"),
            "freeStartAt": item.get("freeStartAt"),
            "freeEndAt": item.get("freeEndAt"),
            "isFreeNow": item.get("isFreeNow"),
        }

    def pick_simple(item: Dict[str, Any]) -> Dict[str, Any]:
        return {
            "id": item.get("id") or item.get("link") or item.get("title"),
            "title": item.get("title"),
            "link": item.get("link"),
        }

    epic_now = sorted([pick_epic(x) for x in (epic.get("now") or []) if isinstance(x, dict)], key=lambda x: (str(x.get("id") or ""), str(x.get("title") or "")))
    epic_upcoming = sorted([pick_epic(x) for x in (epic.get("upcoming") or []) if isinstance(x, dict)], key=lambda x: (str(x.get("id") or ""), str(x.get("title") or "")))
    steam_list = sorted([pick_simple(x) for x in steam if isinstance(x, dict)], key=lambda x: (str(x.get("id") or ""), str(x.get("title") or "")))
    psn_list = sorted([pick_simple(x) for x in psn if isinstance(x, dict)], key=lambda x: (str(x.get("id") or ""), str(x.get("title") or "")))

    return {
        "epic": {"now": epic_now, "upcoming": epic_upcoming},
        "steam": steam_list,
        "psn": psn_list,
    }


def _snapshot_hash(snapshot: Dict[str, Any]) -> str:
    canon = _canonicalize_for_hash(snapshot)
    raw = json.dumps(canon, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


def _ensure_dir(p: Path) -> None:
    p.mkdir(parents=True, exist_ok=True)


def _sync_history_to_site(history_dir: Path, site_dir: Path) -> None:
    """将 history/ 复制到 site/history/，供 GitHub Pages 展示。"""
    dst_root = site_dir / "history"
    dst_records = dst_root / "records"
    src_records = history_dir / "records"
    _ensure_dir(dst_records)

    # date.db
    db_path = history_dir / "date.db"
    if db_path.exists():
        shutil.copy2(db_path, dst_root / "date.db")

    # records
    if src_records.exists():
        for item in src_records.iterdir():
            if item.is_file():
                shutil.copy2(item, dst_records / item.name)


def main() -> Tuple[Optional[str], Optional[str]]:
    """主函数"""
    parser = ArgumentParser()
    parser.add_argument("output_dir", nargs="?", default="site", help="输出目录（默认 site）")
    parser.add_argument("--history-dir", default="history", help="历史记录存储目录（默认 history）")
    args = parser.parse_args()

    output_dir = args.output_dir
    history_dir = Path(args.history_dir)
    records_dir = history_dir / "records"
    _ensure_dir(records_dir)

    snapshot = asyncio.run(fetch_all(output_dir))

    print(f"Epic: {len(snapshot['epic'].get('now', []))} 正在免费, {len(snapshot['epic'].get('upcoming', []))} 即将免费")
    print(f"Steam: {len(snapshot['steam'])} 条")
    print(f"PSN: {len(snapshot['psn'])} 条")

    # 输出“本次记录”的 JSON（用于 Pages 直接访问），始终覆盖为当前快照
    site_dir = Path(output_dir)
    current_json_path = site_dir / "白嫖信息.json"
    current_json_path.write_text(json.dumps(snapshot, ensure_ascii=False, indent=2), encoding="utf-8")

    # 复制 logo.png 到 site 目录
    if os.path.exists("logo.png"):
        logo_dest = os.path.join(output_dir, "logo.png")
        shutil.copy2("logo.png", logo_dest)
        print(f"\nLogo 已复制到 {logo_dest}")

    # === 历史去重（SQLite）：仅当本次与上次不同才新增记录 ===
    conn = open_db(history_dir)
    current_hash = _snapshot_hash(snapshot)
    last_hash, latest_ts = get_latest_meta(conn)

    template_path = "epic-freebies.html.template"
    html_output_path = os.path.join(output_dir, "index.html")

    created = False
    if current_hash != last_hash:
        latest_ts = _timestamp_cn()
        webp_name = f"{latest_ts}白嫖信息.webp"
        image_rel = f"records/{webp_name}"

        # 先生成主页 HTML（页脚包含历史入口/最新图片）
        if os.path.exists(template_path):
            html_content = render_html(snapshot, template_path, latest_history_ts=latest_ts)
            Path(html_output_path).write_text(html_content, encoding="utf-8")
            print(f"\nHTML 已生成到 {html_output_path}")
        else:
            print(f"\n警告: 找不到模板文件 {template_path}，跳过 HTML 生成")

        # 生成图片（仅在新增历史时生成）
        try:
            from generate_image import generate_webp_from_html

            webp_path = records_dir / webp_name
            generate_webp_from_html(html_output_path, str(webp_path), 1200)
            print(f"\n[HISTORY] 新增历史图片: {webp_path.as_posix()}")
        except Exception as e:
            print(f"\n生成历史图片失败: {e}")
            image_rel = None

        # 写入 SQLite
        insert_record(
            conn,
            ts=latest_ts,
            fetched_at=snapshot.get("fetchedAt"),
            hash_value=current_hash,
            snapshot=snapshot,
            image_rel=image_rel,
        )
        created = True
    else:
        # 未变化：仍生成主页 HTML，但 latest_ts 指向上一次记录
        if os.path.exists(template_path):
            html_content = render_html(snapshot, template_path, latest_history_ts=latest_ts)
            Path(html_output_path).write_text(html_content, encoding="utf-8")
            print(f"\nHTML 已生成到 {html_output_path}")
        else:
            print(f"\n警告: 找不到模板文件 {template_path}，跳过 HTML 生成")
        print("\n[HISTORY] 本次抓取结果与上次一致，不新增历史记录。")

    # === 生成历史页面（渲染为卡片样式）===
    snapshots: List[Dict[str, Any]] = list_snapshots(conn, limit=60)

    history_page_dir = site_dir / "history"
    _ensure_dir(history_page_dir)
    history_index = history_page_dir / "index.html"
    history_index.write_text(
        render_history_page(snapshots, template_path="epic-freebies.html.template"),
        encoding="utf-8",
    )

    # 将历史文件同步到 site/history 供 Pages 发布
    _sync_history_to_site(history_dir, site_dir)

    # nojekyll
    (site_dir / ".nojekyll").write_text("", encoding="utf-8")

    return latest_ts, str(history_dir) if created else None


if __name__ == "__main__":
    main()

