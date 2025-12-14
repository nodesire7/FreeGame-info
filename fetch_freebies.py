#!/usr/bin/env python3
"""
抓取 Epic、Steam、PlayStation 限免游戏数据
"""
import asyncio
import json
import os
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional
from urllib.parse import urljoin

import aiohttp
from bs4 import BeautifulSoup, NavigableString, Tag
from playwright.async_api import Page, TimeoutError as PlaywrightTimeoutError
from playwright.async_api import async_playwright

# 配置
# Epic 官方免费游戏促销接口（专门用于获取每周限免）
EPIC_API_URL = os.getenv(
    "EPIC_API_URL",
    "https://store-site-backend-static-ipv4.ak.epicgames.com/freeGamesPromotions?locale=zh-CN&country=CN&allowCountries=CN",
)
PSN_SOURCE_URL = "https://www.playstation.com/zh-hans-hk/ps-plus/whats-new/"
STEAM_FREEBIES_URL = "https://store.steampowered.com/search/?maxprice=free&specials=1&ndl=1?cc=cn&l=schinese"

PLAYWRIGHT_BROWSER_ARGS = [
    "--disable-blink-features=AutomationControlled",
    "--disable-dev-shm-usage",
    "--disable-gpu",
]
USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/125.0.0.0 Safari/537.36"
)
PLATFORM_LABELS = {
    "win": "Windows",
    "mac": "macOS",
    "linux": "Linux",
}


async def fetch_page_html(
    url: str, *, wait_for_selector: Optional[str] = None, timeout: int = 45_000
) -> str:
    """使用 Playwright 抓取页面 HTML"""
    async with async_playwright() as playwright:
        browser = await playwright.chromium.launch(
            headless=True, args=PLAYWRIGHT_BROWSER_ARGS
        )
        context = None
        try:
            context = await browser.new_context(
                user_agent=USER_AGENT,
                viewport={"width": 1280, "height": 720},
                device_scale_factor=1,
                is_mobile=False,
                java_script_enabled=True,
            )
            await context.add_init_script(
                "Object.defineProperty(navigator, 'webdriver', { get: () => undefined });"
            )
            page = await context.new_page()
            await page.goto(url, wait_until="networkidle", timeout=timeout)
            await page.wait_for_load_state("domcontentloaded")
            await _maybe_handle_playstation_overlays(page, url)
            if wait_for_selector:
                await page.wait_for_selector(wait_for_selector, timeout=timeout)
            await page.wait_for_timeout(1_500)
            html_content = await page.content()
            return html_content
        finally:
            if context is not None:
                await context.close()
            await browser.close()


async def _maybe_handle_playstation_overlays(page: Page, url: str) -> None:
    """处理 PlayStation 页面的弹窗"""
    if "playstation.com" not in url:
        return

    await _dismiss_playstation_cookie_banner(page)
    await _bypass_playstation_age_gate(page)


async def _dismiss_playstation_cookie_banner(page: Page) -> None:
    """关闭 PlayStation Cookie 横幅"""
    selectors = [
        "button[data-testid='privacy-acknowledge']",
        "button[data-testid='onetrust-accept-btn-handler']",
        "button.psw-button:has-text('接受所有')",
        "button.psw-button:has-text('Accept All')",
        "button.psw-button:has-text('允许所有')",
        "button.psw-button:has-text('Allow all')",
    ]

    for selector in selectors:
        try:
            button = await page.query_selector(selector)
            if button:
                await button.click()
                await page.wait_for_timeout(500)
                return
        except Exception:
            continue


