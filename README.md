# Auto TikTok

AI-powered short-video autopilot for Douyin/TikTok creators. It turns topics into publish-ready vertical videos with scripts, voiceover, subtitles, covers, quality gates, local dashboard, Docker deployment, and optional TikTok Content Posting API integration.

![Python](https://img.shields.io/badge/Python-3.10%2B-3776AB)
![Docker](https://img.shields.io/badge/Docker-ready-2496ED)
![License](https://img.shields.io/badge/License-MIT-green)
![Status](https://img.shields.io/badge/Status-MVP%20Autopilot-orange)

基于 MiniMax API 的短视频素材生产流水线，面向抖音/短视频内容创作。

## Highlights

- Topic-to-video Autopilot: 自动选题、脚本、TTS、视频、字幕、封面、合成、发布包
- Structured `video_plan.json`: 每条内容都有可恢复、可重生成的生产蓝图
- Dashboard/API: 本地看板、配额、历史、失败原因、任务队列、Autopilot 启动
- Production baseline: Docker、healthcheck、日志脱敏、CSRF、备份、日志轮转
- Publishing: 默认导出发布包，可选 TikTok 官方 Content Posting API

## Quick Start

```bash
pip install -r requirements.txt
cp .env.example .env
python autopilot.py run --dry-run --count 3
python dashboard.py --host 127.0.0.1 --port 7860
```

Docker:

```bash
docker compose up --build dashboard
```

当前项目已经支持：

- 生成脚本、标题、旁白
- 合成语音、视频、缩略图
- 生成抖音优化内容包
- 生成每日任务与周计划
- 按 `run` 维度保存产物、报告和 manifest
- 为每条内容生成 `video_plan.json`，支持后续查看、恢复和单资产重生成
- 内置本地 Dashboard/API，可查看配额、运行历史、失败原因、队列任务并触发重生成/发布
- 支持手动发布包导出，以及可选 TikTok 官方 Content Posting API 发布适配
- 支持 Autopilot 全自动模式：自动选题、生成、质量门槛、失败修复和自动导出/发布

当前项目默认定位是“内容生产 + 发布准备 + 本地运维 + 全自动批量生成”。TikTok 官方发布链路需要你自行完成开发者应用、OAuth 授权、平台审核和 `TIKTOK_ACCESS_TOKEN` 配置；未配置时 Autopilot 会自动导出人工发布包。

## 功能概览

- **通用流水线**：文本、语音、视频、图片统一编排
- **抖音优化**：黄金 3 秒、互动引导、标题候选、评分、封面、字幕
- **自动化执行**：支持立即执行、内存调度、Windows 定时任务
- **输出治理**：按日期 / run / content 分层落盘，便于追踪每次执行结果
- **任务队列**：Dashboard 操作会进入本地持久化队列，支持状态查看、失败记录和取消排队任务
- **运维工具**：内置健康检查、备份、日志轮转和 manifest 迁移脚本
- **Autopilot**：按配额自动决定可生成数量，低分自动跳过并换题，达标后自动修复缺失资产并进入发布链路

## 前置要求

- Python 3.10+
- `ffmpeg` 与 `ffprobe` 已安装并可在命令行直接调用
- MiniMax Token Plan API Key

## 安装

```bash
pip install -r requirements.txt
```

## 配置

### 1. `.env`

在项目根目录创建 `.env`：

```env
MINIMAX_TOKEN_PLAN_TIER=max
MINIMAX_TOKEN_PLAN_KEY2=your_max_token_plan_key
```

说明：

- `MINIMAX_TOKEN_PLAN_TIER=max` 会按 `Max-标准版` 运行，只走 Max 路由
- Max-only 模式优先读取 `MINIMAX_TOKEN_PLAN_KEY2`；如果只配置了 `MINIMAX_TOKEN_PLAN_KEY`，也会把它当作 Max Key 使用
- 如果同时持有 Ultra 与 Max Key，可不设置 `MINIMAX_TOKEN_PLAN_TIER`，并使用 `MINIMAX_TOKEN_PLAN_KEY` + `MINIMAX_TOKEN_PLAN_KEY2`
- 未显式设置套餐时，路由默认为 **Ultra 优先**；认证失败、模型不支持、额度不足、限流会按真实语义处理
- 现在不是“认证备用 Key”逻辑，而是“套餐能力路由 + 配额回退”

### 2. `config/auto_config.yaml`

自动化默认参数从 `C:\Users\Yanzh\Desktop\auto-tiktok\config\auto_config.yaml` 读取，当前默认值已调整为更接近真实配额：

- 每日默认生成 `3` 条
- 默认开启视频、缩略图
- 默认关闭音乐
- 默认语音：`female_tianmei`
- 默认调度时间：`09:00`

`automation.schedule` 支持两种写法：

- `09:00`
- `0 9 * * *`

## 快速开始

### 生成单个通用内容包

```bash
python main.py --topic "咖啡文化" --style "文艺清新"
```

### 批量生成

```bash
python main.py --batch examples/topics.txt
```

### 生成抖音优化内容

```bash
python douyin_main.py --topic "咖啡文化" --type "生活技巧"
```

### 生成每日内容

```bash
python douyin_main.py --daily
python douyin_main.py --daily --count 5
```

### 生成周计划

```bash
python douyin_main.py --weekly
```

### 立即执行一次自动化任务

```bash
python auto_scheduler.py --run-now
python auto_scheduler.py --run-now --count 3 --types 生活技巧,知识科普
```

### 启动 Autopilot 全自动模式

```bash
python autopilot.py run --count 3 --min-score 65 --provider manual
python autopilot.py run --count 3 --types 生活技巧,知识科普 --provider auto
python autopilot.py run --dry-run --count 5
```

Autopilot 会自动执行：

- 从本地 `trending_topics` 和可选外部热榜 URL 生成候选选题
- 根据视频/图片配额收敛目标数量
- 生成脚本候选并按评分门槛筛选
- 低分内容跳过高成本视频阶段，并继续尝试下一个选题
- 成片缺失时按配置重试 `video`、`subtitle`、`compose`、`cover`
- 达标后自动导出发布包；`--provider auto` 在存在 `TIKTOK_ACCESS_TOKEN` 时走 TikTok，否则回退到发布包

可选外部热榜：

```env
AUTO_TIKTOK_TRENDING_URLS=https://example.com/topics.json
```

### 启动本地 Dashboard

```bash
python dashboard.py --host 127.0.0.1 --port 7860
```

Windows 可直接运行：

```bash
start_dashboard.bat
```

打开 `http://127.0.0.1:7860` 后可查看：

- Max/Ultra 配额快照
- 历史 run 与每条内容状态
- `content_manifest.json` / `video_plan.json` 摘要
- 失败原因
- 单资产重生成：`tts`、`video`、`thumbnail`、`subtitle`、`compose`、`cover`、`titles`
- 任务队列：生成、重生成、发布任务的状态与失败原因
- 发布动作：导出发布包，或在配置 OAuth 后调用 TikTok 官方发布 API
- Autopilot：自动选题、生成、质量门槛、修复、发布包导出

Dashboard 默认适合本机/内网使用。如果要绑定非本地地址，必须设置：

```env
AUTO_TIKTOK_DASHBOARD_TOKEN=replace_with_a_long_random_token
AUTO_TIKTOK_DASHBOARD_SESSION_SECONDS=86400
AUTO_TIKTOK_DASHBOARD_SECURE_COOKIES=false
```

说明：

- 设置 `AUTO_TIKTOK_DASHBOARD_TOKEN` 后，Dashboard 会启用登录、会话 Cookie 和 CSRF 校验
- Docker Compose 默认把端口映射到 `127.0.0.1:7860`，不会直接暴露到公网
- 如需 HTTPS 反代，应把 `AUTO_TIKTOK_DASHBOARD_SECURE_COOKIES=true`
- 不要把 `.env`、访问令牌或 Docker `config` 输出发给他人

### Docker 一键启动

```bash
docker compose up --build dashboard
```

一次性执行每日生成任务：

```bash
docker compose --profile run-once up --build run-once
```

一次性执行 Autopilot：

```bash
docker compose --profile autopilot up --build autopilot
```

容器内置 `/healthz` 健康检查，Compose 已启用 `json-file` 日志轮转，并挂载：

- `./output:/app/output`
- `./logs:/app/logs`
- `./backups:/app/backups`
- `./config/auto_config.yaml:/app/config/auto_config.yaml:ro`

### 发布链路

默认发布方式是导出人工发布包：

```bash
# 在 Dashboard 中点击“导出发布包”
```

产物会写到对应内容目录：

```text
publish/publish_package.json
```

如果要调用 TikTok 官方 Content Posting API，需要先配置：

```env
TIKTOK_ACCESS_TOKEN=your_oauth_access_token
TIKTOK_POST_MODE=inbox
TIKTOK_PRIVACY_LEVEL=SELF_ONLY
```

说明：

- `TIKTOK_POST_MODE=inbox` 会走 TikTok Inbox 上传初始化
- `TIKTOK_POST_MODE=direct` 会走 Direct Post 初始化，并使用 `TIKTOK_PRIVACY_LEVEL`
- 项目会上传视频文件并写回 `publish/tiktok_publish_status.json`
- 真实可发布性取决于 TikTok 开发者应用权限、OAuth scope、账号状态和平台审核

### 定时 Autopilot

```bash
python auto_scheduler.py --install-task --autopilot --time 09:00 --count 3 --min-score 65 --provider auto
python auto_scheduler.py --run-now --autopilot --count 1 --provider manual
```

`--autopilot` 会让计划任务调用 `autopilot.py run`，不再依赖 Dashboard 点击确认。

### 运维命令

```bash
python ops.py health
python ops.py backup
python ops.py rotate-logs --keep-days 14
python ops.py migrate
```

说明：

- `health` 会审计输出目录并返回健康状态
- `backup` 会备份 `output/`、`logs/`、`config/` 和关键启动文件，默认不包含根目录 `.env`
- `rotate-logs` 会把过期日志移动到 `logs/_archive/`
- `migrate` 会修复旧输出目录缺失的 `run_manifest.json`，并创建任务队列系统目录

### 安装 Windows 定时任务

```bash
python auto_scheduler.py --install-task --time 09:00 --count 3 --min-score 65
```

现在安装任务时会把 `count`、`min-score`、`concurrent`、`types` 一并写入计划任务命令行。

## 输出结构

当前真实输出结构如下：

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

说明：

- 每次执行都会创建一个新的 `run_<run_id>`
- 每条内容有自己的三位编号目录，如 `001`
- 每条内容都会写 `content_manifest.json`
- 每条内容都会写 `video_plan.json`，作为脚本、镜头、封面、标题、字幕、模型调用计划和资产路径的结构化蓝图
- 每次运行会把 `daily_generation_report.json`、`weekly_plan_*.json` 等报告直接写在该次 `run` 根目录，减少 `reports/` 这层嵌套
- Autopilot 运行会额外写 `autopilot_report.json`，记录候选选题、跳过原因、修复记录和发布结果
- 每次运行都会写 `run_manifest.json`

## 主要命令

### `main.py`

```bash
python main.py --topic "城市夜景"
python main.py --topic "旅行日记" --no-video --no-music --no-thumbnail
python main.py --batch examples/topics.txt --duration 10
```

### `douyin_main.py`

```bash
python douyin_main.py --topic "冷知识" --type "知识科普"
python douyin_main.py --daily --count 3
python douyin_main.py --weekly
```

### `output_manager.py`

```bash
python output_manager.py audit --json
python output_manager.py maintain --archive-test-artifacts
python ops.py health
python ops.py backup
python ops.py rotate-logs --keep-days 14
python ops.py migrate
python autopilot.py run --dry-run --count 3
```

## 运行特性

### Token Plan 审计结论（2026-04）

当前实现已经按官方 Token Plan 文档和真实接口行为收敛为以下规则：

- **Key 映射**：
  - `MINIMAX_TOKEN_PLAN_TIER=max`：按 `Max-标准版` 使用，只走 Max 路由
  - 未设置套餐时：`MINIMAX_TOKEN_PLAN_KEY` = `Ultra-极速版`，`MINIMAX_TOKEN_PLAN_KEY2` = `Max-标准版`
- **路由**：Max-only 配置只走 `Max`；未设置套餐时默认 `Ultra -> Max`
- **文本模型**：
  - Ultra：`MiniMax-M2.7-highspeed`
  - Max：`MiniMax-M2.7`
- **非文本模型**：
  - TTS：`speech-2.8-hd`
  - 图片：`image-01`
  - 音乐：`music-2.6`
  - 视频：`MiniMax-Hailuo-2.3` / `MiniMax-Hailuo-2.3-Fast`
- **视频规格**：Token Plan 路径统一归一化到 `768P + 6s`
- **错误语义**：
  - `2049 / 401 / 403`：认证问题
  - `2061`：套餐不支持模型
  - `2056 / 429 / 1002 / 1008 / 2045`：额度或容量问题
- **幂等性保护**：图片 / 语音 / 音乐 / 视频这类生成型 `POST` 请求不会自动重试，避免重复扣费或重复生成

项目里每次生成都会把这些实际路由结果写进 manifest / report，包括：

- `key_tier_used`
- `requested_model`
- `applied_model`
- `requested_video_spec`
- `applied_video_spec`
- `cross_tier_fallback`

### 视频模型降级

Token Plan 路径下，视频只会使用官方支持的 Hailuo-2.3 系列：

1. **文生视频**：统一使用 `MiniMax-Hailuo-2.3`
2. **图生视频**：优先使用 `MiniMax-Hailuo-2.3-Fast`

默认视频规格固定收敛为 `768P + 6s`。如果请求了更高规格，结果里会保留 `requested/applied` 差异。

补充说明：

- Ultra / Max 下 **文生视频** 都不会再尝试 `MiniMax-Hailuo-2.3-Fast`
- Ultra / Max 下 **图生视频** 仍可使用 `MiniMax-Hailuo-2.3-Fast`
- 自动化默认会优先尝试 **Fast 图生视频**：先用 `image-01` 生成首帧图，再走 `MiniMax-Hailuo-2.3-Fast`
- 当 Fast 额度不可用、首帧图不可得或流程不适配时，再回退到 **Standard 文生视频**
- 如果首帧图被生成出来且启用了缩略图，该首帧图会直接复用为 `cover.jpg`，避免重复消耗图片额度

### 字幕时长校准

当前字幕生成会优先根据真实音频时长校准语速，减少字幕和旁白漂移。

### WhisperX 兼容字幕

默认字幕引擎仍是本地估算模式，不增加额外依赖。若本机已单独安装 WhisperX，可在 `.env` 中设置：

```env
AUTO_TIKTOK_SUBTITLE_ENGINE=whisperx
```

系统会优先用 WhisperX 生成字级时间戳，并把 `word_timestamps.json` 保存到内容目录；WhisperX 不可用时会回退到估算字幕。也可以通过 `SubtitleGenerator.generate_srt_from_whisperx_json()` 直接把已有 WhisperX JSON 转为 SRT。

### 配额记录

- 文本请求：5 小时窗口
- TTS：按字符统计
- 视频 / 音乐 / 图片：成功后才记账
- `remains` 接口优先使用官方远端状态；远端超时或异常时自动回退到本地状态

补充说明：

- 当前官方 `remains` 返回中的 `current_interval_usage_count` 在真实行为上应按“**剩余**”理解，而不是“已用”
- 当 `remains` 返回异常或空载荷时，项目会保留上一份有效远端缓存，不会把状态错误清空

## 常见问题

### 1. `API 错误[2061]: your current token plan not support model`

说明当前套餐不支持该模型。系统会先尝试当前套餐对应的支持模型，再按 Ultra -> Max 回退；如果全部失败，需要：

- 更换支持视频模型的套餐
- 或在调用时关闭视频生成（如 `--no-video`）

### 2. `API 错误[2049]: invalid api key`

说明 Key 无效。请检查 `.env` 中：

- `MINIMAX_TOKEN_PLAN_KEY`（Ultra）
- `MINIMAX_TOKEN_PLAN_KEY2`（Max）

### 3. `ffmpeg` / `ffprobe` 找不到

请确认它们已经安装并在 PATH 中可用：

```bash
ffmpeg -version
ffprobe -version
```

### 4. 为什么默认不自动生成音乐？

因为当前 Token Plan 自动化路径的“背景音乐”默认需求是**纯音乐**，而真实接口实测下：

- `music-2.6` 可生成**带歌词歌曲**
- 当前 Token Plan 默认**不支持纯音乐背景音乐**

所以自动化默认：

- 视频：开启
- 缩略图：开启
- 音乐：关闭

即使手动开启 `auto_generate_music`，自动化也会在不支持纯音乐时**跳过音乐而不让整包失败**，并把 `status=skipped` / `skip_reason` 写进 manifest。

如果你要真实使用音乐能力，请走“带歌词歌曲生成”路径，而不是依赖自动背景音乐。

### 5. 为什么有时 `chat_completion` 成功但 `content` 为空？

MiniMax 文本模型可能先产出 `reasoning_content`。如果 `max_completion_tokens` 设得太小，可能在思维 token 用完前就触发 `finish_reason=length`，导致 `message.content` 为空。

项目内默认脚本/标题生成没有把 `max_completion_tokens` 压得很低，因此正常流程可用；如果你自己调用底层 `chat_completion()`，不要把 token 上限设得过小。

## 测试与校验

```bash
python -m pytest -q
python -m ruff check .
python -m compileall config src main.py douyin_main.py auto_scheduler.py run_daily.py dashboard.py autopilot.py ops.py output_manager.py
```

## 依赖说明

`requirements.txt` 当前包含：

- `requests`
- `python-dotenv`
- `pyyaml`
- `schedule`
- `colorama`
- `tqdm`

## 致谢

- [MiniMax](https://www.minimaxi.com/)
- [MiniMax 开放平台文档](https://platform.minimaxi.com/)
