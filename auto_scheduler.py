# -*- coding: utf-8 -*-
"""
自动化调度器。
支持 Windows 定时任务和内存常驻调度两种模式。
"""

from __future__ import annotations

import logging
import subprocess
import sys
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional
from xml.sax.saxutils import escape

import schedule

from src.utils.file_manager import FileManager


logger = logging.getLogger(__name__)


def _safe_console_print(text: str = "") -> None:
    message = str(text)
    stream = sys.stdout
    try:
        stream.write(message + "\n")
        stream.flush()
    except UnicodeEncodeError:
        encoding = getattr(stream, "encoding", None) or "utf-8"
        buffer = getattr(stream, "buffer", None)
        if buffer is not None:
            buffer.write((message + "\n").encode(encoding, errors="replace"))
            buffer.flush()
        else:
            sanitized = (message + "\n").encode(
                encoding, errors="replace"
            ).decode(encoding, errors="ignore")
            stream.write(sanitized)
            stream.flush()


def _get_quota_snapshot(settings) -> Dict[str, Any]:
    try:
        settings.refresh_quota_remains(["ultra", "max"])
    except Exception as exc:
        logger.warning(f"刷新套餐剩余额度快照失败，继续使用当前状态: {exc}")
    return settings.get_quota_status()


class WindowsTaskScheduler:
    """Windows Task Scheduler 包装器。"""

    TASK_PREFIX = "AutoTikTok_"

    def __init__(self, project_dir: str):
        self.project_dir = Path(project_dir).resolve()
        self.python_exe = Path(sys.executable).resolve()

    def _build_task_xml(
        self,
        task_name: str,
        command: List[str],
        start_time: Optional[str] = None,
        days_interval: int = 1,
        enabled: bool = True,
    ) -> str:
        start_boundary = (
            f"{datetime.now().strftime('%Y-%m-%d')}T{start_time}:00"
            if start_time
            else datetime.now().strftime("%Y-%m-%dT%H:%M:%S")
        )

        if start_time:
            schedule_str = f"""
  <Triggers>
    <CalendarTrigger>
      <StartBoundary>{escape(start_boundary)}</StartBoundary>
      <Enabled>{str(enabled).lower()}</Enabled>
      <ScheduleByDay>
        <DaysInterval>{days_interval}</DaysInterval>
      </ScheduleByDay>
    </CalendarTrigger>
  </Triggers>"""
        else:
            schedule_str = f"""
  <Triggers>
    <TimeTrigger>
      <StartBoundary>{escape(start_boundary)}</StartBoundary>
      <Enabled>{str(enabled).lower()}</Enabled>
    </TimeTrigger>
  </Triggers>"""

        arguments = " ".join(f'"{arg}"' if " " in arg else arg for arg in command[1:])
        return f"""<?xml version="1.0" encoding="UTF-16"?>
<Task version="1.4" xmlns="http://schemas.microsoft.com/windows/2004/02/mit/task">
  <RegistrationInfo>
    <Description>AutoTikTok 内容生成任务 - {escape(task_name)}</Description>
    <Author>AutoTikTok System</Author>
  </RegistrationInfo>
{schedule_str}
  <Principals>
    <Principal id="Author">
      <LogonType>InteractiveToken</LogonType>
      <RunLevel>HighestAvailable</RunLevel>
    </Principal>
  </Principals>
  <Settings>
    <MultipleInstancesPolicy>IgnoreNew</MultipleInstancesPolicy>
    <DisallowStartIfOnBatteries>false</DisallowStartIfOnBatteries>
    <StopIfGoingOnBatteries>false</StopIfGoingOnBatteries>
    <AllowHardTerminate>true</AllowHardTerminate>
    <StartWhenAvailable>true</StartWhenAvailable>
    <RunOnlyIfNetworkAvailable>false</RunOnlyIfNetworkAvailable>
    <AllowStartOnDemand>true</AllowStartOnDemand>
    <Enabled>{str(enabled).lower()}</Enabled>
    <Hidden>false</Hidden>
    <RunOnlyIfIdle>false</RunOnlyIfIdle>
    <WakeToRun>false</WakeToRun>
    <ExecutionTimeLimit>PT4H</ExecutionTimeLimit>
    <Priority>7</Priority>
  </Settings>
  <Actions Context="Author">
    <Exec>
      <Command>{escape(str(command[0]))}</Command>
      <Arguments>{escape(arguments)}</Arguments>
      <WorkingDirectory>{escape(str(self.project_dir))}</WorkingDirectory>
    </Exec>
  </Actions>
</Task>"""

    def create_daily_task(
        self,
        task_name: str,
        run_time: str = "09:00",
        count: int = 3,
        min_score: int = 65,
        max_concurrent: int = 1,
        content_types: Optional[List[str]] = None,
        log_level: str = "INFO",
        enabled: bool = True,
        autopilot: bool = False,
        publish_provider: str = "manual",
    ) -> bool:
        full_name = f"{self.TASK_PREFIX}{task_name}"
        script_path = self.project_dir / ("autopilot.py" if autopilot else "run_daily.py")
        if not script_path.exists():
            logger.error(f"执行脚本不存在: {script_path}")
            return False

        command = [
            str(self.python_exe),
            "-u",
            str(script_path),
        ]
        if autopilot:
            command.append("run")
        command.extend(
            [
            "--count",
            str(count),
            "--min-score",
            str(min_score),
            "--log-level",
            log_level,
            ]
        )
        if not autopilot:
            command.extend(["--concurrent", str(max_concurrent)])
        else:
            command.extend(["--provider", publish_provider])
        if content_types:
            command.extend(["--types", ",".join(content_types)])
        xml_content = self._build_task_xml(
            task_name=task_name,
            command=command,
            start_time=run_time,
            days_interval=1,
            enabled=enabled,
        )
        xml_path = self.project_dir / f"{full_name}.xml"

        try:
            xml_path.write_text(xml_content, encoding="utf-16")
            subprocess.run(
                ["schtasks", "/Delete", "/TN", full_name, "/F"],
                capture_output=True,
                text=True,
            )
            result = subprocess.run(
                ["schtasks", "/Create", "/TN", full_name, "/XML", str(xml_path)],
                capture_output=True,
                text=True,
            )
            if result.returncode == 0:
                logger.info(f"定时任务已创建: {full_name}（每天 {run_time}）")
                return True
            logger.error(f"创建任务失败: {result.stderr.strip()}")
            return False
        except Exception as exc:
            logger.error(f"创建定时任务异常: {exc}")
            return False
        finally:
            if xml_path.exists():
                xml_path.unlink()

    def delete_task(self, task_name: str) -> bool:
        full_name = f"{self.TASK_PREFIX}{task_name}"
        result = subprocess.run(
            ["schtasks", "/Delete", "/TN", full_name, "/F"],
            capture_output=True,
            text=True,
        )
        return result.returncode == 0

    def list_tasks(self) -> List[Dict[str, str]]:
        result = subprocess.run(
            ["schtasks", "/Query", "/FO", "CSV", "/NH"],
            capture_output=True,
            text=True,
        )
        tasks: List[Dict[str, str]] = []
        for line in result.stdout.splitlines():
            if self.TASK_PREFIX not in line or '"' not in line:
                continue
            parts = line.strip().split('","')
            if len(parts) < 3:
                continue
            name = parts[0].replace('"', "")
            if not name.startswith(self.TASK_PREFIX):
                continue
            tasks.append(
                {
                    "name": name,
                    "next_run": parts[1].replace('"', ""),
                    "status": parts[2].replace('"', "").replace("\r", ""),
                }
            )
        return tasks

    def run_task_now(self, task_name: str) -> bool:
        full_name = f"{self.TASK_PREFIX}{task_name}"
        result = subprocess.run(
            ["schtasks", "/Run", "/TN", full_name],
            capture_output=True,
            text=True,
        )
        return result.returncode == 0


