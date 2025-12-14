# 限免游戏信息抓取工具

一个简单的 Python 工具，用于抓取 Epic、Steam、PlayStation 限免游戏信息并生成静态 HTML 页面。

## 功能特性

- 🎮 抓取 Epic Games Store 限免游戏（通过 API）
- 🎮 抓取 Steam 限免游戏（通过网页解析）
- 🎮 抓取 PlayStation Plus 会员免费游戏（通过网页解析）
- 📄 自动生成美观的静态 HTML 页面
- 🖼️ 支持生成分享拼图（客户端功能）

## 环境要求

- Python 3.11（默认使用 `python3.11`，可通过环境变量 `PYTHON_CMD` 指定其他版本）
- 无需手动安装依赖（脚本会自动创建虚拟环境并安装）

## 使用方法

### 一键运行（推荐）

脚本会自动完成以下操作：
1. ✅ 检查 Python 环境
2. ✅ 创建 Python 虚拟环境（`.venv`）
3. ✅ 安装/更新所有依赖
4. ✅ 安装 Playwright 浏览器
5. ✅ 抓取限免数据
6. ✅ 生成 HTML 页面

```bash
chmod +x update.sh
./update.sh
```

默认执行目录和输出目录为 `/opt/1panel/apps/openresty/openresty/www/sites/gameinfo.gbtgame.me/index`，可通过环境变量 `WORK_DIR` 自定义：

```bash
WORK_DIR=/path/to/work ./update.sh
```

**注意：**
- 执行目录和输出目录是同一个目录
- 虚拟环境（`.venv`）和快照文件（`snapshot.json`）也位于工作目录中
- 模板文件（`epic-freebies.html.template`）需要位于脚本目录中
- 生成的 HTML 文件为 `index.html`，位于工作目录中

### 首次运行

首次运行脚本会自动：
- 创建工作目录（如果不存在）
- 在工作目录中创建 `.venv` 虚拟环境目录
- 安装所有 Python 依赖（aiohttp, beautifulsoup4, playwright）
- 安装 Playwright Chromium 浏览器
- 检查模板文件是否存在（`epic-freebies.html.template` 必须位于脚本目录中）
- 在工作目录中执行数据抓取和 HTML 生成

### 后续运行

后续运行脚本会：
- 自动激活虚拟环境
- 检查并更新依赖（如果需要）
- 执行数据抓取和 HTML 生成

### 手动执行（不推荐）

如果需要手动执行：

1. 创建虚拟环境（如果不存在）：

```bash
python3.11 -m venv .venv
```

2. 激活虚拟环境：

```bash
source .venv/bin/activate
```

3. 安装依赖：

```bash
pip install -r requirements.txt
python -m playwright install chromium
```

4. 抓取数据：

```bash
python fetch_freebies.py snapshot.json
```

5. 生成 HTML：

```bash
python render_html.py snapshot.json epic-freebies.html.template public/index.html
```

## 配置

### Epic API URL

默认使用 Epic 官方 `storefrontLayout` 接口（JSON 数据源），可通过环境变量修改：

`https://store-site-backend-static-ipv4.ak.epicgames.com/storefrontLayout?locale=zh-CN&country=CN&start=6&count=6`

```bash
# 示例：切换到英文/美国区，并拉取不同分页范围
export EPIC_API_URL="https://store-site-backend-static-ipv4.ak.epicgames.com/storefrontLayout?locale=en-US&country=US&start=0&count=30"
```

### 输出目录

通过环境变量 `OUTPUT_DIR` 设置：

```bash
export OUTPUT_DIR="/var/www/html"
./update.sh
```

### 部署目录

脚本会自动将生成的 `index.html` 文件部署到目标目录。默认部署目录为：

```
/opt/1panel/apps/openresty/openresty/www/sites/gameinfo.gbtgame.me/index
```

可通过环境变量 `DEPLOY_DIR` 自定义部署目录：

```bash
# 使用自定义部署目录
export DEPLOY_DIR="/var/www/html"
./update.sh

# 禁用自动部署（设置为空）
export DEPLOY_DIR=""
./update.sh
```

**注意事项：**
- 如果目标目录不存在，脚本会尝试创建（可能需要 sudo 权限）
- 如果目标目录无写入权限，脚本会尝试使用 sudo 复制文件
- 部署时会自动设置文件权限为 644（确保 web 服务器可以读取）
- 如果需要 sudo 权限，可能需要输入密码

### Python 版本

默认使用 `python3.11`，可通过环境变量 `PYTHON_CMD` 指定其他 Python 版本：

```bash
# 使用 Python 3.12
PYTHON_CMD=python3.12 ./update.sh

# 使用特定路径的 Python
PYTHON_CMD=/usr/bin/python3.11 ./update.sh
```

## 定时任务

### 使用 cron

