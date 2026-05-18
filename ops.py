#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""运维工具：健康检查、备份、日志轮转和轻量迁移。"""

from __future__ import annotations

import argparse
import json
import shutil
import zipfile
from datetime import datetime, timedelta
from pathlib import Path
from typing import Dict, List

from output_manager import audit_output
from src.utils.file_manager import FileManager


def _timestamp() -> str:
    return datetime.now().strftime("%Y%m%d_%H%M%S")


def backup_project(
    *,
    output_dir: Path,
    logs_dir: Path,
    backup_dir: Path,
    include_logs: bool = True,
) -> Dict[str, object]:
    backup_dir.mkdir(parents=True, exist_ok=True)
    target = backup_dir / f"auto_tiktok_backup_{_timestamp()}.zip"
    with zipfile.ZipFile(target, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        for root in [output_dir, logs_dir if include_logs else None, Path("config")]:
            if root is None or not root.exists():
                continue
            for item in root.rglob("*"):
                if item.is_file():
                    archive.write(item, item.as_posix())
        for item in [Path("README.md"), Path("docker-compose.yml"), Path("Dockerfile")]:
            if item.exists():
                archive.write(item, item.as_posix())
    return {"backup_path": str(target), "size": target.stat().st_size}


def rotate_logs(*, logs_dir: Path, keep_days: int = 14) -> Dict[str, List[str]]:
    archived: List[str] = []
    removed: List[str] = []
    if not logs_dir.exists():
        return {"archived": archived, "removed": removed}

    cutoff = datetime.now() - timedelta(days=keep_days)
    archive_root = logs_dir / "_archive" / _timestamp()
    for item in logs_dir.rglob("*.log"):
        if "_archive" in item.parts:
            continue
        modified = datetime.fromtimestamp(item.stat().st_mtime)
        if modified >= cutoff:
            continue
        archive_root.mkdir(parents=True, exist_ok=True)
        target = archive_root / item.name
        shutil.move(str(item), str(target))
        archived.append(str(target))

    for directory in sorted(logs_dir.rglob("*"), reverse=True):
        if directory.is_dir() and directory != logs_dir and not any(directory.iterdir()):
            directory.rmdir()
            removed.append(str(directory))
    return {"archived": archived, "removed_empty_dirs": removed}


def migrate_output_manifests(*, output_dir: Path) -> Dict[str, object]:
    repaired: List[str] = []
    if not output_dir.exists():
        return {"repaired": repaired}

    for day_dir in output_dir.iterdir():
        if not day_dir.is_dir() or day_dir.name.count("-") != 2:
            continue
        for run_dir in day_dir.iterdir():
            if not run_dir.is_dir() or not run_dir.name.startswith("run_"):
                continue
            run_id = run_dir.name.removeprefix("run_")
            manager = FileManager(output_dir, date_suffix=day_dir.name, run_id=run_id)
            slots = sorted(item for item in run_dir.iterdir() if item.is_dir() and item.name.isdigit())
            for slot in slots:
                manager.reserve_content_slot(int(slot.name))
            repaired.append(str(manager.run_manifest_path))

    (output_dir / "_system" / "tasks").mkdir(parents=True, exist_ok=True)
    return {"repaired": repaired, "count": len(repaired)}


def health(output_dir: Path) -> Dict[str, object]:
    audit = audit_output(output_dir)
    return {
        "status": "ok" if not audit.get("warnings") else "warning",
        "audit_warnings": audit.get("warnings", []),
        "day_count": audit.get("day_count", 0),
    }


def main() -> None:
    parser = argparse.ArgumentParser(description="Auto TikTok 运维工具")
    parser.add_argument("command", choices=["health", "backup", "rotate-logs", "migrate"])
    parser.add_argument("--output-dir", default="output")
    parser.add_argument("--logs-dir", default="logs")
    parser.add_argument("--backup-dir", default="backups")
    parser.add_argument("--keep-days", type=int, default=14)
    args = parser.parse_args()

    output_dir = Path(args.output_dir)
    logs_dir = Path(args.logs_dir)
    backup_dir = Path(args.backup_dir)

    if args.command == "health":
        result = health(output_dir)
    elif args.command == "backup":
        result = backup_project(output_dir=output_dir, logs_dir=logs_dir, backup_dir=backup_dir)
    elif args.command == "rotate-logs":
        result = rotate_logs(logs_dir=logs_dir, keep_days=args.keep_days)
    else:
        result = migrate_output_manifests(output_dir=output_dir)
    print(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
