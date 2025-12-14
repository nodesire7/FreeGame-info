#!/usr/bin/env python3
"""
生成 HTML 静态页面
"""
import html
import json
import os
import re
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional

# 常量
SHARE_CANVAS_WIDTH = 1080
SHARE_PADDING = 72
SHARE_TITLE_BLOCK_HEIGHT = 120
SHARE_SECTION_GAP = 52
SHARE_CARD_HEIGHT = 220
SHARE_CARD_GAP = 24
SHARE_CARD_RADIUS = 24
SHARE_CARD_INSET = 24
SHARE_COVER_WIDTH = 268
SHARE_COVER_RADIUS = 18
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


def format_full_datetime(timestamp: Optional[int] = None) -> str:
    """格式化完整日期时间"""
    if not timestamp:
        return "待定"
    dt = datetime.fromtimestamp(timestamp / 1000)
    return dt.strftime("%Y-%m-%d %H:%M")


def format_datetime(timestamp: Optional[int] = None) -> str:
    """格式化日期时间"""
    if not timestamp:
        return "待定"
    dt = datetime.fromtimestamp(timestamp / 1000)
    return dt.strftime("%m月%d日 %H:%M")


def format_date_range(start_at: Optional[int] = None, end_at: Optional[int] = None) -> str:
    """格式化日期范围"""
    if start_at and end_at:
        start = datetime.fromtimestamp(start_at / 1000).strftime("%m月%d日 %H:%M")
        end = datetime.fromtimestamp(end_at / 1000).strftime("%m月%d日 %H:%M")
        return f"{start} 至 {end}"
    if end_at:
        end = datetime.fromtimestamp(end_at / 1000).strftime("%m月%d日 %H:%M")
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
    diff_ms = target_timestamp - int(datetime.now().timestamp() * 1000)
    if diff_ms <= 0:
        return finished_text
    minutes = diff_ms // 60000
    days = minutes // (60 * 24)
    hours = (minutes % (60 * 24)) // 60
    mins = minutes % 60
    parts = []
    if days:
        parts.append(f"{days} 天")
    if hours:
        parts.append(f"{hours} 小时")
    if not days and mins:
        parts.append(f"{mins} 分钟")
    if not parts:
        return f"{prefix} 不足 1 分钟"
    return f"{prefix} {' '.join(parts)}"


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
    publisher = game.get("publisher") or game.get("seller")
    if publisher:
        summary.append(f"发行：{publisher}")
    developer = game.get("developer")
    if developer and developer != publisher:
        summary.append(f"开发：{developer}")
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

    if is_free_now and free_end_at:
        primary_timer = format_remaining(
            free_end_at, prefix="剩余", finished_text="已结束"
        )
        secondary_timer = f"截止：{format_datetime(free_end_at)}"
    elif free_start_at and free_start_at > int(datetime.now().timestamp() * 1000):
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

    link_text = "查看详情" if variant == "upcoming" else "前往领取"
    description = (game.get("description") or "Epic 官方暂未提供详细介绍。").strip()

    summary_html = ""
    if summary:
        summary_html = f'<div class="epic-freebies__card-summary">{"".join(f"<span>{escape_html(text)}</span>" for text in summary)}</div>'

    return f"""<article class="epic-freebies__card">
  <div class="epic-freebies__card-cover">
    {cover_html}
  </div>
  <div class="epic-freebies__card-body">
    <header class="epic-freebies__card-header">
      <div class="epic-freebies__card-title-row">
        <h3 class="epic-freebies__card-title">{escape_html(game["title"])}</h3>
        <span class="epic-freebies__badge">原价 {escape_html(price_label)}</span>
      </div>
      <p class="epic-freebies__card-desc">{escape_html(description)}</p>
    </header>
    {summary_html}
    <div class="epic-freebies__card-footer">
      <div class="epic-freebies__card-timing">
        <span class="epic-freebies__meta-primary">{escape_html(primary_timer)}</span>
        <span class="epic-freebies__meta-secondary">{escape_html(deadline_text)}</span>
      </div>
      <a class="epic-freebies__card-link" href="{escape_attribute(game["link"])}" target="_blank" rel="noopener noreferrer">{link_text}</a>
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
        summary_html = f'<div class="epic-freebies__card-summary">{"".join(f"<span>{escape_html(text)}</span>" for text in summary)}</div>'

    return f"""<article class="epic-freebies__card">
  <div class="epic-freebies__card-cover">
    {cover_html}
  </div>
  <div class="epic-freebies__card-body">
    <header class="epic-freebies__card-header">
      <div class="epic-freebies__card-title-row">
        <h3 class="epic-freebies__card-title">{escape_html(game["title"])}</h3>
        <span class="epic-freebies__badge">Steam 限免</span>
      </div>
      <p class="epic-freebies__card-desc">{escape_html(description)}</p>
    </header>
    {summary_html}
    <div class="epic-freebies__card-footer">
      <div class="epic-freebies__card-timing">
        <span class="epic-freebies__meta-primary">{escape_html(price_text)}</span>
        <span class="epic-freebies__meta-secondary">{escape_html(price_detail)}</span>
      </div>
      <a class="epic-freebies__card-link" href="{escape_attribute(game["link"])}" target="_blank" rel="noopener noreferrer">前往 Steam 领取</a>
    </div>
  </div>