async def _bypass_playstation_age_gate(page: Page) -> None:
    """绕过 PlayStation 年龄验证"""
    try:
        month_input = await page.query_selector("#age-gate-month")
        day_input = await page.query_selector("#age-gate-day")
        year_input = await page.query_selector("#age-gate-year")
        if not (month_input and day_input and year_input):
            return

        await month_input.fill("1")
        await day_input.fill("1")
        await year_input.fill("1990")

        await page.dispatch_event("#age-gate-year", "blur")

        confirm_selector = ".age-gate__input-btn"
        try:
            await page.wait_for_function(
                """
                (selector) => {
                    const el = document.querySelector(selector);
                    if (!el) return false;
                    const ariaDisabled = el.getAttribute('aria-disabled');
                    return !el.classList.contains('cta__disabled') && ariaDisabled !== 'true';
                }
                """,
                confirm_selector,
                timeout=5_000,
            )
        except Exception:
            pass

        await page.click(confirm_selector)

        try:
            await page.wait_for_selector(
                "#age-gate-year", state="detached", timeout=5_000
            )
        except Exception:
            await page.wait_for_function(
                "() => { const el = document.querySelector('.age-gate'); return !el || el.getAttribute('aria-hidden') === 'true' || el.style.display === 'none'; }",
                timeout=5_000,
            )

        await page.wait_for_timeout(1_000)
    except Exception:
        return


def _collect_text_lines(paragraph: Optional[Tag]) -> List[str]:
    """收集段落中的文本行"""
    if paragraph is None:
        return []

    fragments: List[str] = []

    for node in paragraph.children:
        if isinstance(node, NavigableString):
            text = str(node).strip()
            if text:
                fragments.append(text)
        elif isinstance(node, Tag):
            if node.name.lower() == "br":
                fragments.append("\n")
            else:
                text = node.get_text(" ", strip=True)
                if text:
                    fragments.append(text)

    joined = " ".join(fragments)
    lines = [line.strip() for line in joined.split("\n") if line and line.strip()]
    return lines


def _extract_image_url(media_block: Optional[Tag], base_url: str) -> Optional[str]:
    """从媒体块中提取图片 URL"""
    if media_block is None:
        return None

    candidates: List[str] = []

    for attr in ("data-src", "data-srcset", "data-image", "data-background", "data-bg"):
        value = media_block.get(attr)
        if value:
            candidates.append(value)

    style = media_block.get("style", "")
    if "url(" in style:
        start = style.find("url(") + 4
        end = style.find(")", start)
        if end > start:
            candidates.append(style[start:end].strip('\'" '))

    img_tag = media_block.find("img")
    if img_tag:
        for attr in ("src", "data-src", "data-original", "data-large_image"):
            value = img_tag.get(attr)
            if value:
                candidates.append(value)
        srcset = img_tag.get("srcset")
        if srcset:
            candidates.extend(srcset.split(","))

    source_tag = media_block.find("source")
    if source_tag:
        srcset = source_tag.get("srcset")
        if srcset:
            candidates.extend(srcset.split(","))

    for candidate in candidates:
        candidate = candidate.strip()
        if not candidate:
            continue
        url_part = candidate.split(" ")[0]
        if not url_part:
            continue
        absolute_url = urljoin(base_url, url_part)
        return absolute_url

    return None


def _parse_iso_datetime_ms(value: Optional[str]) -> Optional[int]:
    """解析 Epic/网页接口常见的 ISO 时间字符串为毫秒时间戳。"""
    if not value:
        return None
    try:
        dt = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
        return int(dt.timestamp() * 1000)
    except (ValueError, TypeError):
        return None


def _pick_epic_cover(game: Dict[str, Any]) -> str:
    """从 Epic 游戏数据中提取封面图片 URL"""
    images = game.get("keyImages")
    if not isinstance(images, list):
        return ""
    # 优先选择竖版封面
    preferred = ["OfferImageTall", "Thumbnail", "DieselStoreFrontTall", "DieselStoreFrontWide", "OfferImageWide"]
    for image_type in preferred:
        for item in images:
            if isinstance(item, dict) and item.get("type") == image_type:
                url = item.get("url")
                if isinstance(url, str) and url.strip():
                    return url.strip()
    # 回退：任意图片
    for item in images:
        if isinstance(item, dict):
            url = item.get("url")
            if isinstance(url, str) and url.strip():
                return url.strip()
    return ""


