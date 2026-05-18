#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
抖音专属内容生成主入口
针对抖音平台优化的内容生成工具

使用方法:
    python douyin_main.py --topic "咖啡文化" --type "生活技巧"
    python douyin_main.py --daily  # 按配置生成每日内容
    python douyin_main.py --weekly  # 生成一周计划
"""

import argparse
import logging
import sys
from pathlib import Path
from datetime import datetime

from config.settings import get_settings, ensure_output_dirs
from src.pipeline.douyin_pipeline import DouyinPipeline
from src.utils.logger import setup_logger


def setup(log_level: str = "INFO"):
    """初始化设置"""
    ensure_output_dirs()
    settings = get_settings()
    settings.set_log_level(log_level)
    dated_log_dir = Path(settings.output.log_dir) / datetime.now().strftime("%Y-%m-%d")
    log_file = dated_log_dir / f"douyin_{datetime.now().strftime('%H%M%S_%f')}.log"
    logger = setup_logger(
        "douyin_pipeline",
        log_file=str(log_file),
        log_level=settings.log_level,
        configure_root=True,
    )
    return logger


def generate_single_content(
    topic: str,
    content_type: str = "生活技巧",
    duration: int = 6,
    generate_video: bool = True,
    generate_music: bool = True,
    logger: logging.Logger | None = None,
):
    """生成单个抖音内容"""
    if logger is None:
        logger = logging.getLogger(__name__)

    logger.info(f"开始生成抖音内容: {topic}")

    pipeline = DouyinPipeline()

    try:
        pack = pipeline.generate_douyin_content(
            topic=topic,
            content_type=content_type,
            duration=duration,
            generate_video=generate_video,
            generate_music=generate_music,
            generate_thumbnail=True,
        )

        # 打印结果
        print("\n" + "=" * 60)
        print("抖音内容生成完成!")
        print("=" * 60)
        print(f"主题: {pack.topic}")
        print(f"类型: {pack.content_type}")
        viral_score = pack.viral_score or {"score": 0, "level": "未知"}
        print(f"爆款评分: {viral_score['score']}/100 ({viral_score['level']})")
        print("\n开头（黄金3秒）:")
        print(f"  {pack.hook}")
        print("\n行动号召:")
        print(f"  {pack.cta}")
        print("\n互动问题:")
        print(f"  {pack.engagement_question}")
        print(f"\n话题标签: {', '.join(pack.hashtags)}")
        print(f"\n最佳发布时间: {pack.best_post_time}")

        if pack.video_path:
            print(f"\n视频: {pack.video_path}")
        if pack.audio_path:
            print(f"音频: {pack.audio_path}")
        if pack.music_path:
            print(f"音乐: {pack.music_path}")
        if pack.thumbnail_path:
            print(f"缩略图: {pack.thumbnail_path}")
        if pack.final_video_path:
            print(f"最终视频: {pack.final_video_path}")
        if pack.cover_path:
            print(f"视频封面: {pack.cover_path}")

        print("\n标题建议:")
        for i, title in enumerate(pack.titles[:3], 1):
            print(f"  {i}. {title}")

        # 推荐发布文案
        description = pipeline._build_description(pack)
        print("\n推荐发布文案:")
        print(f"  {description}")

        print("\n" + "=" * 60)

        return pack

    except Exception as e:
        logger.error(f"生成失败: {str(e)}", exc_info=True)
        raise
    finally:
        pipeline.close()


def generate_daily_content(count: int = 3, logger: logging.Logger | None = None):
    """生成每日内容。"""
    if logger is None:
        logger = logging.getLogger(__name__)

    logger.info("开始生成每日内容...")

    pipeline = DouyinPipeline()

    try:
        packs = pipeline.generate_daily_content(count=count)

        print("\n" + "=" * 60)
        print("每日内容生成完成!")
        print("=" * 60)

        for i, pack in enumerate(packs, 1):
            print(f"\n{i}. {pack.topic} ({pack.content_type})")
            score_data = pack.viral_score or {"score": 0}
            print(f"   爆款评分: {score_data['score']}/100")
            print(f"   开头: {pack.hook[:30]}...")
            print(f"   最佳发布时间: {pack.best_post_time}")

        return packs

    except Exception as e:
        logger.error(f"生成失败: {str(e)}", exc_info=True)
        raise
    finally:
        pipeline.close()


def generate_weekly_plan(logger: logging.Logger | None = None):
    """生成一周内容计划"""
    if logger is None:
        logger = logging.getLogger(__name__)

    logger.info("开始生成一周内容计划...")

    pipeline = DouyinPipeline()

    try:
        calendar = pipeline.generate_weekly_plan()

        print("\n" + "=" * 60)
        print("一周内容计划生成完成!")
        print("=" * 60)

        for day_plan in calendar:
            print(
                f"\n第{day_plan['day']}天 - {day_plan['date']} ({day_plan['weekday']})"
            )
            print(f"  主题: {day_plan['topic']}")
            print(f"  类型: {day_plan['content_type']}")
            print(
                f"  爆款评分: {day_plan['viral_score']['score']}/100 ({day_plan['viral_score']['level']})"
            )
            print(f"  最佳发布时间: {day_plan['best_post_time']}")

        return calendar

    except Exception as e:
        logger.error(f"生成失败: {str(e)}", exc_info=True)
        raise
    finally:
        pipeline.close()


def main():
    """主函数"""
    settings = get_settings()
    parser = argparse.ArgumentParser(
        description="抖音专属内容生成工具 - 专为抖音平台优化的内容生成",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""

示例:
  # 生成单个内容
  python douyin_main.py --topic "咖啡文化" --type "生活技巧"
  
  # 生成每日内容（数量由配置或 --count 决定）
  python douyin_main.py --daily
  
  # 生成一周内容计划
  python douyin_main.py --weekly
  
  # 指定内容类型
  python douyin_main.py --topic "旅行日记" --type "旅行vlog"
        """,
    )

    # 单个内容生成
    parser.add_argument("--topic", "-t", type=str, help="内容主题")

    parser.add_argument(
        "--type",
        "-c",
        type=str,
        default="生活技巧",
        choices=[
            "生活技巧",
            "情感共鸣",
            "知识科普",
            "娱乐搞笑",
            "美食探店",
            "旅行vlog",
            "萌宠日常",
        ],
        help="内容类型（默认: 生活技巧）",
    )

    parser.add_argument(
        "--duration",
        "-d",
        type=int,
        default=settings.auto.content_strategy.default_duration,
        choices=[6, 10],
        help=f"视频时长（默认: {settings.auto.content_strategy.default_duration}秒）",
    )

    parser.add_argument("--no-video", action="store_true", help="不生成视频")

    parser.add_argument("--no-music", action="store_true", help="不生成音乐")

    # 批量生成
    parser.add_argument("--daily", action="store_true", help="生成每日内容")

    parser.add_argument(
        "--count",
        type=int,
        default=settings.auto.content_strategy.daily_count,
        help=f"每日内容数量（默认: {settings.auto.content_strategy.daily_count}）",
    )

    parser.add_argument("--weekly", action="store_true", help="生成一周内容计划")

    parser.add_argument(
        "--log-level",
        type=str,
        default="INFO",
        choices=["DEBUG", "INFO", "WARNING", "ERROR"],
        help="日志级别",
    )

    args = parser.parse_args()

    # 初始化
    logger = setup(args.log_level)

    # 检查 API Key
    settings = get_settings()
    if not settings.api.has_available_key():
        logger.error("API Key 未设置！")
        print("错误: API Key 未设置！")
        print("Max 套餐请在 .env 中设置 MINIMAX_TOKEN_PLAN_TIER=max 和 Token Plan Key")
        sys.exit(1)

    try:
        # 每日内容模式
        if args.daily:
            generate_daily_content(count=args.count, logger=logger)

        # 一周计划模式
        elif args.weekly:
            generate_weekly_plan(logger)

        # 单个内容模式
        elif args.topic:
            generate_single_content(
                topic=args.topic,
                content_type=args.type,
                duration=args.duration,
                generate_video=not args.no_video,
                generate_music=not args.no_music,
                logger=logger,
            )

        # 未指定模式
        else:
            parser.print_help()
            print("\n推荐使用 --daily 生成每日内容，或使用 --weekly 生成一周计划")

    except KeyboardInterrupt:
        logger.info("用户中断")
        print("\n已取消")
        sys.exit(0)

    except Exception as e:
        logger.error(f"执行失败: {str(e)}", exc_info=True)
        print(f"\n错误: {str(e)}")
        sys.exit(1)


if __name__ == "__main__":
    main()
