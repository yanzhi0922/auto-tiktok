<p align="center">
  <img src="docs/assets/readme-hero.svg" alt="Auto TikTok - AI short-video autopilot" width="100%" />
</p>

<h1 align="center">Auto TikTok</h1>

<p align="center">
  <strong>Local-first AI short-video autopilot for Douyin/TikTok creators.</strong><br />
  Turn topics into structured plans, generated assets, quality-checked videos, and publish-ready packages.
</p>

<p align="center">
  <a href="README.md">English</a> ·
  <a href="README.zh-CN.md">简体中文</a> ·
  <a href="docs/AUTOPILOT.md">Autopilot</a> ·
  <a href="docs/DEPLOYMENT.md">Deployment</a> ·
  <a href="docs/PROMOTION.md">Promotion</a>
</p>

<p align="center">
  <a href="https://github.com/yanzhi0922/auto-tiktok/actions/workflows/ci.yml"><img src="https://github.com/yanzhi0922/auto-tiktok/actions/workflows/ci.yml/badge.svg" alt="CI" /></a>
  <img src="https://img.shields.io/badge/Python-3.10%2B-3776AB?logo=python&logoColor=white" alt="Python 3.10+" />
  <img src="https://img.shields.io/badge/Docker-ready-2496ED?logo=docker&logoColor=white" alt="Docker ready" />
  <img src="https://img.shields.io/badge/MiniMax-Token%20Plan-10B981" alt="MiniMax Token Plan" />
  <img src="https://img.shields.io/badge/License-MIT-green" alt="MIT license" />
</p>

---

Auto TikTok is a production-minded automation toolkit for short-video creators and builders. It takes a topic or trend source, creates a recoverable `video_plan.json`, generates scripts, TTS, video, subtitles, covers, reports, and publishing packages, then lets you monitor and repair everything from a local dashboard.

It is not just a script generator. The core idea is a durable **VideoPlan**: every content item has a structured blueprint, model call plan, asset paths, quality score, quota audit, and recovery path.

## Why Star This Project

| What you need | What Auto TikTok gives you |
| --- | --- |
| Generate shorts without hand-building each scene | Topic-to-video Autopilot with script, voice, video, subtitles, cover, and composition |
| Keep AI generation recoverable | A durable `video_plan.json` plus per-content `content_manifest.json` |
| See what happened after a run | Dashboard, run history, quota snapshot, failures, queue status, and reports |
| Avoid wasting paid quota | Quality gates, score thresholds, quota-aware target counts, and asset repair |
| Prepare for real publishing | Manual publish packages by default, optional TikTok Content Posting API adapter |
| Run it locally like a product | Docker, healthcheck, CSRF/session protection, log redaction, backup, rotation, migration |

## One-Minute Start

```bash
git clone https://github.com/yanzhi0922/auto-tiktok.git
cd auto-tiktok
cp .env.example .env
docker compose up --build dashboard
```

Open:

```text
http://127.0.0.1:7860
```

Run Autopilot:

```bash
python autopilot.py run --count 3 --min-score 65 --provider auto
```

Dry run first:

```bash
python autopilot.py run --dry-run --count 5
```

## Workflow

<p align="center">
  <img src="docs/assets/pipeline.svg" alt="Auto TikTok automation pipeline" width="100%" />
</p>

## What It Generates

| Output | Description |
| --- | --- |
| `video_plan.json` | Structured plan for script, shots, title, subtitles, cover, model calls, and asset paths |
| `content_manifest.json` | Per-content status, asset locations, provider results, failures, and audit data |
| `script.json`, `titles.json`, `score.json` | Short-video script, title candidates, and quality score |
| `*.mp3`, `*.mp4`, `subtitle.srt`, `cover.jpg` | Generated voiceover, video, subtitles, final composition, and cover |
| `publish/publish_package.json` | Manual publishing package with title, copy, hashtags, paths, and metadata |
| `autopilot_report.json` | Autopilot topic attempts, skips, retries, repairs, and publishing results |

## Feature Matrix

| Area | Included |
| --- | --- |
| Topic sourcing | Local `trending_topics`, optional external topic URLs, content type filters |
| Script generation | Multiple candidates, score gates, low-score skip before costly video calls |
| MiniMax support | Max/Ultra routing, Token Plan model normalization, quota accounting |
| Video generation | Hailuo 2.3 path, `768P + 6s` Token Plan normalization, cover reuse |
| Subtitles | Duration-calibrated local subtitles, optional WhisperX compatibility |
| Dashboard | Quota, history, manifests, failures, queue, regeneration, publishing, Autopilot |
| Publishing | Manual package export, optional TikTok Inbox or Direct Post API adapter |
| Operations | Docker, healthcheck, backup, log rotation, migration, redacted logs |
| Safety | Local-only default dashboard bind, optional auth token, session cookie, CSRF |

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
- Never commit or share `.env`, API keys, access tokens, Docker config output, or raw logs containing private data.

Main automation settings live in:

```text
config/auto_config.yaml
```

Current defaults:

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
- limits target count by available video/image quota;
- generates script candidates and applies quality gates;
- skips low-score content before high-cost video generation;
- repairs missing assets such as video, subtitle, final composition, and cover;
- exports publish packages by default;
- uses TikTok publishing only when a valid access token is configured.

Optional external topic sources:

```env
AUTO_TIKTOK_TRENDING_URLS=https://example.com/topics.json
```

## Dashboard

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

For HTTPS reverse proxies:

```env
AUTO_TIKTOK_DASHBOARD_SECURE_COOKIES=true
```

## Docker

```bash
docker compose up --build dashboard
docker compose --profile run-once up --build run-once
docker compose --profile autopilot up --build autopilot
```

Compose includes:

- `/healthz` healthcheck;
- local-only default port binding: `127.0.0.1:7860`;
- `json-file` log rotation;
- mounted `output/`, `logs/`, `backups/`, and `config/auto_config.yaml`.

## Publishing

Manual publish package export is the default workflow. The package is written to:

```text
publish/publish_package.json
```

To use TikTok's official Content Posting API:

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

```bash
python auto_scheduler.py --install-task --autopilot --time 09:00 --count 3 --min-score 65 --provider auto
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
- [Douyin Guide](docs/DOUYIN_GUIDE.md)
- [Automation Usage](docs/AUTO_USAGE.md)
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

The default automation path expects background instrumental music, while `music-2.6` is better suited to song generation with lyrics. The pipeline skips music by default so video generation remains reliable and quota-aware.

## Acknowledgements

- [MiniMax](https://www.minimaxi.com/)
- [MiniMax Open Platform](https://platform.minimaxi.com/)
