#!/usr/bin/env python3
"""
主调度：调用各独立 fetcher（epic_fetch / psn_fetch / steam），生成静态页面，并将历史写入 SQLite（date.db）。
"""
import asyncio
import hashlib
import json
import os
import re
import shutil
from email.utils import format_datetime as format_rss_date
from xml.etree import ElementTree as ET
from argparse import ArgumentParser
from datetime import datetime, timezone, timedelta
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

# 导入各个独立的 fetcher
from epic_fetch import fetch_epic
from psn_fetch import fetch_psn
from steam_fetch import fetch_steam
from itad_fetch import fetch_itad, redistribute_itad_deals
from gog_fetch import fetch_gog
from xbox_fetch import fetch_xbox
from gamerpower_fetch import fetch_gamerpower, is_steam_giveaway
from render_html import render_html, render_history_page, convert_epic_new_format
from history_db import open_db, get_latest_meta, get_latest_image_rel, insert_record, list_snapshots


PRIMARY_PLATFORMS = ("epic", "steam", "psn", "gog", "xbox", "gamerpower")
CURRENT_JSON = "白嫖信息.json"
SOURCE_URLS = {
    "epic": "https://store.epicgames.com/zh-CN/free-games",
    "steam": "https://store.steampowered.com/search/?maxprice=free&specials=1&ndl=1&cc=cn&l=schinese",
    "psn": "https://www.playstation.com/zh-hans-hk/ps-plus/whats-new/#monthly-games",
    "gog": "https://www.gog.com/zh/games?priceRange=0,0",
    "xbox": "https://www.xbox.com/zh-HK/xbox-game-pass/games",
    "itad": "https://isthereanydeal.com/giveaways/",
    "gamerpower": "https://www.gamerpower.com/giveaways",
}


def _rows(data):
    if not isinstance(data, list) or any(not isinstance(item, dict) for item in data):
        raise ValueError("来源返回的条目格式异常")
    return data


def _epic_groups(data):
    if isinstance(data, list):
        return convert_epic_new_format(_rows(data))
    return {key: _rows(data[key]) for key in ("now", "upcoming")}


def _itad_parts(data):
    if isinstance(data, list):
        return {
            "deals": [row for row in _rows(data) if "cut" in row],
            "bundles": [row for row in data if "cut" not in row],
        }
    return {key: _rows(data[key]) for key in ("deals", "bundles")}


def _read_snapshot(path):
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        if isinstance(data, dict) and data.get("fetchedAt"):
            return data
    except FileNotFoundError:
        pass
    except (OSError, ValueError) as exc:
        print(f"[WARN] 无法读取快照 {path}: {exc}")
    return {}


def _resolve_source(current, prior, previous_status, previous_time, checked_at):
    if current is not None:
        return current, {"state": "ok", "checkedAt": checked_at, "asOf": checked_at}
    # 老版本未记录抓取状态，空数组可能来自故障，不能视为上次成功。
    as_of = previous_status.get("asOf") if previous_status else previous_time
    if previous_status.get("state") != "unavailable" and as_of and prior is not None:
        has_rows = any(prior.values()) if isinstance(prior, dict) else bool(prior)
        if previous_status or has_rows:
            return prior, {"state": "cached", "checkedAt": checked_at, "asOf": as_of}
    return None, {"state": "unavailable", "checkedAt": checked_at, "asOf": None}


def _combined_status(statuses, checked_at):
    if any(status["state"] == "unavailable" for status in statuses):
        return {"state": "unavailable", "checkedAt": checked_at, "asOf": None}
    state = "cached" if any(s["state"] == "cached" for s in statuses) else "ok"
    oldest = min((s["asOf"] for s in statuses), key=datetime.fromisoformat)
    return {"state": state, "checkedAt": checked_at, "asOf": oldest}


