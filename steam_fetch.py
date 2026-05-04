#!/usr/bin/env python3
"""
Steam 限免抓取脚本：
- 拉取 Steam 搜索结果页面（基础信息：ID、标题、价格、折扣、平台）
- 通过 Steam Store API 批量获取详细信息（开发商、发行商、类型、真实描述）
- 产出 enriched 游戏列表
"""
import asyncio
import json
import os
import re
from typing import Any, Dict, List, Optional

import aiohttp
from bs4 import BeautifulSoup
from playwright.async_api import async_playwright, TimeoutError as PlaywrightTimeoutError

STEAM_FREEBIES_URL = "https://store.steampowered.com/search/?maxprice=free&specials=1&ndl=1&cc=cn&l=schinese"
STEAM_API_BASE = "https://store.steampowered.com/api/appdetails"
USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/125.0.0.0 Safari/537.36"
)

PLATFORM_LABELS = {
    "win": "Windows",
    "mac": "macOS",
    "linux": "Linux",
}

# API 批量大小和请求间隔（避免限流）
API_BATCH_SIZE = 10
API_REQUEST_INTERVAL = 1.0  # 秒


async def _fetch_with_aiohttp(url: str, session: aiohttp.ClientSession, timeout: int = 30) -> str:
    """使用 aiohttp 发送 HTTP GET 请求"""
    headers = {
        "User-Agent": USER_AGENT,
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8",
        "Accept-Language": "zh-CN,zh;q=0.9,en;q=0.8",
        "Accept-Encoding": "gzip, deflate, br",
        "Connection": "keep-alive",
        "Upgrade-Insecure-Requests": "1",
    }
    async with session.get(url, headers=headers, timeout=aiohttp.ClientTimeout(total=timeout)) as resp:
        resp.raise_for_status()
        return await resp.text()


async def _fetch_html_page() -> str:
    """抓取 Steam 搜索结果页面 HTML"""
    async with aiohttp.ClientSession() as session:
        return await _fetch_with_aiohttp(STEAM_FREEBIES_URL, session)


