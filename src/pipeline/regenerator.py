# -*- coding: utf-8 -*-
"""
基于 video_plan.json 的单资产重生成服务。

Dashboard 和命令行可以复用这里的能力。所有高成本动作都必须显式调用，
模块本身不会后台自动重试。
"""

from __future__ import annotations

from pathlib import Path
from typing import Any, Dict, Optional

from config.settings import get_settings
from src.api import ImageAPI, MusicAPI, SpeechAPI, TextAPI, VideoAPI
from src.pipeline.video_plan import VideoPlan
from src.video_editor import SubtitleGenerator, VideoComposer


class AssetRegenerationService:
    """按 video_plan 重生成单个资产。"""

    def __init__(self, output_dir: str | Path = "output"):
        self.output_dir = Path(output_dir).resolve()
        self.settings = get_settings()

    def _resolve_plan_path(
        self,
        *,
        plan_path: Optional[str] = None,
        content_dir: Optional[str] = None,
    ) -> Path:
        if plan_path:
            candidate = Path(plan_path)
        elif content_dir:
            candidate = Path(content_dir) / "video_plan.json"
        else:
            raise ValueError("必须提供 plan_path 或 content_dir")

        resolved = candidate.resolve()
        if not resolved.exists():
            raise FileNotFoundError(f"video_plan 不存在: {resolved}")
        return resolved

    def _ensure_inside_output(self, path: Path) -> None:
        try:
            path.resolve().relative_to(self.output_dir)
        except ValueError as exc:
            raise ValueError(f"拒绝访问输出目录外的路径: {path}") from exc

    def regenerate(
        self,
        *,
        asset: str,
        plan_path: Optional[str] = None,
        content_dir: Optional[str] = None,
    ) -> Dict[str, Any]:
        resolved_plan_path = self._resolve_plan_path(
            plan_path=plan_path,
            content_dir=content_dir,
        )
        self._ensure_inside_output(resolved_plan_path)
        plan = VideoPlan.load(resolved_plan_path)
        resolved_content_dir = Path(plan.content_dir or resolved_plan_path.parent)
        self._ensure_inside_output(resolved_content_dir)

        asset = asset.strip().lower()
        handlers = {
            "script": self._regenerate_script,
            "titles": self._regenerate_titles,
            "tts": self._regenerate_tts,
            "audio": self._regenerate_tts,
            "thumbnail": self._regenerate_thumbnail,
            "cover": self._regenerate_cover,
            "video": self._regenerate_video,
            "subtitle": self._regenerate_subtitle,
            "compose": self._regenerate_compose,
            "final_video": self._regenerate_compose,
            "music": self._regenerate_music,
        }
        if asset not in handlers:
            raise ValueError(f"不支持重生成资产: {asset}")

        result = handlers[asset](plan, resolved_content_dir)
        plan.save(resolved_plan_path)
        return {
            "asset": asset,
            "plan_path": str(resolved_plan_path),
            "result": result,
        }

    def _regenerate_script(self, plan: VideoPlan, content_dir: Path) -> Dict[str, Any]:
        api = TextAPI()
        try:
            script = api.generate_script(
                topic=plan.topic,
                style=plan.style or plan.content_type or "短视频",
                duration=plan.duration,
            )
            plan.script.update(script)
            plan.record_call("script", api.last_request_metadata)
            output_path = content_dir / "script.json"
            output_path.write_text(
                __import__("json").dumps(script, ensure_ascii=False, indent=2),
                encoding="utf-8",
            )
            plan.record_asset("script", output_path)
            return {"path": str(output_path), "metadata": api.last_request_metadata}
        finally:
            api.close()

    def _regenerate_titles(self, plan: VideoPlan, content_dir: Path) -> Dict[str, Any]:
        api = TextAPI()
        try:
            titles = api.generate_titles(
                topic=plan.topic,
                content_type=plan.content_type or "短视频",
                count=5,
            )
            plan.titles = titles
            plan.record_call("titles", api.last_request_metadata)
            output_path = content_dir / "titles.json"
            output_path.write_text(
                __import__("json").dumps({"titles": titles}, ensure_ascii=False, indent=2),
                encoding="utf-8",
            )
            plan.record_asset("titles", output_path)
            return {"path": str(output_path), "titles": titles}
        finally:
            api.close()

    def _regenerate_tts(self, plan: VideoPlan, content_dir: Path) -> Dict[str, Any]:
        narration = str(plan.script.get("narration") or "").strip()
        if not narration:
            raise ValueError("video_plan.script.narration 为空，无法重生成语音")

        api = SpeechAPI()
        try:
            output_path = content_dir / f"{plan.topic[:30] or 'audio'}.mp3"
            audio_path = api.synthesize_to_file(
                text=narration,
                output_path=str(output_path),
                voice_id=plan.voice or self.settings.auto.content_strategy.default_voice,
            )
            plan.record_call("tts", api.last_request_metadata)
            plan.record_asset("audio", audio_path, source_stage="tts")
            return {"path": str(audio_path), "metadata": api.last_request_metadata}
        finally:
            api.close()

    def _regenerate_thumbnail(self, plan: VideoPlan, content_dir: Path) -> Dict[str, Any]:
        prompt = (
            str(plan.cover.get("prompt") or "").strip()
            or str(plan.script.get("video_description") or "").strip()
            or f"{plan.topic}, {plan.content_type or ''}, vertical 9:16 short video cover"
        )
        api = ImageAPI()
        try:
            output_path = content_dir / "cover.jpg"
            thumbnail_path = api.create_thumbnail(prompt=prompt, output_path=str(output_path))
            plan.cover.update({"prompt": prompt, "path": str(thumbnail_path), "source": "image"})
            plan.record_call("thumbnail", api.last_request_metadata, prompt=prompt)
            plan.record_asset("thumbnail", thumbnail_path, source_stage="thumbnail")
            return {"path": str(thumbnail_path), "metadata": api.last_request_metadata}
        finally:
            api.close()

    def _regenerate_cover(self, plan: VideoPlan, content_dir: Path) -> Dict[str, Any]:
        video_asset = plan.assets.get("final_video") or plan.assets.get("video")
        video_path = Path(video_asset.path) if video_asset and video_asset.path else None
        if not video_path or not video_path.exists():
            return self._regenerate_thumbnail(plan, content_dir)

        thumbnail_asset = plan.assets.get("thumbnail")
        thumbnail_path = (
            Path(thumbnail_asset.path)
            if thumbnail_asset and thumbnail_asset.path and Path(thumbnail_asset.path).exists()
            else None
        )
        composer = VideoComposer()
        cover_path = composer.set_video_cover(
            video_path=str(video_path),
            thumbnail_path=str(thumbnail_path) if thumbnail_path else None,
            output_path=str(content_dir / "cover.jpg"),
        )
        plan.record_asset("cover", cover_path, source_stage="cover")
        plan.cover.update({"path": str(cover_path)})
        return {"path": str(cover_path)}

    def _regenerate_video(self, plan: VideoPlan, content_dir: Path) -> Dict[str, Any]:
        prompt = (
            plan.scenes[0].prompt
            if plan.scenes
            else str(plan.script.get("video_description") or "").strip()
        )
        if not prompt:
            raise ValueError("video_plan 中没有可用于视频生成的 prompt")

        api = VideoAPI()
        try:
            thumbnail_asset = plan.assets.get("thumbnail")
            output_path = content_dir / f"{plan.topic[:30] or 'video'}.mp4"
            if thumbnail_asset and thumbnail_asset.path and Path(thumbnail_asset.path).exists():
                video_path = api.generate_video_from_image(
                    prompt=prompt,
                    first_frame_image=thumbnail_asset.path,
                    output_path=str(output_path),
                    model=self.settings.models.video_model_fast,
                    duration=plan.duration,
                    resolution="768P",
                )
            else:
                video_path = api.generate_video(
                    prompt=prompt,
                    output_path=str(output_path),
                    model=self.settings.models.video_model,
                    duration=plan.duration,
                    resolution="768P",
                )
            plan.record_call("video", api.last_request_metadata, prompt=prompt)
            plan.record_asset("video", video_path, source_stage="video")
            return {"path": str(video_path), "metadata": api.last_request_metadata}
        finally:
            api.close()

    def _regenerate_subtitle(self, plan: VideoPlan, content_dir: Path) -> Dict[str, Any]:
        narration = str(plan.script.get("narration") or "").strip()
        audio_asset = plan.assets.get("audio")
        audio_path = Path(audio_asset.path) if audio_asset and audio_asset.path else None
        output_path = content_dir / "subtitle.srt"
        generator = SubtitleGenerator()
        if audio_path and audio_path.exists():
            srt_path = generator.generate_srt_from_audio(
                audio_path=str(audio_path),
                text_fallback=narration,
                output_path=str(output_path),
                engine=str(plan.subtitles.get("engine") or "estimate"),
            )
        else:
            srt_path = generator.generate_srt(
                text=narration,
                output_path=str(output_path),
            )
        plan.subtitles["path"] = str(srt_path)
        plan.record_asset("subtitle", srt_path, source_stage="subtitle")
        return {"path": str(srt_path)}

    def _regenerate_compose(self, plan: VideoPlan, content_dir: Path) -> Dict[str, Any]:
        video_asset = plan.assets.get("video")
        audio_asset = plan.assets.get("audio")
        music_asset = plan.assets.get("music")
        subtitle_asset = plan.assets.get("subtitle")
        if not video_asset or not video_asset.path:
            raise ValueError("缺少 video 资产，无法合成最终视频")

        composer = VideoComposer()
        final_path = composer.compose_with_voice_mixing(
            video_path=video_asset.path,
            audio_path=audio_asset.path if audio_asset and audio_asset.path else "",
            music_path=music_asset.path if music_asset and music_asset.path else None,
            srt_path=subtitle_asset.path if subtitle_asset and subtitle_asset.path else None,
            output_path=str(content_dir / "final.mp4"),
        )
        plan.record_asset("final_video", final_path, source_stage="compose")
        return {"path": str(final_path)}

    def _regenerate_music(self, plan: VideoPlan, content_dir: Path) -> Dict[str, Any]:
        if not self.settings.models.supports_music_instrumental():
            plan.record_asset(
                "music",
                status="skipped",
                source_stage="music",
                reason="Token Plan 不支持纯音乐背景音乐",
            )
            return {"status": "skipped", "reason": "Token Plan 不支持纯音乐背景音乐"}

        api = MusicAPI()
        try:
            output_path = content_dir / "music.mp3"
            music_path = api.generate_instrumental(
                prompt=plan.content_type or plan.topic,
                output_path=str(output_path),
            )
            plan.record_call("music", api.last_request_metadata)
            plan.record_asset("music", music_path, source_stage="music")
            return {"path": str(music_path), "metadata": api.last_request_metadata}
        finally:
            api.close()
