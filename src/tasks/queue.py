# -*- coding: utf-8 -*-
"""轻量 JSON 持久化任务队列。"""

from __future__ import annotations

import json
import threading
import time
import uuid
from dataclasses import asdict, dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional

from src.pipeline.douyin_pipeline import DouyinPipeline
from src.pipeline.autopilot import AutopilotService
from src.pipeline.regenerator import AssetRegenerationService
from src.publish.publisher import PublisherService
from src.utils.redaction import redact_obj


TASK_STATUSES = {
    "queued",
    "running",
    "succeeded",
    "failed",
    "canceled",
    "cancel_requested",
}


def _now() -> str:
    return datetime.now().isoformat()


@dataclass
class TaskRecord:
    id: str
    task_type: str
    payload: Dict[str, Any]
    status: str = "queued"
    result: Optional[Dict[str, Any]] = None
    error: Optional[str] = None
    created_at: str = field(default_factory=_now)
    updated_at: str = field(default_factory=_now)
    started_at: Optional[str] = None
    finished_at: Optional[str] = None


class TaskQueue:
    """单进程任务队列，支持持久化和后台 worker。"""

    def __init__(
        self,
        *,
        base_dir: str | Path = "output",
        max_workers: int = 1,
    ):
        self.base_dir = Path(base_dir)
        self.system_dir = self.base_dir / "_system" / "tasks"
        self.system_dir.mkdir(parents=True, exist_ok=True)
        self.state_file = self.system_dir / "tasks.json"
        self.max_workers = max(1, int(max_workers))
        self._lock = threading.RLock()
        self._stop_event = threading.Event()
        self._workers: List[threading.Thread] = []
        self.tasks: Dict[str, TaskRecord] = {}
        self.handlers: Dict[str, Callable[[Dict[str, Any]], Dict[str, Any]]] = {
            "regenerate_asset": self._handle_regenerate_asset,
            "publish": self._handle_publish,
            "generate_daily": self._handle_generate_daily,
            "autopilot_run": self._handle_autopilot_run,
        }
        self._load()

    def _load(self) -> None:
        if not self.state_file.exists():
            return
        try:
            raw = json.loads(self.state_file.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            return
        for item in raw.get("tasks", []):
            try:
                task = TaskRecord(**item)
            except TypeError:
                continue
            if task.status == "running":
                task.status = "failed"
                task.error = "进程重启时任务仍在运行，已标记为失败"
                task.finished_at = _now()
                task.updated_at = _now()
            self.tasks[task.id] = task
        self._save()

    def _save(self) -> None:
        payload = {
            "updated_at": _now(),
            "tasks": [
                asdict(task)
                for task in sorted(
                    self.tasks.values(),
                    key=lambda item: item.created_at,
                    reverse=True,
                )
            ],
        }
        tmp_path = self.state_file.with_name(".tasks.json.tmp")
        tmp_path.write_text(
            json.dumps(redact_obj(payload), ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
        tmp_path.replace(self.state_file)

    def enqueue(self, task_type: str, payload: Dict[str, Any]) -> TaskRecord:
        if task_type not in self.handlers:
            raise ValueError(f"未知任务类型: {task_type}")
        task = TaskRecord(
            id=uuid.uuid4().hex,
            task_type=task_type,
            payload=dict(payload or {}),
        )
        with self._lock:
            self.tasks[task.id] = task
            self._save()
        return task

    def list_tasks(self, limit: int = 100) -> List[Dict[str, Any]]:
        with self._lock:
            items = sorted(
                self.tasks.values(),
                key=lambda item: item.created_at,
                reverse=True,
            )
            return [asdict(item) for item in items[:limit]]

    def get_task(self, task_id: str) -> Optional[Dict[str, Any]]:
        with self._lock:
            task = self.tasks.get(task_id)
            return asdict(task) if task else None

    def cancel(self, task_id: str) -> Dict[str, Any]:
        with self._lock:
            task = self.tasks.get(task_id)
            if not task:
                raise KeyError(f"任务不存在: {task_id}")
            if task.status == "queued":
                task.status = "canceled"
                task.finished_at = _now()
            elif task.status == "running":
                task.status = "cancel_requested"
            task.updated_at = _now()
            self._save()
            return asdict(task)

    def start(self) -> None:
        if self._workers:
            return
        self._stop_event.clear()
        for index in range(self.max_workers):
            worker = threading.Thread(
                target=self._worker_loop,
                name=f"task-worker-{index + 1}",
                daemon=True,
            )
            worker.start()
            self._workers.append(worker)

    def stop(self) -> None:
        self._stop_event.set()
        for worker in self._workers:
            worker.join(timeout=2)
        self._workers = []

    def _next_task(self) -> Optional[TaskRecord]:
        with self._lock:
            for task in sorted(self.tasks.values(), key=lambda item: item.created_at):
                if task.status == "queued":
                    task.status = "running"
                    task.started_at = _now()
                    task.updated_at = task.started_at
                    self._save()
                    return task
        return None

    def _worker_loop(self) -> None:
        while not self._stop_event.is_set():
            task = self._next_task()
            if not task:
                time.sleep(0.5)
                continue
            self._execute(task)

    def _execute(self, task: TaskRecord) -> None:
        try:
            handler = self.handlers[task.task_type]
            result = handler(task.payload)
            with self._lock:
                current = self.tasks[task.id]
                if current.status == "cancel_requested":
                    current.status = "canceled"
                else:
                    current.status = "succeeded"
                current.result = redact_obj(result)
                current.error = None
                current.finished_at = _now()
                current.updated_at = current.finished_at
                self._save()
        except Exception as exc:
            with self._lock:
                current = self.tasks[task.id]
                current.status = "failed"
                current.error = str(exc)
                current.finished_at = _now()
                current.updated_at = current.finished_at
                self._save()

    def _handle_regenerate_asset(self, payload: Dict[str, Any]) -> Dict[str, Any]:
        service = AssetRegenerationService(output_dir=self.base_dir)
        return service.regenerate(
            asset=str(payload.get("asset") or ""),
            plan_path=payload.get("plan_path"),
            content_dir=payload.get("content_dir"),
        )

    def _handle_publish(self, payload: Dict[str, Any]) -> Dict[str, Any]:
        provider = str(payload.get("provider") or "manual")
        plan_path = payload.get("plan_path")
        if not plan_path:
            raise ValueError("发布任务缺少 plan_path")
        return PublisherService().publish(plan_path=plan_path, provider=provider)

    def _handle_generate_daily(self, payload: Dict[str, Any]) -> Dict[str, Any]:
        count = int(payload.get("count") or 1)
        content_types = payload.get("content_types")
        if isinstance(content_types, str):
            content_types = [item.strip() for item in content_types.split(",") if item.strip()]
        pipeline = DouyinPipeline(output_dir=str(self.base_dir))
        try:
            packs = pipeline.generate_daily_content(
                count=count,
                content_types=content_types,
            )
            return {
                "count": len(packs),
                "packs": [
                    {
                        "topic": getattr(pack, "topic", None),
                        "content_index": getattr(pack, "content_index", None),
                        "content_dir": str(getattr(pack, "content_dir", "") or ""),
                        "video_plan_path": str(getattr(pack, "video_plan_path", "") or ""),
                    }
                    for pack in packs
                ],
            }
        finally:
            pipeline.close()

    def _handle_autopilot_run(self, payload: Dict[str, Any]) -> Dict[str, Any]:
        content_types = payload.get("content_types")
        if isinstance(content_types, str):
            content_types = [item.strip() for item in content_types.split(",") if item.strip()]
        return AutopilotService(output_dir=self.base_dir).run(
            count=int(payload.get("count") or 0) or None,
            content_types=content_types,
            min_score=int(payload.get("min_score") or 0) or None,
            publish_provider=payload.get("publish_provider"),
            dry_run=bool(payload.get("dry_run", False)),
        )