</article>"""


def render_psn_card(game: Dict[str, Any]) -> str:
    """渲染 PlayStation 游戏卡片"""
    cover = game.get("image", "")
    cover_html = (
        f'<img src="{escape_attribute(cover)}" alt="{escape_attribute(game["title"])}" loading="lazy">'
        if cover
        else '<span>暂无封面</span>'
    )

    timing_parts = []
    if game.get("highlight"):
        timing_parts.append(
            f'<span class="epic-freebies__meta-primary">{escape_html(game["highlight"])}</span>'
        )
    if game.get("platforms"):
        timing_parts.append(
            f'<span class="epic-freebies__meta-secondary">{escape_html(game["platforms"])}</span>'
        )
    if game.get("period"):
        timing_parts.append(
            f'<span class="epic-freebies__meta-secondary">领取时间：{escape_html(game["period"])}</span>'
        )

    description = (game.get("description") or "当前仍在同步 PlayStation 官方描述。").strip()

    return f"""<article class="epic-freebies__card">
  <div class="epic-freebies__card-cover">
    {cover_html}
  </div>
  <div class="epic-freebies__card-content">
    <header class="epic-freebies__card-header">
      <div class="epic-freebies__card-title-row">
        <h3 class="epic-freebies__card-title">{escape_html(game["title"])}</h3>
        <span class="epic-freebies__badge">PlayStation</span>
      </div>
      <p class="epic-freebies__card-desc">{escape_html(description)}</p>
    </header>
    <div class="epic-freebies__card-footer">
      <div class="epic-freebies__card-timing">
        {"".join(timing_parts)}
      </div>
      <a class="epic-freebies__card-link" href="{escape_attribute(game["link"])}" target="_blank" rel="noopener noreferrer">前往 PS Store 查看</a>
    </div>
  </div>