def _build_epic_link(game: Dict[str, Any]) -> str:
    """构建 Epic 商店链接"""
    url_slug = game.get("urlSlug")
    if isinstance(url_slug, str) and url_slug.strip() and url_slug not in ("[]", ""):
        return f"https://store.epicgames.com/p/{url_slug.strip()}"
    product_slug = game.get("productSlug")
    if isinstance(product_slug, str) and product_slug.strip() and product_slug not in ("[]", ""):
        return f"https://store.epicgames.com/p/{product_slug.strip()}"
    # 尝试从 offerMappings 提取
    mappings = game.get("offerMappings")
    if isinstance(mappings, list):
        for mapping in mappings:
            if isinstance(mapping, dict):
                page_slug = mapping.get("pageSlug")
                if isinstance(page_slug, str) and page_slug.strip():
                    return f"https://store.epicgames.com/p/{page_slug.strip()}"
    # 回退：使用 namespace/id
    namespace = game.get("namespace")
    game_id = game.get("id")
    if namespace and game_id:
        return f"https://store.epicgames.com/p/{namespace}/{game_id}"
    return "https://store.epicgames.com/free-games"


async def fetch_epic() -> Dict[str, List[Dict[str, Any]]]:
    """抓取 Epic 限免游戏（使用 freeGamesPromotions 接口）"""
    async with aiohttp.ClientSession() as session:
        try:
            async with session.get(EPIC_API_URL, timeout=aiohttp.ClientTimeout(total=30)) as resp:
                if resp.status != 200:
                    raise Exception(f"Epic API returned status {resp.status}")
                payload = await resp.json()

                # 提取游戏列表：data.Catalog.searchStore.elements[]
                elements = (
                    payload.get("data", {})
                    .get("Catalog", {})
                    .get("searchStore", {})
                    .get("elements")
                )
                if not isinstance(elements, list):
                    raise Exception("Unexpected Epic API response format: missing elements")

                now_list: List[Dict[str, Any]] = []
                upcoming_list: List[Dict[str, Any]] = []

                for game in elements:
                    if not isinstance(game, dict):
                        continue

                    # 验证价格：确保是真正免费的游戏（discountPrice=0 且 originalPrice>0）
                    price_obj = game.get("price")
                    if isinstance(price_obj, dict):
                        total_price = price_obj.get("totalPrice")
                        if isinstance(total_price, dict):
                            discount_price = total_price.get("discountPrice")
                            original_price = total_price.get("originalPrice")
                            # 核心筛选：折扣价为0 且 原价>0（排除永久免费的DLC/Add-on）
                            if discount_price != 0:
                                continue
                            if not isinstance(original_price, (int, float)) or original_price <= 0:
                                continue
                    else:
                        # 如果没有价格信息，跳过（可能是DLC或其他非游戏内容）
                        continue

                    promotions = game.get("promotions")
                    if not isinstance(promotions, dict):
                        continue

                    # 当前免费：promotions.promotionalOffers[0].promotionalOffers[]
                    current_promos = promotions.get("promotionalOffers")
                    if isinstance(current_promos, list) and len(current_promos) > 0:
                        promo_offers = current_promos[0].get("promotionalOffers") if isinstance(current_promos[0], dict) else None
                        if isinstance(promo_offers, list) and len(promo_offers) > 0:
                            promo = promo_offers[0] if isinstance(promo_offers[0], dict) else None
                            if promo:
                                start_ms = _parse_iso_datetime_ms(promo.get("startDate"))
                                end_ms = _parse_iso_datetime_ms(promo.get("endDate"))
                                mapped = _map_epic_game(game, start_ms, end_ms, is_current=True)
                                if mapped:
                                    now_list.append(mapped)
                                    continue

                    # 即将免费：promotions.upcomingPromotionalOffers[0].promotionalOffers[]
                    upcoming_promos = promotions.get("upcomingPromotionalOffers")
                    if isinstance(upcoming_promos, list) and len(upcoming_promos) > 0:
                        promo_offers = upcoming_promos[0].get("promotionalOffers") if isinstance(upcoming_promos[0], dict) else None
                        if isinstance(promo_offers, list) and len(promo_offers) > 0:
                            promo = promo_offers[0] if isinstance(promo_offers[0], dict) else None
                            if promo:
                                start_ms = _parse_iso_datetime_ms(promo.get("startDate"))
                                end_ms = _parse_iso_datetime_ms(promo.get("endDate"))
                                mapped = _map_epic_game(game, start_ms, end_ms, is_current=False)
                                if mapped:
                                    upcoming_list.append(mapped)

                # 排序：当前免费按结束时间，即将免费按开始时间
                now_list.sort(key=lambda x: (x.get("freeEndAt") or 2**63 - 1, x.get("title") or ""))
                upcoming_list.sort(key=lambda x: (x.get("freeStartAt") or 2**63 - 1, x.get("title") or ""))
                return {"now": now_list, "upcoming": upcoming_list}
        except Exception as e:
            print(f"Epic fetch failed: {e}")
            import traceback
            traceback.print_exc()
            return {"now": [], "upcoming": []}


