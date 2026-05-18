# -*- coding: utf-8 -*-
"""全自动短视频生产运行器。"""

from __future__ import annotations

import json
import logging
import os
import random
import time
from dataclasses import asdict, dataclass
from datetime import datetime
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional

import requests

from config.settings import Settings, ensure_output_dirs, get_settings
from src.pipeline.douyin_pipeline import DouyinPipeline
from src.pipeline.orchestrator import QuotaExceededError
from src.pipeline.regenerator import AssetRegenerationService
from src.pipeline.video_plan import VideoPlan
from src.publish.publisher import PublisherService
from src.strategy.douyin_strategy import DouyinContentStrategy
from src.utils.file_manager import FileManager
from src.utils.redaction import redact_obj


logger = logging.getLogger(__name__)


CATEGORY_ALIASES = {
    "life_hacks": "生活技巧",
    "emotional": "情感共鸣",
    "knowledge": "知识科普",
    "entertainment": "娱乐搞笑",
    "food": "美食探店",
    "travel": "旅行vlog",
    "pets": "萌宠日常",
}


@dataclass
class TopicCandidate:
    topic: str
    content_type: str
    source: str = "local"


def _coerce_topic_text(value: Any) -> str:
    if isinstance(value, str):
        return value.strip()
    if isinstance(value, dict):
        for key in ("topic", "title", "keyword", "query", "name"):
            text = str(value.get(key) or "").strip()
            if text:
                return text
    return ""


def _normalize_content_type(value: Any, fallback: str) -> str:
    text = str(value or "").strip()
    return CATEGORY_ALIASES.get(text, text or fallback)


class TopicProvider:
    """合并本地话题库和可选外部话题源。"""

    def __init__(
        self,
        settings: Optional[Settings] = None,
        *,
        http_get: Optional[Callable[..., Any]] = None,
    ):
        self.settings = settings or get_settings()
        self.strategy = DouyinContentStrategy()
        self.http_get = http_get or requests.get

    def build_plan(
        self,
        *,
        count: int,
        content_types: Optional[List[str]] = None,
    ) -> List[TopicCandidate]:
        resolved_types = content_types or self.settings.auto.content_strategy.default_types
        if not resolved_types:
            resolved_types = list(self.strategy.TRENDING_TOPICS)

        external_by_type = self._external_candidates_by_type(resolved_types)
        local_pool = self._local_pool_by_type()
        used_topics: set[str] = set()
        plan: List[TopicCandidate] = []

        for index in range(max(0, count)):
            content_type = resolved_types[index % len(resolved_types)]
            candidate = self._pop_candidate(
                external_by_type,
                content_type=content_type,
                used_topics=used_topics,
            )
            if candidate is None:
                candidate = self._pop_local_candidate(
                    local_pool,
                    content_type=content_type,
                    used_topics=used_topics,
                )
            if candidate is None:
                candidate = TopicCandidate(
                    topic=f"{content_type}灵感",
                    content_type=content_type,
                    source="fallback",
                )
            used_topics.add(candidate.topic)
            plan.append(candidate)

        return plan

    def _local_pool_by_type(self) -> Dict[str, List[str]]:
        pool: Dict[str, List[str]] = {
            content_type: list(topics)
            for content_type, topics in self.strategy.TRENDING_TOPICS.items()
        }
        for raw_key, topics in self.settings.auto.trending_topics.items():
            content_type = _normalize_content_type(raw_key, raw_key)
            pool.setdefault(content_type, [])
            pool[content_type].extend(str(topic).strip() for topic in topics if str(topic).strip())

        for topics in pool.values():
            unique_topics = list(dict.fromkeys(topics))
            random.shuffle(unique_topics)
            topics[:] = unique_topics
        return pool

    def _external_candidates_by_type(
        self,
        content_types: List[str],
    ) -> Dict[str, List[TopicCandidate]]:
        urls = list(self.settings.auto.autopilot.topic_source_urls)
        env_urls = [
            item.strip()
            for item in os.getenv("AUTO_TIKTOK_TRENDING_URLS", "").split(",")
            if item.strip()
        ]
        urls.extend(env_urls)
        candidates: Dict[str, List[TopicCandidate]] = {}
        for url in urls:
            try:
                response = self.http_get(url, timeout=8)
                if hasattr(response, "raise_for_status"):
                    response.raise_for_status()
                payload = self._parse_response_payload(response)
                for candidate in self._candidates_from_payload(
                    payload,
                    source=url,
                    content_types=content_types,
                ):
                    candidates.setdefault(candidate.content_type, []).append(candidate)
            except Exception as exc:
                logger.warning("外部话题源读取失败: %s (%s)", url, exc)
        return candidates

    def _parse_response_payload(self, response: Any) -> Any:
        if hasattr(response, "json"):
            try:
                return response.json()
            except ValueError:
                pass
        text = str(getattr(response, "text", "") or "")
        try:
            return json.loads(text)
        except json.JSONDecodeError:
            return [line.strip() for line in text.splitlines() if line.strip()]

    def _candidates_from_payload(
        self,
        payload: Any,
        *,
        source: str,
        content_types: List[str],
    ) -> List[TopicCandidate]:
        candidates: List[TopicCandidate] = []
        fallback_types = content_types or list(self.strategy.TRENDING_TOPICS)
        if isinstance(payload, dict):
            if isinstance(payload.get("topics"), list):
                payload = payload["topics"]
            else:
                for key, value in payload.items():
                    if not isinstance(value, list):
                        continue
                    content_type = _normalize_content_type(key, fallback_types[0])
                    for item in value:
                        topic = _coerce_topic_text(item)
                        if topic:
                            candidates.append(TopicCandidate(topic, content_type, source))
                return candidates

        if isinstance(payload, list):
            for index, item in enumerate(payload):
                topic = _coerce_topic_text(item)
                if not topic:
                    continue
                fallback_type = fallback_types[index % len(fallback_types)]
                content_type = (
                    _normalize_content_type(item.get("content_type"), fallback_type)
                    if isinstance(item, dict)
                    else fallback_type
                )
                candidates.append(TopicCandidate(topic, content_type, source))
        return candidates

    def _pop_candidate(
        self,
        candidates: Dict[str, List[TopicCandidate]],
        *,
        content_type: str,
        used_topics: set[str],
    ) -> Optional[TopicCandidate]:
        pool = candidates.get(content_type, [])
        while pool:
            candidate = pool.pop(0)
            if candidate.topic not in used_topics:
                return candidate
        return None

    def _pop_local_candidate(
        self,
        pool: Dict[str, List[str]],
        *,
        content_type: str,
        used_topics: set[str],
    ) -> Optional[TopicCandidate]:
        topics = pool.get(content_type, [])
        while topics:
            topic = topics.pop(0)
            if topic not in used_topics:
                return TopicCandidate(topic, content_type, "local")
        fallback_topics = self.strategy.TRENDING_TOPICS.get(content_type, [])
        if fallback_topics:
            return TopicCandidate(random.choice(fallback_topics), content_type, "local_repeat")
        return None


