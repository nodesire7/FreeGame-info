# 快速部署（Releases）

本项目的 **Releases 不是最终生成的页面**，而是提供一套“快速部署”的配置文件与使用说明。  
页面内容由脚本在运行时抓取并生成（`python main.py ...`），并输出到挂载的数据目录。

## 依赖

- Docker / Docker Compose

## 使用方式（推荐）

1. 下载 Releases 里的 `deploy.zip`（Windows）或 `deploy.tar.gz`（Linux/macOS）
2. 解压后进入 `deploy/` 目录
3. 准备环境变量文件（可选）

复制 `env.example` 为 `env` 并按需修改：

```bash
cp env.example env
```

> Windows PowerShell：`Copy-Item env.example env`

4. 拉取镜像

```bash
docker compose --env-file env pull
```

5. 启动（会自动生成页面，并每隔一段时间自动更新）

```bash
docker compose --env-file env up -d
```

访问：`http://localhost:8080/`（端口可通过 `PORT` 修改）

## 输出文件位置

解压目录下会生成：

- `./data/site/`：静态站点（index、history、date.db 等）
- `./data/history/`：历史数据库与图片（SQLite `date.db` + `records/*.webp`）

## 定时更新

本镜像默认会 **常驻运行**，并按 `INTERVAL_SECONDS` 周期自动执行抓取与页面生成。

默认：3 小时一次（10800 秒）。你可以在 `env` 里修改：

- `INTERVAL_SECONDS=3600`（1 小时一次）
- `INTERVAL_SECONDS=600`（10 分钟一次）


