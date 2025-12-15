#!/usr/bin/env python3
"""
独立的 Epic 限免抓取脚本：
- 从 freeGamesPromotions 判定正在/即将免费
- 组合领取链接（/zh-CN/p/<slug>）
- 进入商品页抓取展示价格/描述/平台/发行商/开发商
- 输出 EPIC.json
"""
import asyncio
import json
import os
import re
from datetime import datetime, timezone, timedelta
from typing import Any, Dict, List, Optional
from urllib.parse import quote

import aiohttp
from playwright.async_api import async_playwright

EPIC_PROMOTIONS_API_URL = os.getenv(
    "EPIC_PROMOTIONS_API_URL",
    "https://store-site-backend-static-ipv4.ak.epicgames.com/freeGamesPromotions?locale=zh-CN&country=CN&allowCountries=CN",
)
LOCALE_PREFIX = "https://store.epicgames.com/zh-CN/p/"


def _parse_iso_ms(v: Optional[str]) -> Optional[int]:
    if not v:
        return None
    try:
        return int(datetime.fromisoformat(v.replace("Z", "+00:00")).timestamp() * 1000)
    except Exception:
        return None


def _sanitize_slug(value: Any) -> Optional[str]:
    if not isinstance(value, str):
        return None
    slug = value.strip("/").replace(" ", "-")
    if not slug or slug in ("[]",):
        return None
    if slug.endswith("/home"):
        slug = slug[:-5]
    return slug or None


def _extract_slug(game: Dict[str, Any]) -> Optional[str]:
    for key in ("productSlug", "urlSlug"):
        slug = _sanitize_slug(game.get(key))
        if slug:
            return slug
    attrs = game.get("customAttributes")
    if isinstance(attrs, list):
        for attr in attrs:
            if isinstance(attr, dict) and attr.get("key") == "com.epicgames.app.productSlug":
                slug = _sanitize_slug(attr.get("value"))
                if slug:
                    return slug
    mappings = game.get("offerMappings")
    if isinstance(mappings, list):
        for m in mappings:
            if isinstance(m, dict):
                slug = _sanitize_slug(m.get("pageSlug"))
                if slug:
                    return slug
    catalog = game.get("catalogNs")
    if isinstance(catalog, dict):
        maps = catalog.get("mappings")
        if isinstance(maps, list):
            for m in maps:
                if isinstance(m, dict):
                    slug = _sanitize_slug(m.get("pageSlug"))
                    if slug:
                        return slug
    return None


def _build_link(game: Dict[str, Any]) -> str:
    slug = _extract_slug(game)
    base_url = ""
    if slug:
        base_url = f"{LOCALE_PREFIX}{slug}"
    else:
        ns = game.get("namespace")
        gid = game.get("id")
        if ns and gid:
            base_url = f"{LOCALE_PREFIX}{ns}/{gid}"
        else:
            return "https://store.epicgames.com/free-games"
    
    # 添加区域参数，确保显示人民币价格
    if "?" in base_url:
        return f"{base_url}&locale=zh-CN&country=CN"
    else:
        return f"{base_url}?locale=zh-CN&country=CN"


def _iter_windows(promotions: Dict[str, Any]):
    for is_current, key in ((True, "promotionalOffers"), (False, "upcomingPromotionalOffers")):
        groups = promotions.get(key)
        if not (isinstance(groups, list) and groups):
            continue
        offers = groups[0].get("promotionalOffers") if isinstance(groups[0], dict) else None
        if not (isinstance(offers, list) and offers):
            continue
        for promo in offers:
            if not isinstance(promo, dict):
                continue
            yield is_current, _parse_iso_ms(promo.get("startDate")), _parse_iso_ms(promo.get("endDate"))


