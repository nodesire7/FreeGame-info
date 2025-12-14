import asyncio
from datetime import datetime, timezone, timedelta
import html
from typing import Any, List, Optional
from urllib.parse import urljoin

from bs4 import BeautifulSoup, NavigableString, Tag
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from playwright.async_api import Page, TimeoutError as PlaywrightTimeoutError
from playwright.async_api import async_playwright
from pydantic import BaseModel
import uvicorn

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


class PSPlusItem(BaseModel):
    title: str
    link: str
    image: Optional[str] = None
    description: Optional[str] = None
    highlight: Optional[str] = None
    platforms: Optional[str] = None


class PSPlusResponse(BaseModel):
    source: str
    fetched_at: datetime
    items: List[PSPlusItem]


class SteamFreebieItem(BaseModel):
    title: str
    link: str
    image: Optional[str] = None
    release_date: Optional[str] = None
    platforms: List[str] = []
    discount_text: Optional[str] = None
    original_price: Optional[str] = None
    final_price: Optional[str] = None
    review_summary: Optional[str] = None


class SteamFreebieResponse(BaseModel):
    source: str
    fetched_at: datetime
    items: List[SteamFreebieItem]


app = FastAPI(
    title="Freebie Radar API",
    description="Fetch PlayStation Plus and Steam limited-time freebies.",
    version="1.1.0",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
    allow_credentials=False,
)


PSPLUS_CACHE_TTL = timedelta(hours=3)
_psplus_cache_lock = asyncio.Lock()
_psplus_cache: dict[str, Any] = {
    "response": None,
    "timestamp": None,
}

STEAM_CACHE_TTL = timedelta(hours=3)
_steam_cache_lock = asyncio.Lock()
_steam_cache: dict[str, Any] = {
    "response": None,
    "timestamp": None,
}


async def fetch_page_html(url: str, *, wait_for_selector: Optional[str] = None, timeout: int = 45_000) -> str:
    async with async_playwright() as playwright:
        browser = await playwright.chromium.launch(headless=True, args=PLAYWRIGHT_BROWSER_ARGS)
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
    if "playstation.com" not in url:
        return

    await _dismiss_playstation_cookie_banner(page)
    await _bypass_playstation_age_gate(page)


async def _dismiss_playstation_cookie_banner(page: Page) -> None:
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
            # If the function times out we still attempt to click in case the button is interactable.
            pass

        await page.click(confirm_selector)

        try:
            await page.wait_for_selector("#age-gate-year", state="detached", timeout=5_000)
        except Exception:
            # Some variants hide the age gate instead of removing it entirely.
            await page.wait_for_function(
                "() => { const el = document.querySelector('.age-gate'); return !el || el.getAttribute('aria-hidden') === 'true' || el.style.display === 'none'; }",
                timeout=5_000,
            )

        await page.wait_for_timeout(1_000)
    except Exception:
        # If anything goes wrong, we silently ignore so the normal flow can continue.
        return


def _collect_text_lines(paragraph: Optional[Tag]) -> List[str]:
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
    lines = [
        line.strip()
        for line in joined.split("\n")
        if line and line.strip()
    ]
    return lines


def _extract_image_url(media_block: Optional[Tag], base_url: str) -> Optional[str]:
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


def parse_psplus_html(html_content: str) -> List[PSPlusItem]:
    soup = BeautifulSoup(html_content, "html.parser")
    base_url = "https://www.playstation.com"

    items: List[PSPlusItem] = []
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
        boxes = section.select(".box--light, .box")
        if not boxes:
            continue

        for box in boxes:
            text_block = box.select_one(".txt-block__paragraph") or box
            title_el = text_block.find(["h1", "h2", "h3", "strong"])
            title = title_el.get_text(strip=True) if title_el else ""

            paragraph = text_block.find("p")
            lines = _collect_text_lines(paragraph)
            highlight_lines = [line for line in lines if line.startswith(("·", "•", "-", "—"))]
            description_lines = [line for line in lines if line not in highlight_lines]

            highlight = " / ".join(line.lstrip("·•-— ").strip() for line in highlight_lines) or None
            description = " ".join(description_lines).strip() or None

            media_block = box.select_one(".media-block")
            image = _extract_image_url(media_block, base_url)

            link_el = box.select_one(
                ".btn--cta__btn-container a, .button a, .buttonblock a, a.cta__primary"
            )
            link = link_el.get("href").strip() if link_el and link_el.get("href") else ""
            if link:
                link = urljoin(base_url, link)

            if not title or not link or link in seen_links:
                continue

            platform_el = text_block.select_one(".eyebrow, .eyebrow__text")
            platforms = platform_el.get_text(strip=True) if platform_el else None

            items.append(
                PSPlusItem(
                    title=title,
                    link=link,
                    image=image,
                    description=description or highlight or "PlayStation 官方暂未提供详细描述。",
                    highlight=highlight,
                    platforms=platforms,
                )
            )
            seen_links.add(link)

        if items:
            break

    return items


