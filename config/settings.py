# -*- coding: utf-8 -*-
"""
全局配置管理模块
管理 MiniMax API 密钥、模型配置、输出路径和配额状态。
"""

from __future__ import annotations

import logging
import os
from pathlib import Path
from typing import Any, Dict, List, Optional

from dotenv import load_dotenv
import yaml

from config.token_plan import (
    DEFAULT_TOKEN_PLAN_QUOTAS,
    TOKEN_PLAN_REMAINS_URL,
    TokenPlanQuotaTracker,
    build_default_tiers,
)


load_dotenv()

logger = logging.getLogger(__name__)


def _coerce_bool(value: Any, default: bool) -> bool:
    if isinstance(value, bool):
        return value
    if isinstance(value, str):
        normalized = value.strip().lower()
        if normalized in {"1", "true", "yes", "y", "on"}:
            return True
        if normalized in {"0", "false", "no", "n", "off"}:
            return False
    return default


def _normalize_daily_schedule(value: Any, fallback: str = "09:00") -> str:
    """
    将 YAML 中的时间配置标准化为 HH:MM。

    支持：
    - "09:00"
    - "0 9 * * *"
    """
    if not value:
        return fallback

    if isinstance(value, list):
        for item in value:
            normalized = _normalize_daily_schedule(item, fallback="")
            if normalized:
                return normalized
        return fallback

    text = str(value).strip()
    if not text:
        return fallback

    if ":" in text:
        parts = text.split(":")
        if len(parts) >= 2 and parts[0].isdigit() and parts[1].isdigit():
            hour = max(0, min(23, int(parts[0])))
            minute = max(0, min(59, int(parts[1])))
            return f"{hour:02d}:{minute:02d}"

    cron_parts = text.split()
    if (
        len(cron_parts) == 5
        and cron_parts[0].isdigit()
        and cron_parts[1].isdigit()
    ):
        minute = max(0, min(59, int(cron_parts[0])))
        hour = max(0, min(23, int(cron_parts[1])))
        return f"{hour:02d}:{minute:02d}"

    return fallback


class AutoContentStrategyConfig:
    """自动化内容策略配置。"""

    def __init__(self, data: Optional[Dict[str, Any]] = None):
        data = data or {}
        self.default_types: List[str] = list(
            data.get(
                "default_types",
                [
                    "生活技巧",
                    "情感共鸣",
                    "知识科普",
                    "娱乐搞笑",
                    "美食探店",
                    "旅行vlog",
                    "萌宠日常",
                ],
            )
        )
        self.daily_count: int = max(1, min(int(data.get("daily_count", 3)), 20))
        self.auto_generate_video: bool = _coerce_bool(
            data.get("auto_generate_video", True), True
        )
        self.auto_generate_music: bool = _coerce_bool(
            data.get("auto_generate_music", False), False
        )
        self.auto_generate_thumbnail: bool = _coerce_bool(
            data.get("auto_generate_thumbnail", True), True
        )
        self.default_duration: int = int(data.get("default_duration", 6))
        if self.default_duration not in {6, 10}:
            self.default_duration = 6
        self.default_voice: str = str(data.get("default_voice", "female_tianmei"))
        self.subtitle_engine: str = str(
            data.get(
                "subtitle_engine",
                os.getenv("AUTO_TIKTOK_SUBTITLE_ENGINE", "estimate"),
            )
        ).strip().lower()
        if self.subtitle_engine not in {"estimate", "whisperx"}:
            self.subtitle_engine = "estimate"


class AutoPublishStrategyConfig:
    """发布时间策略配置。"""

    def __init__(self, data: Optional[Dict[str, Any]] = None):
        data = data or {}
        self.best_hours: List[int] = [
            int(hour)
            for hour in data.get("best_hours", [12, 18, 19, 20, 21])
            if str(hour).isdigit()
        ]
        self.weekday_best_time: str = _normalize_daily_schedule(
            data.get("weekday_best_time", "18:00"),
            fallback="18:00",
        )
        self.weekend_best_time: str = _normalize_daily_schedule(
            data.get("weekend_best_time", "12:00"),
            fallback="12:00",
        )


class AutoAutomationConfig:
    """自动化调度配置。"""

    def __init__(self, data: Optional[Dict[str, Any]] = None):
        data = data or {}
        self.enabled: bool = _coerce_bool(data.get("enabled", True), True)
        self.schedule: str = str(data.get("schedule", "09:00"))
        self.daily_time: str = _normalize_daily_schedule(self.schedule, "09:00")
        self.output_dir: str = str(data.get("output_dir", "output"))
        self.log_dir: str = str(data.get("log_dir", "logs"))


