from __future__ import annotations

import json
import logging
import os
from datetime import datetime
from pathlib import Path
from queue import Empty, Queue
from threading import RLock, Thread
from time import time
from typing import Any, Dict, List, Optional

import requests


logger = logging.getLogger(__name__)

TOKEN_PLAN_REMAINS_URL = (
    "https://www.minimaxi.com/v1/api/openplatform/coding_plan/remains"
)

DEFAULT_TOKEN_PLAN_QUOTAS: Dict[str, Dict[str, int]] = {
    "ultra": {
        "text_requests_per_5h": 30000,
        "tts_chars_per_day": 50000,
        "video_fast_per_day": 5,
        "video_per_day": 5,
        "music_per_day": 15,
        "image_per_day": 800,
    },
    "max": {
        "text_requests_per_5h": 4500,
        "tts_chars_per_day": 11000,
        "video_fast_per_day": 2,
        "video_per_day": 2,
        "music_per_day": 100,
        "image_per_day": 120,
    },
}


class TokenPlanTierConfig:
    """单个 Token Plan 套餐层级配置。"""

    def __init__(
        self,
        name: str,
        api_key: str,
        priority: int,
        label: str,
        text_model: str,
    ):
        self.name = name
        self.api_key = api_key
        self.priority = priority
        self.label = label
        self.text_model = text_model

    @property
    def enabled(self) -> bool:
        return bool(self.api_key)


def build_default_tiers(
    ultra_key: str,
    max_key: str,
) -> Dict[str, TokenPlanTierConfig]:
    return {
        "ultra": TokenPlanTierConfig(
            name="ultra",
            api_key=ultra_key,
            priority=0,
            label="Ultra-极速版",
            text_model="MiniMax-M2.7-highspeed",
        ),
        "max": TokenPlanTierConfig(
            name="max",
            api_key=max_key,
            priority=1,
            label="Max-标准版",
            text_model="MiniMax-M2.7",
        ),
    }