async def _fetch_with_playwright() -> str:
    """使用 Playwright 抓取 Steam 页面 HTML（备选方法）"""
    async with async_playwright() as playwright:
        browser = await playwright.chromium.launch(
            headless=True,
            args=[
                "--disable-blink-features=AutomationControlled",
                "--disable-dev-shm-usage",
                "--disable-gpu",
            ],
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
            await page.goto(STEAM_FREEBIES_URL, wait_until="networkidle", timeout=45_000)
            await page.wait_for_load_state("domcontentloaded")
            await page.wait_for_selector("#search_resultsRows", timeout=45_000)
            await page.wait_for_timeout(1_500)
            html_content = await page.content()
            return html_content
        finally:
            if context is not None:
                await context.close()
            await browser.close()


def _extract_app_id_from_url(url: str) -> Optional[int]:
    """从 Steam store URL 中提取 app ID"""
    match = re.search(r'/app/(\d+)/', url)
    if match:
        return int(match.group(1))
    return None


def parse_steam_freebies(html_content: str) -> List[Dict[str, Any]]:
    """解析 Steam 限免 HTML，提取基础信息"""
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

        app_id = _extract_app_id_from_url(link)

        image_el = row.select_one(".search_capsule img")
        image = image_el.get("src").strip() if image_el and image_el.get("src") else None

        release_el = row.select_one(".search_released")
        release_date = release_el.get_text(strip=True) if release_el else None

        discount_el = row.select_one(".discount_block .discount_pct")
        discount_text = discount_el.get_text(strip=True) if discount_el else None

        original_price_el = row.select_one(".discount_block .discount_original_price")
        final_price_el = row.select_one(".discount_block .discount_final_price")
        original_price = original_price_el.get_text(strip=True) if original_price_el else None
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
                "appId": app_id,
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


async def _fetch_steam_api_batch(
    app_ids: List[int], session: aiohttp.ClientSession
) -> Dict[int, Dict[str, Any]]:
    """批量获取 Steam API 详情（最多同时请求 1 个批次）"""
    if not app_ids:
        return {}

    ids_param = ",".join(str(aid) for aid in app_ids)
    url = f"{STEAM_API_BASE}?appids={ids_param}&cc=cn&l=schinese&euro=1"

    try:
        text = await _fetch_with_aiohttp(url, session, timeout=20)
        data = json.loads(text)
        result = {}
        for app_id_str, app_data in data.items():
            app_id = int(app_id_str)
            if app_data.get("success"):
                d = app_data.get("data", {})
                result[app_id] = {
                    "developers": d.get("developers", []),
                    "publishers": d.get("publishers", []),
                    "genres": [g["description"] for g in d.get("genres", [])],
                    "shortDescription": d.get("short_description", ""),
                    "detailedDescription": d.get("detailed_description", ""),
                    "metacriticScore": (d.get("metacritic") or {}).get("score"),
                    "achievementsTotal": (d.get("achievements") or {}).get("total"),
                    "releaseDate": (d.get("release_date") or {}).get("date", ""),
                    "isFree": d.get("is_free", True),
                    "headerImage": d.get("header_image", ""),
                    "backgroundImage": d.get("background", ""),
                }
            else:
                result[app_id] = {}
        return result
    except Exception as e:
        print(f"  ⚠️  API 批次请求失败 {app_ids}: {e}")
        return {aid: {} for aid in app_ids}


def _merge_api_data(
    item: Dict[str, Any], api_data: Dict[str, Any]
) -> Dict[str, Any]:
    """将 API 数据合并到游戏记录中，API 数据优先级更高"""
    merged = dict(item)

    if not api_data:
        return merged

    # 用 API 数据覆盖/补充
    if api_data.get("developers"):
        merged["developers"] = api_data["developers"]
    if api_data.get("publishers"):
        merged["publishers"] = api_data["publishers"]
    if api_data.get("genres"):
        merged["genres"] = api_data["genres"]
    if api_data.get("shortDescription"):
        merged["shortDescription"] = api_data["shortDescription"]
    if api_data.get("detailedDescription"):
        merged["detailedDescription"] = api_data["detailedDescription"]
    if api_data.get("metacriticScore"):
        merged["metacriticScore"] = api_data["metacriticScore"]
    if api_data.get("achievementsTotal"):
        merged["achievementsTotal"] = api_data["achievementsTotal"]
    if api_data.get("releaseDate"):
        # API 日期通常更完整，用它覆盖 HTML 的
        merged["releaseDate"] = api_data["releaseDate"]
    if api_data.get("headerImage"):
        merged["headerImage"] = api_data["headerImage"]
    if api_data.get("backgroundImage"):
        merged["backgroundImage"] = api_data["backgroundImage"]
    if api_data.get("isFree") is not None:
        merged["isFree"] = api_data["isFree"]

    return merged


_STORE_JS_CODE = """
() => {
    const data = {};
    data.title = document.querySelector('#appHubAppName')?.innerText.trim() || '';
    data.price = (document.querySelector('.game_purchase_price.price') ||
                  document.querySelector('.discount_final_price'))?.innerText.trim() || '免费/暂无定价';
    data.releaseDate = document.querySelector('.release_date .date')?.innerText.trim() || '';
    data.developer = document.querySelector('#developers_list a')?.innerText.trim() || '';
    const pubEls = document.querySelectorAll('.dev_row .summary.column');
    data.publisher = pubEls[1]?.innerText.trim() || '';

    const getReview = (selector) => {
        const el = document.querySelector(selector);
        if (!el) return '无';
        const summary = el.querySelector('.game_review_summary')?.innerText.trim() || '';
        const detail = el.getAttribute('data-stellar-tooltip-content')?.replace(/<br>/g, ' ') || '';
        return summary ? `${summary} (${detail})` : '无';
    };
    data.reviews = {
        all: getReview('.user_reviews_summary_row[data-stellar-tooltip-content*="全部"]'),
        recent: getReview('.user_reviews_summary_row[data-stellar-tooltip-content*="最近"]')
    };

    data.tags = Array.from(document.querySelectorAll('.app_tag'))
        .map(tag => tag.innerText.trim()).filter(t => t !== '+').slice(0, 10);
    data.features = Array.from(document.querySelectorAll('.label[data-tooltip-text]'))
        .map(el => el.innerText.trim());

    data.shortDesc = document.querySelector('.game_description_snippet')?.innerText.trim() || '';
    data.detailedDescHTML = document.querySelector('#game_area_description')?.innerHTML.trim() || '';

    data.sysReq = {};
    document.querySelectorAll('.game_area_sys_req_leftCol, .game_area_sys_req_rightCol, .game_area_sys_req_full').forEach(block => {
        const txt = block.innerText || '';
        const isMin = txt.includes('最低') || txt.includes('Minimum') || txt.includes('最低配置');
        const key = isMin ? 'Minimum' : 'Recommended';
        if (!data.sysReq[key]) {
            data.sysReq[key] = Array.from(block.querySelectorAll('ul.bb_ul li')).map(li => li.innerText.trim());
        }
    });

    data.languages = '';
    const langRow = document.querySelector('.game_language_options tr:nth-child(2)');
    if (langRow) {
        data.languages = (langRow.innerText || '').replace(/\\s+/g, ' ').trim();
    }
    data.headerImage = document.querySelector('.game_header_image_full')?.src || '';

    // 额外字段：截图、推荐数
    data.screenshots = Array.from(document.querySelectorAll('.highlight_strip_screenshot img'))
        .map(img => img.src).slice(0, 4);
    data.recommendations = document.querySelector('[data-stellar-tooltip-content*="推荐"]')?.innerText.trim() || '';

    return data;
}
"""

_STORE_DEFAULTS = {
    "reviews": {"all": "无", "recent": "无"},
    "tags": [], "features": [], "shortDesc": "", "detailedDescHTML": "",
    "sysReq": {}, "languages": "", "headerImage": "", "screenshots": [],
    "recommendations": "", "price": "", "releaseDate": "", "developer": "", "publisher": "",
}


async def _fetch_steam_store_metadata(app_id: int, context) -> Dict[str, Any]:
    """
    使用共享的 Playwright browser context 访问 Steam 商店页。
    """
    store_url = f"https://store.steampowered.com/app/{app_id}/?cc=cn&l=schinese"

    try:
        page = await context.new_page()
        page.set_default_timeout(60_000)

        await page.goto(store_url, wait_until="load", timeout=60_000)
        await page.wait_for_timeout(3_000)

        metadata = await page.evaluate(_STORE_JS_CODE)
        await page.close()

        result = dict(_STORE_DEFAULTS)
        result["title"] = metadata.get("title", "")
        result["price"] = metadata.get("price", "")
        result["releaseDate"] = metadata.get("releaseDate", "")
        result["developer"] = metadata.get("developer", "")
        result["publisher"] = metadata.get("publisher", "")
        result["reviews"] = metadata.get("reviews", result["reviews"])
        result["tags"] = metadata.get("tags", [])
        result["features"] = metadata.get("features", [])
        result["shortDesc"] = metadata.get("shortDesc", "")
        result["detailedDescHTML"] = metadata.get("detailedDescHTML", "")
        result["sysReq"] = metadata.get("sysReq", {})
        result["languages"] = metadata.get("languages", "")
        result["headerImage"] = metadata.get("headerImage", "")
        result["screenshots"] = metadata.get("screenshots", [])
        result["recommendations"] = metadata.get("recommendations", "")
        return result
    except Exception as e:
        print(f"  ⚠️ Steam 商店页抓取失败 app/{app_id}: {e}")
        return dict(_STORE_DEFAULTS)


async def fetch_steam(output_path: Optional[str] = None) -> List[Dict[str, Any]]:
    """
    抓取 Steam 限免数据：
    1. 爬取搜索结果页面（基础信息）
    2. 批量调用 Steam API 获取详细信息
    3. Playwright 访问商店页提取丰富元数据（tags/reviews/sysReq等）
    4. 合并数据后返回
    """
    print("开始抓取 Steam 限免数据...")

    # Step 1: 获取 HTML 搜索结果
    try:
        html_content = await _fetch_html_page()
    except Exception as e:
        print(f"aiohttp 获取失败，尝试 Playwright: {e}")
        try:
            html_content = await _fetch_with_playwright()
        except Exception as e2:
            print(f"Playwright 也失败: {e2}")
            return []

    items = parse_steam_freebies(html_content)
    if not items:
        print("Steam: 未找到任何限免游戏")
        return []

    print(f"Steam: 搜索页解析到 {len(items)} 条，正在获取 API 详情...")

    # Step 2: 提取所有 app ID
    app_ids_with_indices = []
    for i, item in enumerate(items):
        if item.get("appId"):
            app_ids_with_indices.append((i, item["appId"]))

    print(f"Steam: 其中 {len(app_ids_with_indices)} 条有 app ID")

    if not app_ids_with_indices:
        print("Steam: 无 app ID，跳过 API 详情获取")
        return items

    # Step 3: 批量获取 API 数据
    all_api_results: Dict[int, Dict[str, Any]] = {}
    app_ids_to_fetch = [aid for _, aid in app_ids_with_indices]

    async with aiohttp.ClientSession() as session:
        for i in range(0, len(app_ids_to_fetch), API_BATCH_SIZE):
            batch = app_ids_to_fetch[i : i + API_BATCH_SIZE]
            progress = f"{i + len(batch)}/{len(app_ids_to_fetch)}"
            print(f"  Steam API: 批次 {progress}...")
            batch_results = await _fetch_steam_api_batch(batch, session)
            all_api_results.update(batch_results)
            if i + API_BATCH_SIZE < len(app_ids_to_fetch):
                await asyncio.sleep(API_REQUEST_INTERVAL)

    # Step 4: 合并 API 数据
    for idx, app_id in app_ids_with_indices:
        api_data = all_api_results.get(app_id, {})
        items[idx] = _merge_api_data(items[idx], api_data)

    # 汇总
    enriched_count = sum(1 for _, aid in app_ids_with_indices if all_api_results.get(aid))
    print(f"Steam: API 详情获取完成，{enriched_count}/{len(app_ids_with_indices)} 条成功 enrichment")

    # Step 5: Playwright 访问商店页提取丰富元数据（共享浏览器 + 并发）
    print(f"Steam: 正在从商店页获取丰富元数据（并发数=3）...")
    semaphore = asyncio.Semaphore(3)

    async def _fetch_with_semaphore(idx: int, app_id: int, ctx):
        async with semaphore:
            title_short = (items[idx].get("title") or "?")[:25]
            print(f"  Steam: [{idx+1}/{len(items)}] {title_short}...")
            store_meta = await _fetch_steam_store_metadata(app_id, ctx)

            if store_meta.get("developer"):
                items[idx]["developers"] = [store_meta["developer"]]
            if store_meta.get("publisher"):
                items[idx]["publishers"] = [store_meta["publisher"]]
            if store_meta.get("releaseDate"):
                items[idx]["releaseDate"] = store_meta["releaseDate"]
            if store_meta.get("price"):
                items[idx]["price_steam"] = store_meta["price"]
            if store_meta.get("shortDesc"):
                items[idx]["shortDescription"] = store_meta["shortDesc"]
            if store_meta.get("detailedDescHTML"):
                items[idx]["detailedDescriptionHTML"] = store_meta["detailedDescHTML"]
            if store_meta.get("tags"):
                items[idx]["steamTags"] = store_meta["tags"]
            if store_meta.get("reviews"):
                items[idx]["reviews"] = store_meta["reviews"]
            if store_meta.get("features"):
                items[idx]["features"] = store_meta["features"]
            if store_meta.get("sysReq"):
                items[idx]["sysReq"] = store_meta["sysReq"]
            if store_meta.get("languages"):
                items[idx]["languages"] = store_meta["languages"]
            if store_meta.get("headerImage"):
                items[idx]["headerImage"] = store_meta["headerImage"]
            if store_meta.get("screenshots"):
                items[idx]["screenshots"] = store_meta["screenshots"]
            if store_meta.get("recommendations"):
                items[idx]["recommendations"] = store_meta["recommendations"]

    async with async_playwright() as p:
        browser = await p.chromium.launch(
            headless=True,
            args=[
                "--disable-blink-features=AutomationControlled",
                "--disable-dev-shm-usage",
                "--disable-gpu",
            ],
        )
        context = await browser.new_context(
            user_agent=USER_AGENT,
            viewport={"width": 1920, "height": 1080},
            locale="zh-CN",
        )
        tasks = []
        for i, item in enumerate(items):
            app_id = item.get("appId")
            if not app_id:
                continue
            tasks.append(_fetch_with_semaphore(i, app_id, context))

        if tasks:
            await asyncio.gather(*tasks)

        await context.close()
        await browser.close()

    print(f"Steam: 商店页元数据获取完成")

    # Step 6: 输出
    if output_path:
        os.makedirs(os.path.dirname(output_path) if os.path.dirname(output_path) else ".", exist_ok=True)
        with open(output_path, "w", encoding="utf-8") as f:
            json.dump(items, f, ensure_ascii=False, indent=2)
        print(f"Steam: 已写入 {output_path}")

    return items


async def fetch_steam_game_detail_from_url(url: str) -> Optional[Dict[str, Any]]:
    """
    从单个 Steam 商品页 URL 获取与主列表一致的详情结构。
    用于把 ITAD 中的 Steam 100% OFF 条目并入 Steam 选项卡。
    """
    async with aiohttp.ClientSession() as session:
        try:
            async with session.get(url, allow_redirects=True, timeout=aiohttp.ClientTimeout(total=30)) as resp:
                if resp.status != 200:
                    return None
                final_url = str(resp.url)
        except Exception:
            return None

    app_id = _extract_app_id_from_url(final_url)
    if not app_id:
        return None

    base_item: Dict[str, Any] = {
        "id": final_url,
        "appId": app_id,
        "title": "",
        "link": final_url,
        "image": "",
        "releaseDate": "",
        "platforms": [],
        "discountText": "-100%",
        "originalPrice": "",
        "finalPrice": "$0.00",
        "reviewSummary": "",
    }

    async with aiohttp.ClientSession() as session:
        api_data = await _fetch_steam_api_batch([app_id], session)
    item = _merge_api_data(base_item, api_data.get(app_id, {}))

    store_meta = await _fetch_steam_store_metadata(app_id)
    if store_meta.get("title"):
        item["title"] = store_meta["title"]
    if store_meta.get("price"):
        item["price_steam"] = store_meta["price"]
    if store_meta.get("releaseDate"):
        item["releaseDate"] = store_meta["releaseDate"]
    if store_meta.get("developer"):
        item["developers"] = [store_meta["developer"]]
    if store_meta.get("publisher"):
        item["publishers"] = [store_meta["publisher"]]
    if store_meta.get("reviews"):
        item["reviews"] = store_meta["reviews"]
        if not item.get("reviewSummary"):
            item["reviewSummary"] = store_meta["reviews"].get("all", "")
    if store_meta.get("tags"):
        item["steamTags"] = store_meta["tags"]
    if store_meta.get("features"):
        item["features"] = store_meta["features"]
    if store_meta.get("shortDesc"):
        item["shortDescription"] = store_meta["shortDesc"]
    if store_meta.get("detailedDescHTML"):
        item["detailedDescriptionHTML"] = store_meta["detailedDescHTML"]
    if store_meta.get("sysReq"):
        item["sysReq"] = store_meta["sysReq"]
    if store_meta.get("languages"):
        item["languages"] = store_meta["languages"]
    if store_meta.get("headerImage"):
        item["headerImage"] = store_meta["headerImage"]
        item["image"] = store_meta["headerImage"]

    if not item.get("title"):
        item["title"] = f"Steam App {app_id}"
    if not item.get("image"):
        item["image"] = item.get("headerImage", "")
    return item


async def main():
    items = await fetch_steam()
    with open("STEAM.json", "w", encoding="utf-8") as f:
        json.dump(items, f, ensure_ascii=False, indent=2)
    print(f"Steam: 抓取完成，找到 {len(items)} 条，已写入 STEAM.json")


if __name__ == "__main__":
    asyncio.run(main())
