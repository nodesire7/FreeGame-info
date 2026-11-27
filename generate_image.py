"""用站内同一套卡片绘图代码导出当期或历史分享图。"""
import base64
from functools import lru_cache
from io import BytesIO
import json
from pathlib import Path
import re
import sys
from tempfile import NamedTemporaryFile

from bs4 import BeautifulSoup
from playwright.sync_api import sync_playwright, Error as PlaywrightError
import qrcode


ASSETS = Path(__file__).resolve().parent
SITE = "https://gameinfo.gbtgame.me/"


def generate_qr_base64(data, size=100):
    buffer = BytesIO()
    qrcode.make(data).save(buffer, format="PNG")
    return base64.b64encode(buffer.getvalue()).decode("ascii")


@lru_cache(maxsize=8)
def poster_branding(url=SITE):
    logo = base64.b64encode((ASSETS / "logo.png").read_bytes()).decode("ascii")
    return {"logo": "data:image/png;base64," + logo,
            "qrImage": "data:image/png;base64," + generate_qr_base64(url)}


def build_share_html(payload):
    from render_html import _extract_style_block, serialize_for_client
    values = {"PAYLOAD": serialize_for_client({**poster_branding(payload.get("qrUrl") or SITE), **payload}),
              "STYLE": _extract_style_block((ASSETS / "epic-freebies.html.template").read_text()),
              "RENDERER": (ASSETS / "share-render.js").read_text()}
    return re.sub(r"\{\{([A-Z]+)\}\}", lambda m: values[m[1]], (ASSETS / "share_template.html").read_text())


def _export(payload, output_file):
    output = Path(output_file)
    mime = "image/webp" if output.suffix.lower() == ".webp" else "image/png"
    with sync_playwright() as p:
        with p.chromium.launch() as browser:
            page = browser.new_page(viewport={"width": 1080, "height": 900})
            # The build can embed public covers from stores without browser CORS headers.
            def embed_cover(route):
                try:
                    response = route.fetch(timeout=6500)
                    route.fulfill(response=response, headers={**response.headers, "access-control-allow-origin": "*"})
                except PlaywrightError:
                    route.abort()
            page.route(re.compile(r"^https?://"), embed_cover)
            page.set_content(build_share_html(payload), wait_until="domcontentloaded")
            result = page.evaluate("async mime => (await window.posterReady).toDataURL(mime, 0.9)", mime)
    if not result.startswith("data:" + mime + ";base64,"):
        raise ValueError("分享图导出格式异常")
    with NamedTemporaryFile(dir=output.parent, delete=False) as pending:
        pending.write(base64.b64decode(result.partition(",")[2], validate=True))
    Path(pending.name).replace(output)
    return str(output)


def generate_share_screenshot(snapshot, output_file, qr_url=SITE):
    from render_html import build_share_payload
    payload = build_share_payload(snapshot)
    if payload:
        return _export({**payload, **poster_branding(qr_url)}, output_file)
    return None


def generate_webp_from_html(html_file, output_file, width=1080, height=None):
    soup = BeautifulSoup(Path(html_file).read_text(), "html.parser")
    node = soup.select_one("#share-payload")
    payload = json.loads(node.string) if node and node.string else None
    if not payload:
        raise ValueError("没有可导出的活动")
    return _export(payload, output_file)


if __name__ == "__main__":
    generate_webp_from_html(*sys.argv[1:3])