class InMemoryScheduler:
    """基于 `schedule` 的内存调度器。"""

    def __init__(self):
        self._jobs: List[Dict[str, Any]] = []
        self._running = False

    def add_daily_job(
        self,
        func: Callable,
        job_name: str,
        run_time: str = "09:00",
    ) -> None:
        schedule.every().day.at(run_time).do(func)
        self._jobs.append({"name": job_name, "time": run_time, "type": "daily"})
        logger.info(f"已添加每日任务: {job_name} @ {run_time}")

    def add_hourly_job(
        self,
        func: Callable,
        job_name: str,
        interval_hours: int = 1,
    ) -> None:
        schedule.every(interval_hours).hours.do(func)
        self._jobs.append(
            {"name": job_name, "interval": interval_hours, "type": "hourly"}
        )
        logger.info(f"已添加周期任务: {job_name} @ 每{interval_hours}小时")

    def run(self, blocking: bool = True) -> None:
        self._running = True
        logger.info("调度器已启动，按 Ctrl+C 退出")
        if not blocking:
            return

        try:
            while self._running:
                schedule.run_pending()
                time.sleep(30)
        except KeyboardInterrupt:
            logger.info("调度器已停止")
            self._running = False

    def stop(self) -> None:
        self._running = False
        schedule.clear()
        logger.info("调度器已清空")


