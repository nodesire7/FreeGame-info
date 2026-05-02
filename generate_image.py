#!/usr/bin/env python3
"""
使用 HTML + Playwright 截图生成分享拼图
构建一个完整的 HTML 页面，使用 Tailwind CSS CDN 渲染，然后截图保存为图片
"""
import os
import sys
import base64
from io import BytesIO
from pathlib import Path
from typing import Optional

import qrcode
from PIL import Image
from playwright.sync_api import sync_playwright


def generate_qr_base64(data: str, size: int = 100) -> str:
    """Generate QR code as base64 PNG"""
    qr = qrcode.QRCode(version=1, box_size=10, border=4)
    qr.add_data(data)
    qr.make(fit=True)
    img = qr.make_image(fill_color="white", back_color="black")
    buffer = BytesIO()
    img.save(buffer, format='PNG')
    return base64.b64encode(buffer.getvalue()).decode()


def build_share_html(payload: dict) -> str:
    """根据分享数据构建完整的 HTML 页面（使用 Tailwind CSS CDN）"""
    qr_data = payload.get('qrUrl', 'https://gbtgame.me')
    qr_base64 = generate_qr_base64(qr_data, 100)
    qr_data_url = f"data:image/png;base64,{qr_base64}"

    sections_html = ""
    for section in payload.get('sections', []):
        items_html = ""
        section_type = section.get('type', '')
        is_itad = section_type == 'itad'

        for item in section.get('items', []):
            if is_itad:
                cover_url = item.get('coverUrl', '')
                cover_html = f'<img src="{cover_url}" class="w-full h-full object-cover" loading="lazy">' if cover_url else '<div class="w-full h-full bg-zinc-800 flex items-center justify-center text-zinc-600 text-xs">暂无封面</div>'
                items_html += f"""
                <div class="flex flex-col lg:flex-row gap-6 bg-zinc-950 border-4 border-zinc-800 p-4">
                    <div class="lg:w-2/5 relative">
                        <div class="border-4 border-white aspect-video overflow-hidden">
                            {cover_html}
                        </div>
                        <div class="absolute -bottom-2 -left-2 bg-red-600 text-white px-3 py-1 font-black italic text-xs">{item.get('store', 'ITAD')}</div>
                    </div>
                    <div class="lg:w-3/5 flex flex-col justify-between py-2 gap-3">
                        <div class="flex flex-col gap-2">
                            <span class="text-lg font-black text-red-600 italic">{item.get('title', '')}</span>
                            <span class="text-zinc-500 text-xs font-bold uppercase">{item.get('tertiary', '')}</span>
                            <span class="text-lg font-black text-red-600 italic">{item.get('primary', '')}</span>
                            <p class="text-zinc-500 text-xs leading-relaxed line-clamp-2">{item.get('description', '')}</p>
                        </div>
                        <div class="flex items-center gap-4 mt-2">
                            <span class="text-zinc-500 text-xs font-bold uppercase">来自 {item.get('store', 'ITAD')}</span>
                        </div>
                    </div>
                </div>"""
            else:
                cover_url = item.get('coverUrl', '')
                cover_html = f'<img src="{cover_url}" class="w-full h-full object-cover" loading="lazy">' if cover_url else '<div class="w-full h-full bg-zinc-800 flex items-center justify-center text-zinc-600 text-xs">暂无封面</div>'
                items_html += f"""
                <div class="flex flex-col lg:flex-row gap-6 bg-zinc-950 border-4 border-zinc-800 p-4">
                    <div class="lg:w-2/5 relative">
                        <div class="border-4 border-white aspect-video overflow-hidden">
                            {cover_html}
                        </div>
                        <div class="absolute -bottom-2 -left-2 bg-red-600 text-white px-3 py-1 font-black italic text-xs">{item.get('originalPrice', '')}</div>
                    </div>
                    <div class="lg:w-3/5 flex flex-col justify-between py-2 gap-3">
                        <div>
                            <h4 class="text-xl font-black italic uppercase tracking-tight">{item.get('title', '')}</h4>
                            <p class="text-zinc-500 text-xs leading-relaxed mt-2 line-clamp-2">{item.get('description', '')}</p>
                        </div>
                        <div class="flex items-center justify-between gap-4 mt-2 pt-2 border-t border-dashed border-zinc-700">
                            <div class="flex flex-col">
                                <span class="text-lg font-black text-red-600 italic">{item.get('primary', '')}</span>
                                <span class="text-zinc-500 text-xs font-bold uppercase">{item.get('secondary', '')}</span>
                            </div>
                            <div class="bg-white text-black px-6 py-2 font-black italic text-xs">{item.get('cta', '立即抢夺')}</div>
                        </div>
                    </div>
                </div>"""

        sections_html += f"""
        <div class="mb-8">
            <div class="flex items-center gap-3 mb-6">
                <div class="w-2 h-10 bg-red-600"></div>
                <h3 class="text-2xl font-black italic uppercase">{section.get('title', '')}</h3>
            </div>
            <div class="grid grid-cols-1 xl:grid-cols-2 gap-6">
                {items_html}
            </div>
        </div>"""

    html = f"""<!DOCTYPE html>
<html lang="zh-CN">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=1080">
    <title>白嫖游戏速报</title>
    <script src="https://cdn.tailwindcss.com"></script>
    <link rel="preconnect" href="https://fonts.googleapis.com">
    <link href="https://fonts.googleapis.com/css2?family=Noto+Sans+SC:wght@300;400;600;700;900&display=swap" rel="stylesheet">
    <script>
        tailwind.config = {{
            theme: {{
                extend: {{
                    fontFamily: {{
                        sans: ['Noto Sans SC', 'Microsoft YaHei', 'PingFang SC', 'sans-serif'],
                    }},
                }},
            }},
        }}
    </script>
    <style>
        body {{ font-family: 'Noto Sans SC', 'Microsoft YaHei', 'PingFang SC', sans-serif; }}
        .line-clamp-2 {{ display: -webkit-box; -webkit-line-clamp: 2; -webkit-box-orient: vertical; overflow: hidden; }}
    </style>
</head>
<body class="bg-black text-white m-0 p-8" style="width: 1080px;">
    <!-- Header -->
    <div class="bg-zinc-950 border-4 border-white p-6 mb-8 relative overflow-hidden">
        <div class="absolute inset-0 opacity-10 pointer-events-none" style="background-image: radial-gradient(#fff 2px, transparent 2px); background-size: 28px 28px;"></div>
        <div class="relative z-10 flex justify-between items-center">
            <div class="flex items-center gap-4">
                <svg class="w-8 h-8 text-red-600" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="4"><path d="M12 3L2 21H22L12 3Z" /></svg>
                <div>
                    <h1 class="text-4xl font-black text-white italic flex items-center gap-3">
                        <span class="text-red-600">/</span>白嫖游戏速报
                    </h1>
                    <p class="text-zinc-400 text-sm mt-1">GBTGAME FREEBIES · EPIC · STEAM · PSN · ITAD</p>
                </div>
            </div>
            <div class="text-right">
                <p class="text-zinc-500 text-xs font-bold italic">GENERATED: {payload.get('generatedAtDisplay', '')}</p>
                <p class="text-zinc-500 text-xs font-bold italic">{payload.get('totalItems', 0)} ITEMS</p>
            </div>
        </div>
    </div>

    <!-- Red accent bar -->
    <div class="h-2 bg-red-600 mb-8"></div>

    <!-- Content Sections -->
    {sections_html}

    <!-- Footer with QR -->
    <div class="bg-zinc-950 border-t-4 border-white pt-6 pb-4 mt-8 flex items-center justify-center gap-8">
        <div class="flex flex-col items-center gap-2">
            <img src="{qr_data_url}" class="w-24 h-24" alt="QR Code">
            <span class="text-white text-xs font-bold uppercase">扫描获取最新限免</span>
        </div>
        <div class="flex flex-col gap-1">
            <span class="text-red-600 font-black text-2xl italic">GBTGAME.ME</span>
            <span class="text-zinc-500 text-xs font-bold italic">EPIC · STEAM · PSN · ITAD</span>
        </div>
    </div>
</body>
</html>"""
    return html


