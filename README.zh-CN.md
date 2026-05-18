# Auto TikTok / 抖音 TikTok 自动短视频工厂

[English](README.md) | [简体中文](README.zh-CN.md)

基于 MiniMax、FFmpeg、Docker 和本地 Dashboard 的抖音/TikTok 短视频自动生成与发布准备工作流。

AI-powered Douyin/TikTok short-video autopilot built on MiniMax, FFmpeg, Docker, and a local operations dashboard.

![Python](https://img.shields.io/badge/Python-3.10%2B-3776AB)
![Docker](https://img.shields.io/badge/Docker-ready-2496ED)
![License](https://img.shields.io/badge/License-MIT-green)
![Status](https://img.shields.io/badge/Status-MVP%20Autopilot-orange)

Auto TikTok 可以把选题自动转成可发布的竖屏短视频内容包：脚本、旁白、字幕、封面、视频素材、质量评分、发布包和运行报告都会结构化落盘。项目还内置本地 Dashboard、任务队列、Docker 运行方式、健康检查、备份、日志轮转，以及可选 TikTok 官方 Content Posting API 适配。

## 核心亮点

- **Topic-to-video Autopilot**：自动选题、脚本、TTS、视频、字幕、封面、合成、质量门槛、发布包导出。
- **结构化 VideoPlan**：每条内容都会写入 `video_plan.json`，包含脚本、镜头、标题、字幕、封面、模型调用计划和资产路径。
- **本地 Dashboard/API**：配额快照、历史 run、失败原因、任务队列、单资产重生成、发布动作和 Autopilot 控制。
- **MiniMax Token Plan 支持**：Max/Ultra 路由、配额统计、模型回退和 manifest 审计字段。
- **发布链路**：默认导出人工发布包；配置 OAuth 后可选调用 TikTok 官方 Content Posting API。
- **产品化基线**：Docker、healthcheck、本机默认绑定、会话/CSRF 防护、日志脱敏、备份、日志轮转和迁移脚本。

## 项目定位

当前项目定位是 **本地优先的短视频生产与发布准备系统**。Autopilot 可以全自动执行内容生成。真正直连 TikTok 发布时，需要你自行完成 TikTok 开发者应用、权限审核、OAuth 授权、账号合规和 `TIKTOK_ACCESS_TOKEN` 配置。

如果没有配置 TikTok 凭证，Autopilot 会自动回退到人工发布包导出。

## 快速开始

```bash
pip install -r requirements.txt
cp .env.example .env
python autopilot.py run --dry-run --count 3
python dashboard.py --host 127.0.0.1 --port 7860
```

Docker：

```bash
docker compose up --build dashboard
```

打开：

```text
http://127.0.0.1:7860
```

## 前置要求

- Python 3.10+
- `ffmpeg` 与 `ffprobe` 已安装并可在命令行直接调用
- MiniMax Token Plan API Key
- Docker Desktop，可选但推荐

## 配置

在项目根目录创建 `.env`：

```env
MINIMAX_TOKEN_PLAN_TIER=max
MINIMAX_TOKEN_PLAN_KEY2=your_max_token_plan_key
```

说明：

- `MINIMAX_TOKEN_PLAN_TIER=max` 会按 Max-only 模式运行。
- Max-only 模式优先读取 `MINIMAX_TOKEN_PLAN_KEY2`，如果没有则回退到 `MINIMAX_TOKEN_PLAN_KEY`。
- 如果同时持有 Ultra 与 Max Key，可以不设置套餐，并同时配置 `MINIMAX_TOKEN_PLAN_KEY` 与 `MINIMAX_TOKEN_PLAN_KEY2`。
- 不要提交或分享 `.env`、API Key、访问令牌、Docker config 输出，以及包含隐私信息的日志。

主要自动化配置文件：

```text
config/auto_config.yaml
```

当前默认值更贴近真实配额：

- 每日默认生成 `3` 条
- 默认开启视频
- 默认开启缩略图
- 默认关闭音乐
- 默认语音：`female_tianmei`
- 默认调度时间：`09:00`

## Autopilot 全自动模式

```bash
python autopilot.py run --count 3 --min-score 65 --provider manual
python autopilot.py run --count 3 --types 生活技巧,知识科普 --provider auto
python autopilot.py run --dry-run --count 5
```

Autopilot 会自动：

- 从本地 `trending_topics` 和可选外部热榜 URL 生成候选选题；
- 根据视频/图片配额收敛目标数量；
- 生成多个脚本候选并按评分门槛筛选；
- 低分内容跳过高成本视频阶段，继续尝试下一个选题；
- 成片缺失时自动修复 `video`、`subtitle`、`compose`、`cover` 等资产；
- 默认导出发布包；
- 配置 TikTok access token 后才调用 TikTok 发布。

可选外部热榜：

```env
AUTO_TIKTOK_TRENDING_URLS=https://example.com/topics.json
```

## 本地 Dashboard

启动 Dashboard：

```bash
python dashboard.py --host 127.0.0.1 --port 7860
```

Windows 也可以直接运行：

```bash
start_dashboard.bat
```

Dashboard 支持：

- Max/Ultra 配额快照；
- 历史 run 与每条内容状态；
- `content_manifest.json` / `video_plan.json` 摘要；
- 失败原因查看；
- 单资产重生成：`tts`、`video`、`thumbnail`、`subtitle`、`compose`、`cover`、`titles`；
- 任务队列：生成、重生成、发布任务的状态与失败原因；
- 发布动作：导出发布包，或在配置 OAuth 后调用 TikTok 官方发布 API；
- Autopilot：自动选题、生成、质量门槛、修复、发布包导出。

如果要绑定非本地地址，必须设置访问令牌：

```env
AUTO_TIKTOK_DASHBOARD_TOKEN=replace_with_a_long_random_token
AUTO_TIKTOK_DASHBOARD_SESSION_SECONDS=86400
AUTO_TIKTOK_DASHBOARD_SECURE_COOKIES=false
```

如果走 HTTPS 反向代理，应设置：

```env
AUTO_TIKTOK_DASHBOARD_SECURE_COOKIES=true
```

## Docker 一键启动

Dashboard：

```bash
docker compose up --build dashboard
```

一次性执行每日生成：

```bash
docker compose --profile run-once up --build run-once
```

一次性执行 Autopilot：

```bash
docker compose --profile autopilot up --build autopilot
```

Compose 已包含：

- `/healthz` 健康检查；
- 默认绑定 `127.0.0.1:7860`，不会直接公网暴露；
- `json-file` 日志轮转；
- 挂载 `output/`、`logs/`、`backups/` 和 `config/auto_config.yaml`。

## 发布链路

默认发布方式是导出人工发布包，产物会写到：

```text
publish/publish_package.json
```

如果要调用 TikTok 官方 Content Posting API，需要配置：

```env
TIKTOK_ACCESS_TOKEN=your_oauth_access_token
TIKTOK_POST_MODE=inbox
TIKTOK_PRIVACY_LEVEL=SELF_ONLY
```

模式说明：

- `TIKTOK_POST_MODE=inbox`：走 TikTok Inbox 上传初始化。
- `TIKTOK_POST_MODE=direct`：走 Direct Post 初始化，并使用 `TIKTOK_PRIVACY_LEVEL`。

真实可发布性取决于 TikTok 开发者应用权限、OAuth scope、账号状态和平台审核。

## 定时任务

安装 Windows 定时 Autopilot：

```bash
python auto_scheduler.py --install-task --autopilot --time 09:00 --count 3 --min-score 65 --provider auto
```

立即执行一次 Autopilot：

```bash
python auto_scheduler.py --run-now --autopilot --count 1 --provider manual
```

## 输出结构

```text
output/
├── _system/
│   └── tasks/
├── YYYY-MM-DD/
│   └── run_<run_id>/
│       ├── 001/
│       │   ├── script.json
│       │   ├── titles.json
│       │   ├── score.json
│       │   ├── video_plan.json
│       │   ├── content_manifest.json
│       │   ├── publish/
│       │   ├── *.mp3 / *.mp4 / cover.jpg / subtitle.srt
│       ├── 002/
│       ├── daily_generation_report.json
│       ├── autopilot_report.json
│       ├── weekly_plan_YYYYMMDD.json
│       └── run_manifest.json
```

每次执行都会创建一个新的 `run_<run_id>`。每条内容会进入三位编号目录，如 `001`，并写入 `content_manifest.json` 和结构化 `video_plan.json`。

## 常用命令

生成通用内容包：

```bash
python main.py --topic "咖啡文化" --style "文艺清新"
python main.py --batch examples/topics.txt
```

生成抖音优化内容：

```bash
python douyin_main.py --topic "咖啡文化" --type "生活技巧"
python douyin_main.py --daily --count 3
python douyin_main.py --weekly
```

输出审计：

```bash
python output_manager.py audit --json
python output_manager.py maintain --archive-test-artifacts
```

运维：

```bash
python ops.py health
python ops.py backup
python ops.py rotate-logs --keep-days 14
python ops.py migrate
```

## Token Plan 行为

项目会把真实路由结果写入 manifest / report：

- `key_tier_used`
- `requested_model`
- `applied_model`
- `requested_video_spec`
- `applied_video_spec`
- `cross_tier_fallback`

当前 Token Plan 规则：

- Max-only：`MINIMAX_TOKEN_PLAN_TIER=max`
- 未显式设置套餐时：Ultra 优先，然后 Max 回退
- 文本：Ultra 使用 `MiniMax-M2.7-highspeed`，Max 使用 `MiniMax-M2.7`
- TTS：`speech-2.8-hd`
- 图片：`image-01`
- 音乐：`music-2.6`
- 视频：`MiniMax-Hailuo-2.3` 或 `MiniMax-Hailuo-2.3-Fast`
- Token Plan 视频规格统一收敛为 `768P + 6s`

图片、语音、音乐、视频这类生成型 `POST` 请求带有幂等性保护，不会自动重试，避免重复扣费或重复生成。

## 字幕

默认字幕引擎会根据真实音频时长估算字幕时间。若本机已单独安装 WhisperX，可配置：

```env
AUTO_TIKTOK_SUBTITLE_ENGINE=whisperx
```

可用时系统会写入 `word_timestamps.json`，用于字级字幕时间戳。WhisperX 不可用时会自动回退到估算字幕。

## 测试与校验

```bash
python -m pytest -q
python -m ruff check .
python -m compileall config src main.py douyin_main.py auto_scheduler.py run_daily.py dashboard.py autopilot.py ops.py output_manager.py
```

## 文档

- [Autopilot](docs/AUTOPILOT.md)
- [部署](docs/DEPLOYMENT.md)
- [推广](docs/PROMOTION.md)
- [抖音指南](DOUYIN_GUIDE.md)
- [自动化使用](AUTO_USAGE.md)
- [安全策略](SECURITY.md)
- [贡献指南](CONTRIBUTING.md)

## 常见问题

### `API 错误[2061]: your current token plan not support model`

说明当前套餐不支持该模型。请使用支持该模型的套餐，或在调用时关闭视频生成，例如 `--no-video`。

### `API 错误[2049]: invalid api key`

请检查 `.env` 中的 `MINIMAX_TOKEN_PLAN_KEY` 与 `MINIMAX_TOKEN_PLAN_KEY2`。如果 Key 曾经泄露，应立即轮换。

### `ffmpeg` / `ffprobe` 找不到

请确认它们已经安装并在 PATH 中可用：

```bash
ffmpeg -version
ffprobe -version
```

### 为什么默认不自动生成音乐？

当前自动化路径默认需要纯背景音乐，而 `music-2.6` 更适合带歌词歌曲生成。为了保证视频生成稳定、配额可控，项目默认关闭音乐。

## 致谢

- [MiniMax](https://www.minimaxi.com/)
- [MiniMax 开放平台](https://platform.minimaxi.com/)
