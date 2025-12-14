# FreeGame-info

Free games radar: 抓取 Epic/Steam/PlayStation 限免游戏信息并生成静态页面

[![Build & Deploy](https://github.com/nodesire7/FreeGame-info/actions/workflows/pages.yml/badge.svg)](https://github.com/nodesire7/FreeGame-info/actions/workflows/pages.yml)

## 在线站点

**主页**: https://nodesire7.github.io/FreeGame-info/

每 3 小时自动更新一次限免数据。

### 历史数据访问

每次更新都会自动保存历史数据到 `archive/` 文件夹，可通过以下方式访问：

- **历史 JSON 数据**: `https://nodesire7.github.io/FreeGame-info/archive/{时间戳}白嫖信息.json`
- **历史图片**: `https://nodesire7.github.io/FreeGame-info/archive/{时间戳}白嫖信息.webp`

时间戳格式：`YYYYMMDDHHmmss`（例如：`20251214202455`）

**示例**：
- JSON: https://nodesire7.github.io/FreeGame-info/archive/20251214202455白嫖信息.json
- 图片: https://nodesire7.github.io/FreeGame-info/archive/20251214202455白嫖信息.webp

> 💡 提示：在主页底部可以找到最新一次更新的历史数据链接。

## 功能特性

- 🎮 **Epic Games Store**：抓取官方 `storefrontLayout` API，获取每周限免游戏
- 🎮 **Steam**：使用 Playwright 抓取限时免费游戏
- 🎮 **PlayStation Plus**：抓取会员免费游戏
- 📄 **静态 HTML 页面**：美观的单页应用
- 🖼️ **分享拼图生成**：使用 Canvas API 生成长图（支持 PNG/WebP）
- 📦 **历史数据归档**：每次更新自动保存 JSON 和图片到 `archive/` 文件夹
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
# 一键生成（推荐）
python main.py site

# 这会自动：
# 1. 抓取所有平台数据（Epic、Steam、PSN）
# 2. 生成 HTML 页面
# 3. 生成历史 JSON 和图片到 site/archive/ 文件夹
```

**手动步骤**（已废弃，建议使用 `main.py`）：

```bash
# 1) 抓取数据
python epic_fetch.py site/EPIC.json
python psn_fetch.py site/PSN.json
python steam_fetch.py site/STEAM.json

# 2) 生成 HTML
python render_html.py site/snapshot.json epic-freebies.html.template site/index.html

# 3) 生成分享拼图
python generate_image.py site/index.html site/archive/时间戳白嫖信息.webp
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
- **自动部署**：生成 `site/index.html`、历史 JSON 和图片，并发布到 GitHub Pages
- **历史归档**：每次更新都会在 `site/archive/` 文件夹中保存带时间戳的 JSON 和图片文件

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
| `main.py` | 主脚本，一键生成所有内容 |
| `epic_fetch.py` | Epic Games 数据抓取脚本 |
| `psn_fetch.py` | PlayStation Plus 数据抓取脚本 |
| `steam_fetch.py` | Steam 数据抓取脚本 |
| `render_html.py` | 渲染 HTML 页面 |
| `generate_image.py` | 生成分享拼图（使用 Playwright + Canvas API） |
| `epic-freebies.html.template` | HTML 模板 |
| `logo.png` | 网站图标 |
| `requirements.txt` | Python 依赖 |

### 生成的文件结构

```
site/
├── index.html              # 主页
├── logo.png                # 网站图标
├── snapshot.json           # 当前数据快照
├── EPIC.json               # Epic 数据
├── PSN.json                # PSN 数据
├── STEAM.json              # Steam 数据
└── archive/                # 历史数据归档
    ├── {时间戳}白嫖信息.json
    └── {时间戳}白嫖信息.webp
```

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