def generate_share_screenshot(snapshot: dict, output_file: str, qr_url: str = "https://gbtgame.me") -> Optional[str]:
    """
    根据快照数据生成分享截图（Build 时直接调用，无需浏览器交互）

    Args:
        snapshot: 完整快照数据
        output_file: 输出的图片文件路径
        qr_url: 二维码指向的 URL

    Returns:
        生成的 WebP 文件路径，失败返回 None
    """
    import tempfile

    try:
        from render_html import build_share_payload, serialize_for_client
    except ImportError:
        print("⚠️  无法导入 render_html，使用内联方式构建分享数据")
        return None

    # 构建分享数据
    share_payload = build_share_payload(snapshot)
    if not share_payload:
        print("⚠️  分享数据为空，跳过分享截图生成")
        return None

    # 添加 QR URL
    share_payload['qrUrl'] = qr_url

    # 生成完整 HTML
    share_html = build_share_html(share_payload)

    # 写入临时文件
    with tempfile.NamedTemporaryFile(mode='w', suffix='.html', encoding='utf-8', delete=False) as f:
        f.write(share_html)
        temp_html_path = f.name

    try:
        # 使用 Playwright 截图
        result = _playwright_screenshot(temp_html_path, output_file)
        return result
    finally:
        # 清理临时文件
        try:
            os.unlink(temp_html_path)
        except Exception:
            pass


