#!/usr/bin/env python3
"""
使用 HTML/Canvas 生成拼图图片
从 HTML 页面中提取分享数据，使用 JavaScript Canvas API 生成拼图并保存为图片
"""
import os
import sys
import json
import qrcode
import base64
from io import BytesIO
from pathlib import Path
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


def generate_webp_from_html(html_file: str, output_file: str, width: int = 1200, height: int = None):
    """
    从 HTML 文件中提取分享数据，使用 Canvas API 生成拼图图片
    
    Args:
        html_file: HTML 文件路径
        output_file: 输出的图片文件路径（支持 WebP 或 PNG）
        width: 已废弃，保留用于兼容性（拼图宽度由分享数据配置决定）
        height: 已废弃，保留用于兼容性（拼图高度由内容自动计算）
    """
    if not os.path.exists(html_file):
        print(f"错误: 找不到 HTML 文件 {html_file}")
        sys.exit(1)
    
    html_path = Path(html_file).absolute()
    
    # 处理文件路径：转换为 file:// URL
    if sys.platform == 'win32':
        file_url = html_path.as_uri()
    else:
        file_url = f"file://{html_path}"
    
    print(f"正在从 HTML 生成拼图: {html_file}")
    print(f"输出文件: {output_file}")
    
    try:
        with sync_playwright() as p:
            # 启动浏览器
            browser = p.chromium.launch(
                headless=True,
                args=[
                    '--no-sandbox',
                    '--disable-setuid-sandbox',
                    '--disable-dev-shm-usage',
                ]
            )
            
            # 创建浏览器上下文（不需要设置固定视口，因为我们要生成 Canvas）
            context = browser.new_context()
            
            # 创建页面
            page = context.new_page()
            
            # 加载 HTML 文件
            page.goto(file_url, wait_until='domcontentloaded', timeout=60000)

            # 等待页面加载完成（添加重试机制）
            try:
                page.wait_for_load_state('networkidle', timeout=30000)
            except Exception as e:
                print(f"⚠️  networkidle 等待超时: {e}，继续尝试...")

            # 等待 share-payload 元素出现（state='attached' 因为 script 标签始终隐藏）
            try:
                page.wait_for_selector('#share-payload', timeout=10000, state='attached')
            except Exception as e:
                print(f"⚠️  未找到 #share-payload 元素: {e}")

            # 提取分享数据（增加详细错误信息）
            result = page.evaluate("""
                () => {
                    try {
                        const payloadNode = document.getElementById('share-payload');
                        if (!payloadNode) {
                            return { error: 'no-payload-node' };
                        }
                        const raw = (payloadNode.textContent || payloadNode.innerText || '').trim();
                        if (!raw || raw === 'null' || raw === '') {
                            return { error: 'empty-payload', raw: raw };
                        }
                        const parsed = JSON.parse(raw);
                        return { success: true, data: parsed };
                    } catch (error) {
                        return { error: error.message, stack: error.stack };
                    }
                }
            """)

            # 解析结果
            if not result or result.get('error'):
                error_msg = result.get('error', 'unknown') if result else 'no-result'
                print(f"❌ 获取分享数据失败: {error_msg}")
                if result and result.get('stack'):
                    print(f"   堆栈: {result['stack'][:200]}")
                browser.close()
                sys.exit(1)

            share_payload = result.get('data')
            if not share_payload:
                print("❌ 分享数据为空，无法生成拼图")
                browser.close()
                sys.exit(1)

            # 检查是否有有效的分享数据
            sections = share_payload.get('sections', [])
            if not sections or not any(section.get('items') for section in sections):
                print("❌ 分享数据中没有有效的条目，无法生成拼图")
                browser.close()
                sys.exit(1)
            
            print(f"找到 {len(sections)} 个分享区块，共 {share_payload.get('totalItems', 0)} 个条目")
            
            # 等待字体加载
            try:
                page.evaluate("""
                    async () => {
                        if (document.fonts && document.fonts.ready) {
                            await document.fonts.ready;
                        }
                    }
                """)
            except Exception:
                pass
            
            # 执行 Canvas 渲染代码
            qr_url = 'https://gbtgame.me'
            qr_code_base64 = generate_qr_base64(qr_url, 100)

            image_base64 = page.evaluate("""
async ({payload, qrCodeBase64}) => {
                    const config = payload.config;
                    const sections = payload.sections;

                    const qrCodeDataUrl = qrCodeBase64 ? "data:image/png;base64," + qrCodeBase64 : null;

                    // 计算画布高度
                    function measureCanvasHeight(sections, config) {
                        const footerHeight = 160;
                        let total = config.padding * 2 + config.titleBlockHeight;
                        for (let i = 0; i < sections.length; i += 1) {
                            const section = sections[i];
                            total += 56;
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

                    // 加载图片（支持跨域）
                    async function loadCover(url) {
                        if (!url) return null;
                        try {
                            const image = new Image();
                            image.crossOrigin = 'anonymous';
                            image.decoding = 'async';
                            return await new Promise((resolve, reject) => {
                                image.onload = () => resolve(image);
                                image.onerror = () => reject(new Error('Image load failed'));
                                image.src = url;
                            });
                        } catch (error) {
                            console.debug('Share cover load failed', error);
                            return null;
                        }
                    }

                    // 文本换行
                    function wrapText(ctx, text, maxWidth, maxLines) {
                        if (!text) return [];
                        const normalized = text.replace(/\s+/g, ' ').trim();
                        if (!normalized) return [];
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
                            while (lastLine.length > 0 && ctx.measureText(lastLine + '…').width > maxWidth) {
                                lastLine = lastLine.slice(0, -1);
                            }
                            truncated[maxLines - 1] = lastLine ? lastLine + '…' : '…';
                            return truncated;
                        }

                        return lines;
                    }

                    // 绘制换行文本
                    function drawWrappedText(ctx, text, options) {
                        if (!text) return options.y;
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

                    // 字体函数
                    function font(weight, size, family) {
                        return weight + ' ' + size + 'px ' + family;
                    }

                    // 绘制卡片
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
                                coverHeight / coverImage.height
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

                        // Title: white bold 22px uppercase
                        ctx.fillStyle = '#ffffff';
                        ctx.font = font(config.fontWeights.bold, 22, config.fontFamily);
                        ctx.fillText(item.title.toUpperCase(), textX, cursorY);
                        cursorY += 30;

                        // Description: gray 14px, max 2 lines
                        if (item.description) {
                            cursorY = drawWrappedText(ctx, item.description, {
                                x: textX, y: cursorY, width: textWidth, lineHeight: 20,
                                font: font(config.fontWeights.regular, 14, config.fontFamily),
                                color: '#888888', maxLines: 2
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

                        // Timer: red bold 20px
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

                    // 绘制ITAD卡片
                    async function drawItadCard(ctx, item, config, x, y, width) {
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

                        // Timer: red bold
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

                    // 创建画布
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
                        config.padding, cursorY
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
                        cursorY + qrSize + 32
                    );
                    ctx.textAlign = 'left';

                    // 导出为 base64
                    return canvas.toDataURL('image/png');
                }""", {"payload": share_payload, "qrCodeBase64": qr_code_base64})
            
            # 从 base64 数据 URL 中提取图片数据
            if not image_base64 or not image_base64.startswith('data:image'):
                print("❌ Canvas 渲染失败，未生成图片数据")
                browser.close()
                sys.exit(1)
            
            # 提取 base64 数据部分
            header, encoded = image_base64.split(',', 1)
            image_data = base64.b64decode(encoded)
            
            # 确定输出格式（根据文件扩展名）
            output_path = Path(output_file)
            actual_output_file = output_file
            
            # Canvas API 通常支持 PNG，但不一定支持 WebP
            # 如果用户要求 WebP，我们先保存为 PNG，然后尝试转换
            if output_path.suffix.lower() == '.webp':
                # 先保存为临时 PNG 文件
                temp_png = output_path.with_suffix('.png')
                with open(temp_png, 'wb') as f:
                    f.write(image_data)
                
                # 尝试使用 PIL 转换为 WebP（如果可用）
                try:
                    from PIL import Image as PILImage
                    img = PILImage.open(temp_png)
                    img.save(output_file, 'WEBP', quality=90)
                    temp_png.unlink()  # 删除临时 PNG 文件
                    print(f"✅ 已转换为 WebP 格式: {output_file}")
                except ImportError:
                    # 如果 PIL 不可用，保存为 PNG 并提示
                    actual_output_file = str(temp_png)
                    print(f"⚠️  Pillow 库未安装，无法转换为 WebP 格式")
                    print(f"⚠️  已保存为 PNG 格式: {actual_output_file}")
                    print(f"提示: 安装 Pillow 库以支持 WebP 转换: pip install Pillow")
                except Exception as e:
                    # 如果转换失败，使用 PNG
                    actual_output_file = str(temp_png)
                    print(f"⚠️  WebP 转换失败: {e}")
                    print(f"⚠️  已保存为 PNG 格式: {actual_output_file}")
            else:
                # 直接保存 PNG 或其他格式
                with open(actual_output_file, 'wb') as f:
                    f.write(image_data)
            
            # 关闭浏览器
            browser.close()
            
            # 检查文件是否生成成功
            if os.path.exists(actual_output_file):
                file_size = os.path.getsize(actual_output_file)
                print(f"✅ 拼图生成成功: {actual_output_file} ({file_size} bytes)")
            else:
                print(f"❌ 图片文件未生成: {actual_output_file}")
                sys.exit(1)
            
    except Exception as e:
        print(f"❌ 图片生成失败: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)


def main():
    """主函数"""
    if len(sys.argv) < 3:
        print("用法: python generate_image.py <html_file> <output_file> [width] [height]")
        print("示例: python generate_image.py index.html gameinfo.webp 1200")
        sys.exit(1)
    
    html_file = sys.argv[1]
    output_file = sys.argv[2]
    width = int(sys.argv[3]) if len(sys.argv) > 3 else 1200
    height = int(sys.argv[4]) if len(sys.argv) > 4 else None
    
    generate_webp_from_html(html_file, output_file, width, height)


if __name__ == "__main__":
    main()

