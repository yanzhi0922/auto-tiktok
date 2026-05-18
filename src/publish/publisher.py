# -*- coding: utf-8 -*-
"""发布链路：手动导出与 TikTok Content Posting API 适配。"""

from __future__ import annotations

import json
import mimetypes
import os
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, Optional

import requests

from src.pipeline.video_plan import VideoPlan
from src.utils.redaction import redact_obj


TIKTOK_API_BASE = "https://open.tiktokapis.com"
TIKTOK_INBOX_INIT = "/v2/post/publish/inbox/video/init/"
TIKTOK_DIRECT_INIT = "/v2/post/publish/video/init/"
TIKTOK_STATUS_FETCH = "/v2/post/publish/status/fetch/"
MIN_TIKTOK_CHUNK_SIZE = 5 * 1024 * 1024
MAX_TIKTOK_CHUNK_SIZE = 64 * 1024 * 1024


def _now() -> str:
    return datetime.now().isoformat()


def _load_plan(plan_path: str | Path) -> VideoPlan:
    return VideoPlan.load(plan_path)


def _first_existing(*paths: Optional[str]) -> Optional[Path]:
    for value in paths:
        if not value:
            continue
        path = Path(value)
        if path.exists():
            return path
    return None


def _chunk_plan(size: int) -> tuple[int, int]:
    if size <= 0:
        raise ValueError("视频文件为空，无法发布")
    if size < MIN_TIKTOK_CHUNK_SIZE:
        return size, 1
    total_chunk_count = max(1, (size + MAX_TIKTOK_CHUNK_SIZE - 1) // MAX_TIKTOK_CHUNK_SIZE)
    chunk_size = size // total_chunk_count
    if chunk_size < MIN_TIKTOK_CHUNK_SIZE:
        raise ValueError("视频分片小于 TikTok 最小分片限制")
    return chunk_size, total_chunk_count


def build_publish_metadata(plan: VideoPlan) -> Dict[str, Any]:
    title = (plan.titles[0] if plan.titles else plan.topic).strip()
    hashtags = [tag for tag in plan.hashtags if isinstance(tag, str)]
    caption_parts = [title]
    if hashtags:
        caption_parts.append(" ".join(hashtags))
    caption = "\n".join(part for part in caption_parts if part).strip()[:2200]

    final_asset = plan.assets.get("final_video")
    video_asset = plan.assets.get("video")
    cover_asset = plan.assets.get("cover") or plan.assets.get("thumbnail")
    video_path = _first_existing(
        final_asset.path if final_asset else None,
        video_asset.path if video_asset else None,
    )
    cover_path = _first_existing(cover_asset.path if cover_asset else None)
    if not video_path:
        raise FileNotFoundError("没有可发布的视频资产")

    return {
        "topic": plan.topic,
        "content_type": plan.content_type,
        "caption": caption,
        "title": title,
        "hashtags": hashtags,
        "video_path": str(video_path),
        "cover_path": str(cover_path) if cover_path else None,
        "plan_path": str(Path(plan.content_dir or ".") / "video_plan.json"),
    }


class ManualExportPublisher:
    """生成发布包，不调用任何第三方平台。"""

    def publish(self, *, plan_path: str | Path) -> Dict[str, Any]:
        plan = _load_plan(plan_path)
        metadata = build_publish_metadata(plan)
        content_dir = Path(plan.content_dir or Path(plan_path).parent)
        package_dir = content_dir / "publish"
        package_dir.mkdir(parents=True, exist_ok=True)
        payload = {
            "provider": "manual",
            "status": "draft_ready",
            "created_at": _now(),
            "metadata": metadata,
            "next_steps": [
                "人工检查视频、封面、标题和话题标签",
                "复制 caption 到平台发布页",
                "上传 video_path 对应视频并选择 cover_path 对应封面",
            ],
        }
        output_path = package_dir / "publish_package.json"
        output_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
        return {"status": "draft_ready", "package_path": str(output_path), "metadata": metadata}


class TikTokContentPostingPublisher:
    """TikTok 官方 Content Posting API。"""

    def __init__(
        self,
        *,
        access_token: Optional[str] = None,
        api_base: str = TIKTOK_API_BASE,
        mode: Optional[str] = None,
        timeout: float = 60.0,
    ):
        self.access_token = access_token or os.getenv("TIKTOK_ACCESS_TOKEN", "")
        self.api_base = api_base.rstrip("/")
        self.mode = (mode or os.getenv("TIKTOK_POST_MODE", "inbox")).strip().lower()
        self.timeout = timeout
        if self.mode not in {"inbox", "direct"}:
            raise ValueError("TIKTOK_POST_MODE 只支持 inbox 或 direct")

    def _headers(self) -> Dict[str, str]:
        if not self.access_token:
            raise RuntimeError("缺少 TIKTOK_ACCESS_TOKEN，无法调用 TikTok 官方发布 API")
        return {
            "Authorization": f"Bearer {self.access_token}",
            "Content-Type": "application/json; charset=UTF-8",
        }

    def publish(self, *, plan_path: str | Path) -> Dict[str, Any]:
        plan = _load_plan(plan_path)
        metadata = build_publish_metadata(plan)
        video_path = Path(metadata["video_path"])
        init_payload = self._build_init_payload(metadata=metadata, video_path=video_path)
        endpoint = TIKTOK_DIRECT_INIT if self.mode == "direct" else TIKTOK_INBOX_INIT

        response = requests.post(
            f"{self.api_base}{endpoint}",
            headers=self._headers(),
            json=init_payload,
            timeout=self.timeout,
        )
        response.raise_for_status()
        init_result = response.json()
        error = init_result.get("error") or {}
        if error.get("code") not in {None, "ok"}:
            raise RuntimeError(f"TikTok 初始化失败: {redact_obj(error)}")

        data = init_result.get("data") or {}
        upload_url = data.get("upload_url")
        publish_id = data.get("publish_id")
        if upload_url:
            self._upload_file(upload_url=upload_url, video_path=video_path)

        result = {
            "provider": "tiktok",
            "mode": self.mode,
            "status": "uploaded",
            "publish_id": publish_id,
            "created_at": _now(),
            "metadata": metadata,
            "init_result": redact_obj(init_result),
        }
        status = self.fetch_status(publish_id) if publish_id else None
        if status:
            result["status_result"] = redact_obj(status)
        self._write_status(plan_path=plan_path, result=result)
        return result

    def fetch_status(self, publish_id: str) -> Dict[str, Any]:
        response = requests.post(
            f"{self.api_base}{TIKTOK_STATUS_FETCH}",
            headers=self._headers(),
            json={"publish_id": publish_id},
            timeout=self.timeout,
        )
        response.raise_for_status()
        return response.json()

    def _build_init_payload(self, *, metadata: Dict[str, Any], video_path: Path) -> Dict[str, Any]:
        size = video_path.stat().st_size
        chunk_size, total_chunk_count = _chunk_plan(size)
        source_info = {
            "source": "FILE_UPLOAD",
            "video_size": size,
            "chunk_size": chunk_size,
            "total_chunk_count": total_chunk_count,
        }
        if self.mode == "inbox":
            return {"source_info": source_info}

        return {
            "post_info": {
                "title": metadata["caption"],
                "privacy_level": os.getenv("TIKTOK_PRIVACY_LEVEL", "SELF_ONLY"),
                "disable_duet": os.getenv("TIKTOK_DISABLE_DUET", "false").lower() == "true",
                "disable_comment": os.getenv("TIKTOK_DISABLE_COMMENT", "false").lower() == "true",
                "disable_stitch": os.getenv("TIKTOK_DISABLE_STITCH", "false").lower() == "true",
                "video_cover_timestamp_ms": int(os.getenv("TIKTOK_COVER_TIMESTAMP_MS", "1000")),
            },
            "source_info": source_info,
        }

    def _upload_file(self, *, upload_url: str, video_path: Path) -> None:
        size = video_path.stat().st_size
        chunk_size, total_chunk_count = _chunk_plan(size)
        content_type = mimetypes.guess_type(video_path.name)[0] or "video/mp4"
        with video_path.open("rb") as file:
            start = 0
            for chunk_index in range(total_chunk_count):
                read_size = chunk_size if chunk_index < total_chunk_count - 1 else size - start
                chunk = file.read(read_size)
                if not chunk:
                    break
                end = start + len(chunk) - 1
                response = requests.put(
                    upload_url,
                    data=chunk,
                    headers={
                        "Content-Type": content_type,
                        "Content-Length": str(len(chunk)),
                        "Content-Range": f"bytes {start}-{end}/{size}",
                    },
                    timeout=max(self.timeout, 300.0),
                )
                response.raise_for_status()
                start = end + 1

    def _write_status(self, *, plan_path: str | Path, result: Dict[str, Any]) -> None:
        content_dir = Path(plan_path).parent
        publish_dir = content_dir / "publish"
        publish_dir.mkdir(parents=True, exist_ok=True)
        (publish_dir / "tiktok_publish_status.json").write_text(
            json.dumps(redact_obj(result), ensure_ascii=False, indent=2),
            encoding="utf-8",
        )


class PublisherService:
    def publish(self, *, plan_path: str | Path, provider: str = "manual") -> Dict[str, Any]:
        provider = (provider or "manual").strip().lower()
        if provider == "manual":
            return ManualExportPublisher().publish(plan_path=plan_path)
        if provider == "tiktok":
            return TikTokContentPostingPublisher().publish(plan_path=plan_path)
        raise ValueError(f"未知发布 provider: {provider}")
