# Promotion Kit

Use this page when introducing Auto TikTok on GitHub, X/Twitter, Reddit, Discord, WeChat, Juejin, V2EX, Product Hunt-style directories, or creator communities.

## One-Liner

Auto TikTok is a local-first AI short-video autopilot that turns topics into structured VideoPlans, generated assets, quality-checked videos, and publish-ready Douyin/TikTok packages.

## Chinese One-Liner

Auto TikTok 是一个本地优先的 AI 短视频自动化系统，可以把选题转成结构化 VideoPlan、生成素材、质量评分，并导出抖音/TikTok 发布包。

## Short Pitch

Auto TikTok helps creators and builders automate repeatable short-video production without giving up observability. It creates a durable `video_plan.json`, generates scripts and assets with MiniMax, composes videos with FFmpeg, tracks quota and run history in a local dashboard, repairs failed assets, and exports publish-ready packages. TikTok Content Posting API integration is available when OAuth credentials are configured.

## Chinese Short Pitch

Auto TikTok 面向想把短视频生产工程化、自动化、自托管的创作者和开发者。它会为每条内容生成稳定的 `video_plan.json`，用 MiniMax 生成脚本与素材，用 FFmpeg 合成视频，通过本地 Dashboard 查看配额、历史、失败原因和任务队列，并在达标后导出发布包；配置 TikTok OAuth 后也可以接入官方发布 API。

## GitHub Description

Local-first AI short-video autopilot for Douyin/TikTok | 本地优先的抖音/TikTok AI 短视频自动生成与发布准备系统

## Suggested Topics

`ai-video`, `video-generation`, `tiktok-automation`, `douyin`, `short-video`, `creator-tools`, `content-automation`, `minimax`, `ffmpeg`, `docker`, `python`, `autopilot`

## Core Differentiators

- **VideoPlan-first**: each content item has a structured blueprint, model call plan, asset paths, score, and recovery state.
- **Local dashboard**: quota, history, manifest summaries, failures, task queue, regeneration, publishing, and Autopilot controls.
- **Quota-aware automation**: score gates, target count limits, asset repair, and Token Plan routing reduce wasted paid calls.
- **Publish-ready output**: manual publishing package by default, optional TikTok Inbox or Direct Post API adapter.
- **Practical self-hosting**: Docker, healthcheck, redacted logs, backup, log rotation, migration scripts, and CI.

## Launch Post

I just open-sourced Auto TikTok: a local-first AI short-video autopilot for Douyin/TikTok workflows.

It turns topics into structured VideoPlans, then generates scripts, voiceover, video, subtitles, covers, quality reports, and publish-ready packages. It includes a local dashboard for quota, run history, failures, task queue, asset regeneration, and Autopilot controls.

Built for creators and developers who want a practical self-hosted pipeline instead of a pile of disconnected scripts.

Repo: https://github.com/yanzhi0922/auto-tiktok

## Chinese Launch Post

我把 Auto TikTok 开源了：一个本地优先的抖音/TikTok AI 短视频自动化系统。

它可以从选题开始生成结构化 `video_plan.json`，再自动生成脚本、旁白、视频、字幕、封面、质量报告和发布包。项目内置本地 Dashboard，可以查看配额、历史运行、失败原因、任务队列、单资产重生成和 Autopilot 状态。

适合想把短视频生产流程工程化、自动化、自托管的创作者和开发者。

GitHub: https://github.com/yanzhi0922/auto-tiktok

## README Hero Copy

```text
Local-first AI short-video autopilot for Douyin/TikTok creators.
Turn topics into structured plans, generated assets, quality-checked videos, and publish-ready packages.
```

## Safe Demo Script

Use dry-run mode when presenting the project publicly:

```bash
git clone https://github.com/yanzhi0922/auto-tiktok.git
cd auto-tiktok
cp .env.example .env
python autopilot.py run --dry-run --count 5
docker compose up --build dashboard
```

Never show real API keys, access tokens, `.env`, raw Docker config output, or private generated content in public demos.