def _create_pipeline(project_dir: Path, date_suffix: str, run_id: str):
    from src.pipeline.douyin_pipeline import DouyinPipeline

    output_dir = project_dir / "output"
    file_manager = FileManager(output_dir, date_suffix=date_suffix, run_id=run_id)
    return DouyinPipeline(output_dir=str(output_dir), file_manager=file_manager)


def _build_topic_plan(
    content_count: int,
    content_types: Optional[List[str]],
    pipeline,
) -> List[Dict[str, Any]]:
    resolved_types = content_types or [
        "生活技巧",
        "情感共鸣",
        "知识科普",
        "娱乐搞笑",
        "美食探店",
        "萌宠日常",
    ]

    type_plan = [resolved_types[index % len(resolved_types)] for index in range(content_count)]
    topics = pipeline.strategy.get_trending_topics_for_types(type_plan)
    plan = []
    for index in range(content_count):
        plan.append(
            {
                "index": index + 1,
                "content_type": type_plan[index],
                "topic": topics[index],
            }
        )
    return plan


def run_daily_generation(
    project_dir: Optional[str] = None,
    content_count: Optional[int] = None,
    content_types: Optional[List[str]] = None,
    max_concurrent: int = 1,
    min_score_threshold: int = 65,
    generate_video: Optional[bool] = None,
    generate_music: Optional[bool] = None,
    generate_thumbnail: Optional[bool] = None,
    output_report: bool = True,
) -> Dict[str, Any]:
    """
    执行每日内容生成任务。
    """

    if project_dir:
        project_path = Path(project_dir).resolve()
    else:
        project_path = Path(__file__).parent.resolve()

    if str(project_path) not in sys.path:
        sys.path.insert(0, str(project_path))

    from config.settings import get_settings, ensure_output_dirs

    ensure_output_dirs()

    start_time = datetime.now()
    date_suffix = start_time.strftime("%Y-%m-%d")
    run_file_manager = FileManager(project_path / "output", date_suffix=date_suffix)
    run_id = run_file_manager.run_id
    settings = get_settings()
    resolved_content_count = content_count or settings.auto.content_strategy.daily_count
    resolved_content_types = (
        content_types or settings.auto.content_strategy.default_types
    )
    resolved_generate_video = (
        settings.auto.content_strategy.auto_generate_video
        if generate_video is None
        else generate_video
    )
    resolved_generate_music = (
        settings.auto.content_strategy.auto_generate_music
        if generate_music is None
        else generate_music
    )
    resolved_generate_thumbnail = (
        settings.auto.content_strategy.auto_generate_thumbnail
        if generate_thumbnail is None
        else generate_thumbnail
    )
    results: Dict[str, Any] = {
        "start_time": start_time.isoformat(),
        "run_id": run_id,
        "run_dir": str(run_file_manager.run_dir),
        "content_count": resolved_content_count,
        "packs": [],
        "succeeded": 0,
        "skipped": 0,
        "errors": [],
        "final_videos": [],
        "quota_before": _get_quota_snapshot(settings),
    }

    seed_pipeline = _create_pipeline(
        project_path, date_suffix=date_suffix, run_id=run_id
    )
    try:
        topic_plan = _build_topic_plan(
            resolved_content_count,
            resolved_content_types,
            seed_pipeline,
        )
    finally:
        seed_pipeline.close()

    def process_pack(pack, topic: str) -> None:
        score_data = pack.viral_score or {}
        score = int(score_data.get("score", 0))
        level = score_data.get("level", "未知")

        logger.info(f"  爆款评分: {score}/100 ({level})")
        if pack.quality_gate_passed is None:
            pack.quality_gate_passed = score >= min_score_threshold

        if not pack.quality_gate_passed:
            logger.warning(f"  评分低于门槛（{min_score_threshold}），标记为待优化")
            results["skipped"] += 1

        results["packs"].append(pack.to_dict())
        results["succeeded"] += 1

        if pack.final_video_path and pack.quality_gate_passed:
            results["final_videos"].append(
                {
                    "path": str(pack.final_video_path),
                    "title": pack.titles[0] if pack.titles else topic,
                    "score": score,
                    "level": level,
                    "hashtags": pack.hashtags,
                    "best_post_time": pack.best_post_time,
                }
            )

    def generate_one(plan_item: Dict[str, Any]):
        pipeline = _create_pipeline(
            project_path, date_suffix=date_suffix, run_id=run_id
        )
        try:
            logger.info(
                f"[{plan_item['index']}/{resolved_content_count}] 生成: {plan_item['topic']} ({plan_item['content_type']})"
            )
            return pipeline.generate_douyin_content(
                topic=plan_item["topic"],
                content_type=plan_item["content_type"],
                duration=settings.auto.content_strategy.default_duration,
                voice=settings.auto.content_strategy.default_voice,
                generate_video=resolved_generate_video,
                generate_music=resolved_generate_music,
                generate_thumbnail=resolved_generate_thumbnail,
                pack_index=plan_item["index"],
                min_score_threshold=min_score_threshold,
            )
        finally:
            pipeline.close()

    try:
        if max_concurrent <= 1:
            for item in topic_plan:
                try:
                    pack = generate_one(item)
                    process_pack(pack, item["topic"])
                except Exception as exc:
                    logger.error(f"  生成失败: {exc}")
                    results["errors"].append(
                        {"topic": item["topic"], "error": str(exc)}
                    )
        else:
            with ThreadPoolExecutor(max_workers=max_concurrent) as executor:
                future_map = {
                    executor.submit(generate_one, item): item for item in topic_plan
                }
                for future in as_completed(future_map):
                    item = future_map[future]
                    try:
                        pack = future.result()
                        process_pack(pack, item["topic"])
                    except Exception as exc:
                        logger.error(f"  生成失败: {exc}")
                        results["errors"].append(
                            {"topic": item["topic"], "error": str(exc)}
                        )
    finally:
        end_time = datetime.now()
        results["end_time"] = end_time.isoformat()
        results["duration_seconds"] = (end_time - start_time).total_seconds()
        results["quota_after"] = _get_quota_snapshot(settings)

    if output_report:
        report_file = run_file_manager.save_json(
            results,
            filename="daily_generation_report.json",
            content_type="reports",
        )
        logger.info(f"报告已保存: {report_file}")

    _safe_console_print(f"\n{'=' * 60}")
    _safe_console_print(f"每日内容生成报告 - {start_time.strftime('%Y-%m-%d %H:%M')}")
    _safe_console_print(f"{'=' * 60}")
    _safe_console_print(f"成功生成: {results['succeeded']}/{resolved_content_count}")
    _safe_console_print(f"达标可发布: {len(results['final_videos'])}")
    _safe_console_print(f"跳过（评分不足）: {results['skipped']}")
    _safe_console_print(f"失败: {len(results['errors'])}")
    _safe_console_print(f"用时: {results['duration_seconds']:.0f}秒")
    _safe_console_print("\n达标视频（可发布）:")
    for video in results["final_videos"]:
        _safe_console_print(f"  [{video['score']}分 {video['level']}] {video['title']}")
        _safe_console_print(f"    {video['hashtags']}")
        _safe_console_print(f"    最佳发布: {video['best_post_time']}")

    if results["errors"]:
        _safe_console_print("\n失败记录:")
        for error in results["errors"]:
            _safe_console_print(f"  - {error['topic']}: {error['error']}")

    _safe_console_print(f"{'=' * 60}")
    return results