</article>"""


def render_epic_section_content(items: List[Dict[str, Any]], empty_text: str, variant: str) -> str:
    """渲染 Epic 区块内容"""
    if not items:
        return f'<div class="epic-freebies__panel-empty">{escape_html(empty_text)}</div>'
    cards = "\n".join(render_epic_card(item, variant) for item in items)
    return f'<div class="epic-freebies__grid">\n{cards}\n</div>'


def render_steam_section_content(items: List[Dict[str, Any]], empty_text: str) -> str:
    """渲染 Steam 区块内容"""
    if not items:
        return f'<div class="epic-freebies__panel-empty">{escape_html(empty_text)}</div>'
    cards = "\n".join(render_steam_card(item) for item in items)
    return f'<div class="epic-freebies__grid">\n{cards}\n</div>'


def render_psn_section_content(items: List[Dict[str, Any]], empty_text: str) -> str:
    """渲染 PlayStation 区块内容"""
    if not items:
        return f'<div class="epic-freebies__panel-empty">{escape_html(empty_text)}</div>'
    cards = "\n".join(render_psn_card(item) for item in items)
    return f'<div class="epic-freebies__grid">\n{cards}\n</div>'


def get_share_client_script() -> str:
    """获取分享客户端脚本（完整版本）"""
    # 完整的 JavaScript 代码，包含分享图片生成功能
    # 从 render.service.ts 的 getShareClientScriptTemplate 方法提取
    return """(function() {
  'use strict';

  const root = document.querySelector('.epic-freebies');
  if (!root) {
    return;
  }

  const shareButton = root.querySelector('[data-share-button]');
  const tabs = Array.from(root.querySelectorAll('.epic-freebies__tab'));
  const panels = Array.from(root.querySelectorAll('.epic-freebies__panel'));

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
    shareButton.setAttribute('download', sharePayload.suggestedFileName || '乐赏限免拼图.png');
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

      const blob = await renderShareCanvas(payload);
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

  async function renderShareCanvas(payload) {
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
    paintBackground(ctx, height, config);

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
      config.padding,
      cursorY,
    );
    cursorY = config.padding + config.titleBlockHeight;

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

  function paintBackground(ctx, height, config) {
    const gradient = ctx.createLinearGradient(0, 0, config.width, height);
    gradient.addColorStop(0, 'rgba(10, 18, 29, 0.96)');
    gradient.addColorStop(1, 'rgba(6, 12, 21, 0.9)');
    ctx.fillStyle = gradient;
    ctx.fillRect(0, 0, config.width, height);
  }

  async function drawCard(ctx, item, config, x, y, width) {
    fillRoundedRect(
      ctx,
      x,
      y,
      width,
      config.cardHeight,
      config.cardRadius,
      'rgba(15, 24, 36, 0.92)',
      'rgba(102, 192, 244, 0.2)',
    );

    const coverX = x + config.cardInset;
    const coverY = y + config.cardInset;
    const coverHeight = config.cardHeight - config.cardInset * 2;

    ctx.save();
    traceRoundedRect(
      ctx,
      coverX,
      coverY,
      config.coverWidth,
      coverHeight,
      config.coverRadius,
    );
    ctx.clip();

    const coverImage = await loadCover(item.coverUrl);
    if (coverImage) {
      const scale = Math.max(
        config.coverWidth / coverImage.width,
        coverHeight / coverImage.height,
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
      ctx.fillText(
        '封面缺失',
        coverX + config.coverWidth / 2,
        coverY + coverHeight / 2 - 10,
      );
      ctx.textAlign = 'left';
    }
    ctx.restore();

    const textX = coverX + config.coverWidth + config.cardInset;
    const textWidth = x + width - config.cardInset - textX;
    let cursorY = y + config.cardInset;

    cursorY = drawWrappedText(ctx, item.title, {
      x: textX,
      y: cursorY,
      width: textWidth,
      lineHeight: 32,
      font: font(config.fontWeights.semibold, 26, config.fontFamily),
      color: '#f3f6fb',
      maxLines: 2,
    }) + 6;

    cursorY = drawWrappedText(ctx, item.primary, {
      x: textX,
      y: cursorY,
      width: textWidth,
      lineHeight: 26,
      font: font(config.fontWeights.regular, 20, config.fontFamily),
      color: '#66c0f4',
      maxLines: 2,
    });

    if (item.secondary) {
      cursorY = drawWrappedText(ctx, item.secondary, {
        x: textX,
        y: cursorY,
        width: textWidth,
        lineHeight: 24,
        font: font(config.fontWeights.regular, 18, config.fontFamily),
        color: '#9bb5d0',
        maxLines: 1,
      });
    }

    if (item.tertiary) {
      cursorY = drawWrappedText(ctx, item.tertiary, {
        x: textX,
        y: cursorY,
        width: textWidth,
        lineHeight: 24,
        font: font(config.fontWeights.regular, 16, config.fontFamily),
        color: '#7f9bb8',
        maxLines: 2,
      });
    }

    if (item.description) {
      drawWrappedText(ctx, item.description, {
        x: textX,
        y: cursorY + 4,
        width: textWidth,
        lineHeight: 24,
        font: font(config.fontWeights.regular, 16, config.fontFamily),
        color: '#7891ab',
        maxLines: 3,
      });
    }
  }

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

  function fillRoundedRect(
    ctx,
    x,
    y,
    width,
    height,
    radius,
    fillStyle,
    strokeStyle,
  ) {
    traceRoundedRect(ctx, x, y, width, height, radius);
    ctx.fillStyle = fillStyle;
    ctx.fill();
    if (strokeStyle) {
      ctx.strokeStyle = strokeStyle;
      ctx.stroke();
    }
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
      anchor.download = fileName || '乐赏限免拼图.png';
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
      if (isActive) {
        panel.removeAttribute('hidden');
      } else {
        panel.setAttribute('hidden', 'hidden');
      }
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
    epic_now = snapshot["epic"]["now"]
    epic_upcoming = snapshot["epic"]["upcoming"]
    steam = snapshot["steam"]
    psn = snapshot["psn"]

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

    if not sections:
        return None

    fetched_at = snapshot.get("fetchedAt")
    if fetched_at:
        dt = datetime.fromisoformat(fetched_at.replace("Z", "+00:00"))
        generated_at_timestamp = int(dt.timestamp() * 1000)
    else:
        generated_at_timestamp = int(datetime.now().timestamp() * 1000)

    total_items = sum(len(section["items"]) for section in sections)

    suggested_file_name = f"乐赏限免拼图-{datetime.now().strftime('%Y%m%d-%H%M')}.png"

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
            "fontWeights": {"light": 300, "regular": 400, "semibold": 600, "bold": 700},
            "fontFamily": f'"{SHARE_FONT_FAMILY}","Microsoft YaHei","PingFang SC","Heiti SC",sans-serif',
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

    tertiary_parts = []
    if price:
        tertiary_parts.append(f"原价 {price}")
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

    return {
        "title": sanitize_text(game.get("title", "")),
        "primary": sanitize_text(game.get("highlight", "PS Plus 会员福利")),
        "secondary": (
            f"可领取时间：{sanitize_text(game['period'])}" if game.get("period") else ""
        ),
        "tertiary": " · ".join(tertiary_parts),
        "description": sanitize_text(game.get("description", "")),
        "coverUrl": game.get("image"),
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


def render_html(snapshot: Dict[str, Any], template_path: str) -> str:
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

    epic_now = snapshot["epic"]["now"]
    epic_upcoming = snapshot["epic"]["upcoming"]
    steam = snapshot["steam"]
    psn = snapshot["psn"]

    epic_now_count = len(epic_now)
    epic_upcoming_count = len(epic_upcoming)
    steam_count = len(steam)
    psn_count = len(psn)
    epic_total_count = epic_now_count + epic_upcoming_count
    total_count = epic_total_count + steam_count + psn_count

    share_payload = build_share_payload(snapshot)
    share_ready = share_payload is not None
    share_data_json = serialize_for_client(share_payload)
    share_script = get_share_client_script()

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
        "SHARE_BUTTON_DISABLED": (
            "" if share_ready else ' aria-disabled="true" tabindex="-1"'
        ),
        "SHARE_BUTTON_LABEL": "生成分享拼图" if share_ready else "分享数据未就绪",
        "SHARE_BUTTON_FILENAME": escape_attribute(
            (share_payload.get("suggestedFileName") if share_payload else None)
            or "乐赏限免拼图.png"
        ),
        "SHARE_BUTTON_URL": escape_attribute("#"),
        "SHARE_DATA_JSON": share_data_json,
        "CLIENT_SCRIPT": share_script,
    }

    html_content = template
    for key, value in replacements.items():
        html_content = html_content.replace(f"{{{{{key}}}}}", value)

    return html_content


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

