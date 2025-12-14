# FreeGame-info

Free games radar: 抓取 Epic/Steam/PlayStation 限免游戏信息并生成静态页面

[![Build & Deploy](https://github.com/nodesire7/FreeGame-info/actions/workflows/pages.yml/badge.svg)](https://github.com/nodesire7/FreeGame-info/actions/workflows/pages.yml)

## 在线站点

**https://nodesire7.github.io/FreeGame-info/**

每 3 小时自动更新一次限免数据。

## 功能特性

- 🎮 **Epic Games Store**：抓取官方 `storefrontLayout` API，获取每周限免游戏
- 🎮 **Steam**：使用 Playwright 抓取限时免费游戏
- 🎮 **PlayStation Plus**：抓取会员免费游戏
- 📄 **静态 HTML 页面**：美观的单页应用
- 🖼️ **分享拼图生成**：使用 Canvas API 生成长图（支持 PNG/WebP）
- 🤖 **GitHub Actions**：自动定时更新并部署到 GitHub Pages

## 本地使用

### 环境要求

- Python 3.11+
- pip

### 安装依赖

```bash
pip install -r requirements.txt
python -m playwright install chromium
```

### 生成静态页面

```bash
# 1) 抓取数据
python fetch_freebies.py snapshot.json

# 2) 生成 HTML
python render_html.py snapshot.json epic-freebies.html.template index.html

# 3) （可选）生成分享拼图
python generate_image.py index.html gameinfo.webp
```

### 一键脚本

**Linux / macOS**:
```bash
chmod +x update.sh
./update.sh
```

**Windows**:
```powershell
.\update.ps1
```

## GitHub Actions 自动化

仓库包含定时任务工作流（`.github/workflows/pages.yml`）：

- **定时运行**：每 3 小时抓取一次（UTC 时间：0:00、3:00、6:00...）
- **手动触发**：在 Actions 页面点击 "Run workflow"
- **自动部署**：生成 `site/index.html` + `site/gameinfo.webp` 并发布到 GitHub Pages

### 如何启用

1. Fork 本仓库
2. 在仓库 Settings → Pages：
   - Source 选择：**GitHub Actions**
3. 在 Actions 页面手动触发一次运行
4. 访问 `https://你的用户名.github.io/FreeGame-info/`

## 数据源说明

### Epic Games

默认使用官方 GraphQL 接口：

```
https://store-site-backend-static-ipv4.ak.epicgames.com/storefrontLayout?locale=zh-CN&country=CN&start=0&count=30
```

筛选条件：
- `price.totalPrice.discountPrice == 0`（现价为 0）
- `price.totalPrice.originalPrice > 0`（原价大于 0）
- 从 `price.lineOffers[0].appliedRules[0].endDate` 提取限免结束时间

**注意**：官方 API 可能不包含"即将开始"的限免游戏（只有已开始的），具体取决于 Epic 的发布策略。

### Steam

抓取 Steam 商店的"限时特惠 + 免费"搜索结果页：

```
https://store.steampowered.com/search/?maxprice=free&specials=1&ndl=1?cc=cn&l=schinese
```

### PlayStation Plus

抓取 PlayStation 官方会员页面：

```
https://www.playstation.com/zh-hans-hk/ps-plus/whats-new/
```

## 文件说明

| 文件 | 说明 |
|------|------|
| `fetch_freebies.py` | 抓取数据主脚本 |
| `render_html.py` | 渲染 HTML 页面 |
| `generate_image.py` | 生成分享拼图（使用 Playwright + Canvas API） |
| `psn_api.py` | FastAPI 服务（可选，提供 PSN/Steam API 接口） |
| `epic-freebies.html.template` | HTML 模板 |
| `requirements.txt` | Python 依赖 |
| `update.sh` / `update.ps1` | 一键更新脚本 |

## 自定义配置

### Epic API URL

通过环境变量覆盖：

```bash
export EPIC_API_URL="https://..."
python fetch_freebies.py snapshot.json
```

### Python 版本

`update.sh` 默认使用 `python3.11`，可通过环境变量 `PYTHON_CMD` 指定：

```bash
PYTHON_CMD=python3.12 ./update.sh
```

## 常见问题

### Playwright 浏览器安装失败

```bash
python -m playwright install --with-deps chromium
```

### WebP 转换失败

安装 Pillow 库：

```bash
pip install Pillow
```

## 许可证

MIT License

---

**在线站点**: https://nodesire7.github.io/FreeGame-info/  
**仓库地址**: https://github.com/nodesire7/FreeGame-info
