#!/bin/bash
# 更新限免数据并生成静态页面
# 自动创建 Python 虚拟环境、安装依赖并运行

set -e

# 配置
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
# 执行目录和输出目录（可以通过环境变量 WORK_DIR 覆盖）
WORK_DIR="${WORK_DIR:-/opt/1panel/apps/openresty/openresty/www/sites/gameinfo.gbtgame.me/index}"
OUTPUT_DIR="${WORK_DIR}"
OUTPUT_FILE="${OUTPUT_DIR}/index.html"
# 虚拟环境和快照文件也放在工作目录
VENV_DIR="${WORK_DIR}/.venv"
SNAPSHOT_FILE="${WORK_DIR}/snapshot.json"
# 模板/脚本/依赖位于仓库（SCRIPT_DIR）中
TEMPLATE_FILE="${SCRIPT_DIR}/epic-freebies.html.template"
REQUIREMENTS_FILE="${SCRIPT_DIR}/requirements.txt"
FETCH_SCRIPT="${SCRIPT_DIR}/fetch_freebies.py"
RENDER_SCRIPT="${SCRIPT_DIR}/render_html.py"
IMAGE_SCRIPT="${SCRIPT_DIR}/generate_image.py"

# Python 配置（可以通过环境变量 PYTHON_CMD 覆盖）
# 如果未指定，默认尝试 python3.11，如果不在 PATH 中，尝试 /usr/bin/python3.11
if [ -z "${PYTHON_CMD}" ]; then
    if command -v python3.11 &> /dev/null; then
        PYTHON_CMD="python3.11"
    elif [ -f "/usr/bin/python3.11" ] && [ -x "/usr/bin/python3.11" ]; then
        PYTHON_CMD="/usr/bin/python3.11"
    else
        PYTHON_CMD="python3.11"
    fi
fi

# 颜色输出
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

# 打印带颜色的消息
info() {
    echo -e "${GREEN}[信息]${NC} $1"
}

warn() {
    echo -e "${YELLOW}[警告]${NC} $1"
}

error() {
    echo -e "${RED}[错误]${NC} $1"
}

step() {
    echo -e "${BLUE}[步骤]${NC} $1"
}

