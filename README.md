# Auto TikTok

[English](README.md) | [简体中文](README.zh-CN.md)

AI-powered Douyin/TikTok short-video autopilot built on MiniMax, FFmpeg, Docker, and a local operations dashboard.

基于 MiniMax 的抖音/TikTok 短视频自动生成与发布工作流。中文文档请看 [README.zh-CN.md](README.zh-CN.md)。

![Python](https://img.shields.io/badge/Python-3.10%2B-3776AB)
![Docker](https://img.shields.io/badge/Docker-ready-2496ED)
![License](https://img.shields.io/badge/License-MIT-green)
![Status](https://img.shields.io/badge/Status-MVP%20Autopilot-orange)

Auto TikTok turns topics into publish-ready vertical videos. It plans the content, generates scripts, voiceover, subtitles, covers, video assets, quality reports, and publishing packages. It also includes a browser dashboard, task queue, Docker runtime, health checks, backups, and an optional TikTok Content Posting API adapter.

## Highlights

- **Topic-to-video Autopilot**: automatic topic selection, script generation, TTS, video assets, subtitles, cover, composition, quality gates, and publishing package export.
- **Structured VideoPlan**: every content item writes a durable `video_plan.json` containing script, shots, title, subtitle, cover, model calls, and asset paths.
- **Local Dashboard/API**: quota snapshot, run history, failure reasons, task queue, asset regeneration, publish actions, and Autopilot controls.
- **MiniMax Token Plan support**: Max/Ultra routing, quota accounting, model fallback, and explicit audit fields in manifests.
- **Publishing workflow**: manual publish package by default, optional TikTok official Content Posting API integration when OAuth is configured.
- **Production baseline**: Docker, healthcheck, local-only default binding, CSRF/session protection, log redaction, backup, log rotation, and migration helpers.

## Product Scope

This project is designed as a **local-first short-video production and publishing-preparation system**. It can run fully automated content generation through Autopilot. Direct TikTok publishing requires your own TikTok developer application, approved permissions, OAuth access token, and platform compliance review.

When TikTok credentials are not configured, Autopilot automatically falls back to exporting a manual publishing package.

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

Open:

```text
http://127.0.0.1:7860
```

## Requirements

- Python 3.10+
- `ffmpeg` and `ffprobe` available in `PATH`
- MiniMax Token Plan API key
- Docker Desktop, optional but recommended

## Configuration

Create `.env` in the project root:

```env
MINIMAX_TOKEN_PLAN_TIER=max
MINIMAX_TOKEN_PLAN_KEY2=your_max_token_plan_key
```

Notes:

- `MINIMAX_TOKEN_PLAN_TIER=max` runs in Max-only mode.
- Max-only mode reads `MINIMAX_TOKEN_PLAN_KEY2` first, then falls back to `MINIMAX_TOKEN_PLAN_KEY`.
- If you own both Ultra and Max keys, leave the tier unset and configure both `MINIMAX_TOKEN_PLAN_KEY` and `MINIMAX_TOKEN_PLAN_KEY2`.
- Do not commit or share `.env`, API keys, access tokens, Docker config output, or generated logs containing private data.

Main automation settings live in:

```text
config/auto_config.yaml
```

Default behavior is tuned for realistic quota usage:

- daily target count: `3`
- video: enabled
- thumbnail: enabled
- music: disabled by default
- voice: `female_tianmei`
- schedule time: `09:00`

## Autopilot

Autopilot is the hands-off production path:

```bash
python autopilot.py run --count 3 --min-score 65 --provider manual
python autopilot.py run --count 3 --types 生活技巧,知识科普 --provider auto
python autopilot.py run --dry-run --count 5
```

It automatically:

- builds topic candidates from local `trending_topics` and optional external topic URLs;
- limits the target count by available video/image quota;
- generates multiple script candidates and applies score gates;
- skips low-score content before high-cost video generation;
- repairs missing assets such as video, subtitle, final composition, and cover;
- exports publish packages by default;
- uses TikTok publishing only when a valid access token is configured.

Optional external topic sources:

```env
AUTO_TIKTOK_TRENDING_URLS=https://example.com/topics.json
```

## Dashboard

Start the local dashboard:

```bash
python dashboard.py --host 127.0.0.1 --port 7860
```

Windows helper:

```bash
start_dashboard.bat
```

The dashboard supports:

- Max/Ultra quota snapshots;
- run history and per-content status;
- `content_manifest.json` and `video_plan.json` summaries;
- failure reason inspection;
- single-asset regeneration for `tts`, `video`, `thumbnail`, `subtitle`, `compose`, `cover`, and `titles`;
- queue status for generation, regeneration, and publishing tasks;
- publishing package export or TikTok API publishing;
- Autopilot run controls.

If you bind the dashboard to a non-localhost address, set an access token:

```env
AUTO_TIKTOK_DASHBOARD_TOKEN=replace_with_a_long_random_token
AUTO_TIKTOK_DASHBOARD_SESSION_SECONDS=86400
AUTO_TIKTOK_DASHBOARD_SECURE_COOKIES=false
```

For HTTPS reverse proxies, set:

```env
AUTO_TIKTOK_DASHBOARD_SECURE_COOKIES=true
```

## Docker

Dashboard:

```bash
docker compose up --build dashboard
```

One-off daily generation:

```bash
docker compose --profile run-once up --build run-once
```

One-off Autopilot run:

```bash
docker compose --profile autopilot up --build autopilot
```

Compose includes:

- `/healthz` healthcheck;
- local-only default port binding: `127.0.0.1:7860`;
- `json-file` log rotation;
- mounted `output/`, `logs/`, `backups/`, and `config/auto_config.yaml`.

## Publishing

Manual publish package export is the default publishing workflow. The package is written to:

```text
publish/publish_package.json
```

To use TikTok's official Content Posting API, configure:

```env
TIKTOK_ACCESS_TOKEN=your_oauth_access_token
TIKTOK_POST_MODE=inbox
TIKTOK_PRIVACY_LEVEL=SELF_ONLY
```

Modes:

- `TIKTOK_POST_MODE=inbox`: upload through TikTok Inbox initialization.
- `TIKTOK_POST_MODE=direct`: use Direct Post initialization and `TIKTOK_PRIVACY_LEVEL`.

Actual publishing availability depends on TikTok developer app approval, OAuth scopes, account status, and platform rules.

## Scheduled Runs

Install a Windows scheduled Autopilot task:

```bash
python auto_scheduler.py --install-task --autopilot --time 09:00 --count 3 --min-score 65 --provider auto
```

Run Autopilot immediately:

```bash
python auto_scheduler.py --run-now --autopilot --count 1 --provider manual
```

## Output Structure

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

Each run creates a new `run_<run_id>` directory. Each content item gets a three-digit folder such as `001`, plus a manifest and a structured `video_plan.json`.

## Common Commands

General content package:

```bash
python main.py --topic "coffee culture" --style "warm documentary"
python main.py --batch examples/topics.txt
```

Douyin-optimized content:

```bash
python douyin_main.py --topic "咖啡文化" --type "生活技巧"
python douyin_main.py --daily --count 3
python douyin_main.py --weekly
```

Output audit:

```bash
python output_manager.py audit --json
python output_manager.py maintain --archive-test-artifacts
```

Operations:

```bash
python ops.py health
python ops.py backup
python ops.py rotate-logs --keep-days 14
python ops.py migrate
```

## Token Plan Behavior

The implementation records real routing details in manifests and reports:

- `key_tier_used`
- `requested_model`
- `applied_model`
- `requested_video_spec`
- `applied_video_spec`
- `cross_tier_fallback`

Current Token Plan rules:

- Max-only mode: `MINIMAX_TOKEN_PLAN_TIER=max`
- Default routing without explicit tier: Ultra first, then Max fallback
- Text: `MiniMax-M2.7-highspeed` for Ultra, `MiniMax-M2.7` for Max
- TTS: `speech-2.8-hd`
- Image: `image-01`
- Music: `music-2.6`
- Video: `MiniMax-Hailuo-2.3` or `MiniMax-Hailuo-2.3-Fast`
- Token Plan video output is normalized to `768P + 6s`

Idempotency protection is enabled for generation-style `POST` calls such as image, voice, music, and video creation to avoid accidental duplicate generation.

## Subtitles

The default subtitle engine estimates timing from real audio duration. WhisperX compatibility is available when WhisperX is installed separately:

```env
AUTO_TIKTOK_SUBTITLE_ENGINE=whisperx
```

When available, the system writes `word_timestamps.json` for word-level subtitle timing. If WhisperX is unavailable, it falls back to estimated subtitles.

## Validation

```bash
python -m pytest -q
python -m ruff check .
python -m compileall config src main.py douyin_main.py auto_scheduler.py run_daily.py dashboard.py autopilot.py ops.py output_manager.py
```

## Documentation

- [Autopilot](docs/AUTOPILOT.md)
- [Deployment](docs/DEPLOYMENT.md)
- [Promotion](docs/PROMOTION.md)
- [Douyin Guide](DOUYIN_GUIDE.md)
- [Automation Usage](AUTO_USAGE.md)
- [Security Policy](SECURITY.md)
- [Contributing](CONTRIBUTING.md)

## FAQ

### `API error [2061]: your current token plan not support model`

The current token plan does not support the requested model. Use a supported plan/model or disable video generation with options such as `--no-video`.

### `API error [2049]: invalid api key`

Check `MINIMAX_TOKEN_PLAN_KEY` and `MINIMAX_TOKEN_PLAN_KEY2` in `.env`. Rotate leaked keys immediately.

### `ffmpeg` or `ffprobe` not found

Make sure both commands are installed and available in `PATH`:

```bash
ffmpeg -version
ffprobe -version
```

### Why is music disabled by default?

The current default automation path expects background instrumental music, while `music-2.6` is better suited to song generation with lyrics. The pipeline skips music by default so video generation remains reliable and quota-aware.

## Acknowledgements

- [MiniMax](https://www.minimaxi.com/)
- [MiniMax Open Platform](https://platform.minimaxi.com/)
