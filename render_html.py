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
from typing import Any, Dict, List, Optional

# 常量 - Red Hacker Brutalist Style
SHARE_CANVAS_WIDTH = 1080
SHARE_PADDING = 48
SHARE_TITLE_BLOCK_HEIGHT = 200
SHARE_SECTION_GAP = 64
SHARE_CARD_HEIGHT = 180
SHARE_CARD_GAP = 16
SHARE_CARD_RADIUS = 0
SHARE_CARD_INSET = 16
SHARE_COVER_WIDTH = 200
SHARE_COVER_RADIUS = 0
MAX_SHARE_ITEMS = 4
SHARE_FONT_FAMILY = "Noto Sans SC"


def escape_html(text: str) -> str:
    """转义 HTML 特殊字符"""
    return html.escape(text)


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
                    # 如果没有秒，设置为当天的 23:59
                    dt = dt.replace(hour=23, minute=59, second=0)
                else:
                    dt = datetime.strptime(date_str, "%Y/%m/%d %H:%M:%S")
                    dt = dt.replace(second=0)
                
                # 转换为 UTC 时间戳（毫秒）
                timestamp_ms = int(dt.timestamp() * 1000)
                
                if status == "ACTIVE":
                    free_end_at_ms = timestamp_ms
                else:  # UPCOMING
                    free_start_at_ms = timestamp_ms
            except Exception:
                pass
        
        converted = {
            "title": game.get("title", ""),
            "link": game.get("link", ""),
            "cover": game.get("cover", ""),
            "originalPriceDesc": game.get("originalPrice", ""),
            "publisher": publisher,
            "creator": creator,
            "description": description,
            "isFreeNow": status == "ACTIVE",
            "freeStartAt": free_start_at_ms,
            "freeEndAt": free_end_at_ms,
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


def render_epic_card(game: Dict[str, Any], variant: str) -> str:
    """渲染 Epic 游戏卡片"""
    summary = []
    
    # 发行商 (publisher)
    publisher = game.get("publisher", "")
    if publisher:
        summary.append(f"发行：{publisher}")
    
    # 开发商 (creator)
    creator = game.get("creator", "")
    if creator and creator != publisher:
        summary.append(f"开发：{creator}")
    
    genres = game.get("genres")
    if genres:
        summary.append(f"类型：{' / '.join(genres)}")
    platforms = game.get("platforms")
    if platforms:
        summary.append(f"平台：{' / '.join(platforms)}")
    elif game.get("platform"):
        summary.append(f"平台：{game['platform']}")

    primary_timer = "活动时间待定"
    secondary_timer = ""

    is_free_now = game.get("isFreeNow", False)
    free_end_at = game.get("freeEndAt")
    free_start_at = game.get("freeStartAt")
    
    # 使用中国时区计算当前时间
    china_tz = timezone(timedelta(hours=8))
    now_ms = int(datetime.now(china_tz).timestamp() * 1000)

    if is_free_now and free_end_at:
        primary_timer = format_remaining(
            free_end_at, prefix="剩余", finished_text="已结束"
        )
        secondary_timer = f"截止：{format_datetime(free_end_at)}"
    elif free_start_at and free_start_at > now_ms:
        primary_timer = format_remaining(
            free_start_at, prefix="距离开放还剩", finished_text="已开放"
        )
        if free_end_at:
            window_text = f"{format_datetime(free_start_at)} - {format_datetime(free_end_at)}"
        else:
            window_text = format_datetime(free_start_at)
        secondary_timer = f"限免窗口：{window_text}"
    elif free_start_at or free_end_at:
        primary_timer = f"活动时间：{format_date_range(free_start_at, free_end_at)}"

    deadline_text = (
        secondary_timer
        or (f"截止：{format_datetime(free_end_at)}" if free_end_at else "")
        or (
            f"开始：{format_datetime(free_start_at)}"
            if variant == "upcoming" and free_start_at
            else "截止时间待定"
        )
    )

    price_label = game.get("originalPriceDesc") or game.get("originalPrice") or "未知"
    cover = game.get("cover", "")
    cover_html = (
        f'<img src="{escape_attribute(cover)}" alt="{escape_attribute(game["title"])}" loading="lazy">'
        if cover
        else '<span>暂无封面</span>'
    )

    link_text = "立即抢夺"
    description = (game.get("description") or "Epic 官方暂未提供详细介绍。").strip()

    summary_html = ""
    if summary:
        summary_inner = escape_html("</span><span class=\"bg-zinc-800 px-3 py-1\">".join(summary))
        summary_html = f'<div class="flex flex-wrap gap-4 text-[10px] font-bold text-zinc-400 italic"><span class="bg-zinc-800 px-3 py-1">{summary_inner}</span></div>'

    # 倒计时：默认使用截止时间（freeEndAt），没有则退化为 freeStartAt（仅用于展示）
    countdown_target_ms: Optional[int] = None
    if isinstance(free_end_at, (int, float)):
        countdown_target_ms = int(free_end_at)
    elif isinstance(free_start_at, (int, float)):
        countdown_target_ms = int(free_start_at)

    countdown_attrs = ""
    countdown_text = escape_html(primary_timer)
    if countdown_target_ms:
        countdown_prefix = "剩余"
        countdown_finished = "已结束"
        countdown_attrs = (
            f' data-countdown-target="{countdown_target_ms}"'
            f' data-countdown-prefix="{escape_attribute(countdown_prefix)}"'
            f' data-countdown-finished="{escape_attribute(countdown_finished)}"'
        )
        countdown_text = f'<span class="countdown-tick"{countdown_attrs}>{countdown_text}</span>'
    else:
        countdown_text = f'<span>{countdown_text}</span>'

    return f"""<article class="relative flex flex-col lg:flex-row gap-8 bg-zinc-950 border-[6px] border-zinc-800 p-6 lg:p-10 transform hover:-rotate-1 transition-transform group">
    <!-- GET corner badge -->
    <div class="absolute -top-4 -right-4 w-16 h-16 bg-white text-black flex items-center justify-center rotate-12 font-black text-xl shadow-[4px_4px_0_0_#d10000] z-20 group-hover:bg-red-600 group-hover:text-white transition-colors">GET</div>

    <!-- Cover image -->
    <div class="lg:w-2/5 relative">
        <div class="border-[8px] border-white shadow-2xl overflow-hidden aspect-video">
            {cover_html}
        </div>
        <div class="absolute -bottom-4 -left-4 bg-red-600 text-white px-6 py-2 font-black italic shadow-[6px_6px_0_0_#fff]">原价 {escape_html(price_label)}</div>
    </div>

    <!-- Content -->
    <div class="lg:w-3/5 flex flex-col justify-between py-2">
        <h4 class="text-3xl font-black italic mb-4 tracking-tighter uppercase">{escape_html(game["title"])}</h4>
        <p class="text-zinc-500 text-sm leading-relaxed mb-6 border-l-4 border-zinc-800 pl-4">{escape_html(description)}</p>
        {summary_html}
        <div class="mt-6 flex flex-col sm:flex-row items-start sm:items-center justify-between gap-4 border-t-2 border-dashed border-zinc-800 pt-4">
            <div class="flex flex-col gap-1">
                <span class="text-2xl font-black text-red-600 italic">{countdown_text}</span>
                <span class="text-[10px] text-zinc-500 font-bold uppercase">{escape_html(deadline_text)}</span>
            </div>
            <a href="{escape_attribute(game["link"])}" class="bg-white text-black px-12 py-4 font-black transform -skew-x-12 hover:bg-red-600 hover:text-white transition-all shadow-[6px_6px_0_0_#d10000] text-sm uppercase" target="_blank" rel="noopener noreferrer">{link_text}</a>
        </div>
    </div>
</article>"""


def render_steam_card(game: Dict[str, Any]) -> str:
    """渲染 Steam 游戏卡片"""
    summary = []
    if game.get("releaseDate"):
        summary.append(f"发行：{game['releaseDate']}")
    platforms = game.get("platforms", [])
    if platforms:
        summary.append(f"平台：{' / '.join(platforms)}")

    discount_text = game.get("discountText")
    final_price = game.get("finalPrice")
    if discount_text:
        price_text = f"折扣：{discount_text}"
        if final_price:
            price_text += f" · 现价 {final_price}"
    elif final_price:
        price_text = f"现价 {final_price}"
    else:
        price_text = "折扣信息：待定"

    price_parts = []
    if game.get("originalPrice"):
        price_parts.append(f"原价 {game['originalPrice']}")
    if final_price:
        price_parts.append(f"现价 {final_price}")
    price_detail = " → ".join(price_parts) if price_parts else "价格信息暂缺"

    cover = game.get("image", "")
    cover_html = (
        f'<img src="{escape_attribute(cover)}" alt="{escape_attribute(game["title"] + " 封面")}" loading="lazy">'
        if cover
        else '<span>暂无封面</span>'
    )

    description = (game.get("reviewSummary") or "限免详情请前往 Steam 商店页查看。").strip()

    summary_html = ""
    if summary:
        summary_inner = escape_html("</span><span class=\"bg-zinc-800 px-3 py-1\">".join(summary))
        summary_html = f'<div class="flex flex-wrap gap-4 text-[10px] font-bold text-zinc-400 italic"><span class="bg-zinc-800 px-3 py-1">{summary_inner}</span></div>'

    return f"""<article class="relative flex flex-col lg:flex-row gap-8 bg-zinc-950 border-[6px] border-zinc-800 p-6 lg:p-10 transform hover:-rotate-1 transition-transform group">
    <!-- GET corner badge -->
    <div class="absolute -top-4 -right-4 w-16 h-16 bg-white text-black flex items-center justify-center rotate-12 font-black text-xl shadow-[4px_4px_0_0_#d10000] z-20 group-hover:bg-red-600 group-hover:text-white transition-colors">GET</div>

    <!-- Cover image -->
    <div class="lg:w-2/5 relative">
        <div class="border-[8px] border-white shadow-2xl overflow-hidden aspect-video">
            {cover_html}
        </div>
        <div class="absolute -bottom-4 -left-4 bg-red-600 text-white px-6 py-2 font-black italic shadow-[6px_6px_0_0_#fff]">Steam 限免</div>
    </div>

    <!-- Content -->
    <div class="lg:w-3/5 flex flex-col justify-between py-2">
        <h4 class="text-3xl font-black italic mb-4 tracking-tighter uppercase">{escape_html(game["title"])}</h4>
        <p class="text-zinc-500 text-sm leading-relaxed mb-6 border-l-4 border-zinc-800 pl-4">{escape_html(description)}</p>
        {summary_html}
        <div class="mt-6 flex flex-col sm:flex-row items-start sm:items-center justify-between gap-4 border-t-2 border-dashed border-zinc-800 pt-4">
            <div class="flex flex-col gap-1">
                <span class="text-2xl font-black text-red-600 italic">{escape_html(price_text)}</span>
                <span class="text-[10px] text-zinc-500 font-bold uppercase">{escape_html(price_detail)}</span>
            </div>
            <a href="{escape_attribute(game["link"])}" class="bg-white text-black px-12 py-4 font-black transform -skew-x-12 hover:bg-red-600 hover:text-white transition-all shadow-[6px_6px_0_0_#d10000] text-sm uppercase" target="_blank" rel="noopener noreferrer">立即抢夺</a>
        </div>
    </div>
</article>"""


def render_psn_card(game: Dict[str, Any]) -> str:
    """渲染 PlayStation 游戏卡片"""
    # 兼容新旧格式（新格式用 cover，旧格式用 image）
    cover = game.get("cover") or game.get("image", "")
    cover_html = (
        f'<img src="{escape_attribute(cover)}" alt="{escape_attribute(game["title"])}" loading="lazy">'
        if cover
        else '<span>暂无封面</span>'
    )

    # 组装 meta 行：highlight + 平台 + 领取时间，全部在同一行
    meta_items = []
    highlight = escape_html(game.get("highlight", "PS Plus 会员免费"))
    if highlight:
        meta_items.append(f'<span class="font-black text-red-600 italic">{highlight}</span>')
    if game.get("platforms"):
        platforms = game["platforms"]
        if isinstance(platforms, list):
            platforms = " / ".join(platforms)
        meta_items.append(
            f'<span class="bg-zinc-800 px-3 py-1 text-[10px] font-bold text-zinc-400 italic">{escape_html(str(platforms))}</span>'
        )
    if game.get("period"):
        meta_items.append(
            f'<span class="bg-zinc-800 px-3 py-1 text-[10px] font-bold text-zinc-400 italic">领取：{escape_html(game["period"])}</span>'
        )
    meta_html = f'<div class="flex flex-wrap gap-x-4 gap-y-2 items-center">{"".join(meta_items)}</div>'

    description = (game.get("description") or "当前仍在同步 PlayStation 官方描述。").strip()

    return f"""<article class="relative flex flex-col lg:flex-row gap-8 bg-zinc-950 border-[6px] border-zinc-800 p-6 lg:p-10 transform hover:-rotate-1 transition-transform group">
    <!-- GET corner badge -->
    <div class="absolute -top-4 -right-4 w-16 h-16 bg-white text-black flex items-center justify-center rotate-12 font-black text-xl shadow-[4px_4px_0_0_#d10000] z-20 group-hover:bg-red-600 group-hover:text-white transition-colors">GET</div>

    <!-- Cover image -->
    <div class="lg:w-2/5 relative">
        <div class="border-[8px] border-white shadow-2xl overflow-hidden aspect-video">
            {cover_html}
        </div>
        <div class="absolute -bottom-4 -left-4 bg-red-600 text-white px-6 py-2 font-black italic shadow-[6px_6px_0_0_#fff]">PlayStation</div>
    </div>

    <!-- Content -->
    <div class="lg:w-3/5 flex flex-col justify-between py-2">
        <h4 class="text-3xl font-black italic mb-4 tracking-tighter uppercase">{escape_html(game["title"])}</h4>
        <p class="text-zinc-500 text-sm leading-relaxed mb-4 border-l-4 border-zinc-800 pl-4 line-clamp-2">{escape_html(description)}</p>
        {meta_html}
        <div class="mt-6 flex items-center justify-end border-t-2 border-dashed border-zinc-800 pt-4">
            <a href="{escape_attribute(game["link"])}" class="bg-white text-black px-12 py-4 font-black transform -skew-x-12 hover:bg-red-600 hover:text-white transition-all shadow-[6px_6px_0_0_#d10000] text-sm uppercase" target="_blank" rel="noopener noreferrer">立即抢夺</a>
        </div>
    </div>
</article>"""


def render_epic_section_content(items: List[Dict[str, Any]], empty_text: str, variant: str) -> str:
    """渲染 Epic 区块内容"""
    if not items:
        return f'<div class="py-16 lg:py-20 px-10 border border-dashed border-zinc-700 text-center text-zinc-500 bg-zinc-950 leading-relaxed">{escape_html(empty_text)}</div>'
    # All epic cards use the same featured horizontal style for desktop readability
    # variant controls layout: "now"=1-col featured, "upcoming"=2-col featured
    grid_class = "grid grid-cols-1 gap-12" if variant == "now" else "grid grid-cols-1 xl:grid-cols-2 gap-10"
    cards = "\n".join(render_epic_card(item, variant) for item in items)
    return f'<div class="{grid_class}">\n{cards}\n</div>'


def render_steam_section_content(items: List[Dict[str, Any]], empty_text: str) -> str:
    """渲染 Steam 区块内容"""
    if not items:
        return f'<div class="py-16 lg:py-20 px-10 border border-dashed border-zinc-700 text-center text-zinc-500 bg-zinc-950 leading-relaxed">{escape_html(empty_text)}</div>'
    # Steam cards use featured horizontal style, 2-col on xl screens
    cards = "\n".join(render_steam_card(item) for item in items)
    return f'<div class="grid grid-cols-1 xl:grid-cols-2 gap-10">\n{cards}\n</div>'


def render_psn_section_content(items: List[Dict[str, Any]], empty_text: str) -> str:
    """渲染 PlayStation 区块内容"""
    if not items:
        return f'<div class="py-16 lg:py-20 px-10 border border-dashed border-zinc-700 text-center text-zinc-500 bg-zinc-950 leading-relaxed">{escape_html(empty_text)}</div>'
    # PSN cards use featured horizontal style, 2-col on xl screens
    cards = "\n".join(render_psn_card(item) for item in items)
    return f'<div class="grid grid-cols-1 xl:grid-cols-2 gap-10">\n{cards}\n</div>'


def render_itad_card(game: Dict[str, Any]) -> str:
    """渲染 ITAD Giveaway 卡片（使用与其他平台一致的横向 Featured 风格）"""
    # 计算剩余时间
    expiry = game.get("expiry")
    china_tz = timezone(timedelta(hours=8))
    now_ts = int(datetime.now(china_tz).timestamp())  # Unix seconds

    if expiry:
        diff = expiry - now_ts
        if diff > 0:
            total_seconds = diff
            days = total_seconds // 86400
            hours = (total_seconds % 86400) // 3600
            minutes = (total_seconds % 3600) // 60
            seconds = total_seconds % 60
            if days > 0:
                remaining_text = f"剩余 {days} 天 {hours:02d}:{minutes:02d}:{seconds:02d}"
            elif hours > 0:
                remaining_text = f"剩余 {hours:02d}:{minutes:02d}:{seconds:02d}"
            else:
                remaining_text = f"剩余 {minutes:02d}:{seconds:02d}"
            expiry_display = datetime.fromtimestamp(expiry, tz=china_tz).strftime("%m月%d日 %H:%M")
        else:
            remaining_text = "已过期"
            expiry_display = datetime.fromtimestamp(expiry, tz=china_tz).strftime("%m月%d日 %H:%M") if expiry else "已过期"
    else:
        remaining_text = "时间待定"
        expiry_display = "截止时间待定"

    store = game.get("store", "ITAD")
    game_count = game.get("gameCount", 0)
    game_count_text = f"{game_count} 款游戏" if game_count else "游戏数量待定"

    is_pending = game.get("isPending", False)
    is_mature = game.get("isMature", False)

    if is_pending:
        badge_text = "待生效"
    elif is_mature:
        badge_text = "MATURE"
    else:
        badge_text = "ITAD"

    # 使用与其他平台一致的横向 Featured 风格
    countdown_target_ms = expiry * 1000 if expiry else None
    countdown_attrs = ""
    countdown_text = escape_html(remaining_text)
    if countdown_target_ms:
        countdown_attrs = (
            f' data-countdown-target="{countdown_target_ms}"'
            f' data-countdown-prefix="剩余"'
            f' data-countdown-finished="已结束"'
        )
        countdown_text = f'<span class="countdown-tick"{countdown_attrs}>{countdown_text}</span>'
    else:
        countdown_text = f'<span>{countdown_text}</span>'

    return f"""<article class="relative flex flex-col lg:flex-row gap-8 bg-zinc-950 border-[6px] border-zinc-800 p-6 lg:p-10 transform hover:-rotate-1 transition-transform group">
    <!-- GET corner badge -->
    <div class="absolute -top-4 -right-4 w-16 h-16 bg-white text-black flex items-center justify-center rotate-12 font-black text-xl shadow-[4px_4px_0_0_#d10000] z-20 group-hover:bg-red-600 group-hover:text-white transition-colors">{escape_html(badge_text)}</div>

    <!-- Store info (left side, replacing cover) -->
    <div class="lg:w-2/5 flex flex-row items-center justify-center gap-3 bg-zinc-900 border-[8px] border-white shadow-2xl aspect-video">
        <span class="text-red-600 font-black text-xl lg:text-2xl italic">{escape_html(store)}</span>
        <span class="text-zinc-500 text-xs lg:text-sm">{escape_html(game_count_text)}</span>
        <span class="text-[10px] text-zinc-600 font-bold italic uppercase">FROM ITAD</span>
    </div>

    <!-- Content -->
    <div class="lg:w-3/5 flex flex-col justify-between py-2">
        <h4 class="text-3xl font-black italic mb-4 tracking-tighter uppercase">{escape_html(game["title"])}</h4>
        <p class="text-zinc-500 text-sm leading-relaxed mb-4 border-l-4 border-zinc-800 pl-4 line-clamp-2">ITAD Bundle Giveaway · {escape_html(game_count_text)}</p>
        <div class="mt-6 flex flex-col sm:flex-row items-start sm:items-center justify-between gap-4 border-t-2 border-dashed border-zinc-800 pt-4">
            <div class="flex flex-col gap-1">
                <span class="text-xl font-black text-red-600 italic leading-tight">{countdown_text} · 截止 {escape_html(expiry_display)}</span>
            </div>
            <a href="{escape_attribute(game["url"])}" class="bg-white text-black px-12 py-4 font-black transform -skew-x-12 hover:bg-red-600 hover:text-white transition-all shadow-[6px_6px_0_0_#d10000] text-sm uppercase" target="_blank" rel="noopener noreferrer">ITAD 查看</a>
        </div>
    </div>
</article>"""


def render_itad_section_content(items: List[Dict[str, Any]], empty_text: str) -> str:
    """渲染 ITAD Giveaways 区块内容"""
    if not items:
        return f'<div class="py-16 lg:py-20 px-10 border border-dashed border-zinc-700 text-center text-zinc-500 bg-zinc-950 leading-relaxed">{escape_html(empty_text)}</div>'
    # ITAD uses horizontal layout, 2-col on xl screens
    cards = "\n".join(render_itad_card(item) for item in items)
    return f'<div class="grid grid-cols-1 xl:grid-cols-2 gap-10">\n{cards}\n</div>'


def get_share_client_script() -> str:
    """获取分享客户端脚本（完整版本）- Red Hacker Brutalist Style"""
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
      node.classList.remove('countdown-tick');
      void node.offsetWidth;
      node.classList.add('countdown-tick');
    });
  };

  updateCountdowns();
  setInterval(updateCountdowns, 1000);

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

  if (sharePayload && shareButton) {
    shareButton.setAttribute('download', sharePayload.suggestedFileName || 'GBTGame限免拼图.png');
  }

  if (shareButton) {
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

      const blob = await renderShareCanvas(payload, null);
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

  async function renderShareCanvas(payload, qrCodeDataUrl) {
    const config = payload.config;
    const sections = payload.sections;
    const height = measureCanvasHeight(sections, config);

    const canvas = document.createElement('canvas');
    canvas.width = config.width;
    canvas.height = height;

    const ctx = canvas.getContext('2d');
    if (!ctx) {
      throw new Error('Canvas 2D context is unavailable');
    }

    ctx.textBaseline = 'top';

    // === BLACK BACKGROUND ===
    ctx.fillStyle = '#000000';
    ctx.fillRect(0, 0, config.width, height);

    // === WHITE DOT GRID PATTERN ===
    const dotSpacing = 28;
    const dotRadius = 1;
    ctx.fillStyle = 'rgba(255, 255, 255, 0.15)';
    for (let x = dotSpacing / 2; x < config.width; x += dotSpacing) {
      for (let y = dotSpacing / 2; y < height; y += dotSpacing) {
        ctx.beginPath();
        ctx.arc(x, y, dotRadius, 0, Math.PI * 2);
        ctx.fill();
      }
    }

    // === TITLE BLOCK ===
    let cursorY = config.padding;

    // Red bar at top (6px)
    ctx.fillStyle = '#d10000';
    ctx.fillRect(0, 0, config.width, 6);

    // White title: "白嫖游戏速报" in bold 52px
    ctx.fillStyle = '#ffffff';
    ctx.font = font(config.fontWeights.bold, 52, config.fontFamily);
    ctx.fillText('白嫖游戏速报', config.padding, cursorY);
    cursorY += 64;

    // Gray subtitle
    ctx.fillStyle = '#888888';
    ctx.font = font(config.fontWeights.regular, 18, config.fontFamily);
    ctx.fillText('GBTGAME FREEBIES · EPIC · STEAM · PSN · ITAD', config.padding, cursorY);
    cursorY += 28;

    // Timestamp line
    ctx.fillStyle = '#666666';
    ctx.font = font(config.fontWeights.light, 14, config.fontFamily);
    ctx.fillText(
      'GENERATED: ' + payload.generatedAtDisplay + ' · ' + payload.totalItems + ' ITEMS',
      config.padding,
      cursorY,
    );
    cursorY = config.padding + config.titleBlockHeight;

    // === SECTIONS ===
    const cardWidth = config.width - config.padding * 2;

    for (let sectionIndex = 0; sectionIndex < sections.length; sectionIndex += 1) {
      const section = sections[sectionIndex];

      // Section header: red vertical bar + white uppercase bold
      ctx.fillStyle = '#d10000';
      ctx.fillRect(config.padding, cursorY, 4, 40);

      ctx.fillStyle = '#ffffff';
      ctx.font = font(config.fontWeights.bold, 32, config.fontFamily);
      ctx.fillText(section.title.toUpperCase(), config.padding + 16, cursorY + 32);
      cursorY += 56;

      // Draw items
      for (let itemIndex = 0; itemIndex < section.items.length; itemIndex += 1) {
        if (itemIndex > 0) {
          cursorY += config.cardGap;
        }
        if (section.type === 'itad') {
          await drawItadCard(ctx, section.items[itemIndex], config, config.padding, cursorY, cardWidth);
        } else {
          await drawCard(ctx, section.items[itemIndex], config, config.padding, cursorY, cardWidth);
        }
        cursorY += config.cardHeight;
      }

      if (sectionIndex !== sections.length - 1) {
        cursorY += config.sectionGap;
      }
    }

    // === FOOTER WITH QR CODE ===
    const footerHeight = 160;
    cursorY = height - footerHeight;

    // Black footer bar
    ctx.fillStyle = '#000000';
    ctx.fillRect(0, cursorY, config.width, footerHeight);

    // White top border 6px
    ctx.fillStyle = '#ffffff';
    ctx.fillRect(0, cursorY, config.width, 6);

    // Red accent bar on left side of footer
    ctx.fillStyle = '#d10000';
    ctx.fillRect(0, cursorY, 8, footerHeight);

    // Draw QR code at bottom center
    if (qrCodeDataUrl) {
      const qrSize = config.qrSize || 100;
      const qrX = (config.width - qrSize) / 2;
      const qrY = cursorY + 16;

      const qrImg = new Image();
      await new Promise(function(resolve, reject) {
        qrImg.onload = resolve;
        qrImg.onerror = reject;
        qrImg.src = qrCodeDataUrl;
      });
      ctx.drawImage(qrImg, qrX, qrY, qrSize, qrSize);
    }

    // Text below QR
    const qrSize = config.qrSize || 100;
    ctx.fillStyle = '#ffffff';
    ctx.font = font(config.fontWeights.regular, 14, config.fontFamily);
    ctx.textAlign = 'center';
    ctx.fillText(
      '扫描获取最新限免 · GBTGAME.ME',
      config.width / 2,
      cursorY + qrSize + 32,
    );
    ctx.textAlign = 'left';

    return await new Promise(function(resolve, reject) {
      canvas.toBlob(
        function(result) {
          if (result) {
            resolve(result);
          } else {
            reject(new Error('Failed to export share canvas'));
          }
        },
        'image/png',
        0.92,
      );
    });
  }

  function measureCanvasHeight(sections, config) {
    const footerHeight = 160;
    let total = config.padding * 2 + config.titleBlockHeight;
    for (let i = 0; i < sections.length; i += 1) {
      const section = sections[i];
      total += 56; // section header
      total += section.items.length * config.cardHeight;
      if (section.items.length > 1) {
        total += (section.items.length - 1) * config.cardGap;
      }
      if (i !== sections.length - 1) {
        total += config.sectionGap;
      }
    }
    total += footerHeight;
    return Math.ceil(total);
  }

  async function drawCard(ctx, item, config, x, y, width) {
    // BLACK CARD with WHITE 4px border (NO rounded corners)
    ctx.fillStyle = '#0a0a0a';
    ctx.fillRect(x, y, width, config.cardHeight);
    ctx.strokeStyle = '#ffffff';
    ctx.lineWidth = 4;
    ctx.strokeRect(x, y, width, config.cardHeight);

    const coverX = x + config.cardInset;
    const coverY = y + config.cardInset;
    const coverHeight = config.cardHeight - config.cardInset * 2;
    const coverWidth = config.coverWidth;

    // Cover with WHITE 4px border, no radius
    ctx.strokeStyle = '#ffffff';
    ctx.lineWidth = 4;
    ctx.strokeRect(coverX, coverY, coverWidth, coverHeight);

    // Load and draw cover image
    const coverImage = await loadCover(item.coverUrl);
    if (coverImage) {
      const scale = Math.max(
        coverWidth / coverImage.width,
        coverHeight / coverImage.height,
      );
      const drawWidth = coverImage.width * scale;
      const drawHeight = coverImage.height * scale;
      const dx = coverX + (coverWidth - drawWidth) / 2;
      const dy = coverY + (coverHeight - drawHeight) / 2;
      ctx.save();
      ctx.beginPath();
      ctx.rect(coverX, coverY, coverWidth, coverHeight);
      ctx.clip();
      ctx.drawImage(coverImage, dx, dy, drawWidth, drawHeight);
      ctx.restore();
    } else {
      ctx.fillStyle = '#1a1a1a';
      ctx.fillRect(coverX, coverY, coverWidth, coverHeight);
      ctx.fillStyle = '#444444';
      ctx.font = font(config.fontWeights.regular, 14, config.fontFamily);
      ctx.textAlign = 'center';
      ctx.fillText('NO IMAGE', coverX + coverWidth / 2, coverY + coverHeight / 2);
      ctx.textAlign = 'left';
    }

    // Content area (right side, 60%)
    const textX = coverX + coverWidth + config.cardInset;
    const textWidth = x + width - config.cardInset - textX;
    let cursorY = y + config.cardInset;

    // Title: white bold italic 22px uppercase
    ctx.fillStyle = '#ffffff';
    ctx.font = font(config.fontWeights.bold, 22, config.fontFamily);
    ctx.fillText(item.title.toUpperCase(), textX, cursorY);
    cursorY += 30;

    // Description: gray 14px, max 2 lines
    if (item.description) {
      cursorY = drawWrappedText(ctx, item.description, {
        x: textX,
        y: cursorY,
        width: textWidth,
        lineHeight: 20,
        font: font(config.fontWeights.regular, 14, config.fontFamily),
        color: '#888888',
        maxLines: 2,
      });
      cursorY += 4;
    }

    // Price tag: red background #d10000 with white text
    if (item.tertiary) {
      const priceText = '原价 ' + item.tertiary;
      ctx.fillStyle = '#d10000';
      const priceWidth = ctx.measureText(priceText).width + 16;
      ctx.fillRect(textX, cursorY, priceWidth, 24);
      ctx.fillStyle = '#ffffff';
      ctx.font = font(config.fontWeights.regular, 12, config.fontFamily);
      ctx.fillText(priceText, textX + 8, cursorY + 16);
      cursorY += 32;
    }

    // Timer: red bold italic 20px
    if (item.primary) {
      ctx.fillStyle = '#d10000';
      ctx.font = font(config.fontWeights.bold, 20, config.fontFamily);
      ctx.fillText(item.primary, textX, cursorY);
      cursorY += 28;
    }

    // CTA button: white background, black text
    const btnText = '立即抢夺';
    ctx.fillStyle = '#ffffff';
    const btnWidth = 120;
    const btnHeight = 32;
    ctx.fillRect(textX, cursorY, btnWidth, btnHeight);
    ctx.fillStyle = '#000000';
    ctx.font = font(config.fontWeights.bold, 14, config.fontFamily);
    ctx.fillText(btnText, textX + 12, cursorY + 22);
  }

  async function drawItadCard(ctx, item, config, x, y, width) {
    // ITAD CARD - no cover, left side store info
    const halfWidth = width / 2;

    // BLACK CARD with WHITE 4px border
    ctx.fillStyle = '#0a0a0a';
    ctx.fillRect(x, y, width, config.cardHeight);
    ctx.strokeStyle = '#ffffff';
    ctx.lineWidth = 4;
    ctx.strokeRect(x, y, width, config.cardHeight);

    // Left side: store name in large red bold
    ctx.fillStyle = '#d10000';
    ctx.font = font(config.fontWeights.bold, 28, config.fontFamily);
    ctx.fillText((item.secondary || 'ITAD').toUpperCase(), x + config.cardInset, y + config.cardInset + 28);

    // Game count below
    if (item.tertiary) {
      ctx.fillStyle = '#888888';
      ctx.font = font(config.fontWeights.regular, 14, config.fontFamily);
      ctx.fillText(item.tertiary, x + config.cardInset, y + config.cardInset + 52);
    }

    // "FROM ITAD" label
    ctx.fillStyle = '#666666';
    ctx.font = font(config.fontWeights.regular, 12, config.fontFamily);
    ctx.fillText('FROM ITAD', x + config.cardInset, y + config.cardInset + 72);

    // Right side: title, timer, CTA
    const textX = x + halfWidth + config.cardInset;
    const textWidth = halfWidth - config.cardInset * 2;
    let cursorY = y + config.cardInset;

    // Title: white bold uppercase
    ctx.fillStyle = '#ffffff';
    ctx.font = font(config.fontWeights.bold, 18, config.fontFamily);
    ctx.fillText(item.title.toUpperCase(), textX, cursorY);
    cursorY += 26;

    // Timer: red bold italic
    if (item.primary) {
      ctx.fillStyle = '#d10000';
      ctx.font = font(config.fontWeights.bold, 18, config.fontFamily);
      ctx.fillText(item.primary, textX, cursorY);
      cursorY += 26;
    }

    // CTA button
    const btnText = '立即抢夺';
    ctx.fillStyle = '#ffffff';
    const btnWidth = 100;
    const btnHeight = 28;
    ctx.fillRect(textX, cursorY, btnWidth, btnHeight);
    ctx.fillStyle = '#000000';
    ctx.font = font(config.fontWeights.bold, 12, config.fontFamily);
    ctx.fillText(btnText, textX + 8, cursorY + 18);
  }

  async function loadCover(url) {
    if (!url) {
      return null;
    }
    try {
      const image = new Image();
      image.crossOrigin = 'anonymous';
      image.decoding = 'async';
      const result = await new Promise(function(resolve, reject) {
        image.onload = function() {
          resolve(image);
        };
        image.onerror = function() {
          reject(new Error('Image load failed'));
        };
        image.src = url;
      });
      return result;
    } catch (error) {
      console.debug('Share cover load failed', error);
      return null;
    }
  }

  function drawWrappedText(ctx, text, options) {
    if (!text) {
      return options.y;
    }
    ctx.font = options.font;
    ctx.fillStyle = options.color;
    ctx.textAlign = 'left';

    const lines = wrapText(ctx, text, options.width, options.maxLines);
    let cursor = options.y;
    for (let i = 0; i < lines.length; i += 1) {
      ctx.fillText(lines[i], options.x, cursor);
      cursor += options.lineHeight;
    }
    return cursor;
  }

  function wrapText(ctx, text, maxWidth, maxLines) {
    if (!text) {
      return [];
    }
    const normalized = text.replace(/\\s+/g, ' ').trim();
    if (!normalized) {
      return [];
    }
    const characters = Array.from(normalized);
    const lines = [];
    let current = '';

    for (let i = 0; i < characters.length; i += 1) {
      const candidate = current + characters[i];
      if (ctx.measureText(candidate).width > maxWidth && current) {
        lines.push(current);
        current = characters[i];
      } else {
        current = candidate;
      }
    }
    if (current) {
      lines.push(current);
    }

    if (typeof maxLines === 'number' && maxLines > 0 && lines.length > maxLines) {
      const truncated = lines.slice(0, maxLines);
      let lastLine = truncated[maxLines - 1];
      while (
        lastLine.length > 0 &&
        ctx.measureText(lastLine + '…').width > maxWidth
      ) {
        lastLine = lastLine.slice(0, -1);
      }
      truncated[maxLines - 1] = lastLine ? lastLine + '…' : '…';
      return truncated;
    }

    return lines;
  }

  function font(weight, size, family) {
    return weight + ' ' + size + 'px ' + family;
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
    });
    panels.forEach(function(panel) {
      const isActive = panel.getAttribute('data-panel') === targetKey;
      panel.classList.toggle('is-active', isActive);
      panel.classList.toggle('hidden', !isActive);
    });
  }

  tabs.forEach(function(tab) {
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
    """构建分享数据"""
    sections = []
    
    # 处理 EPIC 数据（兼容新旧格式）
    epic_data = snapshot.get("epic", {})
    if isinstance(epic_data, list):
        # 新格式：扁平数组，需要转换
        epic_converted = convert_epic_new_format(epic_data)
        epic_now = epic_converted["now"]
        epic_upcoming = epic_converted["upcoming"]
    else:
        # 旧格式：字典包含 now/upcoming
        epic_now = epic_data.get("now", [])
        epic_upcoming = epic_data.get("upcoming", [])
    
    steam = snapshot.get("steam", [])
    
    # 处理 PSN 数据（兼容新旧格式）
    psn_data = snapshot.get("psn", [])
    if psn_data and isinstance(psn_data, list) and len(psn_data) > 0:
        first_psn = psn_data[0] if psn_data else {}
        if "cover" in first_psn or "status" in first_psn:
            psn = convert_psn_new_format(psn_data)
        else:
            psn = psn_data
    else:
        psn = []

    if epic_now:
        sections.append(
            {
                "title": "EPIC 正在免费",
                "items": [
                    map_epic_share_item(item, "now")
                    for item in epic_now[:MAX_SHARE_ITEMS]
                ],
            }
        )
    if epic_upcoming:
        sections.append(
            {
                "title": "EPIC 即将免费",
                "items": [
                    map_epic_share_item(item, "upcoming")
                    for item in epic_upcoming[:MAX_SHARE_ITEMS]
                ],
            }
        )
    if steam:
        sections.append(
            {
                "title": "Steam 限免精选",
                "items": [
                    map_steam_share_item(item) for item in steam[:MAX_SHARE_ITEMS]
                ],
            }
        )
    if psn:
        sections.append(
            {
                "title": "PlayStation 会员福利",
                "items": [
                    map_psn_share_item(item) for item in psn[:MAX_SHARE_ITEMS]
                ],
            }
        )

    itad = snapshot.get("itad", [])
    if itad:
        sections.append(
            {
                "title": "ITAD Bundle Giveaways",
                "type": "itad",
                "items": [
                    map_itad_share_item(item) for item in itad[:MAX_SHARE_ITEMS]
                ],
            }
        )

    if not sections:
        return None

    fetched_at = snapshot.get("fetchedAt")
    if fetched_at:
        dt = datetime.fromisoformat(fetched_at.replace("Z", "+00:00"))
        generated_at_timestamp = int(dt.timestamp() * 1000)
    else:
        # 使用中国时区
        china_tz = timezone(timedelta(hours=8))
        generated_at_timestamp = int(datetime.now(china_tz).timestamp() * 1000)

    total_items = sum(len(section["items"]) for section in sections)

    # 使用中国时区生成文件名
    china_tz = timezone(timedelta(hours=8))
    suggested_file_name = f"GBTGame限免拼图-{datetime.now(china_tz).strftime('%Y%m%d-%H%M')}.webp"

    return {
        "generatedAtDisplay": format_full_datetime(generated_at_timestamp),
        "generatedAtTimestamp": generated_at_timestamp,
        "totalItems": total_items,
        "suggestedFileName": suggested_file_name,
        "sections": sections,
        "config": {
            "width": SHARE_CANVAS_WIDTH,
            "padding": SHARE_PADDING,
            "titleBlockHeight": SHARE_TITLE_BLOCK_HEIGHT,
            "sectionGap": SHARE_SECTION_GAP,
            "cardHeight": SHARE_CARD_HEIGHT,
            "cardGap": SHARE_CARD_GAP,
            "cardRadius": SHARE_CARD_RADIUS,
            "cardInset": SHARE_CARD_INSET,
            "coverWidth": SHARE_COVER_WIDTH,
            "coverRadius": SHARE_COVER_RADIUS,
            "fontWeights": {"light": 300, "regular": 400, "semibold": 600, "bold": 900},
            "fontFamily": f'"{SHARE_FONT_FAMILY}","Microsoft YaHei","PingFang SC","Heiti SC",sans-serif',
            "qrSize": 100,
            "qrMargin": 6,
        },
    }


def map_epic_share_item(game: Dict[str, Any], variant: str) -> Dict[str, Any]:
    """映射 Epic 分享项"""
    primary = "活动时间待定"
    secondary = ""

    is_free_now = game.get("isFreeNow", False)
    free_end_at = game.get("freeEndAt")
    free_start_at = game.get("freeStartAt")

    if is_free_now and free_end_at:
        primary = format_remaining(free_end_at, prefix="剩余", finished_text="已结束")
        secondary = f"截止：{format_datetime(free_end_at)}"
    elif variant == "upcoming" and free_start_at:
        primary = format_remaining(
            free_start_at, prefix="距离开放还剩", finished_text="已开放"
        )
        if free_end_at:
            secondary = f"限免窗口：{format_datetime(free_start_at)} - {format_datetime(free_end_at)}"
        else:
            secondary = f"开始：{format_datetime(free_start_at)}"
    elif free_start_at or free_end_at:
        primary = f"活动时间：{format_date_range(free_start_at, free_end_at)}"

    price = game.get("originalPriceDesc") or game.get("originalPrice") or ""
    platforms = game.get("platforms", [])
    platform_text = " / ".join(filter(None, platforms)) if platforms else ""
    
    # 获取发行商和开发商
    publisher = game.get("publisher", "")
    creator = game.get("creator", "")

    tertiary_parts = []
    if price:
        tertiary_parts.append(f"原价 {price}")
    if publisher:
        tertiary_parts.append(f"发行 {publisher}")
    if creator and creator != publisher:
        tertiary_parts.append(f"开发 {creator}")
    if platform_text:
        tertiary_parts.append(f"平台 {platform_text}")

    return {
        "title": sanitize_text(game.get("title", "")),
        "primary": primary,
        "secondary": secondary,
        "tertiary": " · ".join(tertiary_parts),
        "description": sanitize_text(game.get("description", "")),
        "coverUrl": game.get("cover"),
    }


def map_steam_share_item(game: Dict[str, Any]) -> Dict[str, Any]:
    """映射 Steam 分享项"""
    discount = (
        f"折扣 {sanitize_text(game.get('discountText', ''))}"
        if game.get("discountText")
        else "折扣信息：待定"
    )
    price = (
        f"现价 {sanitize_text(game.get('finalPrice', ''))}"
        if game.get("finalPrice")
        else ""
    )

    tertiary_parts = []
    if game.get("originalPrice"):
        tertiary_parts.append(f"原价 {sanitize_text(game['originalPrice'])}")
    if game.get("releaseDate"):
        tertiary_parts.append(f"发行 {sanitize_text(game['releaseDate'])}")
    platforms = game.get("platforms", [])
    if platforms:
        tertiary_parts.append(f"平台 {sanitize_text(' / '.join(platforms))}")

    return {
        "title": sanitize_text(game.get("title", "")),
        "primary": discount,
        "secondary": price,
        "tertiary": " · ".join(tertiary_parts),
        "description": sanitize_text(game.get("reviewSummary", "")),
        "coverUrl": game.get("image"),
    }


def map_psn_share_item(game: Dict[str, Any]) -> Dict[str, Any]:
    """映射 PlayStation 分享项"""
    tertiary_parts = []
    if game.get("platforms"):
        tertiary_parts.append(f"平台 {sanitize_text(game['platforms'])}")

    # 兼容新旧格式（新格式用 cover，旧格式用 image）
    cover_url = game.get("cover") or game.get("image", "")

    return {
        "title": sanitize_text(game.get("title", "")),
        "primary": sanitize_text(game.get("highlight", "PS Plus 会员福利")),
        "secondary": (
            f"可领取时间：{sanitize_text(game['period'])}" if game.get("period") else ""
        ),
        "tertiary": " · ".join(tertiary_parts),
        "description": sanitize_text(game.get("description", "")),
        "coverUrl": cover_url,
    }


def map_itad_share_item(game: Dict[str, Any]) -> Dict[str, Any]:
    """映射 ITAD 分享项"""
    expiry = game.get("expiry")
    china_tz = timezone(timedelta(hours=8))
    now_ts = int(datetime.now(china_tz).timestamp())

    if expiry:
        diff = expiry - now_ts
        if diff > 0:
            total_seconds = diff
            days = total_seconds // 86400
            hours = (total_seconds % 86400) // 3600
            minutes = (total_seconds % 3600) // 60
            seconds = total_seconds % 60
            if days > 0:
                primary = f"剩余 {days} 天 {hours:02d}:{minutes:02d}:{seconds:02d}"
            elif hours > 0:
                primary = f"剩余 {hours:02d}:{minutes:02d}:{seconds:02d}"
            else:
                primary = f"剩余 {minutes:02d}:{seconds:02d}"
        else:
            primary = "已过期"
    else:
        primary = "时间待定"

    return {
        "title": sanitize_text(game.get("title", "")),
        "primary": primary,
        "secondary": f"来自 {sanitize_text(game.get('store', 'ITAD'))}",
        "tertiary": f"{game.get('gameCount', 0)} 款游戏",
        "description": "",
        "coverUrl": "",
        "store": sanitize_text(game.get("store", "ITAD")),
        "gameCount": game.get("gameCount", 0),
    }


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
    """渲染 HTML"""
    with open(template_path, "r", encoding="utf-8") as f:
        template = f.read()

    fetched_at = snapshot.get("fetchedAt")
    if fetched_at:
        try:
            dt = datetime.fromisoformat(fetched_at.replace("Z", "+00:00"))
            fetched_at_display = format_full_datetime(int(dt.timestamp() * 1000))
        except Exception:
            fetched_at_display = "等待同步"
    else:
        fetched_at_display = "等待同步"
    
    # 历史记录 URL（Pages）
    latest_image_url = ""
    if latest_history_ts:
        latest_image_url = f"history/records/{latest_history_ts}白嫖信息.webp"

    # 处理 EPIC 数据（兼容新旧格式）
    epic_data = snapshot.get("epic", {})
    if isinstance(epic_data, list):
        # 新格式：扁平数组，需要转换
        epic_converted = convert_epic_new_format(epic_data)
        epic_now = epic_converted["now"]
        epic_upcoming = epic_converted["upcoming"]
    else:
        # 旧格式：字典包含 now/upcoming
        epic_now = epic_data.get("now", [])
        epic_upcoming = epic_data.get("upcoming", [])
    
    # 处理 PSN 数据（兼容新旧格式）
    psn_data = snapshot.get("psn", [])
    if psn_data and isinstance(psn_data, list) and len(psn_data) > 0:
        # 检查是否是新格式（新格式第一个元素通常有 status 字段）
        first_psn = psn_data[0] if psn_data else {}
        if "cover" in first_psn or "status" in first_psn:
            # 新格式：扁平数组
            psn = convert_psn_new_format(psn_data)
        else:
            # 旧格式
            psn = psn_data
    else:
        psn = []

    steam = snapshot.get("steam", [])
    itad = snapshot.get("itad", [])

    epic_now_count = len(epic_now)
    epic_upcoming_count = len(epic_upcoming)
    steam_count = len(steam)
    psn_count = len(psn)
    itad_count = len(itad)
    epic_total_count = epic_now_count + epic_upcoming_count
    total_count = epic_total_count + steam_count + psn_count + itad_count

    share_payload = build_share_payload(snapshot)
    share_ready = share_payload is not None
    share_data_json = serialize_for_client(share_payload)
    share_script = get_share_client_script()
    
    # 页脚链接：历史页 + 最新归档（如有）
    links: list[str] = []
    links.append('<span>历史记录：<a href="history/" target="_blank" rel="noopener noreferrer">查看</a></span>')
    links.append('<span>数据库：<a href="history/date.db" target="_blank" rel="noopener noreferrer">date.db</a></span>')
    links.append('<span>本次记录：<a href="白嫖信息.json" target="_blank" rel="noopener noreferrer">JSON</a></span>')
    if latest_image_url:
        links.append(
            '<span>最新归档：'
            f'<a href="{escape_attribute(latest_image_url)}" target="_blank" rel="noopener noreferrer">图片</a>'
            "</span>"
        )
    archive_links = "".join(links)

    replacements = {
        "FETCHED_AT": escape_html(fetched_at_display),
        "TOTAL_COUNT": str(total_count),
        "TAB_BADGE_EPIC": str(epic_total_count),
        "TAB_BADGE_STEAM": str(steam_count),
        "TAB_BADGE_PSN": str(psn_count),
        "EPIC_NOW_COUNT": str(epic_now_count),
        "EPIC_UPCOMING_COUNT": str(epic_upcoming_count),
        "STEAM_COUNT": str(steam_count),
        "PSN_COUNT": str(psn_count),
        "ITAD_COUNT": str(itad_count),
        "TAB_BADGE_ITAD": str(itad_count),
        "EPIC_NOW_CONTENT": render_epic_section_content(
            epic_now, "当前暂无正在进行的限免活动。", "now"
        ),
        "EPIC_UPCOMING_CONTENT": render_epic_section_content(
            epic_upcoming, "暂无即将开始的官方限免活动。", "upcoming"
        ),
        "STEAM_CONTENT": render_steam_section_content(
            steam, "暂未检测到 Steam 官方限免活动，请稍后再试。"
        ),
        "PSN_CONTENT": render_psn_section_content(
            psn, "暂未检测到 PlayStation 公布的会员免费游戏。"
        ),
        "ITAD_CONTENT": render_itad_section_content(
            itad, "暂未检测到 ITAD Bundle Giveaways。"
        ),
        "SHARE_BUTTON_DISABLED": (
            "" if share_ready else ' aria-disabled="true" tabindex="-1"'
        ),
        "SHARE_BUTTON_LABEL": "下载分享图片" if share_webp_url else ("生成分享拼图" if share_ready else "分享数据未就绪"),
        "SHARE_BUTTON_FILENAME": escape_attribute(
            (share_payload.get("suggestedFileName") if share_payload else None)
            or "GBTGame限免拼图.webp"
        ),
        "SHARE_BUTTON_URL": escape_attribute(share_webp_url or "#"),
        "SHARE_DATA_JSON": share_data_json,
        "CLIENT_SCRIPT": share_script,
        "ARCHIVE_LINKS": archive_links,
    }

    html_content = template
    for key, value in replacements.items():
        html_content = html_content.replace(f"{{{{{key}}}}}", value)

    return html_content


def _extract_style_block(template: str) -> str:
    m = re.search(r"<style>[\s\S]*?</style>", template)
    return m.group(0) if m else "<style></style>"


def render_history_page(
    records: list[dict[str, Any]],
    *,
    template_path: str,
    base_title: str = "历史记录 | 白嫖游戏信息",
) -> str:
    """
    渲染历史记录页（渲染为卡片样式）。
    records: 每条为完整 snapshot（包含 fetchedAt / epic / steam / psn）
    """
    with open(template_path, "r", encoding="utf-8") as f:
        template = f.read()
    style_block = _extract_style_block(template)

    # 组装记录内容（最新在前）
    blocks: list[str] = []
    for snap in records:
        fetched_at = snap.get("fetchedAt")
        fetched_at_display = "等待同步"
        if fetched_at:
            try:
                dt = datetime.fromisoformat(str(fetched_at).replace("Z", "+00:00"))
                fetched_at_display = format_full_datetime(int(dt.timestamp() * 1000))
            except Exception:
                fetched_at_display = str(fetched_at)

        # 处理 EPIC 数据（兼容新旧格式）
        epic_data = snap.get("epic", {})
        if isinstance(epic_data, list):
            # 新格式：扁平数组，需要转换
            epic_converted = convert_epic_new_format(epic_data)
            epic_now = epic_converted["now"]
            epic_upcoming = epic_converted["upcoming"]
        else:
            # 旧格式：字典包含 now/upcoming
            epic_now = (epic_data.get("now") or []) if isinstance(epic_data, dict) else []
            epic_upcoming = (epic_data.get("upcoming") or []) if isinstance(epic_data, dict) else []
        
        steam = snap.get("steam") or []
        
        # 处理 PSN 数据（兼容新旧格式）
        psn_data = snap.get("psn") or []
        if psn_data and isinstance(psn_data, list) and len(psn_data) > 0:
            first_psn = psn_data[0] if psn_data else {}
            if "cover" in first_psn or "status" in first_psn:
                psn = convert_psn_new_format(psn_data)
            else:
                psn = psn_data
        else:
            psn = []

        itad = snap.get("itad") or []

        total = len(epic_now) + len(epic_upcoming) + len(steam) + len(psn) + len(itad)

        def _subsection(title: str, count: int, body_html: str) -> str:
            return (
                '<div class="p-4 lg:p-6 rounded-steam-lg bg-steam-card border border-steam-accent/15 shadow-steam-card mb-4 last:mb-0">'
                '<header class="flex items-center justify-between gap-3 mb-4">'
                f'<h4 class="text-sm lg:text-base font-semibold tracking-wide m-0 text-steam-text">{escape_html(title)}</h4>'
                f'<span class="px-3 py-1 rounded-full bg-steam-accent/20 text-steam-accent text-xs tracking-wide">{count}</span>'
                "</header>"
                f'<div class="epic-freebies__section-body">{body_html}</div>'
                "</div>"
            )

        body_parts: list[str] = []
        body_parts.append(
            _subsection(
                "EPIC 正在免费",
                len(epic_now),
                render_epic_section_content(epic_now, "当前暂无正在进行的限免活动。", "now"),
            )
        )
        body_parts.append(
            _subsection(
                "EPIC 即将免费",
                len(epic_upcoming),
                render_epic_section_content(epic_upcoming, "暂无即将开始的官方限免活动。", "upcoming"),
            )
        )
        body_parts.append(
            _subsection(
                "Steam 限免",
                len(steam),
                render_steam_section_content(steam, "暂未检测到 Steam 官方限免活动，请稍后再试。"),
            )
        )
        body_parts.append(
            _subsection(
                "PlayStation 本月会员免费",
                len(psn),
                render_psn_section_content(psn, "暂未检测到 PlayStation 公布的会员免费游戏。"),
            )
        )
        body_parts.append(
            _subsection(
                "ITAD Bundle Giveaways",
                len(itad),
                render_itad_section_content(itad, "暂未检测到 ITAD Bundle Giveaways。"),
            )
        )

        blocks.append(
            '<div class="mb-8 last:mb-0">'
            '<header class="flex items-center justify-between gap-4 mb-5 p-4 lg:p-6 rounded-steam-lg bg-steam-section border border-steam-accent/15">'
            f'<h3 class="text-base lg:text-lg font-bold tracking-wide m-0 text-steam-text">{escape_html(fetched_at_display)}</h3>'
            f'<span class="px-3 py-1 rounded-full bg-steam-accent/20 text-steam-accent text-xs tracking-wide">{total}</span>'
            "</header>"
            f'<div class="epic-freebies__section-body">{"".join(body_parts)}</div>'
            "</div>"
        )

    content_html = "".join(blocks) if blocks else '<div class="py-16 lg:py-20 px-10 rounded-steam-lg border border-dashed border-steam-accent/30 text-center text-steam-text-muted bg-steam-bg/60 leading-relaxed">暂无历史记录</div>'

    # history 页 favicon 相对路径不同
    favicon_href = "../logo.png"

    return f"""<!DOCTYPE html>
<html lang="zh-CN">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  <title>{escape_html(base_title)}</title>
  <link rel="icon" type="image/png" href="{favicon_href}">
  <!-- Tailwind CSS CDN -->
  <script src="https://cdn.tailwindcss.com?plugins=forms"></script>
  <script>
    tailwind.config = {{
      theme: {{
        extend: {{
          colors: {{
            'steam-bg': '#0a151f',
            'steam-text': '#f3f6fb',
            'steam-text-muted': '#9bb5d0',
            'steam-accent': '#66c0f4',
            'steam-accent-strong': '#1994d6',
          }},
          borderRadius: {{
            'steam-xl': '28px',
            'steam-lg': '20px',
          }},
          backgroundImage: {{
            'steam-section': 'linear-gradient(145deg, rgba(10, 19, 29, 0.92), rgba(6, 12, 21, 0.9))',
          }},
          boxShadow: {{
            'steam-card': '0 24px 45px rgba(4, 8, 16, 0.55)',
          }},
        }},
      }},
    }}
  </script>
  <style>
    body {{
      font-family: "Segoe UI", "Microsoft YaHei", "PingFang SC", sans-serif;
      background: radial-gradient(45% 60% at 10% 10%, rgba(102, 192, 244, 0.18), transparent 60%),
                  radial-gradient(30% 40% at 80% 0%, rgba(19, 126, 207, 0.18), transparent 70%),
                  linear-gradient(160deg, #060e17 0%, #0b1826 40%, #02070d 100%);
      -webkit-font-smoothing: antialiased;
    }}
    .line-clamp-3 {{ display: -webkit-box; -webkit-line-clamp: 3; -webkit-box-orient: vertical; overflow: hidden; }}
  </style>
</head>
<body class="m-0 min-h-screen text-steam-text antialiased">
  <div class="relative min-h-screen py-10 lg:py-14">
    <div class="mx-auto max-w-[1180px] px-4 lg:px-8">
      <header class="relative overflow-hidden rounded-steam-xl bg-gradient-to-br from-[rgba(17,28,42,0.95)] to-[rgba(9,15,24,0.9)] border border-steam-accent/20 shadow-steam-hero flex flex-col gap-4 p-8 lg:p-14 mb-10">
        <div class="absolute inset-0 -z-10 opacity-60 bg-[radial-gradient(145deg,rgba(19,126,207,0.22),transparent_65%)]"></div>
        <div class="relative z-10 flex flex-col gap-3 max-w-xl">
          <span class="inline-flex items-center gap-2 px-3.5 py-1.5 rounded-full bg-steam-accent/20 text-steam-accent text-xs tracking-widest uppercase">Game Freebie Radar</span>
          <h1 class="text-2xl lg:text-[36px] font-bold tracking-wide m-0">历史记录</h1>
          <p class="text-steam-text-muted text-sm leading-relaxed max-w-lg m-0">仅当抓取结果与上次不同才会新增一条历史记录。</p>
          <div class="flex items-center gap-3">
            <a href="../" class="inline-flex items-center gap-2 px-4 py-2.5 rounded-steam-md bg-steam-bg/80 border border-steam-accent/20 text-steam-text-muted text-xs tracking-wide no-underline hover:border-steam-accent/40 transition-colors">返回主页</a>
          </div>
        </div>
      </header>
      <section class="p-6 lg:p-10 xl:p-12 rounded-steam-xl bg-steam-section border border-steam-accent/15 shadow-steam-section" role="main">
        {content_html}
      </section>
    </div>
  </div>
</body>
</html>"""


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

