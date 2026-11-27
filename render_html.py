#!/usr/bin/env python3
"""
生成 HTML 静态页面
"""
import html
import json
import os
import re
from datetime import datetime, timezone, timedelta
from pathlib import Path
from gamerpower_fetch import giveaway_stores, gog_store_giveaway
from typing import Any, Dict, List, Optional

MAX_SHARE_ITEMS = 4
ASSETS = Path(__file__).resolve().parent


def escape_html(text: str) -> str:
    """转义 HTML 特殊字符"""
    return html.escape(text or "")


def escape_attribute(text: str) -> str:
    """转义 HTML 属性"""
    if not text:
        return "#"
    return escape_html(text)


# ============== EPIC 新格式转换函数 ==============

def convert_epic_new_format(epic_list: List[Dict[str, Any]]) -> Dict[str, List[Dict[str, Any]]]:
    """
    将 EPIC 新格式转换为渲染所需格式
    新格式: [{"title", "status", "publisher", "creator", "description", "originalPrice", "date", "link", "cover"}]
    旧格式: {"now": [...], "upcoming": [...]}
    """
    now_list = []
    upcoming_list = []
    
    for game in epic_list:
        status = game.get("status", "")
        
        # 提取发行商和开发商
        publisher = game.get("publisher", "未知发行商")
        creator = game.get("creator", "")
        
        # 使用游戏实际的 description，如果没有则用默认值
        description = game.get("description", "") or "Epic 官方暂未提供详细介绍。"
        
        # 解析日期字符串为时间戳（毫秒）
        date_str = game.get("date", "")
        free_start_at_ms = None
        free_end_at_ms = None
        
        if date_str:
            try:
                # 解析日期
                if len(date_str.split(":")) == 2:
                    dt = datetime.strptime(date_str, "%Y/%m/%d %H:%M")
                    dt = dt.replace(second=0)
                else:
                    dt = datetime.strptime(date_str, "%Y/%m/%d %H:%M:%S")

                # 上游的无偏移日期使用北京时间。
                timestamp_ms = int(dt.replace(tzinfo=timezone(timedelta(hours=8))).timestamp() * 1000)
                
                if status == "ACTIVE":
                    free_end_at_ms = timestamp_ms
                else:  # UPCOMING
                    free_start_at_ms = timestamp_ms
            except (ValueError, TypeError):
                pass
        
        converted = {
            **game,
            "title": game.get("title", ""),
            "link": game.get("link", ""),
            "cover": game.get("cover", ""),
            "originalPriceDesc": game.get("originalPrice", ""),
            "publisher": publisher,
            "creator": creator,
            "description": description,
            "isFreeNow": status == "ACTIVE",
            "freeStartAt": game.get("freeStartAt") or free_start_at_ms,
            "freeEndAt": game.get("freeEndAt") or free_end_at_ms,
        }
        
        if status == "ACTIVE":
            now_list.append(converted)
        else:  # UPCOMING
            upcoming_list.append(converted)
    
    return {"now": now_list, "upcoming": upcoming_list}


# ============== PSN 新格式转换函数 ==============