def _map_epic_game(
    game: Dict[str, Any], 
    start_ms: Optional[int], 
    end_ms: Optional[int], 
    is_current: bool
) -> Optional[Dict[str, Any]]:
    """将 Epic API 游戏数据映射为统一格式"""
    title = game.get("title")
    if not title or not isinstance(title, str):
        return None
    
    title = title.strip()
    if not title:
        return None

    # 提取价格信息（用于显示原价）
    price_obj = game.get("price")
    original_price_desc = None
    if isinstance(price_obj, dict):
        total_price = price_obj.get("totalPrice")
        if isinstance(total_price, dict):
            fmt_price = total_price.get("fmtPrice")
            if isinstance(fmt_price, dict):
                original_price_desc = fmt_price.get("originalPrice")

    seller_obj = game.get("seller")
    seller_name = seller_obj.get("name") if isinstance(seller_obj, dict) else None

    return {
        "id": str(game.get("id") or game.get("namespace") or title),
        "title": title,
        "description": str(game.get("description") or ""),
        "cover": _pick_epic_cover(game),
        "link": _build_epic_link(game),
        "isFreeNow": is_current,
        "freeStartAt": start_ms,
        "freeEndAt": end_ms,
        "originalPrice": None,
        "originalPriceDesc": original_price_desc,
        "isBundle": False,
        "platforms": None,
        "platform": None,
        "seller": seller_name,
        "developer": game.get("developerDisplayName"),
        "publisher": game.get("publisherDisplayName"),
        "genres": None,
    }


