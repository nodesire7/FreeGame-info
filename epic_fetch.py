#!/usr/bin/env python3
"""
Epic 限免游戏抓取脚本：
- 使用 Epic Games 官方 freeGamesPromotions API
- 返回简化的 JSON 格式（与用户提供的新 JS 逻辑一致）
- 格式：title, status, description, originalPrice, date, link, cover
"""
import asyncio
import json
import os
from datetime import datetime, timezone, timedelta
from typing import Any, Dict, List, Optional

import aiohttp

EPIC_API_URL = os.getenv(
    "EPIC_API_URL",
    "https://store-site-backend-static.ak.epicgames.com/freeGamesPromotions?locale=zh-CN&country=CN&allowCountries=CN",
)


def _parse_iso_to_beijing(iso_date: Optional[str]) -> str:
    """
    将 ISO 日期字符串转换为中国北京时间格式
    例如：2026-02-13T00:00:00Z -> 2026/02/13 00:00:00
    """
    if not iso_date:
        return ""
    
    try:
        # 解析 ISO 格式日期
        dt = datetime.fromisoformat(iso_date.replace("Z", "+00:00"))
        
        # 转换为北京时间 (UTC+8)
        beijing_tz = timezone(timedelta(hours=8))
        dt_beijing = dt.astimezone(beijing_tz)
        
        # 格式化为指定格式
        return dt_beijing.strftime("%Y/%m/%d %H:%M:%S")
    except Exception:
        return ""


def _build_link(game: Dict[str, Any]) -> str:
    """
    构建 Epic 游戏详情页链接
    优先使用 productSlug，其次使用 catalogNs.mappings.pageSlug，最后用 urlSlug
    """
    # 优先使用 productSlug
    slug = game.get("productSlug")
    if slug:
        return f"https://store.epicgames.com/zh-CN/p/{slug}"
    
    # 尝试从 catalogNs.mappings 获取
    catalog_ns = game.get("catalogNs")
    if isinstance(catalog_ns, dict):
        mappings = catalog_ns.get("mappings")
        if isinstance(mappings, list) and mappings:
            page_slug = mappings[0].get("pageSlug")
            if page_slug:
                return f"https://store.epicgames.com/zh-CN/p/{page_slug}"
    
    # 尝试使用 urlSlug
    slug = game.get("urlSlug")
    if slug:
        return f"https://store.epicgames.com/zh-CN/p/{slug}"
    
    return "https://store.epicgames.com/zh-CN/free-games"


def _pick_cover(game: Dict[str, Any]) -> str:
    """
    提取游戏封面图
    优先使用 OfferImageWide，其次使用 Thumbnail
    """
    images = game.get("keyImages")
    if not isinstance(images, list):
        return ""
    
    # 优先查找 OfferImageWide
    for img in images:
        if isinstance(img, dict):
            img_type = img.get("type", "")
            if img_type == "OfferImageWide":
                url = img.get("url")
                if url:
                    return url
    
    # 其次查找 Thumbnail
    for img in images:
        if isinstance(img, dict):
            img_type = img.get("type", "")
            if img_type == "Thumbnail":
                url = img.get("url")
                if url:
                    return url
    
    # 如果都没有，使用第一张图片
    if images:
        first_img = images[0]
        if isinstance(first_img, dict):
            url = first_img.get("url")
            if url:
                return url
    
    return ""


def _extract_description(game: Dict[str, Any]) -> str:
    """
    提取游戏简介
    优先取 description，没有则取 keyText
    """
    # 优先取 description
    description = game.get("description")
    if description:
        # 清理换行符
        return description.replace("\n", " ").strip()
    
    # 取 keyText
    key_text = game.get("keyText")
    if key_text:
        return key_text.replace("\n", " ").strip()
    
    return "暂无游戏简介。"


