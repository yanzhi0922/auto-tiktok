# -*- coding: utf-8 -*-
"""
结构化视频计划。

`video_plan.json` 是每条内容的可恢复生产蓝图：先记录要生成什么，再逐步
写回实际素材、模型路由和失败信息。它不替代 manifest，而是给重生成、看板
和后续发布链路提供稳定输入。
"""

from __future__ import annotations

import json
from dataclasses import asdict, dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional


PLAN_VERSION = "1.0"


def _now() -> str:
    return datetime.now().isoformat()


def _path_text(value: Any) -> Optional[str]:
    if value is None:
        return None
    return str(value)


@dataclass
class ModelCallPlan:
    stage: str
    resource: str
    requested_model: Optional[str] = None
    applied_model: Optional[str] = None
    tier: Optional[str] = None
    prompt: Optional[str] = None
    status: str = "planned"
    metadata: Dict[str, Any] = field(default_factory=dict)
    updated_at: str = field(default_factory=_now)

    def update(self, **kwargs: Any) -> None:
        for key, value in kwargs.items():
            if value is not None:
                setattr(self, key, value)
        self.updated_at = _now()


@dataclass
class ScenePlan:
    index: int
    prompt: str
    camera_hint: Optional[str] = None
    duration: int = 6
    asset_path: Optional[str] = None
    status: str = "planned"


@dataclass
class AssetPlan:
    kind: str
    path: Optional[str] = None
    status: str = "planned"
    source_stage: Optional[str] = None
    metadata: Dict[str, Any] = field(default_factory=dict)
    updated_at: str = field(default_factory=_now)

    def update(self, *, path: Any = None, status: Optional[str] = None, **metadata: Any) -> None:
        if path is not None:
            self.path = _path_text(path)
        if status is not None:
            self.status = status
        if metadata:
            self.metadata.update({key: value for key, value in metadata.items() if value is not None})
        self.updated_at = _now()