class TokenPlanQuotaTracker:
    """
    MiniMax Token Plan 配额追踪器。

    - 本地状态按套餐层级（ultra / max）分别记账
    - 支持 remains 接口远端剩余额度
    - 远端不可用时自动回退到本地状态
    """

    def __init__(
        self,
        tiers: Dict[str, TokenPlanTierConfig],
        quotas_by_tier: Dict[str, Dict[str, int]],
        state_file: Path,
        remains_url: str = TOKEN_PLAN_REMAINS_URL,
    ):
        self.tiers = tiers
        self.tier_order = sorted(tiers, key=lambda name: tiers[name].priority)
        self.quotas_by_tier = quotas_by_tier
        self.state_file = state_file
        self.remains_url = remains_url
        self.state_file.parent.mkdir(parents=True, exist_ok=True)
        self._lock = RLock()
        self._last_reset_date: Optional[str] = None

        self._daily_stats: Dict[str, Dict[str, int]] = {
            tier: {
                "video_fast": 0,
                "video_standard": 0,
                "music": 0,
                "image": 0,
                "tts_chars": 0,
            }
            for tier in self.tier_order
        }
        self._text_stats: Dict[str, Dict[str, float]] = {
            tier: {
                "window_start": time(),
                "requests_in_window": 0,
            }
            for tier in self.tier_order
        }
        self._remote_remains: Dict[str, Dict[str, Any]] = {
            tier: {
                "status": {},
                "raw": None,
                "updated_at": None,
            }
            for tier in self.tier_order
        }

        self._load_state()
        self._check_date_reset()
        self._check_text_window_reset()

    def normalize_tier(self, tier: str) -> str:
        normalized = (tier or "ultra").strip().lower()
        if normalized not in self.tiers:
            raise KeyError(f"未知 Token Plan 套餐层级: {tier}")
        return normalized

    def get_api_key(self, tier: str) -> str:
        return self.tiers[self.normalize_tier(tier)].api_key

    def get_tier_quota(self, tier: str) -> Dict[str, int]:
        return self.quotas_by_tier[self.normalize_tier(tier)]

    def _default_video_resource_for_tier(self, tier: str) -> str:
        normalized = self.normalize_tier(tier)
        return "video_fast" if normalized == "ultra" else "video_standard"

    def _today_key(self) -> str:
        return datetime.now().strftime("%Y-%m-%d")

    def _load_state(self) -> None:
        if not self.state_file.exists():
            legacy_state_file = self.state_file.parent.parent / "quota_state.json"
            if legacy_state_file.exists():
                try:
                    self.state_file.parent.mkdir(parents=True, exist_ok=True)
                    legacy_state_file.replace(self.state_file)
                except OSError:
                    self.state_file = legacy_state_file

        if not self.state_file.exists():
            return

        try:
            data = json.loads(self.state_file.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as exc:
            logger.warning(f"读取配额状态失败，将使用默认值: {exc}")
            return

        self._last_reset_date = data.get("last_reset_date")

        daily_stats = data.get("daily_stats", {})
        if daily_stats and all(
            isinstance(value, (int, float)) for value in daily_stats.values()
        ):
            self._daily_stats["ultra"]["video_fast"] = int(
                daily_stats.get("video_fast", daily_stats.get("video", 0))
            )
            self._daily_stats["ultra"]["video_standard"] = int(
                daily_stats.get("video_standard", 0)
            )
            for key in ("music", "image", "tts_chars"):
                self._daily_stats["ultra"][key] = int(daily_stats.get(key, 0))
        else:
            for tier in self.tier_order:
                tier_stats = daily_stats.get(tier, {})
                for key in ("video_fast", "video_standard", "music", "image", "tts_chars"):
                    self._daily_stats[tier][key] = int(tier_stats.get(key, 0))
                legacy_video = int(tier_stats.get("video", 0))
                if legacy_video and not (
                    self._daily_stats[tier]["video_fast"]
                    or self._daily_stats[tier]["video_standard"]
                ):
                    self._daily_stats[tier][
                        self._default_video_resource_for_tier(tier)
                    ] = legacy_video

        text_stats = data.get("text_stats", {})
        if text_stats and "requests_in_window" in text_stats:
            self._text_stats["ultra"] = {
                "window_start": float(text_stats.get("window_start", time())),
                "requests_in_window": int(text_stats.get("requests_in_window", 0)),
            }
        else:
            for tier in self.tier_order:
                tier_stats = text_stats.get(tier, {})
                self._text_stats[tier] = {
                    "window_start": float(tier_stats.get("window_start", time())),
                    "requests_in_window": int(
                        tier_stats.get("requests_in_window", 0)
                    ),
                }

        remote_remains = data.get("remote_remains", {})
        for tier in self.tier_order:
            tier_remote = remote_remains.get(tier, {})
            self._remote_remains[tier] = {
                "status": tier_remote.get("status", {}),
                "raw": tier_remote.get("raw"),
                "updated_at": tier_remote.get("updated_at"),
            }

    def _save_state(self) -> None:
        data = {
            "last_reset_date": self._last_reset_date or self._today_key(),
            "daily_stats": self._daily_stats,
            "text_stats": self._text_stats,
            "remote_remains": self._remote_remains,
        }
        try:
            tmp_file = self.state_file.with_name(
                f".{self.state_file.name}.{os.getpid()}.{int(time() * 1000)}.tmp"
            )
            tmp_file.write_text(
                json.dumps(data, ensure_ascii=False, indent=2),
                encoding="utf-8",
            )
            tmp_file.replace(self.state_file)
        except OSError as exc:
            logger.warning(f"写入配额状态失败: {exc}")

    def _check_date_reset(self) -> None:
        today = self._today_key()
        if self._last_reset_date != today:
            for tier in self.tier_order:
                self._daily_stats[tier] = {
                    "video_fast": 0,
                    "video_standard": 0,
                    "music": 0,
                    "image": 0,
                    "tts_chars": 0,
                }
            self._last_reset_date = today
            logger.info("非文本配额已重置（新的一天）")
            self._save_state()

    def _check_text_window_reset(self, tier: Optional[str] = None) -> None:
        tiers = [tier] if tier else list(self.tier_order)
        now = time()
        changed = False
        for current_tier in tiers:
            window_start = float(self._text_stats[current_tier].get("window_start", now))
            if now - window_start > 5 * 3600:
                self._text_stats[current_tier] = {
                    "window_start": now,
                    "requests_in_window": 0,
                }
                changed = True
        if changed:
            logger.info("文本请求配额窗口已重置（5小时滚动）")
            self._save_state()

    def _resource_key(self, resource: str) -> str:
        normalized = resource.lower()
        if normalized == "tts":
            return "tts_chars"
        if normalized == "video":
            return "video_standard"
        return normalized

    def _local_status_for_resource(self, tier: str, resource: str) -> Dict[str, Any]:
        tier = self.normalize_tier(tier)
        self._check_date_reset()
        self._check_text_window_reset(tier)
        quotas = self.get_tier_quota(tier)

        if resource == "text_5h":
            window_start = float(self._text_stats[tier].get("window_start", time()))
            used = int(self._text_stats[tier].get("requests_in_window", 0))
            limit = quotas["text_requests_per_5h"]
            return {
                "used_in_window": used,
                "limit": limit,
                "remaining": max(limit - used, 0),
                "window_seconds_remaining": int(
                    max(0, 5 * 3600 - (time() - window_start))
                ),
                "source": "local",
            }

        if resource == "video":
            fast_status = self._local_status_for_resource(tier, "video_fast")
            standard_status = self._local_status_for_resource(tier, "video_standard")
            return {
                "used": int(fast_status.get("used", 0))
                + int(standard_status.get("used", 0)),
                "limit": int(fast_status.get("limit", 0))
                + int(standard_status.get("limit", 0)),
                "remaining": int(fast_status.get("remaining", 0))
                + int(standard_status.get("remaining", 0)),
                "source": "local",
            }

        resource_key = self._resource_key(resource)
        used = int(self._daily_stats[tier].get(resource_key, 0))
        limit_key = {
            "video_fast": "video_fast_per_day",
            "video_standard": "video_per_day",
            "music": "music_per_day",
            "image": "image_per_day",
            "tts_chars": "tts_chars_per_day",
        }[resource_key]
        limit = quotas[limit_key]
        return {
            "used": used,
            "limit": limit,
            "remaining": max(limit - used, 0),
            "source": "local",
        }

    def _merge_remote_status(
        self, tier: str, resource: str, local_status: Dict[str, Any]
    ) -> Dict[str, Any]:
        remote_status = self._remote_remains.get(tier, {}).get("status", {})
        remote_resource = remote_status.get(resource)
        if not isinstance(remote_resource, dict):
            return local_status
        remote_limit = self._coerce_int(remote_resource.get("limit"))
        local_limit = self._coerce_int(local_status.get("limit"))
        if (
            remote_limit is not None
            and local_limit is not None
            and remote_limit != local_limit
        ):
            logger.info(
                "%s/%s 远端缓存限额 %s 与当前套餐限额 %s 不一致，忽略旧缓存",
                tier,
                resource,
                remote_limit,
                local_limit,
            )
            return local_status

        merged = local_status.copy()
        merged.update({k: v for k, v in remote_resource.items() if v is not None})
        remaining = int(merged.get("remaining", local_status.get("remaining", 0)))
        merged["remaining"] = remaining
        if resource == "text_5h":
            merged["used_in_window"] = max(int(merged["limit"]) - remaining, 0)
            merged["window_seconds_remaining"] = int(
                merged.get(
                    "window_seconds_remaining",
                    local_status.get("window_seconds_remaining", 0),
                )
            )
        else:
            merged["used"] = max(int(merged["limit"]) - remaining, 0)
        merged["source"] = "remote"
        merged["updated_at"] = self._remote_remains.get(tier, {}).get("updated_at")
        return merged

    def get_resource_status(self, tier: str, resource: str) -> Dict[str, Any]:
        local_status = self._local_status_for_resource(tier, resource)
        return self._merge_remote_status(tier, resource, local_status)

    def _check_resource(
        self,
        tier: str,
        resource: str,
        amount: int = 1,
        refresh_remote: bool = False,
    ) -> bool:
        if resource == "video":
            if refresh_remote:
                self.refresh_remote_remains(tier)
            return self._check_resource(
                tier=tier,
                resource="video_fast",
                amount=amount,
                refresh_remote=False,
            ) or self._check_resource(
                tier=tier,
                resource="video_standard",
                amount=amount,
                refresh_remote=False,
            )
        if refresh_remote:
            self.refresh_remote_remains(tier)
        resource_key = "text_5h" if resource == "text" else resource
        status = self.get_resource_status(tier, resource_key)
        return int(status.get("remaining", 0)) >= max(amount, 0)

    def check_resource(
        self,
        resource: str,
        amount: int = 1,
        tier: Optional[str] = None,
        refresh_remote: bool = False,
    ) -> bool:
        with self._lock:
            if tier:
                return self._check_resource(
                    tier=tier,
                    resource=resource,
                    amount=amount,
                    refresh_remote=refresh_remote,
                )

            for current_tier in self.tier_order:
                if not self.get_api_key(current_tier):
                    continue
                if self._check_resource(
                    tier=current_tier,
                    resource=resource,
                    amount=amount,
                    refresh_remote=refresh_remote,
                ):
                    return True
            return False

    def record_usage(self, resource: str, amount: int = 1, tier: str = "ultra") -> None:
        tier = self.normalize_tier(tier)
        amount = max(amount, 0)
        with self._lock:
            if resource == "text":
                self._check_text_window_reset(tier)
                self._text_stats[tier]["requests_in_window"] = int(
                    self._text_stats[tier].get("requests_in_window", 0)
                ) + amount
                remote_key = "text_5h"
            else:
                self._check_date_reset()
                if resource == "video":
                    resource_key = self._default_video_resource_for_tier(tier)
                else:
                    resource_key = self._resource_key(resource)
                self._daily_stats[tier][resource_key] += amount
                if resource_key == "tts_chars":
                    remote_key = "tts"
                elif resource_key in {"video_fast", "video_standard"}:
                    remote_key = resource_key
                else:
                    remote_key = resource_key

            remote_status = self._remote_remains.get(tier, {}).get("status", {})
            if isinstance(remote_status.get(remote_key), dict):
                current_remaining = int(remote_status[remote_key].get("remaining", 0))
                remote_status[remote_key]["remaining"] = max(
                    current_remaining - amount, 0
                )
                remote_status[remote_key]["source"] = "remote-cached"
            if remote_key in {"video_fast", "video_standard"} and isinstance(
                remote_status.get("video"), dict
            ):
                current_video_remaining = int(
                    remote_status["video"].get("remaining", 0)
                )
                remote_status["video"]["remaining"] = max(
                    current_video_remaining - amount,
                    0,
                )
                remote_status["video"]["source"] = "remote-cached"

            self._save_state()

    def _coerce_int(self, value: Any) -> Optional[int]:
        if isinstance(value, bool):
            return None
        if isinstance(value, (int, float)):
            return int(value)
        if isinstance(value, str) and value.strip().isdigit():
            return int(value.strip())
        return None

    def _find_remaining_number(self, node: Any) -> Optional[int]:
        if isinstance(node, dict):
            for key in ("remaining", "remain", "remains", "left", "available"):
                value = self._coerce_int(node.get(key))
                if value is not None:
                    return value
            for value in node.values():
                nested = self._find_remaining_number(value)
                if nested is not None:
                    return nested
        elif isinstance(node, list):
            for item in node:
                nested = self._find_remaining_number(item)
                if nested is not None:
                    return nested
        else:
            return self._coerce_int(node)
        return None

    def _search_remaining(self, node: Any, aliases: List[str]) -> Optional[int]:
        alias_set = [alias.lower() for alias in aliases]
        if isinstance(node, dict):
            for key, value in node.items():
                key_lower = str(key).lower()
                if any(alias in key_lower for alias in alias_set):
                    result = self._find_remaining_number(value)
                    if result is not None:
                        return result
                nested = self._search_remaining(value, aliases)
                if nested is not None:
                    return nested
        elif isinstance(node, list):
            for item in node:
                nested = self._search_remaining(item, aliases)
                if nested is not None:
                    return nested
        return None

    def _normalize_model_remains_payload(
        self, payload: Dict[str, Any], tier: str
    ) -> Dict[str, Dict[str, Any]]:
        entries = payload.get("model_remains")
        if not isinstance(entries, list):
            return {}

        def _pick_entry(
            aliases: List[str],
            *,
            prefer_fast: Optional[bool] = None,
        ) -> Optional[Dict[str, Any]]:
            alias_set = [alias.lower() for alias in aliases]
            matches: List[Dict[str, Any]] = []
            for item in entries:
                if not isinstance(item, dict):
                    continue
                model_name = str(item.get("model_name", "")).lower()
                if any(alias in model_name for alias in alias_set):
                    matches.append(item)

            if not matches:
                return None

            if prefer_fast is None:
                return matches[0]

            preferred = [
                item
                for item in matches
                if ("fast" in str(item.get("model_name", "")).lower()) == prefer_fast
            ]
            return preferred[0] if preferred else matches[0]

        def _build_entry(
            item: Dict[str, Any],
            *,
            fallback_limit: int,
            include_window: bool = False,
        ) -> Optional[Dict[str, Any]]:
            total = self._coerce_int(item.get("current_interval_total_count"))
            remaining = self._coerce_int(
                item.get("current_interval_remaining_count")
            )
            if remaining is None:
                remaining = self._coerce_int(item.get("current_interval_remain_count"))
            if remaining is None:
                remaining = self._coerce_int(item.get("current_interval_usage_count"))
            if total is None or remaining is None:
                return None

            normalized: Dict[str, Any] = {
                "limit": total if total is not None else fallback_limit,
                "remaining": max(min(remaining, total), 0),
                "source": "remote",
            }
            if include_window:
                remains_time = self._coerce_int(item.get("remains_time"))
                normalized["window_seconds_remaining"] = max(
                    int((remains_time or 0) / 1000),
                    0,
                )
            return normalized

        quotas = self.get_tier_quota(tier)
        text_item = _pick_entry(["minimax-m", "m2.7", "m*", "highspeed"])
        tts_item = _pick_entry(["speech", "tts"])
        image_item = _pick_entry(["image-01", "image"])
        music_item = _pick_entry(["music-2.6", "music-2.5", "music"])
        video_fast_item = _pick_entry(
            ["hailuo-2.3-fast", "hailuo-2.3-fast-6s-768p", "video-fast"],
            prefer_fast=True,
        )
        video_standard_item = _pick_entry(
            ["hailuo-2.3-6s-768p", "hailuo-2.3", "video-standard"],
            prefer_fast=False,
        )

        normalized: Dict[str, Dict[str, Any]] = {}
        candidates = {
            "text_5h": (
                text_item,
                quotas["text_requests_per_5h"],
                True,
            ),
            "tts": (
                tts_item,
                quotas["tts_chars_per_day"],
                False,
            ),
            "image": (
                image_item,
                quotas["image_per_day"],
                False,
            ),
            "music": (
                music_item,
                quotas["music_per_day"],
                False,
            ),
            "video_fast": (
                video_fast_item,
                quotas["video_fast_per_day"],
                False,
            ),
            "video_standard": (
                video_standard_item,
                quotas["video_per_day"],
                False,
            ),
        }
        for resource, (item, fallback_limit, include_window) in candidates.items():
            if not item:
                continue
            entry = _build_entry(
                item,
                fallback_limit=fallback_limit,
                include_window=include_window,
            )
            if entry:
                normalized[resource] = entry

        if normalized.get("video_fast") or normalized.get("video_standard"):
            fast_entry = normalized.get(
                "video_fast",
                {
                    "limit": quotas["video_fast_per_day"],
                    "remaining": quotas["video_fast_per_day"],
                    "source": "remote",
                },
            )
            standard_entry = normalized.get(
                "video_standard",
                {
                    "limit": quotas["video_per_day"],
                    "remaining": quotas["video_per_day"],
                    "source": "remote",
                },
            )
            normalized["video"] = {
                "limit": int(fast_entry.get("limit", 0))
                + int(standard_entry.get("limit", 0)),
                "remaining": int(fast_entry.get("remaining", 0))
                + int(standard_entry.get("remaining", 0)),
                "source": "remote",
            }

        return normalized

    def _normalize_remote_remains_payload(
        self, payload: Dict[str, Any], tier: str
    ) -> Dict[str, Dict[str, Any]]:
        if not isinstance(payload, dict):
            return {}

        base_resp = payload.get("base_resp")
        if isinstance(base_resp, dict):
            status_code = int(base_resp.get("status_code", 0) or 0)
            if status_code not in {0, 200}:
                return {}

        normalized_from_models = self._normalize_model_remains_payload(payload, tier)
        if normalized_from_models:
            return normalized_from_models

        root = payload.get("data") if isinstance(payload.get("data"), dict) else payload
        quotas = self.get_tier_quota(tier)
        aliases = {
            "text_5h": [
                "text",
                "m2.7",
                "m2_7",
                "m2-7",
                "highspeed",
                "minimax-m2.7",
            ],
            "tts": ["tts", "speech"],
            "image": ["image"],
            "music": ["music"],
            "video_fast": [
                "hailuo-2.3-fast",
                "hailuo_2_3_fast",
                "minimax-hailuo-2.3-fast",
            ],
            "video_standard": [
                "hailuo-2.3",
                "hailuo_2_3",
                "minimax-hailuo-2.3",
            ],
            "video": ["video", "hailuo"],
        }
        limit_map = {
            "text_5h": quotas["text_requests_per_5h"],
            "tts": quotas["tts_chars_per_day"],
            "image": quotas["image_per_day"],
            "music": quotas["music_per_day"],
            "video_fast": quotas["video_fast_per_day"],
            "video_standard": quotas["video_per_day"],
            "video": quotas["video_per_day"],
        }

        normalized: Dict[str, Dict[str, Any]] = {}
        for resource, resource_aliases in aliases.items():
            remaining = self._search_remaining(root, resource_aliases)
            if remaining is None:
                continue
            entry: Dict[str, Any] = {
                "limit": limit_map[resource],
                "remaining": max(remaining, 0),
                "source": "remote",
            }
            if resource == "text_5h":
                entry["window_seconds_remaining"] = self._local_status_for_resource(
                    tier, "text_5h"
                )["window_seconds_remaining"]
            normalized[resource] = entry

        return normalized

    def refresh_remote_remains(
        self, tier: str, timeout: float = 5.0
    ) -> Optional[Dict[str, Dict[str, Any]]]:
        tier = self.normalize_tier(tier)
        api_key = self.get_api_key(tier)
        if not api_key:
            return None

        result_queue: Queue[tuple[str, Any]] = Queue(maxsize=1)

        def _worker() -> None:
            connect_timeout = max(min(timeout, 3.0), 0.5)
            read_timeout = max(timeout, 0.5)
            try:
                response = requests.get(
                    self.remains_url,
                    headers={
                        "Authorization": f"Bearer {api_key}",
                        "Content-Type": "application/json",
                    },
                    timeout=(connect_timeout, read_timeout),
                )
                response.raise_for_status()
                result_queue.put(("ok", response.json()))
            except Exception as exc:
                result_queue.put(("error", exc))

        thread = Thread(
            target=_worker,
            name=f"token-plan-remains-{tier}",
            daemon=True,
        )
        thread.start()
        thread.join(timeout + 0.1)
        if thread.is_alive():
            logger.warning(f"刷新 {tier} remains 超时未返回，继续使用本地配额状态")
            return None

        try:
            status, payload_or_error = result_queue.get_nowait()
        except Empty:
            logger.warning(f"刷新 {tier} remains 未返回结果，继续使用本地配额状态")
            return None

        if status != "ok":
            logger.warning(
                f"刷新 {tier} remains 失败，继续使用本地配额状态: {payload_or_error}"
            )
            return None

        payload = payload_or_error

        normalized = self._normalize_remote_remains_payload(payload, tier)
        if not normalized:
            logger.warning(f"刷新 {tier} remains 返回空结果，继续保留上一份有效状态")
            return None
        with self._lock:
            self._remote_remains[tier] = {
                "status": normalized,
                "raw": payload,
                "updated_at": datetime.now().isoformat(),
            }
            self._save_state()
        return normalized

    def get_status(self) -> Dict[str, Any]:
        with self._lock:
            self._check_date_reset()
            self._check_text_window_reset()

            tiers_status = {
                tier: {
                    "video_fast": self.get_resource_status(tier, "video_fast"),
                    "video_standard": self.get_resource_status(tier, "video_standard"),
                    "video": self.get_resource_status(tier, "video"),
                    "music": self.get_resource_status(tier, "music"),
                    "image": self.get_resource_status(tier, "image"),
                    "tts": self.get_resource_status(tier, "tts"),
                    "text_5h": self.get_resource_status(tier, "text_5h"),
                    "enabled": bool(self.get_api_key(tier)),
                    "label": self.tiers[tier].label,
                }
                for tier in self.tier_order
            }

            def _aggregate(resource: str) -> Dict[str, Any]:
                active = [
                    tiers_status[tier][resource]
                    for tier in self.tier_order
                    if tiers_status[tier]["enabled"]
                ]
                if not active:
                    aggregated: Dict[str, Any] = {
                        "remaining": 0,
                        "limit": 0,
                        "available_tiers": [],
                    }
                    if resource == "text_5h":
                        aggregated["used_in_window"] = 0
                        aggregated["window_seconds_remaining"] = 0
                    else:
                        aggregated["used"] = 0
                    return aggregated

                remaining = sum(int(item.get("remaining", 0)) for item in active)
                limit = sum(int(item.get("limit", 0)) for item in active)
                aggregated: Dict[str, Any] = {
                    "limit": limit,
                    "remaining": remaining,
                    "available_tiers": [
                        tier
                        for tier in self.tier_order
                        if tiers_status[tier]["enabled"]
                        and int(tiers_status[tier][resource].get("remaining", 0)) > 0
                    ],
                }
                if resource == "text_5h":
                    aggregated["used_in_window"] = max(limit - remaining, 0)
                    aggregated["window_seconds_remaining"] = min(
                        int(item.get("window_seconds_remaining", 0)) for item in active
                    )
                else:
                    aggregated["used"] = max(limit - remaining, 0)
                return aggregated

            return {
                "date": self._today_key(),
                "video_fast": _aggregate("video_fast"),
                "video_standard": _aggregate("video_standard"),
                "video": _aggregate("video"),
                "music": _aggregate("music"),
                "image": _aggregate("image"),
                "tts": _aggregate("tts"),
                "text_5h": _aggregate("text_5h"),
                "tiers": tiers_status,
            }