class AutoAutopilotConfig:
    """全自动生产配置。"""

    def __init__(self, data: Optional[Dict[str, Any]] = None):
        data = data or {}
        self.enabled: bool = _coerce_bool(data.get("enabled", True), True)
        self.default_count: int = max(1, min(int(data.get("default_count", 3)), 20))
        self.min_score: int = max(0, min(int(data.get("min_score", 65)), 100))
        self.publish_min_score: int = max(
            0,
            min(int(data.get("publish_min_score", self.min_score)), 100),
        )
        self.script_attempts: int = max(1, min(int(data.get("script_attempts", 4)), 8))
        self.script_accept_score: int = max(
            0,
            min(int(data.get("script_accept_score", self.min_score)), 100),
        )
        self.max_topic_attempts: int = max(
            self.default_count,
            min(int(data.get("max_topic_attempts", self.default_count * 3)), 100),
        )
        self.max_generation_retries: int = max(
            0,
            min(int(data.get("max_generation_retries", 1)), 5),
        )
        self.auto_publish: bool = _coerce_bool(data.get("auto_publish", True), True)
        self.publish_provider: str = str(data.get("publish_provider", "manual")).lower()
        self.publish_fallback_provider: str = str(
            data.get("publish_fallback_provider", "manual")
        ).lower()
        self.asset_retries: List[str] = [
            str(item).strip().lower()
            for item in data.get(
                "asset_retries",
                ["video", "subtitle", "compose", "cover"],
            )
            if str(item).strip()
        ]
        self.topic_source_urls: List[str] = [
            str(item).strip()
            for item in data.get("topic_source_urls", [])
            if str(item).strip()
        ]


class AutoConfig:
    """`config/auto_config.yaml` 的结构化访问层。"""

    def __init__(self, data: Optional[Dict[str, Any]] = None):
        data = data or {}
        self.content_strategy = AutoContentStrategyConfig(
            data.get("content_strategy", {})
        )
        self.publish_strategy = AutoPublishStrategyConfig(
            data.get("publish_strategy", {})
        )
        self.automation = AutoAutomationConfig(data.get("automation", {}))
        self.autopilot = AutoAutopilotConfig(data.get("autopilot", {}))
        self.trending_topics: Dict[str, List[str]] = {
            str(key): list(value) if isinstance(value, list) else []
            for key, value in (data.get("trending_topics", {}) or {}).items()
        }

    @classmethod
    def load(cls, path: Path) -> "AutoConfig":
        if not path.exists():
            logger.info(f"未找到自动化配置文件，使用默认配置: {path}")
            return cls()

        try:
            raw_data = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
        except (OSError, yaml.YAMLError) as exc:
            logger.warning(f"读取自动化配置失败，将使用默认配置: {exc}")
            return cls()

        if not isinstance(raw_data, dict):
            logger.warning("自动化配置格式无效，将使用默认配置")
            return cls()

        return cls(raw_data)


