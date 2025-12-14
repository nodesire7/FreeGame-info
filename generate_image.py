#!/usr/bin/env python3
"""
使用 HTML/Canvas 生成拼图图片
从 HTML 页面中提取分享数据，使用 JavaScript Canvas API 生成拼图并保存为图片
"""
import os
import sys
import json
import base64
from pathlib import Path
from playwright.sync_api import sync_playwright


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
            
            # 等待页面加载完成
            page.wait_for_load_state('networkidle', timeout=30000)
            
            # 提取分享数据
            share_payload = page.evaluate("""
                () => {
                    const payloadNode = document.getElementById('share-payload');
                    if (!payloadNode) {
                        return null;
                    }
                    try {
                        const raw = (payloadNode.textContent || payloadNode.innerText || '').trim();
                        if (!raw || raw === 'null') {
                            return null;
                        }
                        return JSON.parse(raw);
                    } catch (error) {
                        console.error('Failed to parse share payload', error);
                        return null;
                    }
                }
            """)
            
            if not share_payload:
                print("❌ 未找到分享数据，无法生成拼图")
                print("提示: HTML 文件中需要包含 <script type='application/json' id='share-payload'> 元素")
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
            # 使用内联实现生成拼图（与 HTML 页面中的逻辑一致）
            image_base64 = page.evaluate("""
                async (payload) => {
                    const config = payload.config;
                    const sections = payload.sections;
                    
                    // 计算画布高度
                    function measureCanvasHeight(sections, config) {
                        let total = config.padding * 2 + config.titleBlockHeight;
                        for (let i = 0; i < sections.length; i += 1) {
                            const section = sections[i];
                            total += 40;
                            total += section.items.length * config.cardHeight;
                            if (section.items.length > 1) {
                                total += (section.items.length - 1) * config.cardGap;
                            }
                            if (i !== sections.length - 1) {
                                total += config.sectionGap;
                            }
                        }
                        return Math.ceil(total);
                    }
                    
                    // 绘制圆角矩形路径
                    function traceRoundedRect(ctx, x, y, width, height, radius) {
                        const r = Math.min(radius, width / 2, height / 2);
                        ctx.beginPath();
                        ctx.moveTo(x + r, y);
                        ctx.lineTo(x + width - r, y);
                        ctx.quadraticCurveTo(x + width, y, x + width, y + r);
                        ctx.lineTo(x + width, y + height - r);
                        ctx.quadraticCurveTo(x + width, y + height, x + width - r, y + height);
                        ctx.lineTo(x + r, y + height);
                        ctx.quadraticCurveTo(x, y + height, x, y + height - r);
                        ctx.lineTo(x, y + r);
                        ctx.quadraticCurveTo(x, y, x + r, y);
                        ctx.closePath();
                    }
                    
                    // 填充圆角矩形
                    function fillRoundedRect(ctx, x, y, width, height, radius, fillStyle, strokeStyle) {
                        traceRoundedRect(ctx, x, y, width, height, radius);
                        ctx.fillStyle = fillStyle;
                        ctx.fill();
                        if (strokeStyle) {
                            ctx.strokeStyle = strokeStyle;
                            ctx.stroke();
                        }
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
                    
                    // 文本换行（修复正则表达式转义）
                    function wrapText(ctx, text, maxWidth, maxLines) {
                        if (!text) return [];
                        // 规范化空白字符（将多个空白字符替换为单个空格）
                        const normalized = text.replace(/\\s+/g, ' ').trim();
                        if (!normalized) return [];
                        // 按字符分割，支持中文和 emoji
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
                        fillRoundedRect(
                            ctx, x, y, width, config.cardHeight, config.cardRadius,
                            'rgba(15, 24, 36, 0.92)', 'rgba(102, 192, 244, 0.2)'
                        );
                        
                        const coverX = x + config.cardInset;
                        const coverY = y + config.cardInset;
                        const coverHeight = config.cardHeight - config.cardInset * 2;
                        
                        ctx.save();
                        traceRoundedRect(ctx, coverX, coverY, config.coverWidth, coverHeight, config.coverRadius);
                        ctx.clip();
                        
                        const coverImage = await loadCover(item.coverUrl);
                        if (coverImage) {
                            const scale = Math.max(
                                config.coverWidth / coverImage.width,
                                coverHeight / coverImage.height
                            );
                            const drawWidth = coverImage.width * scale;
                            const drawHeight = coverImage.height * scale;
                            const dx = coverX + (config.coverWidth - drawWidth) / 2;
                            const dy = coverY + (coverHeight - drawHeight) / 2;
                            ctx.drawImage(coverImage, dx, dy, drawWidth, drawHeight);
                        } else {
                            ctx.fillStyle = '#11202f';
                            ctx.fillRect(coverX, coverY, config.coverWidth, coverHeight);
                            ctx.fillStyle = '#305677';
                            ctx.font = font(config.fontWeights.regular, 18, config.fontFamily);
                            ctx.textAlign = 'center';
                            ctx.fillText('封面缺失', coverX + config.coverWidth / 2, coverY + coverHeight / 2 - 10);
                            ctx.textAlign = 'left';
                        }
                        ctx.restore();
                        
                        const textX = coverX + config.coverWidth + config.cardInset;
                        const textWidth = x + width - config.cardInset - textX;
                        let cursorY = y + config.cardInset;
                        
                        cursorY = drawWrappedText(ctx, item.title, {
                            x: textX, y: cursorY, width: textWidth, lineHeight: 32,
                            font: font(config.fontWeights.semibold, 26, config.fontFamily),
                            color: '#f3f6fb', maxLines: 2
                        }) + 6;
                        
                        cursorY = drawWrappedText(ctx, item.primary, {
                            x: textX, y: cursorY, width: textWidth, lineHeight: 26,
                            font: font(config.fontWeights.regular, 20, config.fontFamily),
                            color: '#66c0f4', maxLines: 2
                        });
                        
                        if (item.secondary) {
                            cursorY = drawWrappedText(ctx, item.secondary, {
                                x: textX, y: cursorY, width: textWidth, lineHeight: 24,
                                font: font(config.fontWeights.regular, 18, config.fontFamily),
                                color: '#9bb5d0', maxLines: 1
                            });
                        }
                        
                        if (item.tertiary) {
                            cursorY = drawWrappedText(ctx, item.tertiary, {
                                x: textX, y: cursorY, width: textWidth, lineHeight: 24,
                                font: font(config.fontWeights.regular, 16, config.fontFamily),
                                color: '#7f9bb8', maxLines: 2
                            });
                        }
                        
                        if (item.description) {
                            drawWrappedText(ctx, item.description, {
                                x: textX, y: cursorY + 4, width: textWidth, lineHeight: 24,
                                font: font(config.fontWeights.regular, 16, config.fontFamily),
                                color: '#7891ab', maxLines: 3
                            });
                        }
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
                    
                    // 绘制背景
                    const gradient = ctx.createLinearGradient(0, 0, config.width, height);
                    gradient.addColorStop(0, 'rgba(10, 18, 29, 0.96)');
                    gradient.addColorStop(1, 'rgba(6, 12, 21, 0.9)');
                    ctx.fillStyle = gradient;
                    ctx.fillRect(0, 0, config.width, height);
                    
                    // 绘制标题
                    let cursorY = config.padding;
                    ctx.fillStyle = '#f3f6fb';
                    ctx.font = font(config.fontWeights.semibold, 42, config.fontFamily);
                    ctx.fillText('白嫖游戏信息', config.padding, cursorY);
                    cursorY += 54;
                    
                    ctx.font = font(config.fontWeights.regular, 20, config.fontFamily);
                    ctx.fillStyle = '#a0bed8';
                    ctx.fillText('Epic · Steam · PlayStation 限免速览', config.padding, cursorY);
                    cursorY += 36;
                    
                    ctx.font = font(config.fontWeights.light, 18, config.fontFamily);
                    ctx.fillStyle = '#7f9bb8';
                    ctx.fillText(
                        '生成时间：' + payload.generatedAtDisplay + ' · 条目数：' + payload.totalItems,
                        config.padding, cursorY
                    );
                    cursorY = config.padding + config.titleBlockHeight;
                    
                    // 绘制各个区块
                    const cardWidth = config.width - config.padding * 2;
                    for (let sectionIndex = 0; sectionIndex < sections.length; sectionIndex += 1) {
                        const section = sections[sectionIndex];
                        ctx.font = font(config.fontWeights.semibold, 28, config.fontFamily);
                        ctx.fillStyle = '#66c0f4';
                        ctx.fillText(section.title, config.padding, cursorY);
                        cursorY += 40;
                        
                        for (let itemIndex = 0; itemIndex < section.items.length; itemIndex += 1) {
                            if (itemIndex > 0) {
                                cursorY += config.cardGap;
                            }
                            await drawCard(ctx, section.items[itemIndex], config, config.padding, cursorY, cardWidth);
                            cursorY += config.cardHeight;
                        }
                        
                        if (sectionIndex !== sections.length - 1) {
                            cursorY += config.sectionGap;
                        }
                    }
                    
                    // 导出为 base64
                    return canvas.toDataURL('image/png');
                }
            """, share_payload)
            
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