async def fetch_all(output_dir: str = "site", previous=None) -> Dict[str, Any]:
    """按来源保留最近一次成功结果，独立处理 ITAD 的折扣和礼包。"""
    os.makedirs(output_dir, exist_ok=True)
    if previous is None:
        previous = _read_snapshot(Path(output_dir) / CURRENT_JSON)
    fetchers = {
        "epic": fetch_epic(), "steam": fetch_steam(None), "psn": fetch_psn(),
        "gog": fetch_gog(), "xbox": fetch_xbox(), "itad": fetch_itad(),
        "gamerpower": fetch_gamerpower(),
    }
    outcomes = await asyncio.gather(*fetchers.values(), return_exceptions=True)
    checked_at = datetime.now(_china_tz()).isoformat()
    previous_time = previous.get("fetchedAt")
    previous_statuses = previous.get("sourceStatus") or {}
    statuses = {}
    successful = {}
    for key, outcome in zip(fetchers, outcomes):
        try:
            if isinstance(outcome, BaseException):
                raise outcome
            if key == "epic":
                successful[key] = _epic_groups(outcome)
            elif key == "itad":
                if not isinstance(outcome, dict):
                    raise ValueError("ITAD 来源格式异常")
                successful[key] = outcome
            else:
                successful[key] = _rows(outcome)
        except Exception as exc:
            # URLs in exceptions may include credentials.
            print(f"[FAIL] {key}: {type(exc).__name__}")

    previous_itad = _itad_parts(previous.get("itad") or [])
    current_itad = successful.get("itad") or {}
    old_itad_status = previous_statuses.get("itad") or {}
    components = {}
    itad_data = {}
    for part in ("deals", "bundles"):
        current = None
        if part in current_itad and part not in (current_itad.get("errors") or {}):
            try:
                current = _rows(current_itad[part])
            except ValueError:
                print(f"[FAIL] itad/{part}: 无效的条目格式")
        prior_status = (old_itad_status.get("components") or {}).get(part, old_itad_status)
        data, components[part] = _resolve_source(current, previous_itad[part], prior_status, previous_time, checked_at)
        itad_data[part] = data or []

    # 分发过的 ITAD 条目已是平台格式，按其真实来源恢复，避免平台或 ITAD 故障导致重复。
    snapshot = {"fetchedAt": checked_at, "sources": SOURCE_URLS, "sourceStatus": statuses}
    for key in PRIMARY_PLATFORMS:
        old = previous.get(key)
        if key == "steam":
            old = [row for row in old or [] if row.get("source") != "gamerpower"]
        elif key == "gamerpower":
            # Steam 激活活动在快照中归入 Steam，缓存按实际采集来源还原。
            old = list(old or []) + [row for row in previous.get("steam") or [] if row.get("source") == "gamerpower"]
        groups = _epic_groups(old or []) if key == "epic" else {"items": old or []}
        primary = {k: [row for row in rows if row.get("source") != "itad"] for k, rows in groups.items()}
        primary = primary if key == "epic" else primary["items"]
        old_status = previous_statuses.get(key) or {}
        prior_status = old_status.get("primary", old_status)
        # 旧抓取器曾将 GOG 付费商品及 Xbox 导航链接作为免费游戏返回。
        if key in ("gog", "xbox") and not prior_status:
            primary = None
        data, status = _resolve_source(successful.get(key), primary, prior_status, previous_time, checked_at)
        snapshot[key] = data if data is not None else ({"now": [], "upcoming": []} if key == "epic" else [])
        statuses[key] = status
        if components["deals"]["state"] != "ok":
            any_cached = False
            for group, rows in groups.items():
                cached = [row for row in rows if row.get("source") == "itad"]
                target = snapshot[key][group] if key == "epic" else snapshot[key]
                existing = {str(row.get("title", "")).strip().casefold() for row in target}
                retained = [r for r in cached if str(r.get("title", "")).strip().casefold() not in existing]
                target.extend(retained)
                any_cached |= bool(retained)
            if any_cached:
                deal_status = components["deals"]
                if deal_status["state"] == "unavailable" and previous_time and not prior_status:
                    # 早期格式把所有已知商店的折扣转移到了平台列表。
                    deal_status.update(state="cached", asOf=previous_time)
                statuses[key] = {**_combined_status([status, deal_status], checked_at), "primary": status}
    statuses["itad"] = {**_combined_status(components.values(), checked_at), "components": components}
    snapshot["itad"] = redistribute_itad_deals(
        itad_data, snapshot["epic"], snapshot["steam"], snapshot["psn"], snapshot["gog"], snapshot["xbox"]
    )
    other_giveaways = []
    for game in snapshot["gamerpower"]:
        if is_steam_giveaway(game):
            snapshot["steam"].append({**game, "source": "gamerpower", "offerType": "externalGiveaway"})
        else:
            other_giveaways.append(game)
    snapshot["gamerpower"] = other_giveaways
    return snapshot


def _china_tz() -> timezone:
    return timezone(timedelta(hours=8))


def _timestamp_cn() -> str:
    return datetime.now(_china_tz()).strftime("%Y%m%d%H%M%S")


