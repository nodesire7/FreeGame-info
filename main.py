#!/usr/bin/env python3
"""
主调度：调用各独立 fetcher（epic_fetch / psn_fetch / steam），合并为 snapshot.json，并生成 HTML
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
    
    snapshot_path = os.path.join(output_dir, "snapshot.json")
    with open(snapshot_path, "w", encoding="utf-8") as f:
        json.dump(snapshot, f, ensure_ascii=False, indent=2)
    
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


def _load_manifest(history_dir: Path) -> Dict[str, Any]:
    manifest_path = history_dir / "manifest.json"
    if manifest_path.exists():
        try:
            return json.loads(manifest_path.read_text(encoding="utf-8"))
        except Exception:
            pass
    return {"version": 1, "records": []}


def _save_manifest(history_dir: Path, manifest: Dict[str, Any]) -> None:
    history_dir.mkdir(parents=True, exist_ok=True)
    (history_dir / "manifest.json").write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8"
    )


def _ensure_dir(p: Path) -> None:
    p.mkdir(parents=True, exist_ok=True)


def _sync_history_to_site(history_dir: Path, site_dir: Path) -> None:
    """将 history/ 复制到 site/history/，供 GitHub Pages 展示。"""
    dst_root = site_dir / "history"
    dst_records = dst_root / "records"
    src_records = history_dir / "records"
    _ensure_dir(dst_records)

    # manifest
    manifest_path = history_dir / "manifest.json"
    if manifest_path.exists():
        shutil.copy2(manifest_path, dst_root / "manifest.json")

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

    print(f"\n数据已保存到 {output_dir}/snapshot.json")
    print(f"Epic: {len(snapshot['epic'].get('now', []))} 正在免费, {len(snapshot['epic'].get('upcoming', []))} 即将免费")
    print(f"Steam: {len(snapshot['steam'])} 条")
    print(f"PSN: {len(snapshot['psn'])} 条")

    # 复制 logo.png 到 site 目录
    if os.path.exists("logo.png"):
        logo_dest = os.path.join(output_dir, "logo.png")
        shutil.copy2("logo.png", logo_dest)
        print(f"\nLogo 已复制到 {logo_dest}")

    # === 历史去重：仅当内容发生变化才新增记录 ===
    manifest = _load_manifest(history_dir)
    records: List[Dict[str, Any]] = manifest.get("records") if isinstance(manifest.get("records"), list) else []
    current_hash = _snapshot_hash(snapshot)
    last_hash = records[-1].get("hash") if records else None

    created = False
    latest_ts: Optional[str] = records[-1].get("timestamp") if records else None
    if current_hash != last_hash:
        latest_ts = _timestamp_cn()
        json_name = f"{latest_ts}白嫖信息.json"
        webp_name = f"{latest_ts}白嫖信息.webp"

        json_path = records_dir / json_name
        json_path.write_text(json.dumps(snapshot, ensure_ascii=False, indent=2), encoding="utf-8")
        print(f"\n[HISTORY] 新增历史 JSON: {json_path.as_posix()}")

        # 生成 HTML（先生成 index，再生成图片）
        template_path = "epic-freebies.html.template"
        html_output_path = os.path.join(output_dir, "index.html")
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

        # 更新 manifest
        rec = {
            "timestamp": latest_ts,
            "fetchedAt": snapshot.get("fetchedAt"),
            "hash": current_hash,
            "json": f"records/{json_name}",
            "webp": f"records/{webp_name}",
            "counts": {
                "epicNow": len(snapshot.get("epic", {}).get("now", []) or []),
                "epicUpcoming": len(snapshot.get("epic", {}).get("upcoming", []) or []),
                "steam": len(snapshot.get("steam") or []),
                "psn": len(snapshot.get("psn") or []),
            },
        }
        records.append(rec)
        manifest["records"] = records
        _save_manifest(history_dir, manifest)
        created = True
    else:
        # 未变化：仍生成主页 HTML，但 latest_ts 指向上一次记录
        template_path = "epic-freebies.html.template"
        html_output_path = os.path.join(output_dir, "index.html")
        if os.path.exists(template_path):
            html_content = render_html(snapshot, template_path, latest_history_ts=latest_ts)
            Path(html_output_path).write_text(html_content, encoding="utf-8")
            print(f"\nHTML 已生成到 {html_output_path}")
        else:
            print(f"\n警告: 找不到模板文件 {template_path}，跳过 HTML 生成")
        print("\n[HISTORY] 本次抓取结果与上次一致，不新增历史记录。")

    # === 生成历史页面（渲染为卡片样式）===
    # 读取所有历史 snapshot（最新在前）
    snapshots: List[Dict[str, Any]] = []
    for rec in reversed(records):
        rel = rec.get("json")
        if not isinstance(rel, str):
            continue
        p = history_dir / rel
        if p.exists():
            try:
                snapshots.append(json.loads(p.read_text(encoding="utf-8")))
            except Exception:
                continue

    site_dir = Path(output_dir)
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

