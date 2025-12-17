#!/usr/bin/env bash
set -euo pipefail

# 目标：拉起后自动周期生成（默认 3 小时一次，可配置），并提供静态文件服务

DATA_DIR="${DATA_DIR:-/data}"
OUTPUT_DIR="${OUTPUT_DIR:-${DATA_DIR}/site}"
HISTORY_DIR="${HISTORY_DIR:-${DATA_DIR}/history}"

PORT="${PORT:-8080}"

# 默认 3 小时（10800 秒）
INTERVAL_SECONDS="${INTERVAL_SECONDS:-10800}"

# 只生成一次并退出（0/1）
ONE_SHOT="${ONE_SHOT:-0}"

# 是否启动内置静态服务（0/1）
SERVE="${SERVE:-1}"

mkdir -p "${OUTPUT_DIR}" "${HISTORY_DIR}"

run_generate() {
  echo "[info] generate: OUTPUT_DIR=${OUTPUT_DIR} HISTORY_DIR=${HISTORY_DIR}"
  python main.py "${OUTPUT_DIR}" --history-dir "${HISTORY_DIR}" || true
}

# 首次生成
run_generate

server_pid=""
if [ "${SERVE}" = "1" ]; then
  echo "[info] serve: http://0.0.0.0:${PORT}/ (dir=${OUTPUT_DIR})"
  python -m http.server "${PORT}" --directory "${OUTPUT_DIR}" &
  server_pid="$!"
fi

if [ "${ONE_SHOT}" = "1" ]; then
  echo "[info] ONE_SHOT=1, exit after first generate."
  if [ -n "${server_pid}" ]; then
    wait "${server_pid}"
  fi
  exit 0
fi

echo "[info] loop every ${INTERVAL_SECONDS}s"
while true; do
  sleep "${INTERVAL_SECONDS}" || true
  run_generate
done