def parse_psplus_html(html_content: str) -> List[Dict[str, Any]]:
    """解析 PlayStation Plus HTML"""
    soup = BeautifulSoup(html_content, "html.parser")
    base_url = "https://www.playstation.com"

    items: List[Dict[str, Any]] = []
    seen_links: set[str] = set()

    section_candidates: List[Tag] = []
    monthly_sections = soup.select("section#monthly-games")
    section_candidates.extend(monthly_sections)

    legacy_section = soup.select_one(
        "#gdk__content > div > div.root > div > div > div:nth-child(4) > section.gpdc-section.theme--light"
    )
    if legacy_section:
        section_candidates.append(legacy_section)

    if not section_candidates:
        section_candidates.extend(soup.select("section.gpdc-section"))

    for section in section_candidates:
        # 尝试多种选择器来查找游戏卡片
        boxes = section.select(".box--light, .box, .psw-product-tile, .product-tile, [data-qa='product-tile']")
        if not boxes:
            # 尝试更通用的选择器
            boxes = section.select("article, .card, .tile")
        
        if not boxes:
            continue

        for box in boxes:
            # 尝试多种方式提取文本块
            text_block = (
                box.select_one(".txt-block__paragraph") or
                box.select_one(".text-block") or
                box.select_one(".product-tile__details") or
                box.select_one(".psw-product-tile__details") or
                box
            )
            
            # 尝试多种方式提取标题
            title_el = (
                text_block.select_one("h1, h2, h3, h4, .title, .product-title, [data-qa='product-title']") or
                text_block.find(["h1", "h2", "h3", "h4", "strong"])
            )
            title = title_el.get_text(strip=True) if title_el else ""

            paragraph = text_block.find("p") or text_block.select_one(".description, .product-description")
            lines = _collect_text_lines(paragraph)
            highlight_lines = [
                line for line in lines if line.startswith(("·", "•", "-", "—"))
            ]
            description_lines = [line for line in lines if line not in highlight_lines]

            highlight = (
                " / ".join(line.lstrip("·•-— ").strip() for line in highlight_lines)
                or None
            )
            description = " ".join(description_lines).strip() or None

            # 尝试多种方式提取图片
            media_block = (
                box.select_one(".media-block") or
                box.select_one(".image-block") or
                box.select_one("img")
            )
            image = _extract_image_url(media_block, base_url)

            # 尝试多种方式提取链接
            link_el = (
                box.select_one(".btn--cta__btn-container a, .button a, .buttonblock a, a.cta__primary") or
                box.select_one("a[href*='/games/'], a[href*='/product/']") or
                box.select_one("a")
            )
            link = link_el.get("href").strip() if link_el and link_el.get("href") else ""
            if link:
                link = urljoin(base_url, link)

            if not title or not link or link in seen_links:
                continue

            platform_el = text_block.select_one(".eyebrow, .eyebrow__text, .platform")
            platforms = platform_el.get_text(strip=True) if platform_el else None

            items.append(
                {
                    "id": link,
                    "title": title,
                    "link": link,
                    "image": image,
                    "description": description or highlight or "PlayStation 官方暂未提供详细描述。",
                    "highlight": highlight,
                    "platforms": platforms,
                }
            )
            seen_links.add(link)

        if items:
            break

    return items


def parse_steam_freebies(html_content: str) -> List[Dict[str, Any]]:
    """解析 Steam 限免 HTML"""
    soup = BeautifulSoup(html_content, "html.parser")
    rows_container = soup.select_one("#search_resultsRows")
    if rows_container is None:
        return []

    items: List[Dict[str, Any]] = []

    for row in rows_container.select("a.search_result_row"):
        title_el = row.select_one(".title")
        link = row.get("href", "").strip()
        if not title_el or not link:
            continue

        title = title_el.get_text(strip=True)
        if not title:
            continue

        image_el = row.select_one(".search_capsule img")
        image = image_el.get("src").strip() if image_el and image_el.get("src") else None

        release_el = row.select_one(".search_released")
        release_date = release_el.get_text(strip=True) if release_el else None

        discount_el = row.select_one(".discount_block .discount_pct")
        discount_text = discount_el.get_text(strip=True) if discount_el else None

        original_price_el = row.select_one(".discount_block .discount_original_price")
        final_price_el = row.select_one(".discount_block .discount_final_price")
        original_price = (
            original_price_el.get_text(strip=True) if original_price_el else None
        )
        final_price = final_price_el.get_text(strip=True) if final_price_el else None

        review_el = row.select_one(".search_review_summary")
        review_summary_raw = review_el.get("data-tooltip-html") if review_el else None
        review_summary = (
            BeautifulSoup(review_summary_raw, "html.parser").get_text(" ", strip=True)
            if review_summary_raw
            else None
        )

        platform_spans = row.select(".search_platforms .platform_img")
        platforms: List[str] = []
        for span in platform_spans:
            classes = span.get("class", [])
            for class_name in classes:
                if class_name in PLATFORM_LABELS:
                    label = PLATFORM_LABELS[class_name]
                    if label not in platforms:
                        platforms.append(label)

        items.append(
            {
                "id": link or title,
                "title": title,
                "link": link,
                "image": image,
                "releaseDate": release_date,
                "platforms": platforms,
                "discountText": discount_text,
                "originalPrice": original_price,
                "finalPrice": final_price,
                "reviewSummary": review_summary,
            }
        )

    return items