def _clean_html_text(raw: Optional[str]) -> Optional[str]:
    if not raw:
        return None
    text = BeautifulSoup(raw, "html.parser").get_text(" ", strip=True)
    return text or None


def parse_steam_freebies(html_content: str) -> List[SteamFreebieItem]:
    soup = BeautifulSoup(html_content, "html.parser")
    rows_container = soup.select_one("#search_resultsRows")
    if rows_container is None:
        return []

    items: List[SteamFreebieItem] = []

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
        original_price = original_price_el.get_text(strip=True) if original_price_el else None
        final_price = final_price_el.get_text(strip=True) if final_price_el else None

        review_el = row.select_one(".search_review_summary")
        review_summary = _clean_html_text(review_el.get("data-tooltip-html")) if review_el else None

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
            SteamFreebieItem(
                title=title,
                link=link,
                image=image,
                release_date=release_date,
                platforms=platforms,
                discount_text=discount_text,
                original_price=original_price,
                final_price=final_price,
                review_summary=review_summary,
            )
        )

    return items


@app.get("/psplus", response_model=PSPlusResponse)
async def get_psplus():
    async with _psplus_cache_lock:
        now = datetime.now(timezone.utc)
        cached_response = _psplus_cache["response"]
        cached_timestamp = _psplus_cache["timestamp"]

        if (
            cached_response is not None
            and cached_timestamp is not None
            and now - cached_timestamp < PSPLUS_CACHE_TTL
        ):
            return cached_response

        try:
            html_content = await fetch_page_html(
                PSN_SOURCE_URL,
                wait_for_selector="section#monthly-games",
            )
        except PlaywrightTimeoutError as exc:
            raise HTTPException(status_code=504, detail=f"Timeout fetching PlayStation page: {exc}") from exc
        except Exception as exc:
            raise HTTPException(status_code=502, detail=f"Failed to fetch PlayStation page: {exc}") from exc

        items = parse_psplus_html(html_content)
        if not items:
            raise HTTPException(
                status_code=502,
                detail="Failed to parse any items. The PlayStation page structure may have changed.",
            )

        refreshed_at = datetime.now(timezone.utc)
        response = PSPlusResponse(
            source=PSN_SOURCE_URL,
            fetched_at=refreshed_at,
            items=items,
        )
        _psplus_cache["response"] = response
        _psplus_cache["timestamp"] = refreshed_at
        return response


@app.get("/steam", response_model=SteamFreebieResponse)
async def get_steam_freebies():
    async with _steam_cache_lock:
        now = datetime.now(timezone.utc)
        cached_response = _steam_cache["response"]
        cached_timestamp = _steam_cache["timestamp"]

        if (
            cached_response is not None
            and cached_timestamp is not None
            and now - cached_timestamp < STEAM_CACHE_TTL
        ):
            return cached_response

        try:
            html_content = await fetch_page_html(
                STEAM_FREEBIES_URL,
                wait_for_selector="#search_resultsRows",
            )
        except PlaywrightTimeoutError as exc:
            raise HTTPException(status_code=504, detail=f"Timeout fetching Steam page: {exc}") from exc
        except Exception as exc:
            raise HTTPException(status_code=502, detail=f"Failed to fetch Steam freebies: {exc}") from exc

        items = parse_steam_freebies(html_content)
        if not items:
            raise HTTPException(
                status_code=502,
                detail="Failed to parse Steam freebies. The Steam page structure may have changed.",
            )

        refreshed_at = datetime.now(timezone.utc)
        response = SteamFreebieResponse(
            source=STEAM_FREEBIES_URL,
            fetched_at=refreshed_at,
            items=items,
        )
        _steam_cache["response"] = response
        _steam_cache["timestamp"] = refreshed_at
        return response


@app.get("/health")
async def health_check():
    return {"status": "ok"}


def main():
    uvicorn.run(
        "psn_api:app",
        host="0.0.0.0",
        port=8000,
        reload=False,
        log_level="info",
    )


if __name__ == "__main__":
    main()

