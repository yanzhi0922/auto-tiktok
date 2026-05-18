#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""全自动短视频生产入口。"""

from __future__ import annotations

import argparse
import json
import logging
import sys
from pathlib import Path


PROJECT_DIR = Path(__file__).parent.resolve()
if str(PROJECT_DIR) not in sys.path:
    sys.path.insert(0, str(PROJECT_DIR))


def _configure_console_encoding() -> None:
    for stream_name in ("stdout", "stderr"):
        stream = getattr(sys, stream_name, None)
        if stream is None or not hasattr(stream, "reconfigure"):
            continue
        try:
            stream.reconfigure(encoding="utf-8", errors="replace")
        except Exception:
            continue


def _parse_types(value: str | None) -> list[str] | None:
    if not value:
        return None
    return [item.strip() for item in value.split(",") if item.strip()]


def main() -> None:
    from config.settings import get_settings
    from src.pipeline.autopilot import AutopilotService
    from src.utils.logger import setup_logger

    _configure_console_encoding()
    settings = get_settings()
    parser = argparse.ArgumentParser(description="Auto TikTok Autopilot")
    parser.add_argument("command", nargs="?", default="run", choices=["run"])
    parser.add_argument(
        "--count",
        type=int,
        default=settings.auto.autopilot.default_count,
        help=f"目标成片数量（默认 {settings.auto.autopilot.default_count}）",
    )
    parser.add_argument(
        "--min-score",
        type=int,
        default=settings.auto.autopilot.min_score,
        help=f"最低爆款评分（默认 {settings.auto.autopilot.min_score}）",
    )
    parser.add_argument(
        "--types",
        default=None,
        help="内容类型，逗号分隔，如：生活技巧,知识科普",
    )
    parser.add_argument(
        "--provider",
        default=settings.auto.autopilot.publish_provider,
        choices=["manual", "tiktok", "auto"],
        help="发布方式：manual 导出发布包，tiktok 调官方 API，auto 有 token 则 TikTok 否则 manual",
    )
    parser.add_argument("--dry-run", action="store_true", help="只生成计划，不消耗额度")
    parser.add_argument(
        "--log-level",
        default=settings.log_level,
        choices=["DEBUG", "INFO", "WARNING", "ERROR"],
    )
    args = parser.parse_args()

    log_dir = PROJECT_DIR / "logs"
    log_dir.mkdir(parents=True, exist_ok=True)
    setup_logger(
        "autopilot",
        level=args.log_level,
        log_file=str(log_dir / "autopilot.log"),
        configure_root=True,
    )
    logging.getLogger("autopilot").info("启动 Autopilot")

    result = AutopilotService().run(
        count=args.count,
        content_types=_parse_types(args.types),
        min_score=args.min_score,
        publish_provider=args.provider,
        dry_run=args.dry_run,
    )
    print(json.dumps(result, ensure_ascii=False, indent=2))
    if result.get("status") not in {"succeeded", "no_publishable_video"}:
        sys.exit(1)


if __name__ == "__main__":
    main()