def _playwright_screenshot(html_file: str, output_file: str) -> Optional[str]:
    """使用 Playwright 对 HTML 文件截图"""
    from pathlib import Path

    if not os.path.exists(html_file):
        print(f"错误: 找不到 HTML 文件 {html_file}")
        return None

    html_path = Path(html_file).absolute()
    output_path = Path(output_file)
    actual_output = output_file

    try:
        with sync_playwright() as p:
            browser = p.chromium.launch(
                headless=True,
                args=[
                    '--no-sandbox',
                    '--disable-setuid-sandbox',
                    '--disable-dev-shm-usage',
                ]
            )

            context = browser.new_context(viewport={'width': 1080, 'height': 1920})
            page = context.new_page()

            page.goto(f"file://{html_path}", wait_until='domcontentloaded', timeout=60000)

            try:
                page.wait_for_load_state('networkidle', timeout=30000)
            except Exception as e:
                print(f"⚠️  networkidle 等待超时: {e}，继续...")

            page.wait_for_timeout(2000)

            screenshot_bytes = page.screenshot(type='png', full_page=True)
            page.close()
            browser.close()

        # 保存为 PNG（后续可转为 WebP）
        if output_path.suffix.lower() == '.webp':
            temp_png = output_path.with_suffix('.png')
            temp_png.write_bytes(screenshot_bytes)
            try:
                img = Image.open(temp_png).convert('RGBA')
                img.save(output_file, 'PNG')
                temp_png.unlink()
                img.close()
            except Exception as e:
                print(f"⚠️  WebP 转换失败: {e}，保存为 PNG")
                actual_output = str(temp_png)
        else:
            Path(output_file).write_bytes(screenshot_bytes)

        file_size = Path(actual_output).stat().st_size
        print(f"✅ 分享截图生成成功: {actual_output} ({file_size} bytes)")
        return actual_output

    except Exception as e:
        print(f"❌ 截图失败: {e}")
        import traceback
        traceback.print_exc()
        return None