class AutopilotService:
    """自动选题、生成、修复和发布的自治运行器。"""

    def __init__(
        self,
        *,
        settings: Optional[Settings] = None,
        output_dir: str | Path | None = None,
        topic_provider: Optional[TopicProvider] = None,
        pipeline_factory: Optional[Callable[..., Any]] = None,
        publisher: Optional[Any] = None,
        regenerator_factory: Optional[Callable[[Path], Any]] = None,
    ):
        self.settings = settings or get_settings()
        self.output_dir = Path(output_dir or self.settings.output.base_dir)
        self.topic_provider = topic_provider or TopicProvider(self.settings)
        self.pipeline_factory = pipeline_factory or self._default_pipeline_factory
        self.publisher = publisher or PublisherService()
        self.regenerator_factory = regenerator_factory or (
            lambda output_dir: AssetRegenerationService(output_dir=output_dir)
        )

    def run(
        self,
        *,
        count: Optional[int] = None,
        content_types: Optional[List[str]] = None,
        min_score: Optional[int] = None,
        publish_provider: Optional[str] = None,
        dry_run: bool = False,
    ) -> Dict[str, Any]:
        ensure_output_dirs()
        config = self.settings.auto.autopilot
        target_count = count or config.default_count
        min_score = config.min_score if min_score is None else min_score
        target_count = self._quota_limited_count(target_count)
        max_candidates = max(config.max_topic_attempts, target_count)

        start_time = datetime.now()
        date_suffix = start_time.strftime("%Y-%m-%d")
        file_manager = FileManager(self.output_dir, date_suffix=date_suffix)
        topic_plan = self.topic_provider.build_plan(
            count=max_candidates,
            content_types=content_types,
        )
        report: Dict[str, Any] = {
            "status": "running",
            "mode": "autopilot",
            "started_at": start_time.isoformat(),
            "run_id": file_manager.run_id,
            "run_dir": str(file_manager.run_dir),
            "target_count": target_count,
            "min_score": min_score,
            "publish_provider": publish_provider or config.publish_provider,
            "topic_plan": [asdict(candidate) for candidate in topic_plan],
            "candidates": [],
            "final_videos": [],
            "publications": [],
            "skipped": [],
            "errors": [],
            "quota_before": self._safe_quota_snapshot(),
        }

        if target_count <= 0:
            report["status"] = "quota_exhausted"
            return self._finish_report(file_manager, report, start_time)

        pipeline = None
        try:
            pipeline = None if dry_run else self.pipeline_factory(
                output_dir=str(self.output_dir),
                file_manager=file_manager,
            )
            for index, candidate in enumerate(topic_plan, start=1):
                if len(report["final_videos"]) >= target_count:
                    break
                if dry_run:
                    report["candidates"].append({**asdict(candidate), "status": "planned"})
                    continue
                pack = self._generate_candidate(
                    pipeline,
                    candidate=candidate,
                    index=index,
                    min_score=min_score,
                )
                if not pack:
                    report["errors"].append(
                        {**asdict(candidate), "status": "failed_before_pack"}
                    )
                    continue
                candidate_record = self._record_candidate(candidate, pack)
                report["candidates"].append(candidate_record)

                if not pack.quality_gate_passed:
                    report["skipped"].append(candidate_record)
                    continue

                repair_results = self._repair_assets(pack)
                final_video_path = self._resolve_asset_path(pack, "final_video")
                if not final_video_path:
                    report["errors"].append(
                        {
                            **candidate_record,
                            "status": "failed_missing_final_video",
                            "repairs": repair_results,
                        }
                    )
                    continue

                final_record = {
                    **candidate_record,
                    "status": "ready",
                    "final_video_path": str(final_video_path),
                    "repairs": repair_results,
                }
                publication = self._maybe_publish(
                    pack,
                    score=int(candidate_record.get("score") or 0),
                    provider=publish_provider or config.publish_provider,
                )
                if publication:
                    final_record["publication"] = publication
                    report["publications"].append(publication)
                report["final_videos"].append(final_record)
        except QuotaExceededError as exc:
            report["errors"].append({"status": "quota_exhausted", "error": str(exc)})
            report["status"] = "quota_exhausted"
        finally:
            if pipeline and hasattr(pipeline, "close"):
                pipeline.close()

        if report["status"] == "running":
            report["status"] = "succeeded" if report["final_videos"] else "no_publishable_video"
        return self._finish_report(file_manager, report, start_time)

    def _default_pipeline_factory(self, *, output_dir: str, file_manager: FileManager):
        return DouyinPipeline(output_dir=output_dir, file_manager=file_manager)

    def _quota_limited_count(self, requested_count: int) -> int:
        if requested_count <= 0:
            return 0
        status = self._safe_quota_snapshot()
        strategy = self.settings.auto.content_strategy
        limits = [requested_count]
        if strategy.auto_generate_video:
            limits.append(int((status.get("video") or {}).get("remaining", requested_count)))
        if strategy.auto_generate_thumbnail:
            limits.append(int((status.get("image") or {}).get("remaining", requested_count)))
        return max(0, min(limits))

    def _safe_quota_snapshot(self) -> Dict[str, Any]:
        try:
            self.settings.refresh_quota_remains()
        except Exception as exc:
            logger.warning("刷新配额失败，使用本地配额状态: %s", exc)
        try:
            return redact_obj(self.settings.get_quota_status())
        except Exception as exc:
            return {"error": str(exc)}

    def _generate_candidate(
        self,
        pipeline: Any,
        *,
        candidate: TopicCandidate,
        index: int,
        min_score: int,
    ) -> Optional[Any]:
        config = self.settings.auto.autopilot
        last_error: Optional[Exception] = None
        for attempt in range(config.max_generation_retries + 1):
            try:
                return pipeline.generate_douyin_content(
                    topic=candidate.topic,
                    content_type=candidate.content_type,
                    duration=self.settings.auto.content_strategy.default_duration,
                    voice=self.settings.auto.content_strategy.default_voice,
                    generate_video=self.settings.auto.content_strategy.auto_generate_video,
                    generate_music=self.settings.auto.content_strategy.auto_generate_music,
                    generate_thumbnail=self.settings.auto.content_strategy.auto_generate_thumbnail,
                    pack_index=index,
                    min_score_threshold=min_score,
                    script_max_attempts=config.script_attempts,
                    script_accept_score=config.script_accept_score,
                )
            except QuotaExceededError:
                raise
            except Exception as exc:
                last_error = exc
                logger.warning(
                    "Autopilot 候选生成失败，准备重试: %s (%s/%s)",
                    candidate.topic,
                    attempt + 1,
                    config.max_generation_retries + 1,
                )
                if attempt < config.max_generation_retries:
                    time.sleep(1.0)
        if last_error:
            logger.error("Autopilot 候选最终失败: %s", last_error)
        return None

    def _record_candidate(self, candidate: TopicCandidate, pack: Any) -> Dict[str, Any]:
        score_data = pack.viral_score or {}
        return {
            **asdict(candidate),
            "status": "quality_passed" if pack.quality_gate_passed else "quality_skipped",
            "score": int(score_data.get("score") or 0),
            "level": score_data.get("level"),
            "content_dir": str(pack.content_dir) if pack.content_dir else None,
            "video_plan_path": str(pack.video_plan_path) if pack.video_plan_path else None,
        }

    def _repair_assets(self, pack: Any) -> List[Dict[str, Any]]:
        plan_path = getattr(pack, "video_plan_path", None)
        if not plan_path or not Path(plan_path).exists():
            return []
        results: List[Dict[str, Any]] = []
        regenerator = self.regenerator_factory(self.output_dir)
        for asset in self.settings.auto.autopilot.asset_retries:
            if not self._asset_needs_repair(pack, asset):
                continue
            try:
                result = regenerator.regenerate(asset=asset, plan_path=str(plan_path))
                results.append({"asset": asset, "status": "succeeded", "result": result})
            except Exception as exc:
                results.append({"asset": asset, "status": "failed", "error": str(exc)})
        return results

    def _asset_needs_repair(self, pack: Any, asset: str) -> bool:
        if asset == "video":
            return not self._resolve_asset_path(pack, "video")
        if asset in {"compose", "final_video"}:
            return not self._resolve_asset_path(pack, "final_video")
        if asset in {"cover", "thumbnail"}:
            return not self._resolve_asset_path(pack, "cover")
        if asset == "subtitle":
            return not self._resolve_asset_path(pack, "subtitle")
        return False

    def _resolve_asset_path(self, pack: Any, asset: str) -> Optional[Path]:
        attr_map = {
            "video": "video_path",
            "final_video": "final_video_path",
            "cover": "cover_path",
            "thumbnail": "thumbnail_path",
            "subtitle": None,
        }
        attr = attr_map.get(asset)
        if attr:
            value = getattr(pack, attr, None)
            if value and Path(value).exists():
                return Path(value)

        plan_path = getattr(pack, "video_plan_path", None)
        if not plan_path or not Path(plan_path).exists():
            return None
        plan = VideoPlan.load(plan_path)
        plan_asset = plan.assets.get(asset)
        if plan_asset and plan_asset.path and Path(plan_asset.path).exists():
            if attr:
                setattr(pack, attr, Path(plan_asset.path))
            return Path(plan_asset.path)
        return None

    def _maybe_publish(self, pack: Any, *, score: int, provider: str) -> Optional[Dict[str, Any]]:
        config = self.settings.auto.autopilot
        if not config.auto_publish or score < config.publish_min_score:
            return None
        plan_path = getattr(pack, "video_plan_path", None)
        if not plan_path:
            return None
        resolved_provider = self._resolve_publish_provider(provider)
        try:
            result = self.publisher.publish(
                plan_path=str(plan_path),
                provider=resolved_provider,
            )
            return {
                "provider": resolved_provider,
                "status": "succeeded",
                "plan_path": str(plan_path),
                "result": redact_obj(result),
            }
        except Exception as exc:
            return {
                "provider": resolved_provider,
                "status": "failed",
                "plan_path": str(plan_path),
                "error": str(exc),
            }

    def _resolve_publish_provider(self, provider: str) -> str:
        provider = (provider or "manual").strip().lower()
        if provider == "auto":
            return "tiktok" if os.getenv("TIKTOK_ACCESS_TOKEN") else "manual"
        if provider == "tiktok" and not os.getenv("TIKTOK_ACCESS_TOKEN"):
            return self.settings.auto.autopilot.publish_fallback_provider
        return provider

    def _finish_report(
        self,
        file_manager: FileManager,
        report: Dict[str, Any],
        start_time: datetime,
    ) -> Dict[str, Any]:
        end_time = datetime.now()
        report["ended_at"] = end_time.isoformat()
        report["duration_seconds"] = (end_time - start_time).total_seconds()
        report["quota_after"] = self._safe_quota_snapshot()
        report["success_count"] = len(report.get("final_videos", []))
        report["error_count"] = len(report.get("errors", []))
        report["skipped_count"] = len(report.get("skipped", []))
        report_path = file_manager.save_json(
            redact_obj(report),
            filename="autopilot_report.json",
            content_type="reports",
        )
        report["report_path"] = str(report_path)
        return redact_obj(report)
