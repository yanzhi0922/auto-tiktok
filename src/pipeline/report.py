# -*- coding: utf-8 -*-
"""
报告生成器。
"""

from __future__ import annotations

import html
import logging
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional

from src.utils.file_manager import FileManager


logger = logging.getLogger(__name__)


class ReportGenerator:
    """报告生成器。"""

    def __init__(self, file_manager: Optional[FileManager] = None):
        self.file_manager = file_manager or FileManager()

    def _serialize_pack(self, pack: Any) -> Dict[str, Any]:
        pack_dict = pack.to_dict() if hasattr(pack, "to_dict") else {}
        return {
            "topic": getattr(pack, "topic", pack_dict.get("topic")),
            "content_type": getattr(pack, "content_type", pack_dict.get("content_type")),
            "has_video": bool(getattr(pack, "video_path", pack_dict.get("video_path"))),
            "has_audio": bool(getattr(pack, "audio_path", pack_dict.get("audio_path"))),
            "has_music": bool(getattr(pack, "music_path", pack_dict.get("music_path"))),
            "has_thumbnail": bool(getattr(pack, "thumbnail_path", pack_dict.get("thumbnail_path"))),
            "titles_count": len(getattr(pack, "titles", pack_dict.get("titles", [])) or []),
            "video_path": str(getattr(pack, "video_path", "")) if getattr(pack, "video_path", None) else pack_dict.get("video_path"),
            "audio_path": str(getattr(pack, "audio_path", "")) if getattr(pack, "audio_path", None) else pack_dict.get("audio_path"),
            "music_path": str(getattr(pack, "music_path", "")) if getattr(pack, "music_path", None) else pack_dict.get("music_path"),
            "thumbnail_path": str(getattr(pack, "thumbnail_path", "")) if getattr(pack, "thumbnail_path", None) else pack_dict.get("thumbnail_path"),
            "final_video_path": str(getattr(pack, "final_video_path", "")) if getattr(pack, "final_video_path", None) else pack_dict.get("final_video_path"),
            "cover_path": str(getattr(pack, "cover_path", "")) if getattr(pack, "cover_path", None) else pack_dict.get("cover_path"),
            "errors": getattr(pack, "errors", pack_dict.get("errors", [])),
            "hook_type_used": getattr(pack, "hook_type_used", pack_dict.get("hook_type_used")),
            "viral_score": getattr(pack, "viral_score", pack_dict.get("viral_score")),
            "quality_gate_passed": getattr(pack, "quality_gate_passed", pack_dict.get("quality_gate_passed")),
            "key_tier_used": getattr(pack, "key_tier_used", pack_dict.get("key_tier_used")),
            "requested_model": getattr(pack, "requested_model", pack_dict.get("requested_model")),
            "applied_model": getattr(pack, "applied_model", pack_dict.get("applied_model")),
            "requested_video_spec": getattr(pack, "requested_video_spec", pack_dict.get("requested_video_spec")),
            "applied_video_spec": getattr(pack, "applied_video_spec", pack_dict.get("applied_video_spec")),
            "cross_tier_fallback": bool(getattr(pack, "cross_tier_fallback", pack_dict.get("cross_tier_fallback", False))),
            "generation_metadata": getattr(pack, "generation_metadata", pack_dict.get("generation_metadata", {})),
        }

    def _success_rate(self, success_count: int, error_count: int) -> str:
        attempts = success_count + error_count
        if attempts == 0:
            return "0.0%"
        return f"{success_count / attempts * 100:.1f}%"

    def generate_task_report(
        self,
        task_name: str,
        content_packs: List[Any],
        start_time: datetime,
        end_time: datetime,
        errors: Optional[List[Dict[str, Any]]] = None,
        output_path: Optional[str] = None,
    ) -> Path:
        duration = (end_time - start_time).total_seconds()
        serialized_packs = [self._serialize_pack(pack) for pack in content_packs]
        error_list = errors or []

        report = {
            "report_type": "任务执行报告",
            "task_name": task_name,
            "generated_at": datetime.now().isoformat(),
            "execution_time": {
                "start": start_time.isoformat(),
                "end": end_time.isoformat(),
                "duration_seconds": round(duration, 2),
                "duration_formatted": self._format_duration(duration),
            },
            "statistics": {
                "total_packs": len(serialized_packs),
                "packs_with_video": sum(1 for item in serialized_packs if item["has_video"]),
                "packs_with_audio": sum(1 for item in serialized_packs if item["has_audio"]),
                "packs_with_music": sum(1 for item in serialized_packs if item["has_music"]),
                "packs_with_thumbnail": sum(1 for item in serialized_packs if item["has_thumbnail"]),
                "packs_with_titles": sum(1 for item in serialized_packs if item["titles_count"] > 0),
            },
            "content_packs": serialized_packs,
            "errors": error_list,
            "success_rate": self._success_rate(len(serialized_packs), len(error_list)),
        }

        if output_path is None:
            filename = self.file_manager.generate_filename(
                prefix=f"report_{task_name}",
                extension="json",
                suffix=datetime.now().strftime("%Y%m%d_%H%M%S"),
            )
            report_path = self.file_manager.save_json(
                report,
                filename,
                content_type="reports",
            )
        else:
            report_path = self.file_manager.write_json_to_path(output_path, report)
        logger.info(f"任务报告已生成: {report_path}")
        return report_path

    def generate_usage_report(
        self,
        api_calls: Dict[str, int],
        quotas: Dict[str, int],
        output_path: Optional[str] = None,
    ) -> Path:
        usage_rates: Dict[str, Dict[str, Any]] = {}
        for api, calls in api_calls.items():
            quota = quotas.get(api, 0)
            if quota > 0:
                usage_rates[api] = {
                    "calls": calls,
                    "quota": quota,
                    "usage_rate": f"{calls / quota * 100:.1f}%",
                    "remaining": quota - calls,
                }
            else:
                usage_rates[api] = {
                    "calls": calls,
                    "quota": "无限制",
                    "usage_rate": "N/A",
                    "remaining": "N/A",
                }

        report = {
            "report_type": "API 使用量报告",
            "generated_at": datetime.now().isoformat(),
            "usage": usage_rates,
            "total_calls": sum(api_calls.values()),
            "summary": {
                "most_used_api": max(api_calls.items(), key=lambda item: item[1])[0] if api_calls else None,
                "highest_usage_rate": max(
                    usage_rates.items(),
                    key=lambda item: item[1]["calls"] / max(item[1]["quota"], 1)
                    if isinstance(item[1]["quota"], int) else 0,
                )[0] if usage_rates else None,
            },
        }

        if output_path is None:
            filename = self.file_manager.generate_filename(
                prefix="usage_report",
                extension="json",
                suffix=datetime.now().strftime("%Y%m%d_%H%M%S"),
            )
            report_path = self.file_manager.save_json(
                report,
                filename,
                content_type="reports",
            )
        else:
            report_path = self.file_manager.write_json_to_path(output_path, report)
        logger.info(f"API 使用量报告已生成: {report_path}")
        return report_path

    def generate_summary_report(self, output_path: Optional[str] = None) -> Path:
        stats = self.file_manager.get_stats()
        recent_runs = []
        if self.file_manager.day_dir.exists():
            run_dirs = sorted(
                (
                    item
                    for item in self.file_manager.day_dir.iterdir()
                    if item.is_dir() and item.name.startswith("run_")
                ),
                key=lambda item: item.stat().st_mtime,
                reverse=True,
            )
            for run_dir in run_dirs[:10]:
                run_files = [path for path in run_dir.rglob("*") if path.is_file()]
                recent_runs.append(
                    {
                        "path": str(run_dir),
                        "file_count": len(run_files),
                        "size_mb": round(
                            sum(path.stat().st_size for path in run_files)
                            / 1024
                            / 1024,
                            2,
                        ),
                        "modified": datetime.fromtimestamp(
                            run_dir.stat().st_mtime
                        ).isoformat(),
                    }
                )

        report = {
            "report_type": "输出目录摘要报告",
            "generated_at": datetime.now().isoformat(),
            "statistics": stats,
            "recent_runs": recent_runs,
        }

        if output_path is None:
            filename = self.file_manager.generate_filename(
                prefix="summary_report",
                extension="json",
                suffix=datetime.now().strftime("%Y%m%d_%H%M%S"),
            )
            report_path = self.file_manager.save_json(
                report,
                filename,
                content_type="reports",
            )
        else:
            report_path = self.file_manager.write_json_to_path(output_path, report)
        logger.info(f"摘要报告已生成: {report_path}")
        return report_path

    def generate_html_report(
        self,
        task_name: str,
        content_packs: List[Any],
        start_time: datetime,
        end_time: datetime,
        errors: Optional[List[Dict[str, Any]]] = None,
        output_path: Optional[str] = None,
    ) -> Path:
        duration = (end_time - start_time).total_seconds()
        serialized_packs = [self._serialize_pack(pack) for pack in content_packs]
        error_list = errors or []
        safe_task_name = html.escape(task_name)

        sections = [
            "<!DOCTYPE html>",
            '<html lang="zh-CN">',
            "<head>",
            '    <meta charset="UTF-8">',
            '    <meta name="viewport" content="width=device-width, initial-scale=1.0">',
            f"    <title>任务执行报告 - {safe_task_name}</title>",
            "    <style>",
            "        body { font-family: 'Microsoft YaHei', Arial, sans-serif; max-width: 1200px; margin: 0 auto; padding: 20px; background-color: #f5f5f5; }",
            "        .header { background: linear-gradient(135deg, #667eea 0%, #764ba2 100%); color: white; padding: 30px; border-radius: 10px; margin-bottom: 20px; }",
            "        .stats { display: grid; grid-template-columns: repeat(auto-fit, minmax(200px, 1fr)); gap: 15px; margin-bottom: 20px; }",
            "        .stat-card, .content-pack { background: white; padding: 20px; border-radius: 8px; box-shadow: 0 2px 4px rgba(0,0,0,0.1); }",
            "        .content-pack { margin-bottom: 15px; }",
            "        .tags { display: flex; gap: 10px; flex-wrap: wrap; }",
            "        .tag { background: #e0e0e0; padding: 5px 12px; border-radius: 15px; font-size: 12px; }",
            "        .tag.success { background: #c8e6c9; color: #2e7d32; }",
            "        .error { background: #ffebee; border-left: 4px solid #f44336; padding: 15px; margin-bottom: 15px; border-radius: 4px; }",
            "        .footer { text-align: center; margin-top: 30px; color: #666; font-size: 12px; }",
            "    </style>",
            "</head>",
            "<body>",
            '    <div class="header">',
            "        <h1>任务执行报告</h1>",
            f"        <p>{safe_task_name}</p>",
            f"        <p>生成时间: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}</p>",
            "    </div>",
            '    <div class="stats">',
            f'        <div class="stat-card"><h3>总内容包</h3><div class="value">{len(serialized_packs)}</div></div>',
            f'        <div class="stat-card"><h3>视频生成</h3><div class="value">{sum(1 for item in serialized_packs if item["has_video"])}</div></div>',
            f'        <div class="stat-card"><h3>音频生成</h3><div class="value">{sum(1 for item in serialized_packs if item["has_audio"])}</div></div>',
            f'        <div class="stat-card"><h3>执行时长</h3><div class="value">{self._format_duration(duration)}</div></div>',
            "    </div>",
            "    <h2>内容包详情</h2>",
        ]

        for item in serialized_packs:
            tags = []
            if item["has_video"]:
                tags.append('<span class="tag success">视频</span>')
            if item["has_audio"]:
                tags.append('<span class="tag success">音频</span>')
            if item["has_music"]:
                tags.append('<span class="tag success">音乐</span>')
            if item["has_thumbnail"]:
                tags.append('<span class="tag success">缩略图</span>')

            meta_lines = []
            if item.get("content_type"):
                meta_lines.append(
                    f"<p><strong>类型:</strong> {html.escape(str(item['content_type']))}</p>"
                )
            if item.get("quality_gate_passed") is not None:
                meta_lines.append(
                    "<p><strong>质量门:</strong> "
                    + ("通过" if item["quality_gate_passed"] else "未通过")
                    + "</p>"
                )
            if item.get("viral_score"):
                score_info = item["viral_score"] or {}
                meta_lines.append(
                    "<p><strong>爆款评分:</strong> "
                    f"{html.escape(str(score_info.get('score', '-')))} / 100 "
                    f"({html.escape(str(score_info.get('level', '-')))})"
                    "</p>"
                )
            if item.get("hook_type_used"):
                meta_lines.append(
                    f"<p><strong>开头策略:</strong> {html.escape(str(item['hook_type_used']))}</p>"
                )
            if item.get("key_tier_used"):
                meta_lines.append(
                    f"<p><strong>套餐:</strong> {html.escape(str(item['key_tier_used']))}</p>"
                )
            if item.get("requested_model") or item.get("applied_model"):
                meta_lines.append(
                    f"<p><strong>模型:</strong> 请求 {html.escape(str(item.get('requested_model') or '-'))} / 实际 {html.escape(str(item.get('applied_model') or '-'))}</p>"
                )
            if item.get("requested_video_spec") or item.get("applied_video_spec"):
                requested_spec = item.get("requested_video_spec") or {}
                applied_spec = item.get("applied_video_spec") or {}
                meta_lines.append(
                    "<p><strong>视频规格:</strong> "
                    f"请求 {html.escape(str(requested_spec))} / 实际 {html.escape(str(applied_spec))}"
                    "</p>"
                )
            if item.get("cross_tier_fallback"):
                meta_lines.append("<p><strong>回退:</strong> 发生跨套餐回退</p>")

            sections.extend([
                '    <div class="content-pack">',
                f"        <h3>{html.escape(str(item['topic'] or '未命名主题'))}</h3>",
                '        <div class="tags">',
                f"            {''.join(tags)}",
                "        </div>",
                *[f"        {line}" for line in meta_lines],
                "    </div>",
            ])

        if error_list:
            sections.append("    <h2>错误信息</h2>")
            for error in error_list:
                sections.extend([
                    '    <div class="error">',
                    f"        <strong>{html.escape(str(error.get('topic', '未知')))}</strong>: {html.escape(str(error.get('message') or error.get('error', '未知错误')))}",
                    "    </div>",
                ])

        sections.extend([
            '    <div class="footer">',
            "        <p>MiniMax Auto TikTok Pipeline - 自动内容生产流水线</p>",
            "    </div>",
            "</body>",
            "</html>",
        ])

        if output_path is None:
            filename = self.file_manager.generate_filename(
                prefix=f"report_{task_name}",
                extension="html",
                suffix=datetime.now().strftime("%Y%m%d_%H%M%S"),
            )
            output_file = self.file_manager.save_text(
                "\n".join(sections),
                filename,
                content_type="reports",
            )
        else:
            output_file = self.file_manager.write_text_to_path(
                output_path,
                "\n".join(sections),
            )
        logger.info(f"HTML 报告已生成: {output_file}")
        return output_file

    def _format_duration(self, seconds: float) -> str:
        if seconds < 60:
            return f"{seconds:.1f}秒"
        if seconds < 3600:
            minutes = int(seconds // 60)
            remain_seconds = int(seconds % 60)
            return f"{minutes}分{remain_seconds}秒"
        hours = int(seconds // 3600)
        minutes = int((seconds % 3600) // 60)
        return f"{hours}小时{minutes}分"
