FROM python:3.11-slim

LABEL org.opencontainers.image.title="game_info"
LABEL org.opencontainers.image.description="抓取 Epic/Steam/PlayStation 限免信息，生成静态页面与历史记录（SQLite date.db），并生成分享长图。"
LABEL org.opencontainers.image.source="https://github.com/nodesire7/FreeGame-info"
LABEL org.opencontainers.image.authors="Nodesire7 <amocnfk@gmail.com>"

WORKDIR /app

COPY requirements.txt /app/requirements.txt
RUN python -m pip install --upgrade pip && pip install -r /app/requirements.txt

# Playwright & Chromium dependencies
RUN python -m playwright install --with-deps chromium

COPY . /app

# 运行时建议挂载 /data，用于持久化 history/date.db 与 records 图片
VOLUME ["/data"]

ENV OUTPUT_DIR=/data/site
ENV HISTORY_DIR=/data/history

CMD ["python", "main.py", "/data/site", "--history-dir", "/data/history"]


