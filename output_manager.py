#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
输出目录审计与维护工具。

用于长期运行场景下的输出目录巡检、历史遗留迁移、根目录清理与测试产物归档。
"""

from __future__ import annotations

import argparse
import json
import shutil
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Dict, Iterable, List

from src.utils.file_manager import FileManager


LEGACY_FLAT_DIRS = [
    "audios",
    "final",
    "images",
    "music",
    "reports",
    "subtitles",
    "texts",
    "videos",
]

TEST_ARTIFACT_DIRS = [
    "test_audio",
    "test_subs",
    "tmp",
]

REPORT_SUFFIXES = {".json", ".html"}


@dataclass
class DirStat:
    path: Path
    file_count: int
    total_size: int

    def to_dict(self) -> Dict[str, object]:
        return {
            "path": str(self.path),
            "file_count": self.file_count,
            "total_size": self.total_size,
        }


def scan_dir(path: Path) -> DirStat:
    files = [item for item in path.rglob("*") if item.is_file()]
    return DirStat(
        path=path,
        file_count=len(files),
        total_size=sum(file.stat().st_size for file in files),
    )


def iter_day_dirs(base_dir: Path) -> Iterable[Path]:
    if not base_dir.exists():
        return []

    return sorted(
        item
        for item in base_dir.iterdir()
        if item.is_dir() and item.name[:4].isdigit() and item.name.count("-") == 2
    )


def collect_day_layout(day_dir: Path) -> Dict[str, List[Path]]:
    run_dirs = sorted(
        item for item in day_dir.iterdir() if item.is_dir() and item.name.startswith("run_")
    )
    legacy_content_dirs = sorted(
        item
        for item in day_dir.iterdir()
        if item.is_dir() and item.name.startswith("content_")
    )
    legacy_aux_dirs = sorted(
        item
        for item in day_dir.iterdir()
        if item.is_dir()
        and not item.name.startswith("run_")
        and not item.name.startswith("content_")
    )
    root_report_files = sorted(
        item
        for item in day_dir.iterdir()
        if item.is_file() and item.suffix.lower() in REPORT_SUFFIXES
    )

    return {
        "runs": run_dirs,
        "legacy_content_dirs": legacy_content_dirs,
        "legacy_aux_dirs": legacy_aux_dirs,
        "root_report_files": root_report_files,
    }


def audit_output(base_dir: Path) -> Dict[str, object]:
    per_day = []
    for day_dir in iter_day_dirs(base_dir):
        layout = collect_day_layout(day_dir)
        per_day.append(
            {
                "date": day_dir.name,
                "run_count": len(layout["runs"]),
                "legacy_content_dir_count": len(layout["legacy_content_dirs"]),
                "legacy_aux_dir_count": len(layout["legacy_aux_dirs"]),
                "legacy_aux_dirs": [item.name for item in layout["legacy_aux_dirs"]],
                "root_report_count": len(layout["root_report_files"]),
                "root_report_files": [
                    item.name for item in layout["root_report_files"]
                ],
                "runs": [scan_dir(run).to_dict() for run in layout["runs"][:20]],
            }
        )

    legacy_root = []
    for dir_name in LEGACY_FLAT_DIRS + TEST_ARTIFACT_DIRS:
        path = base_dir / dir_name
        if path.exists() and path.is_dir():
            legacy_root.append(scan_dir(path).to_dict())

    stray_root_files = (
        [
            str(item)
            for item in base_dir.iterdir()
            if item.is_file() and item.name != ".gitkeep"
        ]
        if base_dir.exists()
        else []
    )

    warnings: List[str] = []
    if legacy_root:
        warnings.append("根目录仍存在旧版平铺目录或测试目录。")
    if stray_root_files:
        warnings.append("输出根目录存在散落文件，建议迁移到 _system 或对应 run 目录。")
    if any(day["legacy_content_dir_count"] > 0 for day in per_day):
        warnings.append("存在旧版 content_* 直接挂在日期目录下的历史布局。")
    if any(day["legacy_aux_dir_count"] > 0 for day in per_day):
        warnings.append("存在日期目录级别的辅助目录，建议迁移到 run 内部。")
    if any(day["root_report_count"] > 0 for day in per_day):
        warnings.append("存在直接写在日期目录根部的历史报告文件。")

    return {
        "base_dir": str(base_dir),
        "generated_at": datetime.now().isoformat(),
        "day_count": len(per_day),
        "days": per_day,
        "legacy_root_dirs": legacy_root,
        "stray_root_files": stray_root_files,
        "warnings": warnings,
    }


def ensure_unique_target(path: Path) -> Path:
    if not path.exists():
        return path

    counter = 2
    while True:
        candidate = path.with_name(f"{path.stem}_{counter}{path.suffix}")
        if not candidate.exists():
            return candidate
        counter += 1


def move_path(source: Path, target: Path) -> Path:
    resolved_target = ensure_unique_target(target)
    resolved_target.parent.mkdir(parents=True, exist_ok=True)
    shutil.move(str(source), str(resolved_target))
    return resolved_target


def next_legacy_run_id(day_dir: Path) -> str:
    timestamp = datetime.now().strftime("%H%M%S")
    candidate = f"legacy_{timestamp}"
    counter = 2

    while (day_dir / f"run_{candidate}").exists():
        candidate = f"legacy_{timestamp}_{counter}"
        counter += 1

    return candidate


def migrate_root_stray_files(base_dir: Path) -> Dict[str, List[str]]:
    moved: List[str] = []
    removed: List[str] = []

    if not base_dir.exists():
        return {"moved": moved, "removed": removed}

    system_dir = base_dir / "_system"
    system_dir.mkdir(parents=True, exist_ok=True)
    archive_root = system_dir / "legacy_root_files" / datetime.now().strftime(
        "%Y%m%d_%H%M%S"
    )

    for item in sorted(base_dir.iterdir()):
        if not item.is_file() or item.name == ".gitkeep":
            continue

        if item.name == "quota_state.json":
            target = system_dir / item.name
            if target.exists():
                if item.read_bytes() == target.read_bytes():
                    item.unlink()
                    removed.append(str(item))
                    continue
                archive_root.mkdir(parents=True, exist_ok=True)
                target = archive_root / item.name
            moved.append(str(move_path(item, target)))
            continue

        archive_root.mkdir(parents=True, exist_ok=True)
        moved.append(str(move_path(item, archive_root / item.name)))

    return {"moved": moved, "removed": removed}


def migrate_legacy_output(base_dir: Path) -> Dict[str, object]:
    migrated_days: List[Dict[str, object]] = []

    for day_dir in iter_day_dirs(base_dir):
        layout = collect_day_layout(day_dir)
        legacy_items = (
            layout["legacy_content_dirs"]
            + layout["legacy_aux_dirs"]
            + layout["root_report_files"]
        )
        if not legacy_items:
            continue

        file_manager = FileManager(
            base_dir=base_dir,
            date_suffix=day_dir.name,
            run_id=next_legacy_run_id(day_dir),
        )

        migration_items: List[Dict[str, object]] = []
        legacy_content_dirs = sorted(
            layout["legacy_content_dirs"],
            key=lambda item: (item.stat().st_mtime, item.name),
        )

        for index, source_dir in enumerate(legacy_content_dirs, start=1):
            _, target_dir = file_manager.reserve_content_slot(index)
            if target_dir.exists():
                target_dir.rmdir()
            final_dir = move_path(source_dir, target_dir)
            migration_items.append(
                {
                    "type": "content_dir",
                    "source": str(source_dir),
                    "target": str(final_dir),
                }
            )

        for report_file in layout["root_report_files"]:
            final_path = move_path(report_file, file_manager.reports_dir / report_file.name)
            migration_items.append(
                {
                    "type": "report_file",
                    "source": str(report_file),
                    "target": str(final_path),
                }
            )

        if layout["legacy_aux_dirs"]:
            shared_dir = file_manager.run_dir / "legacy_shared"
            shared_dir.mkdir(parents=True, exist_ok=True)

            for aux_dir in layout["legacy_aux_dirs"]:
                if aux_dir.name == "thumbnails":
                    target_dir = file_manager.run_dir / aux_dir.name
                else:
                    target_dir = shared_dir / aux_dir.name
                final_dir = move_path(aux_dir, target_dir)
                migration_items.append(
                    {
                        "type": "aux_dir",
                        "source": str(aux_dir),
                        "target": str(final_dir),
                    }
                )

        manifest = {
            "migration_type": "legacy_output_relayout",
            "migrated_at": datetime.now().isoformat(),
            "date": day_dir.name,
            "run_id": file_manager.run_id,
            "run_dir": str(file_manager.run_dir),
            "moved_items": migration_items,
        }
        manifest_path = file_manager.save_json(
            manifest,
            filename="migration_manifest.json",
            content_type="reports",
        )
        migrated_days.append(
            {
                "date": day_dir.name,
                "run_dir": str(file_manager.run_dir),
                "moved_count": len(migration_items),
                "manifest": str(manifest_path),
            }
        )

    root_result = migrate_root_stray_files(base_dir)
    return {
        "migrated_days": migrated_days,
        "root_files": root_result,
    }


def cleanup_output(
    base_dir: Path,
    archive_test_artifacts: bool = False,
) -> Dict[str, object]:
    removed: List[str] = []
    archived: List[str] = []

    for dir_name in LEGACY_FLAT_DIRS:
        path = base_dir / dir_name
        if path.exists() and path.is_dir() and not any(path.iterdir()):
            path.rmdir()
            removed.append(str(path))

    if archive_test_artifacts:
        archive_root = (
            base_dir
            / "_system"
            / "archived_artifacts"
            / datetime.now().strftime("%Y%m%d_%H%M%S")
        )
        archive_root.mkdir(parents=True, exist_ok=True)
        for dir_name in TEST_ARTIFACT_DIRS:
            path = base_dir / dir_name
            if path.exists():
                target = archive_root / path.name
                shutil.move(str(path), str(target))
                archived.append(str(target))

    for dir_name in LEGACY_FLAT_DIRS:
        path = base_dir / dir_name
        if path.exists() and path.is_dir() and not any(path.iterdir()):
            path.rmdir()
            if str(path) not in removed:
                removed.append(str(path))

    return {
        "removed": removed,
        "archived": archived,
    }


def maintain_output(
    base_dir: Path,
    archive_test_artifacts: bool = False,
) -> Dict[str, object]:
    migration = migrate_legacy_output(base_dir)
    cleanup = cleanup_output(
        base_dir=base_dir,
        archive_test_artifacts=archive_test_artifacts,
    )
    audit = audit_output(base_dir)
    return {
        "migration": migration,
        "cleanup": cleanup,
        "audit": audit,
    }


def main() -> None:
    parser = argparse.ArgumentParser(description="输出目录审计与维护工具")
    parser.add_argument(
        "command",
        choices=["audit", "cleanup", "migrate-legacy", "maintain"],
        help="执行的动作",
    )
    parser.add_argument("--base-dir", default="output", help="输出根目录")
    parser.add_argument(
        "--archive-test-artifacts",
        action="store_true",
        help="归档 test_audio/test_subs/tmp 目录到 output/_system/archived_artifacts",
    )
    parser.add_argument(
        "--json",
        action="store_true",
        help="以 JSON 输出结果",
    )
    args = parser.parse_args()

    base_dir = Path(args.base_dir)
    if args.command == "audit":
        result = audit_output(base_dir)
    elif args.command == "cleanup":
        result = cleanup_output(
            base_dir=base_dir,
            archive_test_artifacts=args.archive_test_artifacts,
        )
    elif args.command == "migrate-legacy":
        result = migrate_legacy_output(base_dir)
    else:
        result = maintain_output(
            base_dir=base_dir,
            archive_test_artifacts=args.archive_test_artifacts,
        )

    if args.json:
        print(json.dumps(result, ensure_ascii=False, indent=2))
        return

    print(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