class APIConfig:
    """API 配置。"""

    def __init__(self):
        self.primary_tier: str = "ultra"
        self.secondary_tier: str = "max"
        configured_tier = os.getenv("MINIMAX_TOKEN_PLAN_TIER", "").strip().lower()
        if configured_tier not in {"", "ultra", "max"}:
            logger.warning(
                "未知 MINIMAX_TOKEN_PLAN_TIER=%s，将使用默认 Ultra -> Max 路由",
                configured_tier,
            )
            configured_tier = ""
        self.configured_tier: Optional[str] = configured_tier or None

        raw_primary_api_key = os.getenv("MINIMAX_TOKEN_PLAN_KEY", "")
        raw_secondary_api_key = os.getenv("MINIMAX_TOKEN_PLAN_KEY2", "")

        if configured_tier == "max":
            self.primary_api_key = ""
            self.secondary_api_key = raw_secondary_api_key or raw_primary_api_key
            self.tier_order: List[str] = ["max"]
        elif configured_tier == "ultra":
            self.primary_api_key = raw_primary_api_key or raw_secondary_api_key
            self.secondary_api_key = ""
            self.tier_order = ["ultra"]
        else:
            self.primary_api_key = raw_primary_api_key
            self.secondary_api_key = raw_secondary_api_key
            self.tier_order = ["ultra", "max"]

        self.api_key: str = self.primary_api_key or self.secondary_api_key
        self.backup_api_key: str = (
            self.secondary_api_key
            if not self.configured_tier and self.primary_api_key
            else ""
        )
        self.base_url: str = "https://api.minimaxi.com"
        self.backup_base_url: str = "https://api-bj.minimaxi.com"
        self.remains_url: str = TOKEN_PLAN_REMAINS_URL
        self.max_retries: int = 3
        self.retry_delay: float = 1.0
        self.retry_backoff: float = 2.0
        self.request_timeout: float = 60.0
        self.video_poll_interval: float = 10.0
        self.video_max_wait: float = 600.0
        self.batch_delay: float = 1.0
        self.tiers = build_default_tiers(
            self.primary_api_key,
            self.secondary_api_key,
        )

    def normalize_tier(self, tier: str) -> str:
        normalized = (tier or "ultra").strip().lower()
        if normalized not in self.tiers:
            raise KeyError(f"未知 Token Plan 套餐层级: {tier}")
        return normalized

    def get_tier(self, tier: str):
        return self.tiers[self.normalize_tier(tier)]

    def get_api_key(self, tier: str) -> str:
        return self.get_tier(tier).api_key

    def has_available_key(self) -> bool:
        return any(self.get_api_key(tier) for tier in self.tier_order)

    def resolve_route(self, preferred_tier: Optional[str] = None) -> List[str]:
        if preferred_tier:
            tier = self.normalize_tier(preferred_tier)
            if tier in self.tier_order:
                return [tier] + [item for item in self.tier_order if item != tier]
        return list(self.tier_order)


class ModelsConfig:
    """模型配置。"""

    def __init__(self):
        self.text_model_ultra: str = "MiniMax-M2.7-highspeed"
        self.text_model_max: str = "MiniMax-M2.7"
        self.text_model: str = self.text_model_ultra
        self.speech_model: str = "speech-2.8-hd"
        self.speech_model_turbo: str = "speech-2.8-hd"
        self.video_model: str = "MiniMax-Hailuo-2.3"
        self.video_model_fast: str = "MiniMax-Hailuo-2.3-Fast"
        self.music_model: Optional[str] = "music-2.6"
        self.music_model_standard: Optional[str] = "music-2.6"
        self.music_instrumental_supported: bool = False
        self.image_model: str = "image-01"
        self.image_model_live: str = "image-01"
        self._supported_text_models: Dict[str, set[str]] = {
            "ultra": {self.text_model_ultra},
            "max": {self.text_model_max},
        }
        self._supported_speech_models: set[str] = {self.speech_model}
        self._supported_music_models: set[str] = {
            model
            for model in [self.music_model, self.music_model_standard, "music-2.5"]
            if model
        }
        self._supported_image_models: set[str] = {
            self.image_model,
            self.image_model_live,
        }

    def text_model_for_tier(self, tier: str) -> str:
        return self.text_model_ultra if tier == "ultra" else self.text_model_max

    def normalize_text_model_for_tier(
        self,
        tier: str,
        requested_model: Optional[str] = None,
    ) -> str:
        default_model = self.text_model_for_tier(tier)
        if requested_model in self._supported_text_models.get(tier, set()):
            return requested_model
        return default_model

    def normalize_speech_model(self, requested_model: Optional[str] = None) -> str:
        if requested_model in self._supported_speech_models:
            return requested_model
        return self.speech_model

    def normalize_music_model(self, requested_model: Optional[str] = None) -> Optional[str]:
        if requested_model in self._supported_music_models:
            return requested_model
        return self.music_model

    def supports_music_instrumental(self) -> bool:
        return self.music_instrumental_supported

    def normalize_image_model(self, requested_model: Optional[str] = None) -> str:
        if requested_model in self._supported_image_models:
            return requested_model
        return self.image_model


class QuotasConfig:
    """MiniMax Token Plan 配额配置。"""

    def __init__(self):
        self.tiers: Dict[str, Dict[str, int]] = {
            tier: values.copy()
            for tier, values in DEFAULT_TOKEN_PLAN_QUOTAS.items()
        }
        ultra = self.tiers["ultra"]
        self.text_requests_per_5h: int = ultra["text_requests_per_5h"]
        self.tts_chars_per_day: int = ultra["tts_chars_per_day"]
        self.video_fast_per_day: int = ultra["video_fast_per_day"]
        self.video_per_day: int = ultra["video_per_day"]
        self.music_per_day: int = ultra["music_per_day"]
        self.image_per_day: int = ultra["image_per_day"]

    def for_tier(self, tier: str) -> Dict[str, int]:
        return self.tiers[tier]