async def fetch_epic() -> List[Dict[str, Any]]:
    """
    获取 Epic 限免游戏列表
    返回简化的游戏信息列表
    """
    async with aiohttp.ClientSession() as session:
        try:
            async with session.get(EPIC_API_URL, timeout=aiohttp.ClientTimeout(total=30)) as resp:
                if resp.status != 200:
                    raise RuntimeError(f"Epic API 返回状态码 {resp.status}")
                
                payload = await resp.json()
        
        except asyncio.TimeoutError:
            raise RuntimeError("Epic API 请求超时")
        except aiohttp.ClientError as e:
            raise RuntimeError(f"Epic API 请求失败: {str(e)}")

    # 提取游戏列表
    elements = (
        payload.get("data", {})
        .get("Catalog", {})
        .get("searchStore", {})
        .get("elements")
    )
    
    if not isinstance(elements, list):
        raise RuntimeError("Epic API 返回格式异常")

    # 使用中国时区
    china_tz = timezone(timedelta(hours=8))
    now_ms = int(datetime.now(china_tz).timestamp() * 1000)

    result: List[Dict[str, Any]] = []
    seen: set[str] = set()

    for game in elements:
        if not isinstance(game, dict):
            continue
        
        # 获取唯一标识
        ns = str(game.get("namespace") or "").strip()
        gid = str(game.get("id") or "").strip()
        key = f"{ns}:{gid}" if ns or gid else game.get("title")
        
        if not key:
            continue

        promotions = game.get("promotions")
        if not isinstance(promotions, dict):
            continue

        # 获取促销活动信息
        active_offers = promotions.get("promotionalOffers")
        upcoming_offers = promotions.get("upcomingPromotionalOffers")
        
        # 检查是否有当前免费
        has_active = False
        active_end_date = None
        
        if isinstance(active_offers, list) and active_offers:
            for offer_group in active_offers:
                if isinstance(offer_group, dict):
                    offers = offer_group.get("promotionalOffers")
                    if isinstance(offers, list):
                        for offer in offers:
                            if isinstance(offer, dict):
                                # 检查是否免费（discountPrice 为 0）
                                price_data = game.get("price", {}).get("totalPrice", {})
                                discount_price = price_data.get("discountPrice")
                                
                                if discount_price == 0:
                                    has_active = True
                                    active_end_date = offer.get("endDate")
                                    break
                if has_active:
                    break
        
        # 检查是否有即将免费（重要：采用 JS 逻辑，排除已在促销中的）
        has_upcoming = False
        upcoming_start_date = None
        
        if not has_active and isinstance(upcoming_offers, list) and upcoming_offers:
            for offer_group in upcoming_offers:
                if isinstance(offer_group, dict):
                    offers = offer_group.get("promotionalOffers")
                    if isinstance(offers, list) and offers:
                        has_upcoming = True
                        upcoming_start_date = offers[0].get("startDate")
                        break

        # 如果既没有当前免费也没有即将免费，跳过
        if not has_active and not has_upcoming:
            continue

        # 根据状态确定目标日期
        if has_active:
            status = "ACTIVE"
            target_date = active_end_date
        else:
            status = "UPCOMING"
            target_date = upcoming_start_date

        # 提取原价
        price_data = game.get("price", {})
        total_price = price_data.get("totalPrice", {})
        original_price = total_price.get("fmtPrice", {}).get("originalPrice", "")

        # 提取游戏简介
        description = _extract_description(game)

        game_info = {
            "title": game.get("title", ""),
            "status": status,
            "description": description,
            "originalPrice": original_price,
            "date": _parse_iso_to_beijing(target_date),
            "link": _build_link(game),
            "cover": _pick_cover(game),
        }

        # 检查必填字段，并去重
        if game_info["title"] and game_info["link"]:
            # 使用 (title + link) 作为去重键
            dedup_key = f"{game_info['title']}|{game_info['status']}"
            if dedup_key not in seen:
                seen.add(dedup_key)
                result.append(game_info)

    return result


def save_json(data: List[Dict[str, Any]], path: str = "EPIC.json") -> None:
    """保存数据到 JSON 文件"""
    os.makedirs(os.path.dirname(path) if os.path.dirname(path) else ".", exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)


async def main():
    """主函数"""
    import sys
    
    output = sys.argv[1] if len(sys.argv) > 1 else "EPIC.json"
    
    try:
        data = await fetch_epic()
        save_json(data, output)
        
        active_count = len([g for g in data if g.get("status") == "ACTIVE"])
        upcoming_count = len([g for g in data if g.get("status") == "UPCOMING"])
        
        print(f"Epic 抓取完成！")
        print(f"  正在免费: {active_count} 款")
        print(f"  即将免费: {upcoming_count} 款")
        print(f"  已写入: {output}")
        
    except Exception as e:
        print(f"错误: {str(e)}")
        sys.exit(1)


if __name__ == "__main__":
    asyncio.run(main())
