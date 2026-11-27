# FreeGame-info

追踪游戏限免、会员游戏、跨平台赠送与组合包。

## 在线站点

**项目站** [gameinfo.gbtgame.me](https://gameinfo.gbtgame.me/) · **账号根站** [nodesire7.github.io](https://nodesire7.github.io/)

每 3 小时抓取一次，也可在源码更新后直接发布。两个域名使用同一次构建的公开数据、首页、历史页、RSS 和分享图片。

### 历史数据访问（SQLite）

活动新增、下架，或价格、领取条件、期限等内容变化时才归档。刷新时间、来源检查状态、封面和活动排序变化不会单独触发归档。所有历史快照按时间倒序展示，每页 5 期。

- **历史列表页面**: `https://gameinfo.gbtgame.me/history/`
- **历史数据库（SQLite）**: `https://gameinfo.gbtgame.me/history/date.db`
- **历史图片**: `https://gameinfo.gbtgame.me/history/records/{时间戳}白嫖信息.webp`
- **本次快照 JSON（始终为最新一次抓取结果）**: `https://nodesire7.github.io/FreeGame-info/白嫖信息.json`

时间戳格式：`YYYYMMDDHHmmss`（例如：`20251214202455`）

**示例**：
- 数据库: https://gameinfo.gbtgame.me/history/date.db
- 图片: https://gameinfo.gbtgame.me/history/records/20251214202455白嫖信息.webp
- 本次快照: https://nodesire7.github.io/FreeGame-info/白嫖信息.json

> 💡 提示：在主页底部可以找到“历史记录”入口与“最新归档”链接。

### Releases（版本包）

- **定位**：Releases 用于“快速部署”（提供 Docker Compose 等配置），**不是最终生成的页面**
- 已发布版本的部署包仍可从 Releases 下载。
- **内容**：Release 附带“全平台通用”的快速部署包
  - `deploy.zip`（Windows 推荐）
  - `deploy.tar.gz`（Linux/macOS 推荐）

下载入口：仓库的 Releases 页面（`https://github.com/nodesire7/FreeGame-info/releases`）

#### 如何正确使用 Releases

1. 下载并解压 `deploy.zip` / `deploy.tar.gz`
2. 进入 `deploy/` 目录
3. 复制 `env.example` 为 `env`（可选）
4. 执行一次生成：

```bash
docker compose --env-file env run --rm generator
```

5. 启动静态服务：

```bash
docker compose --env-file env up -d web
```

> Releases 中已将 `IMAGE_TAG` 写成当前版本号，开箱即用。页面仍由容器运行时生成（不是 Release 里预置的）。

## 功能特性

- 🎮 **Epic Games Store**：抓取官方 `freeGamesPromotions` 接口并解析限免窗口
- 🎮 **Steam**：使用 Playwright 抓取限时免费游戏
- 🎮 **PlayStation Plus**：抓取会员免费游戏
- 🎮 **IsThereAnyDeal**：通过官方 API 拉取 `100% OFF` 免费游戏
- 📄 **静态 HTML 页面**：美观的单页应用
- 🖼️ **分享拼图生成**：网页、归档和分享图共用字号、字族和配色；构建端与浏览器使用同一份 Canvas 绘图代码导出 WebP。
- 🗃️ **历史数据归档（SQLite）**：仅在数据变化时写入 `history/date.db`，图片保存到 `history/records/`
- **服务器 Docker** 每 3 小时刷新数据，并把同一期静态文件推送到两个 GitHub Pages 发布分支。

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
# 3. 如数据有变化，写入历史数据库 SQLite（date.db），并生成历史图片与历史列表页
```

**手动步骤**（已废弃，建议使用 `main.py`）：

```bash
# 1) 抓取数据
python epic_fetch.py
python psn_fetch.py
python steam_fetch.py
export ITAD_API_KEY=your_itad_api_key
python itad_fetch.py

# 2) 生成 HTML
python render_html.py

# 3) 生成分享拼图
python generate_image.py site/index.html site/history/records/时间戳白嫖信息.webp
```

## 服务器自动发布

服务器上常驻的 `freegame-publisher` 容器每 60 秒检查源码分支 `main`。源码变化时立即开始生成，平时每次发布成功后每隔 3 小时刷新数据。容器使用持久卷保留历史、版本和待推送的同一批文件，失败后自动重试。配置见 [服务器 Compose](deploy/compose.publisher.yml)。

项目站从 `FreeGame-info/gh-pages` 提供服务，账号根站从 `nodesire7.github.io/main` 提供服务。`FreeGame-info/history` 保存 SQLite、快照和海报。三个分支的提交都由服务器推送。两站使用 GitHub Pages 的分支发布功能。

运维目录为 `/opt/freegame-publisher`。`state/` 保存发布进度；`keys/project` 和 `keys/account` 分别对应两个仓库的可写部署密钥；`keys/known_hosts` 用于验证 GitHub 的 SSH 主机；`itad_api_key` 只供容器读取。用 `docker logs --tail 50 freegame-publisher` 查看发布记录。更新 Python 或浏览器依赖时，需同步重建发布容器的运行环境。

## Docker 本地运行

镜像地址：`nodesire77/game_info`

- `latest`
- `vX.Y`（与 Release 版本号一致，例如 `v1.0`）

示例（拉取后直接常驻运行，自动生成页面，并默认每 3 小时更新一次；可修改间隔）：

```bash
docker run -d --name game_info -p 8080:8080 -v "$(pwd)/data:/data" nodesire77/game_info:latest
```

访问：`http://localhost:8080/`

可选：修改生成间隔（例如 1 小时一次）：

```bash
docker run -d --name game_info -p 8080:8080 -v "$(pwd)/data:/data" -e INTERVAL_SECONDS=3600 nodesire77/game_info:latest
```

容器会输出到：
- `/data/site/`：静态站点（包含 history 页）
- `/data/history/date.db`：历史数据库
- `/data/history/records/`：历史图片

## 数据存储（SQLite / 可扩展）

当前：所有历史快照存储在 SQLite：`history/date.db`（Pages 展示为 `history/date.db`）。

后续可扩展接入（规划）：Redis / MySQL / PostgreSQL（作为历史存储后端）。

## 数据源说明

### Epic Games

默认使用官方接口：

```
https://store-site-backend-static-ipv4.ak.epicgames.com/freeGamesPromotions?locale=zh-CN&country=CN&allowCountries=CN
```

说明：
- 从 promotions 窗口判定 **正在免费** / **即将免费**
- 商品页详细信息（价格/开发商/发行商等）使用浏览器渲染后提取

### Steam

Steam 页签同时展示中国区商店零元特惠和通过站外渠道领取的 Steam 游戏。后者来自 GamerPower 的有效完整游戏赠送列表，单列领取条件和活动链接。

商店数据来自 Steam 的“限时特惠 + 免费”搜索结果页：

```
https://store.steampowered.com/search/?maxprice=free&specials=1&ndl=1&cc=cn&l=schinese
```

### PlayStation Plus

抓取 PlayStation 官方会员页面：

```
https://www.playstation.com/zh-hans-hk/ps-plus/whats-new/
```

### IsThereAnyDeal

通过官方 API 拉取 `100% OFF` 列表：

```
https://api.isthereanydeal.com/deals/v2
```

运行前需要提供环境变量：

```bash
export ITAD_API_KEY=your_itad_api_key
export ITAD_COUNTRY=CN  # 可选，默认 CN
```

### GOG、Xbox 和跨平台赠送

GOG 页签同时收录中国区目录零元促销及 GamerPower 的 GOG 赠送，官方首页横幅和第三方领码分别展示。Xbox 从微软香港区的 Game Pass「最近加入」目录获取订阅条目。GamerPower 补充跨商店的完整游戏赠送与兑换码活动，保留适用平台、领取条件、截止信息和活动原文链接。[GamerPower 数据接口](https://www.gamerpower.com/api-read)

公开 JSON 中的 `sourceStatus` 记录各来源最近一次检查和成功取数的时间。来源请求失败时页面会标明使用上次结果或暂时无法获取。ITAD 的折扣和组合包独立更新。

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
└── history/                # 历史记录页面与资源（用于 Pages 展示）
    ├── index.html
    ├── date.db             # 历史数据库（SQLite）
    └── records/
        └── {时间戳}白嫖信息.webp
```

## 自定义配置

### Epic API URL

通过环境变量覆盖：

```bash
export EPIC_PROMOTIONS_API_URL="https://..."
python main.py site
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