def _pick_cover(game: Dict[str, Any]) -> str:
    images = game.get("keyImages")
    if not isinstance(images, list):
        return ""
    preferred = ["OfferImageTall", "Thumbnail", "DieselStoreFrontTall", "DieselStoreFrontWide", "OfferImageWide"]
    for t in preferred:
        for item in images:
            if isinstance(item, dict) and item.get("type") == t:
                url = item.get("url")
                if isinstance(url, str) and url.strip():
                    return url.strip()
    for item in images:
        if isinstance(item, dict):
            url = item.get("url")
            if isinstance(url, str) and url.strip():
                return url.strip()
    return ""


# 已删除所有 HTML 解析函数，只保留 JavaScript 模式


async def _fetch_page_detail_with_js(page) -> Dict[str, Any]:
    """
    使用 JavaScript 直接从页面提取游戏信息
    """
    js_code = """
    (function() {
        const gameData = {};
        
        // 辅助函数：根据中文标签查找对应的值
        const getValueByLabel = (labelText) => {
            const labelElement = Array.from(document.querySelectorAll('.css-1o0y1dn span, .css-1ed7831 span'))
                .find(span => span.textContent.trim() === labelText);
            
            if (labelElement) {
                const valueContainer = labelElement.closest('.css-1o0y1dn, .css-1ed7831')?.querySelector('.css-btns76');
                if (valueContainer) {
                    const platformsList = valueContainer.querySelector('ul.css-e6kwg0');
                    if (platformsList) {
                        return Array.from(platformsList.querySelectorAll('li')).map(li => li.textContent.trim()).join(', ');
                    }
                    return valueContainer.textContent.trim();
                }
            }
            return null;
        };
        
        // 辅助函数：提取分类/特色标签列表
        const getTagsList = (headingText) => {
            const headingElement = Array.from(document.querySelectorAll('p.eds_1ypbntda')).find(p => p.textContent.trim() === headingText);
            if (headingElement) {
                const tagsContainer = headingElement.closest('.css-11w1nwr')?.nextElementSibling;
                if (tagsContainer) {
                    return Array.from(tagsContainer.querySelectorAll('a span span')).map(span => span.textContent.trim()).join(', ');
                }
            }
            return null;
        };
        
        // 1. 价格信息
        const priceContainer = document.querySelector('.css-169q7x3, .css-1gmuxco');
        if (priceContainer) {
            const currentPriceElement = priceContainer.querySelector('.css-1nblg0t strong span, .css-1nblg0t span:last-child');
            const originalPriceElement = priceContainer.querySelector('.css-4jky3p');
            const discountPercentageElement = priceContainer.querySelector('.eds_1xxntt819');
            
            const currentPrice = currentPriceElement ? currentPriceElement.textContent.trim() : null;
            const originalPrice = originalPriceElement ? originalPriceElement.textContent.trim() : null;
            const discount = discountPercentageElement ? discountPercentageElement.textContent.trim() : null;
            
            // 创建 Price 对象（即使所有值都是 null 也创建，以便调试）
            gameData.Price = {
                current: currentPrice,
                original: originalPrice,
                discount: discount
            };
        } else {
            // 如果找不到价格容器，也创建一个空的 Price 对象用于调试
            gameData.Price = {
                current: null,
                original: null,
                discount: null
            };
        }
        
        // 2. 元数据
        gameData.Platform = getValueByLabel('平台');
        gameData.Developer = getValueByLabel('开发商');
        gameData.Publisher = getValueByLabel('发行商');
        const releaseDateElement = document.querySelector('.css-1o0y1dn time');
        gameData.ReleaseDate = releaseDateElement ? releaseDateElement.textContent.trim() : getValueByLabel('发行日期');
        
        // 3. 游戏类型
        gameData.Genres = getTagsList('游戏类型');
        gameData.Features = getTagsList('特色');
        
        // 4. 游戏简介
        const longDescriptionContainer = document.querySelector('.css-gd3hrz');
        if (longDescriptionContainer) {
            const contentElements = longDescriptionContainer.querySelectorAll('p, li');
            let fullDescription = '';
            contentElements.forEach(el => {
                let text = el.textContent.trim();
                if (text) {
                    if (el.tagName === 'LI') {
                        text = '• ' + text;
                    }
                    fullDescription += text + '\\n\\n';
                }
            });
            gameData.Summary = fullDescription.trim();
        } else {
            const shortDescriptionElement = document.querySelector('.css-lgj0h8 .css-1myreog');
            gameData.Summary = shortDescriptionElement ? shortDescriptionElement.textContent.trim() : null;
        }
        
        return gameData;
    })();
    """
    
    try:
        result = await page.evaluate(js_code)
        return result if result else {}
    except Exception as e:
        print(f"  [DEBUG] JavaScript 执行错误: {str(e)}")
        return {}