# 检查 Python 环境
PYTHON_FOUND=false
if [[ "${PYTHON_CMD}" == /* ]]; then
    # 如果是绝对路径，检查文件是否存在且可执行
    if [ -f "${PYTHON_CMD}" ] && [ -x "${PYTHON_CMD}" ]; then
        PYTHON_FOUND=true
    fi
else
    # 如果是命令名，检查是否在 PATH 中
    if command -v "${PYTHON_CMD}" &> /dev/null; then
        PYTHON_FOUND=true
    fi
fi

if [ "${PYTHON_FOUND}" = false ]; then
    error "未找到 ${PYTHON_CMD}，请先安装 Python 3.11"
    error "可以通过环境变量 PYTHON_CMD 指定其他 Python 版本，例如:"
    error "  PYTHON_CMD=/usr/bin/python3.11 ./update.sh"
    error "  PYTHON_CMD=python3.12 ./update.sh"
    exit 1
fi

# 验证 Python 是否可执行
if ! "${PYTHON_CMD}" --version &> /dev/null; then
    error "无法执行 ${PYTHON_CMD}，请检查 Python 安装"
    exit 1
fi

PYTHON_VERSION=$("${PYTHON_CMD}" --version 2>&1)
info "使用 Python: ${PYTHON_CMD}"
info "检测到 Python 版本: ${PYTHON_VERSION}"

# 创建工作目录（输出目录）
step "创建工作目录..."
mkdir -p "${WORK_DIR}"
if [ ! -d "${WORK_DIR}" ]; then
    error "无法创建工作目录: ${WORK_DIR}"
    exit 1
fi
info "工作目录: ${WORK_DIR}"

# 检查模板文件
step "检查模板文件..."
if [ ! -f "${TEMPLATE_FILE}" ]; then
    error "找不到模板文件: ${TEMPLATE_FILE}"
    error "请确保模板文件与 update.sh 位于同一目录（或调整 TEMPLATE_FILE）"
    exit 1
fi
info "模板文件: ${TEMPLATE_FILE}"

# 创建或激活 Python 虚拟环境
step "设置 Python 虚拟环境..."
if [ ! -d "${VENV_DIR}" ]; then
    info "使用 ${PYTHON_CMD} 创建虚拟环境: ${VENV_DIR}"
    "${PYTHON_CMD}" -m venv "${VENV_DIR}"
else
    info "使用现有虚拟环境: ${VENV_DIR}"
fi

# 激活虚拟环境
source "${VENV_DIR}/bin/activate"

# 升级 pip
step "升级 pip..."
python -m pip install --upgrade pip --quiet

# 安装依赖
step "安装 Python 依赖..."
if [ -f "${REQUIREMENTS_FILE}" ]; then
    pip install -r "${REQUIREMENTS_FILE}" --quiet
    if [ $? -ne 0 ]; then
        error "依赖安装失败"
        exit 1
    fi
else
    error "找不到 requirements.txt: ${REQUIREMENTS_FILE}"
    exit 1
fi

# 验证关键依赖
step "验证依赖..."
MISSING_DEPS=()
python -c "import aiohttp" 2>/dev/null || MISSING_DEPS+=("aiohttp")
python -c "import bs4" 2>/dev/null || MISSING_DEPS+=("beautifulsoup4")
python -c "from playwright.sync_api import sync_playwright" 2>/dev/null || MISSING_DEPS+=("playwright")

if [ ${#MISSING_DEPS[@]} -gt 0 ]; then
    error "缺少依赖: ${MISSING_DEPS[*]}"
    error "请重新安装依赖: pip install -r requirements.txt"
    exit 1
fi

info "所有 Python 依赖已就绪"

# 安装 Playwright 浏览器
step "安装 Playwright 浏览器..."
# Playwright 会自动检查浏览器是否已安装，如果已安装则跳过
# 如果未安装，会自动下载并安装（可能需要几分钟）
info "正在检查/安装 Playwright Chromium 浏览器..."
if python -m playwright install chromium 2>&1; then
    info "Playwright 浏览器就绪"
else
    warn "Playwright 浏览器安装可能失败，但将继续执行..."
    warn "如果运行时出错，请手动安装: source .venv/bin/activate && python -m playwright install chromium"
fi

# 抓取数据
step "抓取限免数据..."
cd "${WORK_DIR}"
python "${FETCH_SCRIPT}" "${SNAPSHOT_FILE}"

if [ ! -f "${SNAPSHOT_FILE}" ]; then
    error "数据抓取失败，未生成快照文件"
    exit 1
fi

info "数据抓取完成: ${SNAPSHOT_FILE}"

# 生成 HTML
step "生成 HTML 页面..."
python "${RENDER_SCRIPT}" "${SNAPSHOT_FILE}" "${TEMPLATE_FILE}" "${OUTPUT_FILE}"

if [ ! -f "${OUTPUT_FILE}" ]; then
    error "HTML 生成失败"
    exit 1
fi

# 设置文件权限（确保 web 服务器可以读取）
chmod 644 "${OUTPUT_FILE}" 2>/dev/null || true
info "HTML 生成完成: ${OUTPUT_FILE}"

# 生成 WebP 图片
step "生成页面图片..."
OUTPUT_IMAGE="${OUTPUT_DIR}/gameinfo.webp"
python "${IMAGE_SCRIPT}" "${OUTPUT_FILE}" "${OUTPUT_IMAGE}" 1200

if [ ! -f "${OUTPUT_IMAGE}" ]; then
    warn "图片生成失败，但将继续执行..."
else
    chmod 644 "${OUTPUT_IMAGE}" 2>/dev/null || true
    info "图片生成完成: ${OUTPUT_IMAGE}"
fi

# 显示统计信息
echo ""
step "数据统计:"
if command -v jq &> /dev/null; then
    epic_now=$(jq -r '.epic.now | length' "${SNAPSHOT_FILE}" 2>/dev/null || echo "0")
    epic_upcoming=$(jq -r '.epic.upcoming | length' "${SNAPSHOT_FILE}" 2>/dev/null || echo "0")
    steam=$(jq -r '.steam | length' "${SNAPSHOT_FILE}" 2>/dev/null || echo "0")
    psn=$(jq -r '.psn | length' "${SNAPSHOT_FILE}" 2>/dev/null || echo "0")
    echo "  Epic 正在免费: ${epic_now}"
    echo "  Epic 即将免费: ${epic_upcoming}"
    echo "  Steam: ${steam}"
    echo "  PlayStation: ${psn}"
else
    warn "未安装 jq，跳过统计信息显示"
fi

echo ""
info "✅ 更新完成！"
info "📄 输出文件: ${OUTPUT_FILE}"
if [ -f "${OUTPUT_IMAGE}" ]; then
    info "🖼️  图片文件: ${OUTPUT_IMAGE}"
fi
info "📦 虚拟环境: ${VENV_DIR}"
info "📁 工作目录: ${WORK_DIR}"

# 停用虚拟环境
deactivate