async def fetch_psn(psn_html_path: Optional[str] = None) -> List[Dict[str, Any]]:
    """抓取 PlayStation Plus 限免游戏"""
    try:
        # 使用 aiohttp 直接下载页面HTML
        print(f"正在下载PSN页面: {PSN_SOURCE_URL}")
        async with aiohttp.ClientSession() as session:
            headers = {
                "User-Agent": USER_AGENT,
                "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8",
                "Accept-Language": "zh-CN,zh;q=0.9,en;q=0.8",
                "Accept-Encoding": "gzip, deflate, br",
                "Connection": "keep-alive",
                "Upgrade-Insecure-Requests": "1",
            }
            async with session.get(PSN_SOURCE_URL, headers=headers, timeout=aiohttp.ClientTimeout(total=30)) as response:
                response.raise_for_status()
                html_content = await response.text()
        
        # 保存HTML到临时文件（用于调试）
        if psn_html_path:
            with open(psn_html_path, "w", encoding="utf-8") as f:
                f.write(html_content)
            print(f"PSN页面已临时保存到: {psn_html_path}")
        
        # 解析HTML内容
        items = parse_psplus_html(html_content)
        print(f"PSN解析结果: 找到 {len(items)} 个游戏")
        if len(items) == 0:
            print("警告: PSN解析未找到任何游戏，可能需要检查页面结构或选择器")
        return items
    except aiohttp.ClientError as e:
        print(f"Network error fetching PlayStation page: {e}")
        import traceback
        traceback.print_exc()
        return []
    except Exception as e:
        print(f"Failed to fetch PlayStation page: {e}")
        import traceback
        traceback.print_exc()
        return []


async def fetch_steam() -> List[Dict[str, Any]]:
    """抓取 Steam 限免游戏"""
    try:
        html_content = await fetch_page_html(
            STEAM_FREEBIES_URL, wait_for_selector="#search_resultsRows"
        )
        return parse_steam_freebies(html_content)
    except PlaywrightTimeoutError as e:
        print(f"Timeout fetching Steam page: {e}")
        return []
    except Exception as e:
        print(f"Failed to fetch Steam freebies: {e}")
        return []


async def fetch_all(psn_html_path: Optional[str] = None) -> Dict[str, Any]:
    """抓取所有平台的限免数据"""
    print("开始抓取限免数据...")
    epic, steam, psn = await asyncio.gather(
        fetch_epic(), fetch_steam(), fetch_psn(psn_html_path)
    )

    snapshot = {
        "fetchedAt": datetime.now(timezone.utc).isoformat(),
        "epic": epic,
        "steam": steam,
        "psn": psn,
        "sources": {
            "epic": EPIC_API_URL,
            "steam": STEAM_FREEBIES_URL,
            "psn": PSN_SOURCE_URL,
        },
    }

    return snapshot


def main():
    """主函数"""
    import sys

    output_file = sys.argv[1] if len(sys.argv) > 1 else "snapshot.json"
    
    # 确定 psn.html 的保存路径（与 snapshot.json 同一目录）
    output_dir = os.path.dirname(os.path.abspath(output_file))
    if not output_dir:
        output_dir = os.getcwd()
    psn_html_path = os.path.join(output_dir, "psn.html")

    snapshot = asyncio.run(fetch_all(psn_html_path))

    with open(output_file, "w", encoding="utf-8") as f:
        json.dump(snapshot, f, ensure_ascii=False, indent=2)

    print(f"数据已保存到 {output_file}")
    print(f"Epic: {len(snapshot['epic']['now'])} 正在免费, {len(snapshot['epic']['upcoming'])} 即将免费")
    print(f"Steam: {len(snapshot['steam'])} 条")
    print(f"PSN: {len(snapshot['psn'])} 条")


if __name__ == "__main__":
    main()