async def _fetch_page_detail(link: str, debug: bool = False) -> Dict[str, Any]:
    """
    使用 Playwright 获取完整渲染后的页面 HTML，然后解析详细信息
    """
    html = None
    debug_info = []
    
    # 优先使用 Playwright 获取完整渲染的页面
    try:
        if debug:
            debug_info.append("尝试使用 Playwright...")
        async with async_playwright() as p:
            browser = await p.chromium.launch(
                headless=True,
                args=[
                    "--disable-blink-features=AutomationControlled",
                    "--disable-dev-shm-usage",
                    "--disable-gpu",
                ]
            )
            context = await browser.new_context(
                user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/125.0.0.0 Safari/537.36",
                viewport={"width": 1920, "height": 1080},
                locale="zh-CN",
                timezone_id="Asia/Shanghai",
                # 设置地理位置为中国，确保显示人民币价格
                geolocation={"latitude": 39.9042, "longitude": 116.4074},  # 北京
                permissions=["geolocation"],
            )
            # 添加反检测脚本
            await context.add_init_script(
                "Object.defineProperty(navigator, 'webdriver', { get: () => undefined });"
            )
            
            page = await context.new_page()
            if debug:
                debug_info.append(f"正在访问: {link}")
            
            # 使用 domcontentloaded 而不是 networkidle，避免无限等待
            try:
                await page.goto(link, wait_until="domcontentloaded", timeout=60_000)
            except Exception as e:
                if debug:
                    debug_info.append(f"页面导航警告: {str(e)}")
                # 即使超时也继续
            
            # 等待页面基本加载
            try:
                await page.wait_for_load_state("domcontentloaded", timeout=15_000)
            except Exception:
                pass  # 即使超时也继续
            if debug:
                debug_info.append("页面基本加载完成，等待内容渲染...")
            
            # 等待关键元素加载（使用更宽松的策略）
            # 先等待页面基本结构加载
            await page.wait_for_timeout(3_000)
            
            # 尝试等待关键选择器
            selectors_to_wait = [
                ".css-169q7x3", ".css-1gmuxco", ".css-1o0y1dn", 
                ".css-gd3hrz"
            ]
            found_selector = None
            
            for selector in selectors_to_wait:
                try:
                    await page.wait_for_selector(selector, timeout=10_000, state="attached")
                    found_selector = selector
                    break
                except Exception:
                    continue
            
            # 等待内容完全渲染（增加等待时间）
            await page.wait_for_timeout(8_000)
            
            # 尝试等待价格容器出现（多次重试）
            price_container_found = False
            for attempt in range(3):
                try:
                    await page.wait_for_selector('.css-169q7x3, .css-1gmuxco', timeout=15_000, state="attached")
                    price_container_found = True
                    if debug:
                        debug_info.append(f"价格容器找到（尝试 {attempt + 1}）")
                    break
                except Exception:
                    if debug:
                        debug_info.append(f"价格容器未找到（尝试 {attempt + 1}），继续等待...")
                    await page.wait_for_timeout(3_000)
            
            # 滚动页面以确保懒加载内容被加载
            await page.evaluate("window.scrollTo(0, document.body.scrollHeight)")
            await page.wait_for_timeout(4_000)
            await page.evaluate("window.scrollTo(0, 0)")
            await page.wait_for_timeout(4_000)
            
            # 再次等待，确保价格信息加载完成
            await page.wait_for_timeout(3_000)
            
            # 使用 JavaScript 直接提取数据
            js_data = await _fetch_page_detail_with_js(page)
            
            await browser.close()
            
            if js_data and isinstance(js_data, dict) and len(js_data) > 0:
                # 将 JavaScript 返回的数据转换为 Python 字典格式
                detail = {}
                if debug:
                    debug_info.append(f"JavaScript 返回数据: {list(js_data.keys())}")
                    debug_info.append(f"JavaScript 完整数据: {js_data}")
                
                # 价格信息
                if js_data.get("Price") and isinstance(js_data["Price"], dict):
                    price = js_data["Price"]
                    if debug:
                        debug_info.append(f"Price 数据: {price}")
                    # 原价（如 "¥384"）
                    if price.get("original"):
                        detail["originalPriceDesc"] = price["original"]
                        # 提取数值
                        price_match = re.search(r"([\d,.]+)", price["original"])
                        if price_match:
                            try:
                                detail["originalPrice"] = float(price_match.group(1).replace(",", ""))
                            except Exception:
                                pass
                    # 当前价格（如 "¥384*"）
                    if price.get("current"):
                        detail["currentPrice"] = price["current"]
                    # 折扣
                    if price.get("discount"):
                        detail["discount"] = price["discount"]
                elif debug:
                    debug_info.append(f"未找到 Price 字段，js_data keys: {list(js_data.keys())}")
                
                # 元数据
                if js_data.get("Platform"):
                    platforms = [p.strip() for p in js_data["Platform"].split(",") if p.strip()]
                    # 去重处理 "WindowsWindows" 这种情况
                    unique_platforms = []
                    seen = set()
                    for p in platforms:
                        # 处理重复的平台名称
                        cleaned = p
                        if len(p) > 4 and p[:len(p)//2] == p[len(p)//2:]:
                            cleaned = p[:len(p)//2]
                        if cleaned not in seen:
                            seen.add(cleaned)
                            unique_platforms.append(cleaned)
                    if unique_platforms:
                        detail["platforms"] = unique_platforms
                
                if js_data.get("Developer"):
                    detail["developer"] = js_data["Developer"]
                
                if js_data.get("Publisher"):
                    detail["publisher"] = js_data["Publisher"]
                
                if js_data.get("ReleaseDate"):
                    detail["releaseDate"] = js_data["ReleaseDate"]
                
                # 游戏类型和特色
                if js_data.get("Genres"):
                    detail["genres"] = [g.strip() for g in js_data["Genres"].split(",") if g.strip()]
                
                if js_data.get("Features"):
                    detail["features"] = [f.strip() for f in js_data["Features"].split(",") if f.strip()]
                
                # 游戏简介
                if js_data.get("Summary"):
                    detail["description"] = js_data["Summary"]
                
                # 检查是否获取到有效数据（即使没有价格信息，其他信息也算成功）
                found_fields = [k for k, v in detail.items() if v not in (None, "", [])]
                if detail and len(found_fields) > 0:
                    if debug:
                        debug_info.append(f"JavaScript 提取成功，获取到 {len(found_fields)} 个字段: {', '.join(found_fields)}")
                        print("  [DEBUG] " + "\n  [DEBUG] ".join(debug_info))
                    return detail
                elif debug:
                    debug_info.append(f"JavaScript 提取的数据无效: detail={detail}, found_fields={found_fields}")
                    print("  [DEBUG] " + "\n  [DEBUG] ".join(debug_info))
            
            if debug:
                debug_info.append(f"JavaScript 提取失败或返回空数据，回退到 HTML 解析")
            
            # 如果 JavaScript 提取失败，回退到 HTML 解析
    except Exception as e:
        if debug:
            debug_info.append(f"Playwright 失败: {str(e)}")
        # Playwright 失败，回退到 aiohttp
        try:
            if debug:
                debug_info.append("回退到 aiohttp...")
            headers = {
                "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/125.0.0.0 Safari/537.36",
                "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8",
                "Accept-Language": "zh-CN,zh;q=0.9,en;q=0.8",
            }
            async with session.get(link, headers=headers, timeout=aiohttp.ClientTimeout(total=20)) as resp:
                if resp.status == 200:
                    html = await resp.text()
                    if debug:
                        debug_info.append("aiohttp 成功获取HTML")
                else:
                    if debug:
                        debug_info.append(f"aiohttp 状态码: {resp.status}")
        except Exception as e2:
            if debug:
                debug_info.append(f"aiohttp 失败: {str(e2)}")
    
    if not html:
        if debug:
            print("  [DEBUG] " + "\n  [DEBUG] ".join(debug_info))
        return {}
    
    try:
        detail = _parse_page_dom(html)
        
        if debug:
            # 检查解析结果
            found_fields = [k for k, v in detail.items() if v not in (None, "", [])]
            debug_info.append(f"解析结果: 找到 {len(found_fields)} 个字段: {', '.join(found_fields) if found_fields else '无'}")
            print("  [DEBUG] " + "\n  [DEBUG] ".join(debug_info))
        
        # 检查是否获取到任何有效字段
        if detail and any(v not in (None, "", []) for v in detail.values()):
            return detail
        return {}
    except Exception as e:
        if debug:
            debug_info.append(f"解析失败: {str(e)}")
            print("  [DEBUG] " + "\n  [DEBUG] ".join(debug_info))
        return {}


async def fetch_epic() -> Dict[str, List[Dict[str, Any]]]:
    async with aiohttp.ClientSession() as session:
        # 只用于 API 调用，页面详情使用 Playwright
        async with session.get(EPIC_PROMOTIONS_API_URL, timeout=aiohttp.ClientTimeout(total=30)) as resp:
            if resp.status != 200:
                raise RuntimeError(f"Epic API status {resp.status}")
            payload = await resp.json()

        elements = (
            payload.get("data", {})
            .get("Catalog", {})
            .get("searchStore", {})
            .get("elements")
        )
        if not isinstance(elements, list):
            raise RuntimeError("Unexpected Epic API format")

        # 使用中国时区（UTC+8）
        china_tz = timezone(timedelta(hours=8))
        now_ms = int(datetime.now(china_tz).timestamp() * 1000)
        now_list: List[Dict[str, Any]] = []
        upcoming_list: List[Dict[str, Any]] = []
        seen: set[str] = set()

        for game in elements:
            if not isinstance(game, dict):
                continue
            ns = str(game.get("namespace") or "").strip()
            gid = str(game.get("id") or "").strip()
            key = f"{ns}:{gid}" if ns or gid else game.get("title")
            if not key or key in seen:
                continue
            seen.add(key)

            price = game.get("price")
            if not isinstance(price, dict):
                continue
            total_price = price.get("totalPrice")
            if not isinstance(total_price, dict):
                continue
            discount_price = total_price.get("discountPrice")
            original_price = total_price.get("originalPrice")
            is_code = bool(game.get("isCodeRedemptionOnly"))
            if discount_price != 0:
                continue
            if not is_code and (not isinstance(original_price, (int, float)) or original_price <= 0):
                continue

            promotions = game.get("promotions") if isinstance(game.get("promotions"), dict) else None
            if not promotions:
                continue

            link = _build_link(game)
            base_info = {
                "id": gid or game.get("title") or key,
                "title": game.get("title") or "未知",
                "description": game.get("description") or "",
                "cover": _pick_cover(game),
                "link": link,
                "seller": (game.get("seller") or {}).get("name") if isinstance(game.get("seller"), dict) else None,
                "developer": game.get("developerDisplayName"),
                "publisher": game.get("publisherDisplayName"),
                "platforms": None,
                "genres": None,
                "originalPrice": str(original_price) if original_price not in (None, "") else None,
                "originalPriceDesc": None,
                "isBundle": game.get("offerType") == "BUNDLE",
                "isCodeRedemptionOnly": is_code,
            }

            has_window = False
            for is_current, start_ms, end_ms in _iter_windows(promotions):
                if end_ms is not None and now_ms >= end_ms:
                    continue
                is_free_now = is_current
                if start_ms is not None and end_ms is not None:
                    is_free_now = start_ms <= now_ms < end_ms
                elif start_ms is not None:
                    is_free_now = start_ms <= now_ms
                elif end_ms is not None:
                    is_free_now = now_ms < end_ms

                mapped = dict(base_info)
                mapped["freeStartAt"] = start_ms
                mapped["freeEndAt"] = end_ms
                mapped["isFreeNow"] = is_free_now

                # 补齐商品页详情（跳过 "Mystery Game" 类型的游戏）
                title = mapped.get('title', '')
                if "Mystery Game" in title:
                    print(f"跳过详细信息获取: {title} (Mystery Game)")
                else:
                    print(f"正在获取详细信息: {title}")
                    page_detail = await _fetch_page_detail(link, debug=False)
                    if page_detail:
                        print(f"  获取到 {len(page_detail)} 个字段: {list(page_detail.keys())}")
                        # 合并所有详细信息字段
                        detail_fields = (
                            "originalPrice", "originalPriceDesc", "description", "platforms", 
                            "genres", "publisher", "developer", "discount", 
                            "features", "releaseDate"
                        )
                        for k in detail_fields:
                            val = page_detail.get(k)
                            if val not in (None, "", []):
                                mapped[k] = val
                                val_str = str(val)[:50].replace('\n', ' ').replace('\xa0', ' ').replace('\u200b', '')
                                try:
                                    print(f"  [OK] {k}: {val_str}")
                                except UnicodeEncodeError:
                                    # 如果编码失败，使用 ASCII 安全的方式打印
                                    val_str_safe = val_str.encode('ascii', 'ignore').decode('ascii')
                                    print(f"  [OK] {k}: {val_str_safe}")
                        
                        # 封面特殊处理：只在 API 没有封面或封面无效时才使用页面获取的封面
                        page_cover = page_detail.get("cover")
                        if page_cover and page_cover not in (None, "", []):
                            # 检查当前封面是否有效（不是字体图标等）
                            current_cover = mapped.get("cover", "")
                            if not current_cover or "joypixel" in current_cover or "font" in current_cover.lower():
                                mapped["cover"] = page_cover
                                print(f"  [OK] cover: {page_cover[:50]}")
                    else:
                        print(f"  [FAIL] 未获取到详细信息，使用基本信息")

                has_window = True
                if is_free_now:
                    now_list.append(mapped)
                else:
                    upcoming_list.append(mapped)

            if not has_window:
                continue

        now_list.sort(key=lambda x: (x.get("freeEndAt") or 2**63 - 1, x.get("title") or ""))
        upcoming_list.sort(key=lambda x: (x.get("freeStartAt") or 2**63 - 1, x.get("title") or ""))
        return {"now": now_list, "upcoming": upcoming_list}


def save_json(data: Dict[str, Any], path: str = "EPIC.json") -> None:
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)


def main():
    import sys
    output = sys.argv[1] if len(sys.argv) > 1 else "EPIC.json"
    data = asyncio.run(fetch_epic())
    save_json(data, output)
    print(f"已写入 {output}，正在免费 {len(data['now'])} 条，即将免费 {len(data['upcoming'])} 条")


if __name__ == "__main__":
    main()

