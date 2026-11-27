// Draw in the website's CSS pixels, then export at 2× for sharing.
async function renderGamePoster(payload) {
    const css = getComputedStyle(document.documentElement);
    const token = name => css.getPropertyValue('--' + name).trim();
    const number = name => parseFloat(token(name));
    const width = 620, margin = number('space-6'), gap = number('space-3');
    const inset = number('space-3'), posterWidth = 76, posterHeight = 114;
    const ink = token('ink'), muted = token('muted'), accent = token('accent');
    const canvas = document.createElement('canvas');
    const ctx = canvas.getContext('2d');
    const font = (size, weight = 400, family = token('body-font')) => weight + ' ' + size + 'px ' + family;

    function lines(value, maxWidth, limit) {
        const result = [];
        let line = '';
        const words = String(value || '').trim().match(/[a-zA-Z0-9]+|[^a-zA-Z0-9]/gu) || [];
        for (const word of words) {
            const chunks = ctx.measureText(word).width > maxWidth ? Array.from(word) : [word];
            for (const chunk of chunks) {
                if (line && ctx.measureText(line + chunk).width > maxWidth) {
                    result.push(line.trim());
                    if (result.length === limit) {
                        let last = result.pop();
                        while (last && ctx.measureText(last + '…').width > maxWidth) last = last.slice(0, -1);
                        return [...result, last.trimEnd() + '…'];
                    }
                    line = '';
                }
                line += line ? chunk : chunk.trimStart();
            }
        }
        if (line.trim()) result.push(line.trim());
        return result;
    }
    function write(value, x, y, style, color, maxWidth, maxLines, lineHeight) {
        ctx.font = style;
        ctx.fillStyle = color;
        for (const line of lines(value, maxWidth, maxLines)) {
            ctx.fillText(line, x, y);
            y += lineHeight;
        }
        return y;
    }
    function roundBox(x, y, w, h, radius, color) {
        ctx.beginPath();
        ctx.roundRect(x, y, w, h, radius);
        ctx.fillStyle = color;
        ctx.fill();
    }
    function load(url) {
        return new Promise(resolve => {
            if (!url) return resolve(null);
            const img = new Image();
            img.crossOrigin = 'anonymous';
            const timer = setTimeout(() => resolve(null), 7000);
            img.onload = () => { clearTimeout(timer); resolve(img); };
            img.onerror = () => { clearTimeout(timer); resolve(null); };
            img.src = url;
        });
    }
    const cache = new Map();
    for (const section of payload.sections) {
        for (const item of section.items) {
            if (!cache.has(item.coverUrl)) cache.set(item.coverUrl, load(item.coverUrl));
        }
    }
    const qr = await load(payload.qrImage);
    const mark = await load(payload.logo);
    const cardWidth = width - margin * 2;
    const textWidth = cardWidth - inset * 2 - posterWidth - gap;
    function cardText(item, x, y) {
        y = write(item.primary, x, y, font(number('type-meta'), 650), accent, textWidth, 1, 19);
        y = write(item.title, x, y + 3, font(number('type-card'), 700), ink, textWidth, 3, 26);
        y = write(item.secondary, x, y + 4, font(number('type-meta')), muted, textWidth, 2, 19);
        return write(item.description || item.tertiary, x, y + 4, font(number('type-body')), ink, textWidth, 2, 21);
    }
    // Measure with exactly the same wrapping used when drawing.
    const sections = payload.sections.map(section => ({
        ...section, heights: section.items.map(item => Math.max(posterHeight, cardText(item, 0, 0)) + inset * 2)
    }));
    const start = 130, sectionHead = 38, sectionGap = number('space-6'), footer = 105;
    const contentHeight = sections.reduce((total, section) => total + sectionHead + sectionGap +
        section.heights.reduce((sum, h) => sum + h + gap, 0), start);
    const height = contentHeight + footer;
    const scale = Math.min(2, 16000 / height); // WebP has a 16383-pixel side limit.
    canvas.width = Math.ceil(width * scale);
    canvas.height = Math.ceil(height * scale);
    ctx.scale(scale, scale);
    ctx.textBaseline = 'top';
    ctx.fillStyle = token('canvas'); ctx.fillRect(0, 0, width, height);
    if (mark) ctx.drawImage(mark, margin, 19, 24, 24);
    write('GBTGAME', margin + (mark ? 32 : 0), 21, font(17, 700), ink, 280, 1, 24);
    write('白嫖游戏速报', margin, 52, font(34, 700, token('heading-font')), ink, cardWidth, 1, 45);
    write(payload.generatedAtDisplay + ' 北京时间　精选 ' + payload.totalItems + ' 项活动',
        margin, 98, font(number('type-meta')), muted, cardWidth, 1, 20);
    let y = start;
    for (const section of sections) {
        write(section.title, margin, y, font(number('type-section'), 700), ink, cardWidth, 1, sectionHead);
        y += sectionHead;
        for (const [index, item] of section.items.entries()) {
            const h = section.heights[index], x = margin + inset, top = y + inset;
            roundBox(margin, y, cardWidth, h, number('card-radius'), token('paper'));
            ctx.strokeStyle = token('line'); ctx.stroke();
            roundBox(x, top, posterWidth, posterHeight, 8, '#23354b');
            ctx.save(); ctx.clip();
            const image = await cache.get(item.coverUrl);
            if (image) {
                const fit = image.width / image.height > 1.35 ? Math.min : Math.max;
                const zoom = fit(posterWidth / image.width, posterHeight / image.height);
                const w = image.width * zoom, h = image.height * zoom;
                ctx.drawImage(image, x + (posterWidth-w)/2, top + (posterHeight-h)/2, w, h);
            } else {
                ctx.fillStyle = '#ffffff'; ctx.font = font(12, 650); ctx.textAlign = 'center';
                ctx.fillText(item.platform || 'GBTGAME', x + posterWidth/2, top + posterHeight/2 - 7, posterWidth - 8);
                ctx.textAlign = 'left';
            }
            ctx.restore();
            cardText(item, x + posterWidth + gap, top);
            y += section.heights[index] + gap;
        }
        y += sectionGap;
    }
    ctx.fillStyle = token('line'); ctx.fillRect(margin, y, cardWidth, 1);
    if (qr) ctx.drawImage(qr, width - margin - 80, y + 12, 80, 80);
    write('查看最新领取活动', margin, y + 26, font(18, 650), ink, cardWidth - 90, 1, 25);
    write('gameinfo.gbtgame.me', margin, y + 53, font(number('type-body')), accent, cardWidth - 90, 1, 20);
    return canvas;
}
