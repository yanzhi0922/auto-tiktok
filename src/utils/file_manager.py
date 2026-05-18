# -*- coding: utf-8 -*-
"""
文件管理工具。
负责输出文件命名、目录组织和基础统计。
"""

from __future__ import annotations

import json
import logging
import os
import re
from datetime import datetime
from pathlib import Path
from threading import Lock
from typing import Any, Dict, List, Optional


logger = logging.getLogger(__name__)


class FileManager:
    """
    文件管理器。

    目录结构：
    output/
    └── YYYY-MM-DD/
        └── run_<run_id>/
            ├── 001/
            ├── 002/
            ├── daily_generation_report.json
            └── run_manifest.json
    """

    INVALID_FILENAME_CHARS = re.compile(r'[<>:"/\\|?*\x00-\x1f]')
    MULTIPLE_UNDERSCORES = re.compile(r"_+")
    _WRITE_LOCK = Lock()

    def __init__(
        self,
        base_dir: str | Path = "output",
        date_suffix: Optional[str] = None,
        run_id: Optional[str] = None,
    ):
        self.base_dir = Path(base_dir)
        self.date_suffix = date_suffix or datetime.now().strftime("%Y-%m-%d")
        self.run_id = self.sanitize_component(
            run_id or self._generate_run_id(), fallback="run"
        )
        self._content_dirs: Dict[int, Path] = {}
        self._next_index = 1
        self.run_dir.mkdir(parents=True, exist_ok=True)
        self.reports_dir.mkdir(parents=True, exist_ok=True)
        self._load_existing_content_dirs()
        self._write_run_manifest()

    @property
    def day_dir(self) -> Path:
        return self.base_dir / self.date_suffix

    @property
    def run_dir(self) -> Path:
        return self.day_dir / f"run_{self.run_id}"

    @property
    def reports_dir(self) -> Path:
        return self.run_dir

    @property
    def run_manifest_path(self) -> Path:
        return self.run_dir / "run_manifest.json"

    def _generate_run_id(self) -> str:
        return f"{datetime.now().strftime('%H%M%S_%f')}_p{os.getpid()}"

    def _load_existing_content_dirs(self) -> None:
        """恢复已存在的 NNN 内容目录，避免复用 run_id 时覆盖 manifest 槽位。"""
        if not self.run_dir.exists():
            return
        for item in sorted(self.run_dir.iterdir()):
            if not item.is_dir() or not item.name.isdigit():
                continue
            index = int(item.name)
            self._content_dirs[index] = item
            self._next_index = max(self._next_index, index + 1)

    @classmethod
    def sanitize_component(cls, value: str, fallback: str = "untitled") -> str:
        cleaned = cls.INVALID_FILENAME_CHARS.sub("_", value)
        cleaned = cleaned.replace("\n", "_").replace("\r", "_").strip().strip(".")
        cleaned = re.sub(r"\s+", "_", cleaned)
        cleaned = cls.MULTIPLE_UNDERSCORES.sub("_", cleaned)
        cleaned = cleaned.strip("_")
        return cleaned[:80] or fallback

    @classmethod
    def sanitize_filename(cls, filename: str) -> str:
        path = Path(filename)
        suffix = path.suffix
        stem = path.name[: -len(suffix)] if suffix else path.name
        safe_stem = cls.sanitize_component(stem)
        safe_suffix = cls.INVALID_FILENAME_CHARS.sub("", suffix).replace(".", "")
        return f"{safe_stem}.{safe_suffix}" if safe_suffix else safe_stem

    def get_content_dir(self, index: Optional[int] = None) -> Path:
        _, content_dir = self.reserve_content_slot(index=index)
        return content_dir

    def reserve_content_slot(self, index: Optional[int] = None) -> tuple[int, Path]:
        if index is None:
            index = self._next_index
            self._next_index += 1
        else:
            self._next_index = max(self._next_index, index + 1)

        if index not in self._content_dirs:
            path = self.run_dir / f"{index:03d}"
            path.mkdir(parents=True, exist_ok=True)
            self._content_dirs[index] = path
            self._write_run_manifest()

        return index, self._content_dirs[index]

    def get_path(self, content_index: int, filename: str, subdir: str = "") -> Path:
        safe_filename = self.sanitize_filename(filename)
        base_path = self.get_content_dir(content_index)
        dir_path = base_path / subdir if subdir else base_path
        dir_path.mkdir(parents=True, exist_ok=True)
        return dir_path / safe_filename

    def get_thumbnails_dir(self) -> Path:
        path = self.run_dir / "thumbnails"
        path.mkdir(parents=True, exist_ok=True)
        return path

    def get_report_path(self, filename: str = "report.json") -> Path:
        return self.reports_dir / self.sanitize_filename(filename)

    def generate_filename(
        self,
        prefix: str,
        extension: str,
        suffix: Optional[str] = None,
    ) -> str:
        base_name = self.sanitize_component(prefix)
        if suffix:
            base_name = f"{base_name}_{self.sanitize_component(suffix)}"

        clean_extension = extension.lstrip(".")
        return f"{base_name}.{clean_extension}" if clean_extension else base_name

    def get_output_path(
        self,
        content_type: str,
        filename: str,
        create_subdir: bool = True,
        content_index: Optional[int] = None,
    ) -> Path:
        safe_filename = self.sanitize_filename(filename)

        if content_type == "reports":
            path = self.reports_dir / safe_filename
        elif content_type == "thumbnails":
            path = self.get_thumbnails_dir() / safe_filename
        else:
            path = self.get_path(content_index or 1, safe_filename)

        if create_subdir:
            path.parent.mkdir(parents=True, exist_ok=True)
        return path

    def save_text(
        self,
        content: str,
        filename: str,
        content_type: str = "texts",
        content_index: Optional[int] = None,
    ) -> Path:
        path = self.get_output_path(content_type, filename, content_index=content_index)
        self._write_text_atomic(path, content)
        return path

    def save_json(
        self,
        data: Dict[str, Any],
        filename: str,
        content_type: str = "reports",
        content_index: Optional[int] = None,
    ) -> Path:
        path = self.get_output_path(content_type, filename, content_index=content_index)
        path.parent.mkdir(parents=True, exist_ok=True)
        self._write_text_atomic(path, json.dumps(data, ensure_ascii=False, indent=2))
        return path

    def save_binary(
        self,
        data: bytes,
        filename: str,
        content_type: str,
        content_index: Optional[int] = None,
    ) -> Path:
        path = self.get_output_path(content_type, filename, content_index=content_index)
        path.parent.mkdir(parents=True, exist_ok=True)
        self._write_bytes_atomic(path, data)
        return path

    def save_content_manifest(
        self,
        content_index: int,
        data: Dict[str, Any],
        filename: str = "content_manifest.json",
    ) -> Path:
        path = self.get_path(content_index, filename)
        self._write_text_atomic(path, json.dumps(data, ensure_ascii=False, indent=2))
        self._write_run_manifest()
        return path

    def write_text_to_path(self, path: str | Path, content: str) -> Path:
        resolved_path = Path(path)
        self._write_text_atomic(resolved_path, content)
        return resolved_path

    def write_json_to_path(self, path: str | Path, data: Dict[str, Any]) -> Path:
        resolved_path = Path(path)
        self._write_text_atomic(
            resolved_path,
            json.dumps(data, ensure_ascii=False, indent=2),
        )
        return resolved_path

    def _write_run_manifest(self) -> None:
        payload = {
            "date": self.date_suffix,
            "run_id": self.run_id,
            "run_dir": str(self.run_dir),
            "content_slots": [
                {
                    "index": index,
                    "path": str(path),
                }
                for index, path in sorted(self._content_dirs.items())
            ],
            "updated_at": datetime.now().isoformat(),
        }
        self._write_text_atomic(
            self.run_manifest_path,
            json.dumps(payload, ensure_ascii=False, indent=2),
        )

    def _write_text_atomic(self, path: Path, content: str) -> None:
        self._write_bytes_atomic(path, content.encode("utf-8"))

    def _write_bytes_atomic(self, path: Path, data: bytes) -> None:
        with self._WRITE_LOCK:
            path.parent.mkdir(parents=True, exist_ok=True)
            tmp_path = path.with_name(
                f".{path.name}.{os.getpid()}.{datetime.now().strftime('%H%M%S%f')}.tmp"
            )
            tmp_path.write_bytes(data)
            tmp_path.replace(path)

    def load_json(self, filepath: str | Path) -> Dict[str, Any]:
        return json.loads(Path(filepath).read_text(encoding="utf-8"))

    def list_files(
        self,
        content_type: str,
        date: Optional[str] = None,
        extension: Optional[str] = None,
    ) -> List[Path]:
        search_dir = self.base_dir / date if date else self.day_dir
        if not search_dir.exists():
            return []

        files = [path for path in search_dir.rglob("*") if path.is_file()]
        if extension:
            expected_suffix = f".{extension.lstrip('.')}"
            files = [path for path in files if path.suffix == expected_suffix]
        return sorted(files)

    def get_stats(self) -> Dict[str, Any]:
        stats = {"total_files": 0, "total_size": 0, "days": {}}
        if not self.base_dir.exists():
            return stats

        day_dirs = sorted(
            item
            for item in self.base_dir.iterdir()
            if item.is_dir()
            and item.name[:4].isdigit()
            and item.name.count("-") == 2
        )

        for day_dir in day_dirs:
            files = [path for path in day_dir.rglob("*") if path.is_file()]
            total_size = sum(path.stat().st_size for path in files)
            run_count = sum(
                1
                for item in day_dir.iterdir()
                if item.is_dir() and item.name.startswith("run_")
            )
            legacy_content_dir_count = sum(
                1
                for item in day_dir.iterdir()
                if item.is_dir() and item.name.startswith("content_")
            )

            stats["days"][day_dir.name] = {
                "file_count": len(files),
                "size_mb": round(total_size / 1024 / 1024, 2),
                "run_count": run_count,
                "legacy_content_dir_count": legacy_content_dir_count,
            }
            stats["total_files"] += len(files)
            stats["total_size"] += total_size

        return stats