def _canonicalize_for_hash(snapshot: Dict[str, Any]) -> Dict[str, Any]:
    """
    用于"是否变更"的去重：只保留决定性字段，避免 fetchedAt/描述变动导致重复记录。
    """
    def pick(items, fields):
        entries = [{field: item[field] for field in fields if field in item} for item in items]
        return sorted(entries, key=lambda row: json.dumps(row, ensure_ascii=False, sort_keys=True))

    platform_fields = ("id", "title", "link", "expiry", "freeStartAt", "freeEndAt", "endDate", "date",
                       "offerType", "status", "isFreeNow", "discountText", "finalPrice", "worth", "platforms")
    epic = snapshot.get("epic") or {"now": [], "upcoming": []}
    if isinstance(epic, list):
        epic = _epic_groups(epic)
    itad_fields = ("id", "title", "url", "expiry", "store", "cut", "price", "gameCount", "isPending")
    itad = _itad_parts(snapshot.get("itad") or [])
    result = {
        "epic": {group: pick(epic.get(group) or [], platform_fields) for group in ("now", "upcoming")},
        "itad": {part: pick(rows, itad_fields) for part, rows in itad.items()},
    }
    for key in PRIMARY_PLATFORMS:
        if key != "epic":
            result[key] = pick(snapshot.get(key) or [], platform_fields)
    return result


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
    if dst_root.resolve() == history_dir.resolve():
        return
    if db_path.exists():
        shutil.copy2(db_path, dst_root / "date.db")

    # records
    if src_records.exists():
        for item in src_records.iterdir():
            if item.is_file():
                shutil.copy2(item, dst_records / item.name)


