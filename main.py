#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
MiniMax Auto TikTok Pipeline - 主入口
全自动短视频素材生产流水线

功能：
- 文本生成（脚本、标题）
- 语音合成（TTS HD）
- 视频生成（Hailuo）
- 音乐生成（music-2.6，自动化默认跳过纯音乐）
- 图片生成（image-01）

使用方法：
    python main.py --topic "咖啡文化" --style "文艺清新"
    python main.py --batch topics.txt
    python main.py --help
"""

import argparse
import logging
import sys
from pathlib import Path
from datetime import datetime
from typing import List, Optional

from config.settings import get_settings, ensure_output_dirs
from src.pipeline import PipelineOrchestrator, ReportGenerator
from src.utils.logger import setup_logger


def setup(log_level: str = "INFO"):
    """初始化设置"""
    # 确保输出目录存在
    ensure_output_dirs()

    # 配置日志
    settings = get_settings()
    settings.set_log_level(log_level)
    dated_log_dir = Path(settings.output.log_dir) / datetime.now().strftime("%Y-%m-%d")
    log_file = dated_log_dir / f"pipeline_{datetime.now().strftime('%H%M%S_%f')}.log"
    setup_logger(
        "minimax_pipeline",
        log_file=str(log_file),
        log_level=settings.log_level,
        configure_root=True,
    )

    return logging.getLogger("minimax_pipeline")


def generate_single(
    topic: str,
    style: str = "轻松幽默",
    duration: int = 6,
    generate_video: bool = True,
    generate_music: bool = True,
    generate_thumbnail: bool = True,
    logger: Optional[logging.Logger] = None,
):
    """
    生成单个内容包

    Args:
        topic: 内容主题
        style: 视频风格
        duration: 视频时长
        generate_video: 是否生成视频
        generate_music: 是否生成音乐
        generate_thumbnail: 是否生成缩略图
        logger: 日志记录器
    """
    if logger is None:
        logger = logging.getLogger(__name__)

    logger.info(f"开始生成内容包: {topic}")

    # 初始化 Pipeline
    pipeline = PipelineOrchestrator()

    # 生成内容包
    start_time = datetime.now()

    try:
        pack = pipeline.generate_content_pack(
            topic=topic,
            style=style,
            duration=duration,
            generate_video=generate_video,
            generate_music=generate_music,
            generate_thumbnail=generate_thumbnail,
        )

        end_time = datetime.now()

        # 生成报告
        report_gen = ReportGenerator(pipeline.file_manager)
        report_path = report_gen.generate_task_report(
            task_name=topic.replace(" ", "_"),
            content_packs=[pack],
            start_time=start_time,
            end_time=end_time,
        )

        # 生成 HTML 报告
        html_path = report_gen.generate_html_report(
            task_name=topic.replace(" ", "_"),
            content_packs=[pack],
            start_time=start_time,
            end_time=end_time,
        )

        logger.info("内容包生成完成!")
        logger.info(f"报告路径: {report_path}")
        logger.info(f"HTML 报告: {html_path}")

        # 打印结果
        print("\n" + "=" * 50)
        print("生成完成!")
        print("=" * 50)
        print(f"主题: {pack.topic}")
        print(f"脚本长度: {len(pack.script or '')} 字符")
        print(f"标题数量: {len(pack.titles) if pack.titles else 0}")

        if pack.video_path:
            print(f"视频: {pack.video_path}")
        if pack.audio_path:
            print(f"音频: {pack.audio_path}")
        if pack.music_path:
            print(f"音乐: {pack.music_path}")
        if pack.thumbnail_path:
            print(f"缩略图: {pack.thumbnail_path}")

        print(f"\n报告: {html_path}")
        print("=" * 50)

        return pack

    except Exception as e:
        logger.error(f"内容包生成失败: {str(e)}", exc_info=True)
        raise
    finally:
        pipeline.close()


def generate_batch(
    topics: List[str],
    style: str = "轻松幽默",
    duration: int = 6,
    generate_video: bool = True,
    generate_music: bool = True,
    generate_thumbnail: bool = True,
    logger: Optional[logging.Logger] = None,
):
    """
    批量生成内容包

    Args:
        topics: 主题列表
        style: 视频风格
        duration: 视频时长
        generate_video: 是否生成视频
        generate_music: 是否生成音乐
        generate_thumbnail: 是否生成缩略图
        logger: 日志记录器
    """
    if logger is None:
        logger = logging.getLogger(__name__)

    logger.info(f"开始批量生成 {len(topics)} 个内容包")

    pipeline = PipelineOrchestrator()
    start_time = datetime.now()
    packs = []
    errors = []

    try:
        for i, topic in enumerate(topics, 1):
            logger.info(f"处理第 {i}/{len(topics)} 个主题: {topic}")

            try:
                pack = pipeline.generate_content_pack(
                    topic=topic,
                    style=style,
                    duration=duration,
                    generate_video=generate_video,
                    generate_music=generate_music,
                    generate_thumbnail=generate_thumbnail,
                )
                packs.append(pack)

            except Exception as e:
                logger.error(f"主题 '{topic}' 生成失败: {str(e)}")
                errors.append({"topic": topic, "message": str(e)})

        end_time = datetime.now()

        report_gen = ReportGenerator(pipeline.file_manager)
        report_path = report_gen.generate_task_report(
            task_name="batch_generation",
            content_packs=packs,
            start_time=start_time,
            end_time=end_time,
            errors=errors,
        )

        html_path = report_gen.generate_html_report(
            task_name="batch_generation",
            content_packs=packs,
            start_time=start_time,
            end_time=end_time,
            errors=errors,
        )

        logger.info("批量生成完成!")
        logger.info(f"成功: {len(packs)}/{len(topics)}")
        logger.info(f"报告路径: {report_path}")
        logger.info(f"HTML 报告: {html_path}")

        print("\n" + "=" * 50)
        print("批量生成完成!")
        print("=" * 50)
        print(f"总数: {len(topics)}")
        print(f"成功: {len(packs)}")
        print(f"失败: {len(errors)}")
        print(f"耗时: {(end_time - start_time).total_seconds():.1f} 秒")
        print(f"\n报告: {html_path}")
        print("=" * 50)

        return packs, errors
    finally:
        pipeline.close()


def main():
    """主函数"""
    settings = get_settings()
    parser = argparse.ArgumentParser(
        description="MiniMax Auto TikTok Pipeline - 全自动短视频素材生产流水线",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
示例:
  # 生成单个内容包
  python main.py --topic "咖啡文化" --style "文艺清新"
  
  # 批量生成（从文件读取主题）
  python main.py --batch topics.txt
  
  # 仅生成文本和音频
  python main.py --topic "旅行日记" --no-video --no-music
  
  # 指定视频时长
  python main.py --topic "美食制作" --duration 10
        """,
    )

    # 单个生成参数
    parser.add_argument("--topic", "-t", type=str, help="内容主题")

    # 批量生成参数
    parser.add_argument(
        "--batch", "-b", type=str, help="批量生成主题文件路径（每行一个主题）"
    )

    # 通用参数
    parser.add_argument(
        "--style", "-s", type=str, default="轻松幽默", help="视频风格（默认: 轻松幽默）"
    )

    parser.add_argument(
        "--duration",
        "-d",
        type=int,
        default=settings.auto.content_strategy.default_duration,
        choices=[6, 10],
        help=f"视频时长（秒，默认: {settings.auto.content_strategy.default_duration}）",
    )

    parser.add_argument("--no-video", action="store_true", help="不生成视频")

    parser.add_argument("--no-music", action="store_true", help="不生成音乐")

    parser.add_argument("--no-thumbnail", action="store_true", help="不生成缩略图")

    parser.add_argument(
        "--log-level",
        type=str,
        default="INFO",
        choices=["DEBUG", "INFO", "WARNING", "ERROR"],
        help="日志级别（默认: INFO）",
    )

    args = parser.parse_args()

    # 初始化
    logger = setup(args.log_level)

    # 检查 API Key
    settings = get_settings()
    if not settings.api.has_available_key():
        logger.error("API Key 未设置！请在 .env 文件中设置 MiniMax Token Plan Key")
        print("错误: API Key 未设置！")
        print("请在项目根目录的 .env 文件中添加:")
        print("MINIMAX_TOKEN_PLAN_TIER=max")
        print("MINIMAX_TOKEN_PLAN_KEY2=your_max_key_here")
        print("如果只保留一个 Key，也可以使用 MINIMAX_TOKEN_PLAN_KEY=your_max_key_here")
        sys.exit(1)

    try:
        # 批量生成模式
        if args.batch:
            # 读取主题文件
            batch_file = Path(args.batch)
            if not batch_file.exists():
                logger.error(f"主题文件不存在: {batch_file}")
                print(f"错误: 主题文件不存在: {batch_file}")
                sys.exit(1)

            with open(batch_file, "r", encoding="utf-8") as f:
                topics = [line.strip() for line in f if line.strip()]

            if not topics:
                logger.error("主题文件为空")
                print("错误: 主题文件为空")
                sys.exit(1)

            generate_batch(
                topics=topics,
                style=args.style,
                duration=args.duration,
                generate_video=not args.no_video,
                generate_music=not args.no_music,
                generate_thumbnail=not args.no_thumbnail,
                logger=logger,
            )

        # 单个生成模式
        elif args.topic:
            generate_single(
                topic=args.topic,
                style=args.style,
                duration=args.duration,
                generate_video=not args.no_video,
                generate_music=not args.no_music,
                generate_thumbnail=not args.no_thumbnail,
                logger=logger,
            )

        # 未指定模式
        else:
            parser.print_help()
            sys.exit(0)

    except KeyboardInterrupt:
        logger.info("用户中断执行")
        print("\n已取消")
        sys.exit(0)

    except Exception as e:
        logger.error(f"执行失败: {str(e)}", exc_info=True)
        print(f"\n错误: {str(e)}")
        sys.exit(1)


if __name__ == "__main__":
    main()