def generate_webp_from_html(html_file: str, output_file: str, width: int = 1080, height: int = None):
    """
    从 HTML 文件中提取分享数据，使用 HTML 截图方式生成拼图

    Args:
        html_file: HTML 文件路径
        output_file: 输出的图片文件路径（支持 WebP 或 PNG）
        width: 截图宽度（默认 1080）
        height: 高度（默认 None，由内容决定）
    """
    if not os.path.exists(html_file):
        print(f"错误: 找不到 HTML 文件 {html_file}")
        sys.exit(1)

    html_path = Path(html_file).absolute()

    print(f"正在从 HTML 生成拼图: {html_file}")
    print(f"输出文件: {output_file}")

    try:
        with sync_playwright() as p:
            browser = p.chromium.launch(
                headless=True,
                args=[
                    '--no-sandbox',
                    '--disable-setuid-sandbox',
                    '--disable-dev-shm-usage',
                ]
            )

            context = browser.new_context(
                viewport={'width': width, 'height': 1920}
            )
            page = context.new_page()

            # 加载 HTML 文件
            page.goto(f"file://{html_path}", wait_until='domcontentloaded', timeout=60000)

            # 等待页面加载完成
            try:
                page.wait_for_load_state('networkidle', timeout=30000)
            except Exception as e:
                print(f"⚠️  networkidle 等待超时: {e}，继续尝试...")

            # 等待 share-payload 元素
            try:
                page.wait_for_selector('#share-payload', timeout=10000, state='attached')
            except Exception as e:
                print(f"⚠️  未找到 #share-payload 元素: {e}")

            # 提取分享数据
            result = page.evaluate("""
                () => {
                    try {
                        const payloadNode = document.getElementById('share-payload');
                        if (!payloadNode) return { error: 'no-payload-node' };
                        const raw = (payloadNode.textContent || payloadNode.innerText || '').trim();
                        if (!raw || raw === 'null' || raw === '') return { error: 'empty-payload' };
                        return { success: true, data: JSON.parse(raw) };
                    } catch (error) {
                        return { error: error.message };
                    }
                }
            """)

            if not result or result.get('error'):
                error_msg = result.get('error', 'unknown')
                print(f"❌ 获取分享数据失败: {error_msg}")
                browser.close()
                sys.exit(1)

            share_payload = result.get('data')
            sections = share_payload.get('sections', [])
            if not sections or not any(section.get('items') for section in sections):
                print("❌ 分享数据中没有有效的条目，无法生成拼图")
                browser.close()
                sys.exit(1)

            print(f"找到 {len(sections)} 个分享区块，共 {share_payload.get('totalItems', 0)} 个条目")

            # 构建 QR URL（使用当前页面 URL 或占位符）
            qr_url = 'https://gbtgame.me'

            # 为 payload 添加 QR 信息
            share_payload['qrUrl'] = qr_url

            # 生成完整 HTML
            share_html = build_share_html(share_payload)

            # 创建新页面来渲染分享 HTML
            page2 = context.new_page()
            page2.set_content(share_html, wait_until='networkidle', timeout=60000)

            # 等待字体和图片加载
            try:
                page2.wait_for_load_state('networkidle', timeout=30000)
            except Exception:
                pass

            # 等待一点时间让所有资源加载
            page2.wait_for_timeout(2000)

            # 截图
            screenshot_bytes = page2.screenshot(
                type='png',
                full_page=True
            )
            page2.close()
            browser.close()

        # 保存为 WebP
        output_path = Path(output_file)
        actual_output_file = output_file

        if output_path.suffix.lower() == '.webp':
            temp_png = output_path.with_suffix('.png')
            temp_png.write_bytes(screenshot_bytes)
            try:
                img = Image.open(temp_png).convert('RGBA')
                img.save(temp_png, 'PNG')
                img.save(output_file, 'PNG')
                temp_png.unlink()
                img.close()
            except Exception as e:
                print(f"⚠️  WebP 转换失败: {e}，保存为 PNG")
                actual_output_file = temp_png
        else:
            Path(output_file).write_bytes(screenshot_bytes)

        file_size = Path(actual_output_file).stat().st_size
        print(f"✅ 拼图生成成功: {actual_output_file} ({file_size} bytes)")

    except Exception as e:
        print(f"❌ 生成失败: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)


if __name__ == '__main__':
    if len(sys.argv) < 3:
        print("用法: python generate_image.py <html_file> <output_file>")
        sys.exit(1)
    generate_webp_from_html(sys.argv[1], sys.argv[2])
