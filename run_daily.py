#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
每日内容生成任务脚本
由 Windows Task Scheduler 定时调用，或手动执行

用法:
    python run_daily.py                      # 按配置生成默认数量
    python run_daily.py --count 3           # 生成3条
    python run_daily.py --min-score 70      # 最低70分才发布
"""

import sys
import logging
from pathlib import Path
from datetime import datetime

# 项目根目录
PROJECT_DIR = Path(__file__).parent
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


def main():
    import argparse
    from config.settings import get_settings

    _configure_console_encoding()
    settings = get_settings()

    parser = argparse.ArgumentParser(description="每日抖音内容生成")
    parser.add_argument(
        "--count",
        type=int,
        default=settings.auto.content_strategy.daily_count,
        help=f"生成数量（默认{settings.auto.content_strategy.daily_count}条）",
    )
    parser.add_argument(
        "--min-score", type=int, default=65, help="最低爆款评分（默认65分）"
    )
    parser.add_argument("--concurrent", type=int, default=1, help="最大并发数（默认1）")
    parser.add_argument(
        "--types",
        type=str,
        default=None,
        help="内容类型，逗号分隔，如：生活技巧,情感共鸣,知识科普",
    )
    parser.add_argument(
        "--log-level",
        type=str,
        default="INFO",
        choices=["DEBUG", "INFO", "WARNING", "ERROR"],
    )

    args = parser.parse_args()

    # 设置日志
    log_dir = PROJECT_DIR / "logs" / datetime.now().strftime("%Y-%m-%d")
    log_dir.mkdir(parents=True, exist_ok=True)
    log_file = log_dir / f"run_daily_{datetime.now().strftime('%H%M%S_%f')}.log"

    logging.basicConfig(
        level=getattr(logging, args.log_level),
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
        handlers=[
            logging.FileHandler(log_file, encoding="utf-8"),
            logging.StreamHandler(sys.stdout),
        ],
    )

    logger = logging.getLogger("run_daily")
    logger.info("=" * 60)
    logger.info("开始执行每日内容生成任务")
    logger.info(f"参数: count={args.count}, min_score={args.min_score}")
    logger.info("=" * 60)

    # 解析内容类型
    content_types = None
    if args.types:
        content_types = [t.strip() for t in args.types.split(",")]

    try:
        from auto_scheduler import run_daily_generation

        results = run_daily_generation(
            project_dir=str(PROJECT_DIR),
            content_count=args.count,
            content_types=content_types,
            max_concurrent=args.concurrent,
            min_score_threshold=args.min_score,
            output_report=True,
        )

        logger.info(
            f"任务完成！成功: {results['succeeded']}, 跳过: {results['skipped']}"
        )

        # 非零退出码表示有错误
        if results["errors"]:
            sys.exit(1)
        elif results["succeeded"] == 0:
            sys.exit(2)  # 无成功内容

    except Exception as e:
        logger.error(f"任务执行异常: {e}", exc_info=True)
        sys.exit(1)


if __name__ == "__main__":
    main()