def main():
    import argparse
    from config.settings import get_settings

    settings = get_settings()

    parser = argparse.ArgumentParser(description="AutoTikTok 自动化调度器")
    parser.add_argument("--project-dir", default=None, help="项目根目录")
    parser.add_argument(
        "--count",
        type=int,
        default=settings.auto.content_strategy.daily_count,
        help=f"每日生成数量（默认{settings.auto.content_strategy.daily_count}条）",
    )
    parser.add_argument(
        "--time",
        type=str,
        default=settings.auto.automation.daily_time,
        help=f"每日执行时间（HH:MM，默认 {settings.auto.automation.daily_time}）",
    )
    parser.add_argument(
        "--install-task", action="store_true", help="安装 Windows 定时任务"
    )
    parser.add_argument("--remove-task", action="store_true", help="删除定时任务")
    parser.add_argument(
        "--list-tasks", action="store_true", help="列出已安装的定时任务"
    )
    parser.add_argument(
        "--run-now", action="store_true", help="立即执行一次生成（不使用调度器）"
    )
    parser.add_argument(
        "--min-score", type=int, default=65, help="最低爆款评分门槛（默认65分）"
    )
    parser.add_argument("--concurrent", type=int, default=1, help="最大并发数（默认1）")
    parser.add_argument(
        "--types",
        type=str,
        default=None,
        help="内容类型，逗号分隔，如：生活技巧,情感共鸣,知识科普",
    )
    parser.add_argument("--autopilot", action="store_true", help="使用全自动模式")
    parser.add_argument(
        "--provider",
        type=str,
        default=settings.auto.autopilot.publish_provider,
        choices=["manual", "tiktok", "auto"],
        help="Autopilot 发布方式",
    )

    args = parser.parse_args()
    project_dir = args.project_dir or str(Path(__file__).parent.resolve())
    content_types = [item.strip() for item in args.types.split(",")] if args.types else None

    if args.install_task:
        scheduler = WindowsTaskScheduler(project_dir)
        scheduler.create_daily_task(
            "daily_content",
            run_time=args.time,
            count=args.count,
            min_score=args.min_score,
            max_concurrent=args.concurrent,
            content_types=content_types,
            autopilot=args.autopilot,
            publish_provider=args.provider,
        )
        return

    if args.remove_task:
        scheduler = WindowsTaskScheduler(project_dir)
        scheduler.delete_task("daily_content")
        return

    if args.list_tasks:
        scheduler = WindowsTaskScheduler(project_dir)
        tasks = scheduler.list_tasks()
        if tasks:
            print(f"{'任务名':<40} {'下次执行':<25} {'状态':<10}")
            print("-" * 80)
            for task in tasks:
                print(f"{task['name']:<40} {task['next_run']:<25} {task['status']:<10}")
        else:
            print("暂无定时任务。使用 --install-task 安装。")
        return

    if args.run_now:
        if args.autopilot:
            from src.pipeline.autopilot import AutopilotService

            print("开始执行 Autopilot...")
            result = AutopilotService().run(
                count=args.count,
                content_types=content_types,
                min_score=args.min_score,
                publish_provider=args.provider,
            )
            print(__import__("json").dumps(result, ensure_ascii=False, indent=2))
        else:
            print("开始生成每日内容...")
            run_daily_generation(
                project_dir=project_dir,
                content_count=args.count,
                content_types=content_types,
                max_concurrent=args.concurrent,
                min_score_threshold=args.min_score,
            )
        return

    print("启动内存调度器（生产环境建议用 --install-task）")
    scheduler = InMemoryScheduler()
    scheduler.add_daily_job(
        lambda: (
            __import__("src.pipeline.autopilot", fromlist=["AutopilotService"])
            .AutopilotService()
            .run(
                count=args.count,
                content_types=content_types,
                min_score=args.min_score,
                publish_provider=args.provider,
            )
            if args.autopilot
            else run_daily_generation(
                project_dir=project_dir,
                content_count=args.count,
                content_types=content_types,
                max_concurrent=args.concurrent,
                min_score_threshold=args.min_score,
            )
        ),
        job_name="daily_content",
        run_time=args.time,
    )
    scheduler.run(blocking=True)


if __name__ == "__main__":
    main()