def generate_feed(snapshot: Dict[str, Any], output_dir: str) -> None:
    """输出各平台和礼包的 RSS 2.0。缓存条目沿用上次成功核对时间。"""
    site_url = "https://gameinfo.gbtgame.me"
    feed = ET.Element("rss", {"version": "2.0", "xmlns:atom": "http://www.w3.org/2005/Atom"})
    channel = ET.SubElement(feed, "channel")
    for tag, value in (
        ("title", "白嫖游戏速报 | GBTGAME"), ("link", site_url),
        ("description", "各游戏平台的限免、会员游戏、礼包和外部赠送活动"), ("language", "zh-CN"),
    ):
        ET.SubElement(channel, tag).text = value
    fetched_at = snapshot.get("fetchedAt") or datetime.now(_china_tz()).isoformat()
    ET.SubElement(channel, "lastBuildDate").text = format_rss_date(datetime.fromisoformat(fetched_at.replace("Z", "+00:00")))
    ET.SubElement(channel, "atom:link", {"href": site_url + "/feed.xml", "rel": "self", "type": "application/rss+xml"})

    epic = snapshot.get("epic") or {}
    if isinstance(epic, list):
        epic = _epic_groups(epic)
    sources = [("epic", "Epic 限免", epic.get("now", [])), ("epic", "Epic 即将限免", epic.get("upcoming", []))]
    for key, label in (("steam", "Steam"), ("psn", "PlayStation"), ("gog", "GOG"), ("xbox", "Xbox"), ("gamerpower", "GamerPower")):
        sources.append((key, label, snapshot.get(key) or []))
    itad = _itad_parts(snapshot.get("itad") or [])
    sources.extend([("deals", "ITAD 折扣", itad["deals"]), ("bundles", "ITAD 礼包", itad["bundles"])])
    statuses = snapshot.get("sourceStatus") or {}
    itad_status = statuses.get("itad") or {}
    for key, label, rows in sources:
        for game in rows:
            title = game.get("title")
            link = game.get("link") or game.get("url")
            if not title or not link:
                continue
            if key in ("deals", "bundles") or game.get("source") == "itad":
                part = "bundles" if key == "bundles" else "deals"
                status = (itad_status.get("components") or {}).get(part, itad_status)
            else:
                source_status = statuses.get("gamerpower" if game.get("source") == "gamerpower" else key) or {}
                status = source_status.get("primary", source_status)
            description = game.get("description") or game.get("shortDescription") or game.get("details") or ""
            if status.get("state") == "cached":
                description = f"上次核对于 {status['asOf']}。{description}"
            timestamp = status.get("asOf") or fetched_at
            item = ET.SubElement(channel, "item")
            ET.SubElement(item, "title").text = title
            ET.SubElement(item, "link").text = link
            ET.SubElement(item, "category").text = label
            ET.SubElement(item, "description").text = str(description)[:240]
            ET.SubElement(item, "pubDate").text = format_rss_date(datetime.fromisoformat(timestamp.replace("Z", "+00:00")))
            identity = ["gamerpower" if game.get("source") == "gamerpower" else key, game.get("id") or link, title]
            guid = hashlib.sha256(json.dumps(identity, ensure_ascii=False).encode("utf-8")).hexdigest()
            ET.SubElement(item, "guid", {"isPermaLink": "false"}).text = guid
    # Merchant descriptions occasionally contain controls that XML 1.0 disallows.
    for node in feed.iter():
        if node.text:
            node.text = re.sub(r"[^\x09\x0a\x0d\x20-\ud7ff\ue000-\ufffd\U00010000-\U0010ffff]", "", node.text)
    ET.indent(feed)
    ET.ElementTree(feed).write(Path(output_dir) / "feed.xml", encoding="utf-8", xml_declaration=True)


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

    conn = open_db(history_dir)
    site_dir = Path(output_dir)
    # CI 的发布目录每次重新创建，history 分支持久保存最近一次核对结果。
    prior = _read_snapshot(history_dir / "latest.json") or _read_snapshot(site_dir / CURRENT_JSON)
    if not prior:
        history = list_snapshots(conn, limit=1)
        prior = history[0] if history else {}
    snapshot = asyncio.run(fetch_all(output_dir, previous=prior))

    print(f"Epic: {len(snapshot['epic'].get('now', []))} 正在免费, {len(snapshot['epic'].get('upcoming', []))} 即将免费")
    print(f"Steam: {len(snapshot['steam'])} 条")
    print(f"PSN: {len(snapshot['psn'])} 条")
    print(f"GOG: {len(snapshot['gog'])} 条")
    print(f"Xbox: {len(snapshot['xbox'])} 条")
    print(f"GamerPower: {len(snapshot['gamerpower'])} 条")
    itad_list = snapshot.get("itad") or []
    print(f"ITAD Giveaways: {len(itad_list)} 个")

    # 输出"本次记录"的 JSON（用于 Pages 直接访问），始终覆盖为当前快照
    serialized = json.dumps(snapshot, ensure_ascii=False, indent=2)
    for path in (site_dir / CURRENT_JSON, history_dir / "latest.json"):
        pending = path.with_suffix(".tmp")
        pending.write_text(serialized, encoding="utf-8")
        pending.replace(path)

    # 复制 logo.png 到 site 目录
    if os.path.exists("logo.png"):
        logo_dest = os.path.join(output_dir, "logo.png")
        shutil.copy2("logo.png", logo_dest)
        print(f"\nLogo 已复制到 {logo_dest}")

    # 复制验证 txt 文件到 site 目录
    txt_file = "6da64ae9f15c6a6e8149.txt"
    if os.path.exists(txt_file):
        txt_dest = os.path.join(output_dir, txt_file)
        shutil.copy2(txt_file, txt_dest)
        print(f"验证文件已复制到 {txt_dest}")

    # === 历史去重（SQLite）：仅当本次与上次不同才新增记录 ===
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
            html_content = render_html(snapshot, template_path, latest_history_ts=latest_ts, share_webp_url=None)
            Path(html_output_path).write_text(html_content, encoding="utf-8")
            print(f"\nHTML 已生成到 {html_output_path}")
        else:
            print(f"\n警告: 找不到模板文件 {template_path}，跳过 HTML 生成")

        # 生成历史图片（仅在新增历史时生成）
        try:
            from generate_image import generate_webp_from_html

            webp_path = records_dir / webp_name
            generate_webp_from_html(html_output_path, str(webp_path), 1200)
            if not webp_path.is_file():
                raise RuntimeError("未生成 WebP 文件")
            html_content = render_html(snapshot, template_path, latest_history_ts=latest_ts, share_webp_url=f"history/{image_rel}")
            Path(html_output_path).write_text(html_content, encoding="utf-8")
            print(f"\n[HISTORY] 新增历史图片: {webp_path.as_posix()}")
        except (Exception, SystemExit) as e:
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
            latest_image_rel = get_latest_image_rel(conn)
            html_content = render_html(snapshot, template_path, latest_history_ts=latest_ts, share_webp_url=f"history/{latest_image_rel}" if latest_image_rel else None)
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

    # === 生成 RSS Feed ===
    generate_feed(snapshot, output_dir)

    # === 生成 robots.txt ===
    robots_path = os.path.join(output_dir, "robots.txt")
    Path(robots_path).write_text("User-agent: *\nAllow: /\n", encoding="utf-8")
    print(f"robots.txt 已生成")

    # 将历史文件同步到 site/history 供 Pages 发布
    _sync_history_to_site(history_dir, site_dir)

    conn.close()

    # nojekyll
    (site_dir / ".nojekyll").write_text("", encoding="utf-8")

    return latest_ts, str(history_dir) if created else None


if __name__ == "__main__":
    main()