@dataclass
class VideoPlan:
    topic: str
    platform: str = "douyin"
    content_type: Optional[str] = None
    style: Optional[str] = None
    duration: int = 6
    voice: Optional[str] = None
    version: str = PLAN_VERSION
    created_at: str = field(default_factory=_now)
    updated_at: str = field(default_factory=_now)
    run_id: Optional[str] = None
    content_index: Optional[int] = None
    content_dir: Optional[str] = None
    script: Dict[str, Any] = field(default_factory=dict)
    titles: List[str] = field(default_factory=list)
    hashtags: List[str] = field(default_factory=list)
    scenes: List[ScenePlan] = field(default_factory=list)
    cover: Dict[str, Any] = field(default_factory=dict)
    subtitles: Dict[str, Any] = field(default_factory=dict)
    model_calls: Dict[str, ModelCallPlan] = field(default_factory=dict)
    assets: Dict[str, AssetPlan] = field(default_factory=dict)
    quality_gate: Dict[str, Any] = field(default_factory=dict)
    errors: List[str] = field(default_factory=list)

    @classmethod
    def create(
        cls,
        *,
        topic: str,
        content_dir: Path,
        run_id: str,
        content_index: int,
        duration: int,
        voice: Optional[str],
        settings: Any,
        platform: str = "douyin",
        content_type: Optional[str] = None,
        style: Optional[str] = None,
        generate_video: bool = True,
        generate_music: bool = True,
        generate_thumbnail: bool = True,
    ) -> "VideoPlan":
        plan = cls(
            topic=topic,
            platform=platform,
            content_type=content_type,
            style=style,
            duration=duration,
            voice=voice,
            run_id=run_id,
            content_index=content_index,
            content_dir=str(content_dir),
        )
        plan.model_calls = {
            "script": ModelCallPlan(
                stage="script",
                resource="text",
                requested_model=settings.models.text_model_ultra,
            ),
            "titles": ModelCallPlan(
                stage="titles",
                resource="text",
                requested_model=settings.models.text_model_ultra,
            ),
            "tts": ModelCallPlan(
                stage="tts",
                resource="tts",
                requested_model=settings.models.speech_model,
            ),
            "video": ModelCallPlan(
                stage="video",
                resource="video",
                requested_model=settings.models.video_model_fast if generate_video else None,
                metadata={
                    "requested_duration": duration,
                    "requested_resolution": "768P",
                    "enabled": bool(generate_video),
                },
            ),
            "thumbnail": ModelCallPlan(
                stage="thumbnail",
                resource="image",
                requested_model=settings.models.image_model if generate_thumbnail else None,
                metadata={"enabled": bool(generate_thumbnail), "aspect_ratio": "9:16"},
            ),
            "music": ModelCallPlan(
                stage="music",
                resource="music",
                requested_model=settings.models.music_model if generate_music else None,
                metadata={"enabled": bool(generate_music), "mode": "instrumental"},
            ),
            "subtitle": ModelCallPlan(
                stage="subtitle",
                resource="local",
                requested_model=None,
                metadata={
                    "engine": getattr(settings.auto.content_strategy, "subtitle_engine", "estimate")
                },
            ),
        }
        for kind in (
            "script",
            "titles",
            "audio",
            "video",
            "music",
            "thumbnail",
            "subtitle",
            "final_video",
            "cover",
        ):
            plan.assets[kind] = AssetPlan(kind=kind)
        plan.cover = {
            "enabled": bool(generate_thumbnail),
            "prompt": "",
            "path": None,
            "source": "image_or_video_frame",
        }
        plan.subtitles = {
            "engine": getattr(settings.auto.content_strategy, "subtitle_engine", "estimate"),
            "path": None,
            "word_level_path": None,
        }
        return plan

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "VideoPlan":
        raw = dict(data)
        raw["scenes"] = [ScenePlan(**item) for item in raw.get("scenes", [])]
        raw["model_calls"] = {
            key: ModelCallPlan(**value)
            for key, value in raw.get("model_calls", {}).items()
        }
        raw["assets"] = {
            key: AssetPlan(**value)
            for key, value in raw.get("assets", {}).items()
        }
        return cls(**raw)

    @classmethod
    def load(cls, path: str | Path) -> "VideoPlan":
        data = json.loads(Path(path).read_text(encoding="utf-8"))
        return cls.from_dict(data)

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)

    def save(self, path: str | Path | None = None) -> Path:
        if path is None:
            if not self.content_dir:
                raise ValueError("video plan 缺少 content_dir，无法保存")
            path = Path(self.content_dir) / "video_plan.json"
        output_path = Path(path)
        output_path.parent.mkdir(parents=True, exist_ok=True)
        self.updated_at = _now()
        tmp_path = output_path.with_name(f".{output_path.name}.tmp")
        tmp_path.write_text(
            json.dumps(self.to_dict(), ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
        tmp_path.replace(output_path)
        return output_path

    def record_call(
        self,
        stage: str,
        metadata: Optional[Dict[str, Any]] = None,
        *,
        prompt: Optional[str] = None,
        status: str = "succeeded",
    ) -> None:
        metadata = dict(metadata or {})
        call = self.model_calls.get(stage) or ModelCallPlan(
            stage=stage,
            resource=str(metadata.get("resource_used") or metadata.get("resource") or "unknown"),
        )
        call.update(
            requested_model=metadata.get("requested_model"),
            applied_model=metadata.get("applied_model"),
            tier=metadata.get("key_tier_used") or metadata.get("tier_used"),
            prompt=prompt,
            status=status,
            metadata={**call.metadata, **metadata},
        )
        self.model_calls[stage] = call

    def record_asset(
        self,
        kind: str,
        path: Any = None,
        *,
        status: str = "succeeded",
        source_stage: Optional[str] = None,
        **metadata: Any,
    ) -> None:
        asset = self.assets.get(kind) or AssetPlan(kind=kind)
        asset.source_stage = source_stage or asset.source_stage
        asset.update(path=path, status=status, **metadata)
        self.assets[kind] = asset

    def record_error(self, message: str) -> None:
        if message not in self.errors:
            self.errors.append(message)
        self.updated_at = _now()


def update_plan_from_pack(plan: VideoPlan, pack: Any) -> VideoPlan:
    """把 ContentPack / DouyinContentPack 的最新状态同步回 VideoPlan。"""

    plan.script = {
        "raw_content": getattr(pack, "script", None),
        "hook": getattr(pack, "hook", None),
        "narration": getattr(pack, "narration", None),
        "video_description": getattr(pack, "video_description", None),
        "engagement_question": getattr(pack, "engagement_question", None),
        "cta": getattr(pack, "cta", None),
        "hook_type_used": getattr(pack, "hook_type_used", None),
    }
    plan.titles = list(getattr(pack, "titles", []) or [])
    plan.hashtags = list(getattr(pack, "hashtags", []) or [])
    plan.quality_gate = dict(getattr(pack, "generation_metadata", {}).get("quality_gate", {}))

    video_prompt = getattr(pack, "video_description", None)
    if video_prompt and not plan.scenes:
        plan.scenes = [
            ScenePlan(
                index=1,
                prompt=video_prompt,
                duration=int(plan.duration or 6),
            )
        ]

    assets = {
        "audio": getattr(pack, "audio_path", None),
        "video": getattr(pack, "video_path", None),
        "music": getattr(pack, "music_path", None),
        "thumbnail": getattr(pack, "thumbnail_path", None),
        "final_video": getattr(pack, "final_video_path", None),
        "cover": getattr(pack, "cover_path", None),
    }
    for kind, path in assets.items():
        if path:
            plan.record_asset(kind, path)

    for stage, metadata in getattr(pack, "generation_metadata", {}).items():
        plan.record_call(stage, metadata)

    for error in getattr(pack, "errors", []) or []:
        plan.record_error(str(error))

    return plan
