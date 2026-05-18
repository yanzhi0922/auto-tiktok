# -*- coding: utf-8 -*-
"""Dashboard 状态读取与安全路径解析。"""

from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional

from config.settings import get_settings


def _read_json(path: Path) -> Optional[Dict[str, Any]]:
    if not path.exists() or not path.is_file():
        return None
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None


def _safe_child(base_dir: Path, *parts: str) -> Path:
    base = base_dir.resolve()
    candidate = base.joinpath(*parts).resolve()
    try:
        candidate.relative_to(base)
    except ValueError as exc:
        raise ValueError(f"路径越界: {candidate}") from exc
    return candidate


def list_runs(base_dir: str | Path = "output", limit: int = 50) -> List[Dict[str, Any]]:
    root = Path(base_dir)
    if not root.exists():
        return []

    runs: List[Dict[str, Any]] = []
    for day_dir in sorted(root.iterdir(), reverse=True):
        if not day_dir.is_dir() or day_dir.name.count("-") != 2:
            continue
        for run_dir in sorted(day_dir.iterdir(), key=lambda item: item.stat().st_mtime, reverse=True):
            if not run_dir.is_dir() or not run_dir.name.startswith("run_"):
                continue
            manifest = _read_json(run_dir / "run_manifest.json") or {}
            report = _read_json(run_dir / "daily_generation_report.json") or {}
            autopilot_report = _read_json(run_dir / "autopilot_report.json") or {}
            effective_report = autopilot_report or report
            content_dirs = [
                item for item in run_dir.iterdir() if item.is_dir() and item.name.isdigit()
            ]
            runs.append(
                {
                    "date": day_dir.name,
                    "run_id": run_dir.name.removeprefix("run_"),
                    "path": str(run_dir),
                    "modified_at": datetime.fromtimestamp(run_dir.stat().st_mtime).isoformat(),
                    "content_count": len(content_dirs),
                    "manifest_slot_count": len(manifest.get("content_slots", [])),
                    "report_status": effective_report.get("status"),
                    "report_success_count": effective_report.get("success_count"),
                    "report_error_count": effective_report.get("error_count"),
                    "report_mode": effective_report.get("mode"),
                }
            )
            if len(runs) >= limit:
                return runs
    return runs


def get_run_detail(
    *,
    base_dir: str | Path = "output",
    date: str,
    run_id: str,
) -> Dict[str, Any]:
    root = Path(base_dir)
    safe_run_id = run_id if run_id.startswith("run_") else f"run_{run_id}"
    run_dir = _safe_child(root, date, safe_run_id)
    if not run_dir.exists() or not run_dir.is_dir():
        raise FileNotFoundError(f"run 不存在: {run_dir}")

    contents: List[Dict[str, Any]] = []
    for content_dir in sorted(
        item for item in run_dir.iterdir() if item.is_dir() and item.name.isdigit()
    ):
        manifest = _read_json(content_dir / "content_manifest.json") or {}
        plan = _read_json(content_dir / "video_plan.json") or {}
        pack = manifest.get("pack", {}) if isinstance(manifest.get("pack"), dict) else {}
        assets = plan.get("assets", {}) if isinstance(plan.get("assets"), dict) else {}
        contents.append(
            {
                "index": int(content_dir.name),
                "path": str(content_dir),
                "status": manifest.get("status"),
                "error": manifest.get("error"),
                "topic": pack.get("topic") or plan.get("topic"),
                "content_type": pack.get("content_type") or plan.get("content_type"),
                "score": (pack.get("viral_score") or {}).get("score"),
                "quality_gate_passed": pack.get("quality_gate_passed"),
                "video_plan_path": str(content_dir / "video_plan.json")
                if (content_dir / "video_plan.json").exists()
                else None,
                "assets": assets,
                "errors": pack.get("errors") or plan.get("errors") or [],
            }
        )

    return {
        "date": date,
        "run_id": safe_run_id.removeprefix("run_"),
        "path": str(run_dir),
        "manifest": _read_json(run_dir / "run_manifest.json"),
        "report": (
            _read_json(run_dir / "autopilot_report.json")
            or _read_json(run_dir / "daily_generation_report.json")
        ),
        "contents": contents,
    }


def get_quota_snapshot(refresh: bool = False) -> Dict[str, Any]:
    settings = get_settings()
    if refresh:
        settings.refresh_quota_remains()
    return settings.get_quota_status()