编辑 crontab：

```bash
crontab -e
```

添加定时任务（例如每 6 小时更新一次）：

```bash
0 */6 * * * cd /path/to/project && ./update.sh >> /var/log/freebies_update.log 2>&1
```

### 使用 systemd timer

创建 `/etc/systemd/system/freebies-update.service`：

```ini
[Unit]
Description=Update Freebies Data

[Service]
Type=oneshot
WorkingDirectory=/path/to/project
ExecStart=/path/to/project/update.sh
User=www-data
```

创建 `/etc/systemd/system/freebies-update.timer`：

```ini
[Unit]
Description=Update Freebies Data Timer

[Timer]
OnBootSec=5min
OnUnitActiveSec=6h
Unit=freebies-update.service

[Install]
WantedBy=timers.target
```

启用并启动：

```bash
sudo systemctl enable freebies-update.timer
sudo systemctl start freebies-update.timer
```

## 文件说明

### 核心文件（位于脚本目录）

- `update.sh` - **一键更新脚本**（自动管理虚拟环境和依赖）
- `fetch_freebies.py` - 抓取限免数据的主脚本
- `render_html.py` - 生成 HTML 页面的脚本
- `requirements.txt` - Python 依赖列表
- `epic-freebies.html.template` - HTML 模板文件（必须位于脚本目录）

### 自动生成的文件（位于工作目录）

- `.venv/` - Python 虚拟环境目录（在工作目录中自动创建）
- `snapshot.json` - JSON 格式的数据快照（在工作目录中自动生成）
- `index.html` - 生成的静态 HTML 页面（在工作目录中自动生成）

## 输出文件

- `snapshot.json` - JSON 格式的数据快照（在工作目录中）
- `index.html` - 生成的静态 HTML 页面（在工作目录中，默认路径为 `/opt/1panel/apps/openresty/openresty/www/sites/gameinfo.gbtgame.me/index/index.html`）

## 部署

脚本会自动在工作目录中生成 `index.html` 文件。默认工作目录为 `/opt/1panel/apps/openresty/openresty/www/sites/gameinfo.gbtgame.me/index`，这是 Web 服务器的文档根目录。

文件生成后，Web 服务器（如 Nginx、Apache）会自动提供服务，无需额外的部署步骤。

### 配置 Web 服务器

确保 Web 服务器配置指向工作目录，例如：

**Nginx 配置示例：**

```nginx
server {
    listen 80;
    server_name gameinfo.gbtgame.me;
    root /opt/1panel/apps/openresty/openresty/www/sites/gameinfo.gbtgame.me/index;
    index index.html;

    location / {
        try_files $uri $uri/ /index.html;
    }
}
```

**注意：** 如果需要修改工作目录，可以通过环境变量 `WORK_DIR` 指定。

## 故障排除

### 权限问题

确保脚本有执行权限：

```bash
chmod +x update.sh
```

### Python 版本过低

确保 Python 版本 >= 3.8：

```bash
python3 --version
```

### 虚拟环境问题

如果虚拟环境损坏，可以删除工作目录中的虚拟环境后重新运行：

```bash
# 删除工作目录中的虚拟环境
rm -rf /opt/1panel/apps/openresty/openresty/www/sites/gameinfo.gbtgame.me/index/.venv
./update.sh
```

### Playwright 浏览器安装失败

如果 Playwright 浏览器安装失败，可以手动安装：

```bash
# 激活工作目录中的虚拟环境
source /opt/1panel/apps/openresty/openresty/www/sites/gameinfo.gbtgame.me/index/.venv/bin/activate
python3 -m playwright install chromium
```

### 模板文件缺失

如果模板文件不存在，请确保 `epic-freebies.html.template` 文件位于脚本目录（`update.sh` 所在的目录）。如果文件不存在，脚本将无法运行并会显示错误信息。

### 工作目录权限问题

如果工作目录不存在或无法创建，脚本会尝试创建目录。如果创建失败，可能需要手动创建并设置权限：

```bash
# 创建工作目录
sudo mkdir -p /opt/1panel/apps/openresty/openresty/www/sites/gameinfo.gbtgame.me/index

# 设置目录权限（根据实际情况调整用户和组）
sudo chown -R www-data:www-data /opt/1panel/apps/openresty/openresty/www/sites/gameinfo.gbtgame.me/index
sudo chmod 755 /opt/1panel/apps/openresty/openresty/www/sites/gameinfo.gbtgame.me/index
```

### 网络问题

如果抓取数据失败，请检查：
1. 网络连接是否正常
2. Epic API 是否可访问
3. Steam/PlayStation 网站是否可访问

### 查看详细日志

脚本使用 `set -e` 会在出错时立即退出。如果需要查看详细错误信息，可以移除 `set -e` 或添加调试输出。

## 许可证

MIT

