# 限免游戏信息抓取工具（Python 独立版）

这是一个 **Python 3** 项目，用于抓取并聚合以下平台的限免/免费内容，并生成静态页面：

- Epic Games Store（使用官方 `storefrontLayout` JSON）
- Steam（Playwright 抓取网页）
- PlayStation Plus（抓取网页解析）

输出：
- `snapshot.json`：数据快照
- `index.html`：静态页面
- （可选）`gameinfo.webp` / PNG：分享拼图图片

更详细的使用说明见 `README_FREEBIES.md`。

## 快速使用（手动）

1) 安装依赖：

```bash
pip install -r requirements.txt
python -m playwright install chromium
```

2) 抓取数据并生成静态页：

```bash
python fetch_freebies.py snapshot.json
python render_html.py snapshot.json epic-freebies.html.template index.html
```

3) （可选）生成拼图：

```bash
python generate_image.py index.html gameinfo.webp
```

## Epic 数据源

默认使用 Epic 官方接口（可通过环境变量 `EPIC_API_URL` 覆盖）：

`https://store-site-backend-static-ipv4.ak.epicgames.com/storefrontLayout?locale=zh-CN&country=CN&start=6&count=6`

## GitHub Actions（自动更新/发布）

仓库包含一个定时任务工作流：`.github/workflows/pages.yml`

- 每 6 小时运行一次（GitHub cron 使用 UTC）
- 自动抓取数据 → 生成 `index.html` / `snapshot.json` / `gameinfo.webp`
- 使用 GitHub Pages（GitHub Actions 部署）发布静态站点

2. 编辑配置文件，设置邮箱：
```bash
ALERT_EMAIL="admin@yourcompany.com"
ENABLE_EMAIL_ALERT=true
```

#### Webhook告警设置（钉钉/企业微信）
1. 在钉钉群或企业微信群中创建机器人
2. 获取Webhook URL
3. 编辑配置文件：
```bash
WEBHOOK_URL="https://oapi.dingtalk.com/robot/send?access_token=xxx"
ENABLE_WEBHOOK_ALERT=true
```

## 宝塔面板集成

### 方法1：通过计划任务
1. 登录宝塔面板
2. 进入 "计划任务"
3. 添加Shell脚本任务：
   - 任务类型：Shell脚本
   - 任务名称：硬盘监控
   - 执行周期：N分钟（建议5-10分钟）
   - 脚本内容：
   ```bash
   /root/disk_monitor.sh --once
   ```

### 方法2：通过网站监控
1. 进入 "监控" → "网站监控"
2. 添加监控项：
   - 监控类型：自定义
   - 监控脚本：`/root/disk_monitor.sh --once`
   - 告警阈值：自定义

### 方法3：通过系统监控
1. 启用宝塔系统监控
2. 在监控设置中添加自定义监控脚本
3. 设置告警规则

## 监控指标说明

### 磁盘IO指标
- **IO使用率**: 磁盘繁忙程度百分比
- **读IOPS**: 每秒读操作次数
- **写IOPS**: 每秒写操作次数
- **读MB/s**: 每秒读取数据量
- **写MB/s**: 每秒写入数据量
- **平均等待**: IO操作平均等待时间

### 磁盘空间指标
- **总大小**: 磁盘总容量
- **已使用**: 已使用空间
- **可用**: 剩余可用空间
- **使用率**: 空间使用百分比

### 系统负载
- 系统1分钟平均负载

## 告警阈值建议

### 生产环境
- IO使用率: 80%
- 磁盘空间: 90%
- 系统负载: 5.0

### 测试环境
- IO使用率: 90%
- 磁盘空间: 95%
- 系统负载: 8.0

## 故障排除

### 常见问题

1. **脚本无执行权限**
   ```bash
   chmod +x disk_monitor.sh
   ```

2. **缺少sysstat包**
   ```bash
   yum install -y sysstat
   ```

3. **iostat命令不可用**
   ```bash
   which iostat
   # 如果不存在，重新安装sysstat
   ```

4. **日志文件过大**
   - 脚本会自动轮转日志
   - 可在配置文件中调整 `LOG_RETENTION_DAYS`

### 日志查看
```bash
# 查看实时日志
tail -f /root/logs/disk_monitor.log

# 查看历史日志
ls -la /root/logs/
```

## 性能优化建议

1. **调整检查间隔**: 根据服务器负载调整 `CHECK_INTERVAL`
2. **选择性监控**: 在 `DEVICES` 中指定特定设备
3. **日志清理**: 定期清理旧日志文件
4. **告警优化**: 避免频繁告警，设置合理的阈值

## 安全注意事项

1. 脚本需要root权限运行
2. 定期更新系统和依赖包
3. 保护配置文件中的敏感信息
4. 限制日志文件访问权限

## 技术支持

如遇问题，请检查：
1. 系统日志: `/var/log/messages`
2. 脚本日志: `/root/logs/disk_monitor.log`
3. 配置文件: `/root/disk_monitor.conf`
4. 运行状态: `./disk_monitor.sh -s`