class OutputConfig:
    """输出目录配置。"""

    def __init__(self, auto_config: Optional[AutoConfig] = None):
        auto_automation = auto_config.automation if auto_config else None
        self.base_dir: Path = Path(
            auto_automation.output_dir if auto_automation else "output"
        )
        self.system_dir_name: str = "_system"
        self.text_dir: str = "texts"
        self.audio_dir: str = "audios"
        self.video_dir: str = "videos"
        self.music_dir: str = "music"
        self.image_dir: str = "images"
        self.report_dir: str = "reports"
        self.log_dir: Path = Path(auto_automation.log_dir if auto_automation else "logs")

    @property
    def system_dir(self) -> Path:
        return self.base_dir / self.system_dir_name

    @property
    def quota_state_file(self) -> Path:
        return self.system_dir / "quota_state.json"


class Settings:
    """全局配置类（单例模式）。"""

    _instance = None

    def __new__(cls):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
            cls._instance._initialized = False
        return cls._instance

    def __init__(self):
        if self._initialized:
            return

        auto_config_path = Path(__file__).with_name("auto_config.yaml")
        self.auto = AutoConfig.load(auto_config_path)
        self.api = APIConfig()
        self.models = ModelsConfig()
        self.quotas = QuotasConfig()
        self.output = OutputConfig(self.auto)
        self.quota_tracker = TokenPlanQuotaTracker(
            tiers=self.api.tiers,
            quotas_by_tier=self.quotas.tiers,
            state_file=self.output.quota_state_file,
            remains_url=self.api.remains_url,
        )
        self.log_level: str = os.getenv("AUTO_TIKTOK_LOG_LEVEL", "INFO").upper()

        self._initialized = True

    def set_log_level(self, level: str) -> None:
        self.log_level = level.upper()

    def check_quota(
        self,
        resource: str,
        amount: int = 1,
        tier: Optional[str] = None,
        refresh_remote: bool = False,
    ) -> bool:
        resource = resource.lower()
        if resource in {
            "video",
            "video_fast",
            "video_standard",
            "music",
            "image",
            "text",
            "tts",
        }:
            return self.quota_tracker.check_resource(
                resource=resource,
                amount=amount,
                tier=tier,
                refresh_remote=refresh_remote,
            )
        return True

    def record_usage(
        self, resource: str, amount: int = 1, tier: Optional[str] = None
    ) -> None:
        resource = resource.lower()
        if resource in {
            "video",
            "video_fast",
            "video_standard",
            "music",
            "image",
            "text",
            "tts",
        }:
            self.quota_tracker.record_usage(
                resource=resource,
                amount=amount,
                tier=tier or "ultra",
            )

    def get_quota_status(self) -> Dict[str, Any]:
        return self.quota_tracker.get_status()

    def refresh_quota_remains(
        self, tiers: Optional[List[str]] = None
    ) -> Dict[str, Optional[Dict[str, Dict[str, Any]]]]:
        refreshed: Dict[str, Optional[Dict[str, Dict[str, Any]]]] = {}
        for tier in tiers or self.api.tier_order:
            refreshed[tier] = self.quota_tracker.refresh_remote_remains(tier)
        return refreshed


def get_settings() -> Settings:
    """获取全局配置实例。"""

    return Settings()


def ensure_output_dirs():
    """确保输出目录存在。"""

    settings = get_settings()
    base_dir = settings.output.base_dir
    dirs = [
        base_dir,
        settings.output.system_dir,
        Path(settings.output.log_dir),
    ]

    for dir_path in dirs:
        dir_path.mkdir(parents=True, exist_ok=True)

    legacy_dirs = [
        base_dir / "audios",
        base_dir / "final",
        base_dir / "images",
        base_dir / "music",
        base_dir / "reports",
        base_dir / "subtitles",
        base_dir / "texts",
        base_dir / "videos",
    ]
    for legacy_dir in legacy_dirs:
        try:
            if legacy_dir.exists() and not any(legacy_dir.iterdir()):
                legacy_dir.rmdir()
        except OSError:
            continue

    return dirs