def convert_psn_new_format(psn_list: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """
    将 PSN 新格式转换为渲染所需格式
    新格式: [{"platform", "title", "description", "originalPrice", "date", "link", "cover", "status"}]
    旧格式: [{"id", "title", "link", "image", "description", "platforms"}]
    """
    result = []
    
    for game in psn_list:
        # 新格式的字段映射
        platform = game.get("platform", "PSN")
        title = game.get("title", "")
        description = game.get("description", "")
        original_price = game.get("originalPrice", "会员免费")
        date = game.get("date", "本月有效")
        link = game.get("link", "")
        cover = game.get("cover", "")
        status = game.get("status", "ACTIVE")
        
        # 构建 highlight 文本
        if "PS Plus" in status or "Monthly" in status:
            highlight = "PS Plus 月度会员免费"
        elif status == "ACTIVE":
            highlight = "会员免费"
        else:
            highlight = status
        
        converted = {
            "id": link,
            "title": title,
            "link": link,
            "image": cover,
            "description": description,
            "highlight": highlight,
            "platforms": [platform] if platform else ["PSN"],
            "period": date,
            "originalPrice": original_price,
        }
        result.append(converted)
    
    return result


def normalize_itad_data(itad_data: Any) -> Dict[str, List[Dict[str, Any]]]:
    """兼容旧数组格式与新 dict 格式。"""
    if isinstance(itad_data, dict):
        deals = [item for item in (itad_data.get("deals") or []) if isinstance(item, dict)]
        bundles = [item for item in (itad_data.get("bundles") or []) if isinstance(item, dict)]
        return {"deals": deals, "bundles": bundles}
    if isinstance(itad_data, list):
        items = [item for item in itad_data if isinstance(item, dict)]
        return {"deals": [item for item in items if "cut" in item],
                "bundles": [item for item in items if "cut" not in item]}
    return {"deals": [], "bundles": []}


def group_itad_deals(deals: List[Dict[str, Any]]) -> List[tuple[str, List[Dict[str, Any]]]]:
    order = ["Steam", "Epic", "PlayStation", "GOG", "Xbox", "Nintendo", "Other"]
    grouped: Dict[str, List[Dict[str, Any]]] = {key: [] for key in order}

    for item in deals:
        family = item.get("storeFamily") or item.get("store") or "Other"
        family = family if family in grouped else "Other"
        grouped[family].append(item)

    return [(key, grouped[key]) for key in order if grouped[key]]


def format_full_datetime(timestamp: Optional[int] = None) -> str:
    """格式化完整日期时间（中国时区）"""
    if not timestamp:
        return "待定"
    # 将 UTC 时间戳转换为中国时区
    china_tz = timezone(timedelta(hours=8))
    dt = datetime.fromtimestamp(timestamp / 1000, tz=timezone.utc).astimezone(china_tz)
    return dt.strftime("%Y-%m-%d %H:%M")


def format_datetime(timestamp: Optional[int] = None) -> str:
    """格式化日期时间（中国时区）"""
    if not timestamp:
        return "待定"
    # 将 UTC 时间戳转换为中国时区
    china_tz = timezone(timedelta(hours=8))
    dt = datetime.fromtimestamp(timestamp / 1000, tz=timezone.utc).astimezone(china_tz)
    return dt.strftime("%m月%d日 %H:%M")


def format_date_range(start_at: Optional[int] = None, end_at: Optional[int] = None) -> str:
    """格式化日期范围（中国时区）"""
    china_tz = timezone(timedelta(hours=8))
    if start_at and end_at:
        start = datetime.fromtimestamp(start_at / 1000, tz=timezone.utc).astimezone(china_tz).strftime("%m月%d日 %H:%M")
        end = datetime.fromtimestamp(end_at / 1000, tz=timezone.utc).astimezone(china_tz).strftime("%m月%d日 %H:%M")
        return f"{start} 至 {end}"
    if end_at:
        end = datetime.fromtimestamp(end_at / 1000, tz=timezone.utc).astimezone(china_tz).strftime("%m月%d日 %H:%M")
        return f"截至 {end}"
    return "时间待定"


def format_remaining(
    target_timestamp: Optional[int] = None,
    prefix: str = "剩余",
    fallback: str = "时间待定",
    finished_text: str = "已结束",
) -> str:
    """格式化剩余时间"""
    if not target_timestamp:
        return f"{prefix} {fallback}"
    # 使用中国时区计算当前时间
    china_tz = timezone(timedelta(hours=8))
    now_ms = int(datetime.now(china_tz).timestamp() * 1000)
    diff_ms = target_timestamp - now_ms
    if diff_ms <= 0:
        return finished_text
    total_seconds = diff_ms // 1000
    days = total_seconds // 86400
    hours = (total_seconds % 86400) // 3600
    minutes = (total_seconds % 3600) // 60
    seconds = total_seconds % 60
    if days > 0:
        return f"{prefix} {days}天 {hours:02d}:{minutes:02d}:{seconds:02d}"
    if hours > 0:
        return f"{prefix} {hours:02d}:{minutes:02d}:{seconds:02d}"
    if minutes > 0:
        return f"{prefix} {minutes:02d}:{seconds:02d}"
    return f"{prefix} 00:{seconds:02d}"


def sanitize_text(value: Optional[str]) -> str:
    """清理文本"""
    if not value:
        return ""
    # 移除 HTML 标签并规范化空白
    text = re.sub(r"<[^>]*>", "", str(value))
    text = re.sub(r"\s+", " ", text)
    return text.strip()


PLATFORMS = {
    "epic": ("Epic Games", "Epic 游戏商城", "https://store.epicgames.com/zh-CN/free-games"),
    "steam": ("Steam", "Steam 商店", "https://store.steampowered.com/search/?specials=1&maxprice=free"),
    "psn": ("PlayStation", "PS Plus 香港", "https://www.playstation.com/zh-hans-hk/ps-plus/whats-new/"),
    "gog": ("GOG", "GOG 商店", "https://www.gog.com/en/games?price=free"),
    "xbox": ("Xbox", "Xbox 商店", "https://www.xbox.com/zh-hk/games"),
    "gamerpower": ("跨平台赠送", "GamerPower", "https://www.gamerpower.com/"),
    "itad": ("ITAD", "IsThereAnyDeal", "https://isthereanydeal.com/"),
}

# Labels describe the offer as reported by the source at the time of the snapshot.
OFFER_GROUPS = {
    "epic_now": ("本期限免", "在活动期间登录 Epic 账号，将游戏添加到游戏库。", "限时领取"),
    "epic_upcoming": ("即将开放", "按预计开放时间排列，具体安排以商店公告为准。", "活动预告"),
    "gog_external": ("站外领取 · GOG 兑换", "先到活动主办方领取，再按活动说明兑换到 GOG 账号。", "站外赠送"),
    "steam_external": ("站外领取 · Steam 激活", "GamerPower 收录的完整游戏赠送，领取条件和剩余名额以活动页为准。", "站外赠送"),
    "steam": ("Steam 商店限免", "游戏和追加内容均可能入选。领取追加内容前，请确认是否需要本体。", "零元优惠"),
    "psn": ("PlayStation 活动", "月度游戏需要有效的 PS Plus 会员资格，适用地区以商店为准。", "会员游戏"),
    "gog": ("GOG 商店限免", "在 GOG 商店或首页赠送横幅领取。", "商店限免"),
    "xbox": ("Xbox 活动", "收录香港 Xbox Game Pass Ultimate 主机目录近期新增的游戏以及零元优惠。会员游戏在订阅有效且仍在库时可玩。", "商店活动"),
    "gamerpower": ("跨平台赠送活动", "GamerPower 收录的完整游戏赠送。区服、账号和剩余兑换码数量以活动页为准。", "赠送活动"),
    "itad_deals": ("零元折扣", "优惠来自 IsThereAnyDeal 收录的商店。", "零元优惠"),
    "itad_bundles": ("游戏礼包与慈善包", "组合包可能需要付费，各档价格及包含内容以商店为准。", "组合包"),
}


def text_value(value):
    if isinstance(value, list):
        return " / ".join(str(part) for part in value if part)
    return sanitize_text(str(value)) if value is not None else ""


def source_url(value):
    return escape_attribute(value) if isinstance(value, str) and value.startswith(("https://", "http://")) else ""


def snapshot_time(value):
    if not value:
        return ""
    try:
        dt = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
        return dt.astimezone(timezone(timedelta(hours=8))).strftime("%Y-%m-%d %H:%M")
    except (TypeError, ValueError, OverflowError):
        return ""


def offer_timestamp(value):
    if isinstance(value, (int, float)) and value > 0:
        return int(value if value > 10 ** 11 else value * 1000)
    return None


def offer_groups(snapshot):
    epic = snapshot.get("epic") or {}
    if isinstance(epic, list):
        epic = convert_epic_new_format(epic)
    itad = normalize_itad_data(snapshot.get("itad"))
    upcoming = sorted(epic.get("upcoming") or [], key=lambda g: offer_timestamp(g.get("freeStartAt")) or float("inf"))
    giveaways = snapshot.get("gamerpower") or []
    def store_groups(store):
        rows = snapshot.get(store) or []
        direct = [game for game in rows if game.get("source") != "gamerpower"]
        external = []
        # 老快照将站外来源存入跨平台列表，包括由 GOG 自己发放的首页赠送。
        for game in [*giveaways, *(r for key in ("steam", "gog") for r in snapshot.get(key) or []
                                    if r.get("source") == "gamerpower")]:
            if store not in giveaway_stores(game):
                continue
            if store == "gog" and gog_store_giveaway(game):
                direct.append({**game, "source": "gamerpower", "offerType": "storeGiveaway"})
            else:
                external.append(game)
        groups = [(store, direct)]
        if external or "gamerpower" in snapshot:
            groups.insert(0 if external and not direct else 1, (store + "_external", external))
        return groups

    groups = {
        "epic": [("epic_now", epic.get("now") or []), ("epic_upcoming", upcoming)],
        "steam": store_groups("steam"),
        "psn": [("psn", snapshot.get("psn") or [])],
        "gog": store_groups("gog"),
        "xbox": [("xbox", snapshot.get("xbox") or [])],
        "itad": [("itad_deals", itad["deals"]), ("itad_bundles", itad["bundles"])],
    }
    if "gamerpower" in snapshot or "gamerpower" in (snapshot.get("sourceStatus") or {}):
        groups["gamerpower"] = [("gamerpower", [game for game in giveaways if not giveaway_stores(game)])]
    return groups


def render_offer(game, group, *, archived=False, for_share=False):
    platform = group.split("_")[0]
    label = OFFER_GROUPS[group][2]
    is_itad = platform == "itad" or str(game.get("source", "")).lower() == "itad"
    if is_itad and platform != "itad":
        label = "零元优惠"
    if game.get("offerType") == "subscription":
        label = "会员游戏"
    if game.get("isPending"):
        label = "活动预告"
    img_url = source_url(game.get("poster") or game.get("headerImage") or game.get("cover") or game.get("image"))
    art = ""
    if img_url:
        art = (f'<img src="{img_url}" alt="" loading="lazy" decoding="async" '
               'onload="if(this.naturalWidth > this.naturalHeight * 1.35){'
               'this.parentElement.classList.add(&quot;wide&quot;);'
               'this.parentElement.style.setProperty(&quot;--art-image&quot;, &quot;url(&quot; + JSON.stringify(this.currentSrc) + &quot;)&quot;);}" '
               'onerror="this.hidden=true">')
    imprint = {"epic": "Epic", "steam": "Steam", "psn": "PS Plus", "xbox": "Xbox", "gog": "GOG",
               "itad": "ITAD", "gamerpower": "GP"}[platform]
    title = escape_html(text_value(game.get("storeTitle") or game.get("title")) or "未命名活动")
    start = offer_timestamp(game.get("freeStartAt"))
    end = offer_timestamp(game.get("freeEndAt") or game.get("expiry"))
    start_label = f"开放 {format_full_datetime(start)}" if start else ""
    end_label = f"截止 {format_full_datetime(end)}" if end else ""
    period = text_value(game.get("period") or game.get("date"))
    external = platform == "gamerpower" or group.endswith("_external") or game.get("source") == "gamerpower"
    if external and game.get("endDate"):
        period = f"截止 {text_value(game['endDate'])}（来源未注明时区）"
    unknown_window = "离库时间未公布" if label == "会员游戏" and platform == "xbox" else "截止时间未公布"
    window = "　".join(part for part in (start_label, end_label) if part) or period or unknown_window
    timer = ""
    if not archived:
        target = start if group == "epic_upcoming" else end
        if target:
            prefix, finish = ("距开放", "已到开放时间") if group == "epic_upcoming" else ("剩余", "已过截止时间")
            timer = (f'<span class="timer" data-countdown-target="{target}" data-countdown-prefix="{prefix}" '
                     f'data-countdown-finished="{finish}">{format_remaining(target, prefix=prefix, finished_text=finish)}</span>')
    description = text_value(game.get("shortDescription") or game.get("description") or game.get("details"))
    origin = game.get("originalPriceDesc") or game.get("originalPrice") or game.get("regularPrice")
    price = text_value(origin)
    if game.get("regularCurrency") and game.get("regularPrice") is not None:
        price = f"{game['regularPrice']} {game['regularCurrency']}"
    if price and platform == "epic" and re.fullmatch(r"\d+(\.\d+)?", price):
        price = f"¥{price}"
    facts = []
    for name, value in [
        ("商店", game.get("store")),
        ("原价", price), ("现价", game.get("finalPrice") or game.get("price")),
        ("参考价值", game.get("worth")), ("地区", {"CN": "中国大陆", "HK": "中国香港"}.get(game.get("region"), game.get("region"))),
        ("内容", f"{game['gameCount']} 款游戏" if game.get("gameCount") else ""),
        ("设备", game.get("platforms")), ("类型", game.get("genres")),
        ("发行商", game.get("publisher") or game.get("publishers")),
    ]:
        value = text_value(value)
        if value and value not in ("未知", "会员免费"):
            facts.append(f'<div><dt>{name}</dt><dd>{escape_html(value)}</dd></div>')
    more = []
    reviews = game.get("reviews") or {}
    for name, value in [
        ("开发商", game.get("creator") or game.get("developers")),
        ("发行日期", game.get("releaseDate")), ("商店标签", game.get("steamTags")),
        ("玩家评测", reviews.get("all") if isinstance(reviews, dict) else ""),
        ("语言", game.get("languages")),
        ("特性", [f for f in (game.get("features") or []) if isinstance(f, str) and "\n" not in f][:5]),
        ("激活平台", game.get("drm")), ("领取步骤", game.get("instructions")),
    ]:
        if value:
            more.append(f'<div><dt>{name}</dt><dd>{escape_html(text_value(value))}</dd></div>')
    if len(description) > 140:
        more.insert(0, f'<div><dt>完整简介</dt><dd>{escape_html(description)}</dd></div>')
        description = re.sub(r"(?<=\s)[a-zA-Z]+$", "", description[:135]).rstrip() + "…"
    detail = (f'<details class="more"><summary>{"领取步骤与资料" if external and game.get("instructions") else "更多游戏资料"}</summary><dl class="facts">{"".join(more)}</dl></details>' if more else "")
    url = source_url(game.get("link") or game.get("url"))
    action = {"itad_bundles": "查看礼包", "steam_external": "查看领取条件", "gamerpower": "查看领取条件"}.get(group, "查看商店")
    if group == "gog_external":
        action = "查看领取条件"
    if group == "gog" and game.get("offerType") == "storeGiveaway":
        url = source_url(game.get("claimUrl")) or "https://www.gog.com/en/#giveaway"
        action, label = "去 GOG 领取", "商店限免" if game.get("claimUrl") else "首页赠送"
    button = f'<a class="store-link" href="{url}" target="_blank" rel="noopener noreferrer">{action}<span aria-hidden="true"> ↗</span></a>' if url else ""
    source = "GamerPower" if external else PLATFORMS[platform][0]
    byline = '<a href="https://isthereanydeal.com/" target="_blank" rel="noopener noreferrer">IsThereAnyDeal</a>' if is_itad else escape_html(source)
    if external and platform in ("steam", "gog"):
        byline = f'<a href="{source_url(game.get("link"))}" target="_blank" rel="noopener noreferrer">GamerPower</a>'
    if for_share:
        return {"title": html.unescape(title), "platform": imprint, "primary": label + " · " + ("IsThereAnyDeal" if is_itad else source),
                "secondary": window, "description": description, "coverUrl": html.unescape(img_url)}
    tone = "upcoming" if label == "活动预告" else "member" if label == "会员游戏" else "bundle" if group == "itad_bundles" else "available"
    heading = f'<a href="{url}" target="_blank" rel="noopener noreferrer">{title}</a>' if url else title
    return f"""<article class="offer">
        <div class="art" aria-hidden="true" data-platform="{platform}"><span>{imprint}</span>{art}</div>
        <div class="offer-copy"><div class="offer-byline"><span class="condition {tone}">{label}</span><span>{byline}</span></div>
        <h3>{heading}</h3><div class="window">{escape_html(window)}{timer}</div>{f'<p class="description">{escape_html(description)}</p>' if description else ''}
        {f'<dl class="facts">{"".join(facts)}</dl>' if facts else ''}
        <div class="offer-foot">{detail}{button}</div></div></article>"""


def render_source(snapshot, platform):
    _, name, official_url = PLATFORMS[platform]
    status = (snapshot.get("sourceStatus") or {}).get(platform) or {}
    state = status.get("state")
    status_text = {"ok": "已更新", "cached": "沿用上次记录", "unavailable": "此次未能获取"}.get(state, "")
    component_states = {item.get("state") for item in (status.get("components") or {}).values()}
    if len(component_states) > 1:
        status_text = "部分数据沿用上次记录" if "cached" in component_states and "unavailable" not in component_states else "部分数据未能获取"
    stamp = snapshot_time(status.get("asOf") if state == "cached" else status.get("checkedAt"))
    source = (snapshot.get("sources") or {}).get(platform)
    source = source_url(source)
    links = f'<a href="{source_url(official_url)}" target="_blank" rel="noopener noreferrer">{name} ↗</a>'
    if source and source != source_url(official_url):
        links += f'<a href="{source}" target="_blank" rel="noopener noreferrer">数据来源 ↗</a>'
    return f'<div class="source"><span>{escape_html(" ".join(x for x in (status_text, stamp) if x))}</span>{links}</div>'


def render_group(key, items, status, archived=False):
    status = status or {}
    component = (status.get("components") or {}).get(key.removeprefix("itad_")) or {}
    state = component.get("state", status.get("state"))
    freshness = {"ok": "已更新", "unavailable": "此次未能获取", "cached": "沿用上次记录"}.get(component.get("state"), "")
    if key.endswith("_external"):
        freshness = {"cached": "沿用上次记录", "unavailable": "此次未能获取"}.get(state, "")
        component = status
    if freshness:
        stamp = snapshot_time(component.get("asOf") if state == "cached" else component.get("checkedAt"))
        freshness = f'<span class="component-state">{freshness} {escape_html(stamp)}</span>'

    heading, note, _ = OFFER_GROUPS[key]
    alerts = {"unavailable": "此次未能获取该来源的数据，请前往来源页面核实。", "cached": "上次可用记录中没有收录此类活动。"}
    empty = alerts.get(state, "本次记录中没有收录此类活动。")
    body = "".join(render_offer(item, key, archived=archived) for item in items)
    return (f'<section class="offer-group"><header><h2>{heading}<small>{len(items)} 项</small></h2>'
            f'<p>{note}{freshness}</p></header>{body or f"""<p class="empty">{empty}</p>"""}</section>')


def get_share_client_script() -> str:
    """绑定来源导航、分享下载和倒计时。"""
    return """(function() {
  'use strict';

  // =========================
  // 倒计时（以截止时间计算）
  // =========================
  const countdownNodes = Array.from(document.querySelectorAll('[data-countdown-target]'));
  const pad2 = (n) => String(n).padStart(2, '0');
  const formatCountdown = (diffMs) => {
    if (diffMs <= 0) return '';
    const totalSeconds = Math.floor(diffMs / 1000);
    const days = Math.floor(totalSeconds / 86400);
    const hours = Math.floor((totalSeconds % 86400) / 3600);
    const minutes = Math.floor((totalSeconds % 3600) / 60);
    const seconds = totalSeconds % 60;
    if (days > 0) {
      return `${days}天 ${pad2(hours)}:${pad2(minutes)}:${pad2(seconds)}`;
    }
    return `${pad2(hours)}:${pad2(minutes)}:${pad2(seconds)}`;
  };

  const updateCountdowns = () => {
    if (!countdownNodes.length) {
      console.warn('Countdown: no nodes found');
      return;
    }
    const now = Date.now();
    countdownNodes.forEach((node) => {
      const targetRaw = node.getAttribute('data-countdown-target');
      if (!targetRaw) return;
      const target = Number(targetRaw);
      if (!Number.isFinite(target)) return;
      const prefix = node.getAttribute('data-countdown-prefix') || '剩余';
      const finished = node.getAttribute('data-countdown-finished') || '已结束';
      const diff = target - now;
      if (diff <= 0) {
        node.textContent = finished;
        node.classList.remove('countdown-tick');
        return;
      }
      const body = formatCountdown(diff);
      node.textContent = body ? `${prefix} ${body}` : finished;

    });
  };

  if (countdownNodes.length) {
    updateCountdowns();
    setInterval(updateCountdowns, 1000);
  }

  const shareButton = document.querySelector('[data-share-button]');
  const tabs = Array.from(document.querySelectorAll('.epic-freebies__tab'));
  const panels = Array.from(document.querySelectorAll('.epic-freebies__panel'));

  let sharePayload = null;
  const payloadNode = document.getElementById('share-payload');
  if (payloadNode) {
    try {
      const raw = (payloadNode.textContent || payloadNode.innerText || '').trim();
      if (raw) {
        sharePayload = JSON.parse(raw);
      }
    } catch (error) {
      console.error('Failed to parse share payload', error);
    }
  }

  const hasArchiveImage = shareButton && shareButton.getAttribute('href') !== '#';
  if (sharePayload && shareButton && !hasArchiveImage) {
    shareButton.setAttribute('download', sharePayload.suggestedFileName || 'GBTGame限免拼图.png');
  }

  if (shareButton && !hasArchiveImage) {
    const originalLabel = (shareButton.textContent || '').trim() || '生成分享拼图';
    shareButton.dataset.originalLabel = originalLabel;

    const hasSections = Boolean(
      sharePayload &&
        Array.isArray(sharePayload.sections) &&
        sharePayload.sections.length > 0,
    );

    if (!hasSections) {
      shareButton.setAttribute('aria-disabled', 'true');
      shareButton.setAttribute('tabindex', '-1');
    } else {
      shareButton.addEventListener('click', function(event) {
        event.preventDefault();
        if (shareButton.dataset.generating === 'true') {
          return;
        }
        generateShareImage(sharePayload, shareButton).catch(function(error) {
          console.error(error);
        });
      });
    }
  }

  async function generateShareImage(payload, button) {
    button.dataset.generating = 'true';
    const originalLabel = button.dataset.originalLabel || button.textContent || '生成分享拼图';
    button.textContent = '生成中...';

    try {
      if (document.fonts && document.fonts.ready) {
        try {
          await document.fonts.ready;
        } catch (fontError) {
          console.debug('Font readiness wait failed', fontError);
        }
      }

      const canvas = await renderGamePoster(payload);
      const blob = await new Promise((resolve, reject) => canvas.toBlob(
        result => result ? resolve(result) : reject(new Error('图片导出失败')), 'image/webp', 0.9));
      await triggerDownload(blob, payload.suggestedFileName);
      button.textContent = '已生成';
      setTimeout(function() {
        button.textContent = originalLabel;
      }, 1600);
    } catch (error) {
      console.error('Failed to generate share puzzle', error);
      button.textContent = '生成失败';
      setTimeout(function() {
        button.textContent = originalLabel;
      }, 2000);
    } finally {
      button.dataset.generating = 'false';
      button.blur();
    }
  }

  function triggerDownload(blob, fileName) {
    return new Promise(function(resolve) {
      const url = URL.createObjectURL(blob);
      const anchor = document.createElement('a');
      anchor.href = url;
      anchor.download = fileName || 'GBTGame限免拼图.png';
      anchor.rel = 'noopener';
      anchor.style.display = 'none';
      document.body.appendChild(anchor);
      anchor.click();
      setTimeout(function() {
        document.body.removeChild(anchor);
        URL.revokeObjectURL(url);
        resolve();
      }, 0);
    });
  }

  function switchTab(targetKey) {
    tabs.forEach(function(tab) {
      const isActive = tab.getAttribute('data-tab') === targetKey;
      tab.classList.toggle('is-active', isActive);
      tab.setAttribute('aria-selected', String(isActive));
      tab.tabIndex = isActive ? 0 : -1;
    });
    panels.forEach(function(panel) {
      const isActive = panel.getAttribute('data-panel') === targetKey;
      panel.classList.toggle('is-active', isActive);
      panel.classList.toggle('hidden', !isActive);
    });
  }

  tabs.forEach(function(tab, index) {
    tab.addEventListener('keydown', function(event) {
      const offsets = {ArrowRight: 1, ArrowDown: 1, ArrowLeft: -1, ArrowUp: -1};
      let next;
      if (event.key in offsets) next = (index + offsets[event.key] + tabs.length) % tabs.length;
      else if (event.key === 'Home') next = 0;
      else if (event.key === 'End') next = tabs.length - 1;
      else return;
      event.preventDefault();
      switchTab(tabs[next].dataset.tab);
      tabs[next].focus();
    });
    tab.addEventListener('click', function() {
      const key = tab.getAttribute('data-tab');
      if (!key || tab.classList.contains('is-active')) {
        return;
      }
      switchTab(key);
    });
  });

})();"""



def build_share_payload(snapshot: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    from generate_image import poster_branding
    sections = []
    for platform, groups in offer_groups(snapshot).items():
        for group, items in groups:
            if not items:
                continue
            title = OFFER_GROUPS[group][0]
            if platform in ("epic", "itad"):
                title = PLATFORMS[platform][0] + " · " + title
            sections.append({"title": title, "items": [
                render_offer(game, group, archived=True, for_share=True) for game in items[:MAX_SHARE_ITEMS]
            ]})
    if not sections:
        return None
    stamp = snapshot_time(snapshot.get("fetchedAt"))
    return {**poster_branding(), "generatedAtDisplay": stamp, "sections": sections,
            "totalItems": sum(len(s["items"]) for s in sections),
            "suggestedFileName": "游戏活动速报-" + stamp.replace(":", "").replace(" ", "-") + ".webp"}


def serialize_for_client(payload: Optional[Dict[str, Any]]) -> str:
    """序列化分享数据为客户端 JSON"""
    if not payload:
        return "null"
    json_str = json.dumps(payload, ensure_ascii=False)
    # 转义特殊字符
    json_str = json_str.replace("<", "\\u003C")
    json_str = json_str.replace("\u2028", "\\u2028")
    json_str = json_str.replace("\u2029", "\\u2029")
    return json_str


def render_html(snapshot: Dict[str, Any], template_path: str, latest_history_ts: str | None = None, share_webp_url: str | None = None) -> str:
    template = Path(template_path).read_text(encoding="utf-8")
    groups = offer_groups(snapshot)
    counts = {key: sum(len(items) for _, items in sections) for key, sections in groups.items()}
    statuses = snapshot.get("sourceStatus") or {}
    selected = next((key for key, count in counts.items() if count and (statuses.get(key) or {}).get("state") == "ok"),
                    next((key for key, count in counts.items() if count), "epic"))
    tabs, panels = [], []
    for key, sections in groups.items():
        name = PLATFORMS[key][0]
        active = key == selected
        tabs.append(f'<button id="tab-{key}" class="epic-freebies__tab{" is-active" if active else ""}" role="tab" '
                    f'aria-selected="{str(active).lower()}" aria-controls="free-panel-{key}" data-tab="{key}" tabindex="{0 if active else -1}">'
                    f'<span>{name}</span><b>{counts[key]}</b></button>')
        status = (snapshot.get("sourceStatus") or {}).get(key) or {}
        contents = [render_group(group, items, statuses.get("gamerpower") if group.endswith("_external") else status) for group, items in sections]
        panels.append(f'<div class="epic-freebies__panel{"" if active else " hidden"}" id="free-panel-{key}" role="tabpanel" '
                      f'aria-labelledby="tab-{key}" data-panel="{key}"><div class="panel-source"><strong>{name}</strong>'
                      f'{render_source(snapshot, key)}</div>{"".join(contents)}</div>')

    payload = build_share_payload(snapshot)
    links = ['<a href="history/date.db">历史数据库</a>', '<a href="白嫖信息.json">本期 JSON</a>']
    if latest_history_ts and share_webp_url:
        links.append(f'<a href="{escape_attribute(share_webp_url)}">本期归档图</a>')
    values = {
        "FETCHED_AT": escape_html(snapshot_time(snapshot.get("fetchedAt")) or "等待同步"),
        "TOTAL_COUNT": str(sum(counts.values())),
        "PLATFORM_TABS": "".join(tabs), "PLATFORM_PANELS": "".join(panels),
        "SHARE_BUTTON_LABEL": "下载分享图" if share_webp_url else "生成分享图",
        "SHARE_BUTTON_URL": escape_attribute(share_webp_url or "#"),
        "SHARE_BUTTON_FILENAME": escape_attribute(Path(share_webp_url).name if share_webp_url else ((payload or {}).get("suggestedFileName") or "限免速报.png")),
        "SHARE_BUTTON_DISABLED": "" if payload or share_webp_url else 'aria-disabled="true" tabindex="-1"',
        "SHARE_DATA_JSON": serialize_for_client(payload),
        "CLIENT_SCRIPT": (ASSETS / "share-render.js").read_text() + "\n" + get_share_client_script(), "ARCHIVE_LINKS": "".join(links),
    }
    return re.sub(r"\{\{([A-Z_]+)\}\}", lambda match: values[match[1]], template)


def _extract_style_block(template: str) -> str:
    m = re.search(r"<style>[\s\S]*?</style>", template)
    return m.group(0) if m else "<style></style>"


def render_history_page(records: list[dict[str, Any]], *, template_path: str, base_title: str = "历史记录 | 白嫖游戏信息") -> str:
    template = Path(template_path).read_text(encoding="utf-8")
    style = _extract_style_block(template)
    blocks = []
    for snap in records:
        groups = offer_groups(snap)
        count = sum(len(items) for sections in groups.values() for _, items in sections)
        blocks.append(f'<details class="record"><summary><strong>{escape_html(snapshot_time(snap.get("fetchedAt")) or "日期待定")}</strong><span>{count} 项活动</span></summary>')
        if snap.get("archiveImage"):
            blocks.append(f'<p class="archive-download"><a class="share-button" href="{escape_attribute(snap["archiveImage"])}" download>下载这期分享图</a></p>')
        for key, sections in groups.items():
            blocks.append(f'<section class="archive-platform"><div class="panel-source"><strong>{PLATFORMS[key][0]}</strong>{render_source(snap, key)}</div>')
            status = (snap.get("sourceStatus") or {}).get(key) or {}
            for group, items in sections:
                group_status = (snap.get("sourceStatus") or {}).get("gamerpower") if group.endswith("_external") else status
                blocks.append(render_group(group, items, group_status, archived=True))
            blocks.append('</section>')
        blocks.append('</details>')
    detail = "".join(blocks) or '<p class="empty">暂无历史记录。</p>'
    return f"""<!DOCTYPE html><html lang="zh-CN"><head><meta charset="UTF-8"><meta name="viewport" content="width=device-width, initial-scale=1">
    <title>{escape_html(base_title)}</title><link rel="icon" href="../logo.png"><link rel="alternate" type="application/rss+xml" href="../feed.xml">
    <script data-cfasync="false" async crossorigin="anonymous" src="https://pagead2.googlesyndication.com/pagead/js/adsbygoogle.js?client=ca-pub-9956808351564739"></script>{style}</head>
    <body><header class="top"><div class="wrap"><a class="brand" href="../"><img width="28" height="28" src="../logo.png" alt="">GBTGAME</a>
    <nav aria-label="站点导航"><a href="../">活动速报</a><a aria-current="page" href="./">历史归档</a><a href="../feed.xml">RSS 订阅</a></nav></div></header>
    <main class="wrap archive"><div class="mast"><div><h1>历史归档</h1><p>展开抓取记录，查看当时收录的活动、价格与领取期限。</p></div></div>
    <div class="archive-heading"><h2>按时间浏览</h2><span>最近 {len(records)} 条记录・北京时间</span></div>{detail}</main>
    <footer class="wrap"><a href="../">返回活动速报</a><a href="date.db">下载历史数据库</a></footer></body></html>"""


def main():
    """主函数"""
    import sys

    snapshot_file = sys.argv[1] if len(sys.argv) > 1 else "snapshot.json"
    template_file = (
        sys.argv[2]
        if len(sys.argv) > 2
        else "epic-freebies.html.template"
    )
    output_file = sys.argv[3] if len(sys.argv) > 3 else "index.html"

    if not os.path.exists(snapshot_file):
        print(f"错误: 找不到快照文件 {snapshot_file}")
        sys.exit(1)

    if not os.path.exists(template_file):
        print(f"错误: 找不到模板文件 {template_file}")
        sys.exit(1)

    with open(snapshot_file, "r", encoding="utf-8") as f:
        snapshot = json.load(f)

    html_content = render_html(snapshot, template_file)

    with open(output_file, "w", encoding="utf-8") as f:
        f.write(html_content)

    print(f"HTML 已生成到 {output_file}")


if __name__ == "__main__":
    main()
