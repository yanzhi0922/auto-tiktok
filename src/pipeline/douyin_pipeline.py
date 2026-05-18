# -*- coding: utf-8 -*-
"""
抖音专属 Pipeline
专门针对抖音平台优化的内容生产流水线
"""

import logging
from typing import Optional, Dict, Any, List
from pathlib import Path
from datetime import datetime

from src.pipeline.orchestrator import (
    PipelineOrchestrator,
    ContentPack,
    QuotaExceededError,
)
from src.strategy.douyin_strategy import DouyinContentStrategy
from src.strategy.viral_script_generator import ViralScriptGenerator
from src.video_editor import SubtitleGenerator, VideoComposer
from src.utils.file_manager import FileManager


logger = logging.getLogger(__name__)


class DouyinContentPack(ContentPack):
    """抖音专属内容包"""

    def __init__(self, topic: str):
        super().__init__(topic)

        # 抖音专属字段
        self.hook: Optional[str] = None  # 黄金3秒开头
        self.cta: Optional[str] = None  # 行动号召
        self.engagement_question: Optional[str] = None  # 互动问题
        self.viral_score: Optional[Dict[str, Any]] = None  # 爆款评分
        self.content_type: Optional[str] = None  # 内容类型
        self.best_post_time: Optional[str] = None  # 最佳发布时间
        self.hashtags: List[str] = []  # 话题标签
        self.hook_type_used: Optional[str] = None  # 实际采用的开头策略

        # 最终成品字段（合成后填充）
        self.final_video_path: Optional[Path] = None  # 合成后的最终视频
        self.cover_path: Optional[Path] = None  # 视频封面
        self.quality_gate_passed: Optional[bool] = None

    def to_dict(self) -> Dict[str, Any]:
        """转换为字典"""
        base_dict = super().to_dict()
        base_dict.update(
            {
                "hook": self.hook,
                "cta": self.cta,
                "engagement_question": self.engagement_question,
                "viral_score": self.viral_score,
                "content_type": self.content_type,
                "best_post_time": self.best_post_time,
                "hashtags": self.hashtags,
                "hook_type_used": self.hook_type_used,
                "final_video_path": str(self.final_video_path)
                if self.final_video_path
                else None,
                "cover_path": str(self.cover_path) if self.cover_path else None,
            }
        )
        return base_dict


class DouyinPipeline(PipelineOrchestrator):
    """抖音专属 Pipeline"""

    def __init__(
        self,
        output_dir: str = "output",
        file_manager: Optional[FileManager] = None,
    ):
        """
        初始化抖音 Pipeline

        Args:
            output_dir: 输出目录
        """
        super().__init__(output_dir, file_manager=file_manager)
        self.strategy = DouyinContentStrategy()
        self.viral_gen = ViralScriptGenerator(self.text_api)
        self.subtitle_gen = SubtitleGenerator()
        self.composer = VideoComposer()

        logger.info("抖音 Pipeline 初始化完成")

    def _build_video_seed_prompt(
        self,
        *,
        topic: str,
        video_prompt: str,
        style: Optional[str] = None,
        content_type: Optional[str] = None,
    ) -> str:
        enriched_prompt = self._enhance_video_prompt(
            video_prompt,
            style=style,
            content_type=content_type,
        )
        prompt_parts = [
            topic,
            content_type or "",
            "Douyin vertical first frame",
            "eye-catching mobile cover image, immediate visual hook, premium creator aesthetic",
            enriched_prompt,
        ]
        return ", ".join(part for part in prompt_parts if part)

    def generate_douyin_content(
        self,
        topic: str,
        content_type: str = "生活技巧",
        duration: int = 6,
        voice: Optional[str] = None,
        generate_video: bool = True,
        generate_music: bool = True,
        generate_thumbnail: bool = True,
        pack_index: int = 1,
        min_score_threshold: Optional[int] = None,
        script_max_attempts: int = 3,
        script_accept_score: Optional[int] = None,
        **kwargs,
    ) -> DouyinContentPack:
        """
        生成抖音专属内容包

        所有输出保存到 output/YYYY-MM-DD/run_<run_id>/NNN/ 目录：
        NNN/
        ├── script.json            # 完整脚本数据
        ├── titles.json            # 备选标题
        ├── score.json             # 爆款评分
        ├── content_manifest.json  # 内容级 manifest
        ├── audio.mp3              # 语音旁白
        ├── video.mp4              # AI 生成视频
        ├── music.mp3              # 背景音乐
        ├── subtitle.srt           # 字幕文件
        └── cover.jpg              # 视频封面

        Args:
            topic: 内容主题
            content_type: 内容类型
            duration: 视频时长（秒）
            voice: 语音音色
            generate_video: 是否生成视频
            generate_music: 是否生成音乐
            generate_thumbnail: 是否生成缩略图
            pack_index: 内容序号（1-5），决定保存到哪个三位编号目录

        Returns:
            抖音内容包
        """
        logger.info(f"开始生成抖音内容: {topic} ({content_type})")
        resolved_voice = voice or self.settings.auto.content_strategy.default_voice

        pack = DouyinContentPack(topic=topic)
        pack.content_type = content_type

        content_index, content_dir = self.file_manager.reserve_content_slot(pack_index)
        pack.content_index = content_index
        pack.content_dir = content_dir
        topic_prefix = self.file_manager.sanitize_component(topic)
        logger.info(f"  内容保存目录: {content_dir}")
        self._create_video_plan_for_pack(
            pack,
            platform="douyin",
            duration=duration,
            voice=resolved_voice,
            content_type=content_type,
            generate_video=generate_video,
            generate_music=generate_music,
            generate_thumbnail=generate_thumbnail,
        )

        def save_json(filename: str, data: dict):
            p = content_dir / filename
            self.file_manager.write_json_to_path(p, data)
            logger.debug(f"  已保存: {p.name}")

        try:
            # 1. 生成爆款脚本
            logger.info("1. 生成爆款脚本（AI驱动）...")
            viral_script = self._generate_viral_script_with_retry(
                topic=topic,
                content_type=content_type,
                duration=duration,
                max_attempts=script_max_attempts,
                early_accept_score=script_accept_score,
            )
            script_request_metadata = dict(viral_script.get("request_metadata") or {})
            if script_request_metadata:
                script_request_metadata["selected_hook_type"] = viral_script.get(
                    "selected_hook_type"
                )
                script_request_metadata["candidate_count"] = len(
                    viral_script.get("candidate_scores", [])
                )
                pack.apply_generation_metadata("script", script_request_metadata)

            pack.hook = viral_script.get("hook", "")
            pack.narration = viral_script.get("narration", "")
            pack.video_description = viral_script.get("video_description", "")
            pack.engagement_question = viral_script.get("engagement_question", "")
            pack.cta = viral_script.get("cta", "")
            pack.hashtags = viral_script.get("hashtags", [])
            pack.script = viral_script.get("raw_content", "")
            pack.hook_type_used = viral_script.get("selected_hook_type")

            for warning in viral_script.get("quality_warnings", []):
                logger.warning(f"  WARNING: {warning}")

            script_selection = {
                "selected_hook_type": viral_script.get("selected_hook_type"),
                "candidate_scores": viral_script.get("candidate_scores", []),
                "score_target": viral_script.get("score_target"),
            }
            pack.generation_metadata["script_selection"] = script_selection
            self._sync_video_plan_for_pack(pack)

            # 2. 评分
            logger.info("2. 计算爆款评分...")
            score_data = dict(
                viral_script.get("precomputed_score")
                or self.viral_gen.calculate_content_score(
                    {
                        "hook": pack.hook,
                        "narration": pack.narration,
                        "engagement_question": pack.engagement_question,
                        "cta": pack.cta,
                        "hashtags": pack.hashtags,
                    }
                )
            )
            pack.viral_score = score_data
            logger.info(
                f"  爆款评分: {score_data['score']}/100 ({score_data['level']} {score_data['level_desc']})"
            )

            save_json(
                "script.json",
                {
                    "topic": topic,
                    "content_type": content_type,
                    "hook": pack.hook,
                    "narration": pack.narration,
                    "video_description": pack.video_description,
                    "engagement_question": pack.engagement_question,
                    "cta": pack.cta,
                    "hashtags": pack.hashtags,
                    "raw_content": pack.script,
                    "selected_hook_type": viral_script.get("selected_hook_type"),
                    "candidate_scores": viral_script.get("candidate_scores", []),
                },
            )
            save_json(
                "score.json",
                {
                    **score_data,
                    "selected_hook_type": viral_script.get("selected_hook_type"),
                    "candidate_scores": viral_script.get("candidate_scores", []),
                },
            )
            self._sync_video_plan_for_pack(pack)

            # 3. 生成标题
            logger.info("3. 生成爆款标题...")
            try:
                titles = self.text_api.generate_titles(
                    topic=topic,
                    content_type=content_type,
                    count=5,
                )
                all_titles = titles + (
                    [viral_script.get("hook", "")] if viral_script.get("hook") else []
                )
                pack.titles = all_titles[:5]
                pack.apply_generation_metadata("titles", self.text_api.last_request_metadata)
            except Exception as e:
                logger.warning(f"  标题生成失败: {e}")
                pack.titles = [pack.hook] if pack.hook else [topic]

            save_json("titles.json", {"titles": pack.titles})
            self._sync_video_plan_for_pack(pack)

            # 4. 补充话题标签
            if len(pack.hashtags) < 3:
                fallback_tags = self._generate_hashtags(topic, content_type)
                merged_tags: List[str] = []
                for tag in pack.hashtags + fallback_tags:
                    if tag not in merged_tags:
                        merged_tags.append(tag)
                pack.hashtags = merged_tags[:8]
                logger.info(f"  补充话题标签: {pack.hashtags}")

            pack.best_post_time = self._get_best_post_time()
            actual_score = int(score_data.get("score", 0))
            self._set_quality_gate_status(
                pack,
                actual_score=actual_score,
                min_score_threshold=min_score_threshold,
                candidate_scores=viral_script.get("candidate_scores", []),
            )
            self._sync_video_plan_for_pack(pack)

            if not pack.quality_gate_passed:
                logger.warning(
                    f"  评分低于门槛（{min_score_threshold}），跳过语音/视频/音乐/缩略图生成"
                )
                logger.info(f"抖音内容生成完成（已跳过高成本阶段）！爆款评分: {pack.viral_score['level']}")
                self._save_pack_manifest(pack, status="skipped")
                return pack

            # 5. 生成语音
            if pack.narration and len(pack.narration) > 10:
                logger.info("6. 生成语音...")
                audio_filename = self.file_manager.generate_filename(
                    prefix=topic_prefix, extension="mp3"
                )
                emotion = self._get_emotion_for_content_type(content_type)
                narration_with_emotion = self.speech_api.add_emotion_tags(
                    pack.narration, emotion
                )
                pack.audio_path = self.speech_api.synthesize_to_file(
                    text=narration_with_emotion,
                    output_path=str(content_dir / audio_filename),
                    voice_id=resolved_voice,
                    emotion=emotion,
                )
                pack.apply_generation_metadata("tts", self.speech_api.last_request_metadata)
                self._sync_video_plan_for_pack(pack)

            # 6. 生成视频
            if generate_video and pack.video_description:
                logger.info("7. 生成视频...")
                camera_movements = {
                    "生活技巧": "[推进]",
                    "情感共鸣": "[缓慢推进]",
                    "知识科普": "[推进]",
                    "娱乐搞笑": "[跟随,轻微晃动]",
                    "美食探店": "[推进,特写]",
                    "旅行vlog": "[左摇]",
                    "萌宠日常": "[固定,推进]",
                }
                camera_hint = camera_movements.get(content_type, "[推进]")
                if "," not in camera_hint and content_type == "娱乐搞笑":
                    camera_hint = "[轻微晃动,跟随]"
                elif content_type == "美食探店":
                    camera_hint = "[推进],[特写]"

                requested_model = self.settings.models.video_model_fast
                requested_resolution = "768P"
                enhanced_prompt = f"{pack.video_description} {camera_hint}"
                logger.info(f"  Prompt: {enhanced_prompt[:120]}...")
                logger.info(
                    f"  请求模型: {requested_model}，运镜: {camera_hint}，请求分辨率: {requested_resolution}"
                )

                pack.video_path = self._generate_video_with_hybrid_routing(
                    pack,
                    topic=topic,
                    topic_prefix=topic_prefix,
                    video_prompt=enhanced_prompt,
                    duration=duration,
                    requested_model=requested_model,
                    requested_resolution=requested_resolution,
                    generate_thumbnail=generate_thumbnail,
                    content_type=content_type,
                    video_kwargs={"fast_pretreatment": True},
                )
                self._sync_video_plan_for_pack(pack)

            # 7. 生成音乐
            if generate_music:
                music_skip_reason = self._music_skip_reason_for_automation()
                if music_skip_reason:
                    logger.info(f"8. 跳过音乐生成: {music_skip_reason}")
                    self._record_music_skip(pack, music_skip_reason)
                    self._sync_video_plan_for_pack(pack)
                elif self.settings.models.music_model:
                    self._check_quota("music")
                    logger.info("8. 生成音乐...")
                    music_style = self.strategy.MUSIC_STYLE_MAP.get(
                        content_type, "轻松,明快,节奏感"
                    )
                    music_filename = self.file_manager.generate_filename(
                        prefix=topic_prefix, extension="mp3"
                    )
                    pack.music_path = self.music_api.generate_instrumental(
                        prompt=music_style, output_path=str(content_dir / music_filename)
                    )
                    pack.apply_generation_metadata("music", self.music_api.last_request_metadata)
                    self._sync_video_plan_for_pack(pack)
                else:
                    logger.info("8. 跳过音乐生成（上传抖音时使用抖音曲库）")

            # 8. 生成缩略图
            if generate_thumbnail and not pack.thumbnail_path:
                logger.info("9. 生成缩略图...")
                image_quota_available = self.settings.check_quota(
                    "image",
                    refresh_remote=True,
                )
                pack.thumbnail_path = self._create_thumbnail_with_video_fallback(
                    pack,
                    topic=topic,
                    content_type=content_type,
                    output_path=content_dir / "cover.jpg",
                    image_quota_available=image_quota_available,
                )
                self._sync_video_plan_for_pack(pack)
            elif generate_thumbnail and pack.thumbnail_path:
                logger.info(f"9. 复用首帧图作为缩略图: {pack.thumbnail_path}")
                self._sync_video_plan_for_pack(pack)

            # 9. 合成最终视频
            final_video_path = self._compose_final_douyin_video(
                pack, duration, content_dir
            )
            if final_video_path:
                pack.final_video_path = final_video_path
                logger.info(f"最终视频已合成: {final_video_path}")
                self._sync_video_plan_for_pack(pack)

            # 10. 设置封面
            if pack.thumbnail_path and (pack.video_path or pack.final_video_path):
                cover_path = self.composer.set_video_cover(
                    video_path=str(pack.final_video_path or pack.video_path),
                    thumbnail_path=str(pack.thumbnail_path),
                    output_path=str(content_dir / "cover.jpg"),
                )
                pack.cover_path = cover_path
                logger.info(f"视频封面已设置: {cover_path}")
                self._sync_video_plan_for_pack(pack)

            logger.info(f"抖音内容生成完成！爆款评分: {pack.viral_score['level']}")
            self._save_pack_manifest(pack, status="succeeded")

        except Exception as e:
            logger.error(f"抖音内容生成失败: {str(e)}")
            pack.errors.append(str(e))
            self._save_pack_manifest(pack, status="failed", error=str(e))
            raise

        return pack

    def _generate_viral_script_with_retry(
        self,
        *,
        topic: str,
        content_type: str,
        duration: int,
        max_attempts: int = 3,
        early_accept_score: Optional[int] = None,
    ) -> Dict[str, Any]:
        hook_sequence = self.viral_gen.get_hook_sequence(
            content_type,
            max_attempts=max_attempts,
        )
        best_script: Optional[Dict[str, Any]] = None
        best_score = -1
        candidate_scores: List[Dict[str, Any]] = []

        for attempt, hook_type in enumerate(hook_sequence, start=1):
            script = self.viral_gen.generate(
                topic=topic,
                content_type=content_type,
                duration=duration,
                hook_type=hook_type,
            )
            request_metadata = dict(self.text_api.last_request_metadata or {})

            raw_content = (script.get("raw_content") or "").strip()
            if not raw_content:
                candidate_scores.append(
                    {
                        "attempt": attempt,
                        "hook_type": hook_type,
                        "status": "empty",
                    }
                )
                if attempt < len(hook_sequence):
                    logger.warning(
                        f"  爆款脚本返回空内容，继续尝试 hook={hook_sequence[attempt]}"
                    )
                continue

            script = self._normalize_script_candidate(
                script=script,
                topic=topic,
                content_type=content_type,
            )
            score_data = self.viral_gen.calculate_content_score(
                {
                    "hook": script.get("hook", ""),
                    "narration": script.get("narration", ""),
                    "engagement_question": script.get("engagement_question", ""),
                    "cta": script.get("cta", ""),
                    "hashtags": script.get("hashtags", []),
                }
            )
            score = int(score_data.get("score", 0))
            candidate_scores.append(
                {
                    "attempt": attempt,
                    "hook_type": hook_type,
                    "status": "scored",
                    "score": score,
                    "level": score_data.get("level"),
                }
            )

            logger.info(
                f"  脚本候选 {attempt}/{len(hook_sequence)}: hook={hook_type}, score={score}"
            )

            if score > best_score:
                best_score = score
                best_script = {
                    **script,
                    "selected_hook_type": hook_type,
                    "precomputed_score": score_data,
                    "request_metadata": request_metadata,
                }

            if early_accept_score is not None and score >= early_accept_score:
                logger.info(
                    f"  脚本候选达到优先分数线 {early_accept_score}，采用 hook={hook_type}"
                )
                break

        if best_script:
            selected_hook_type = best_script.get("selected_hook_type")
            for item in candidate_scores:
                item["selected"] = item.get("hook_type") == selected_hook_type
            best_script["candidate_scores"] = candidate_scores
            best_script["score_target"] = early_accept_score
            if early_accept_score is not None and best_score < early_accept_score:
                logger.warning(
                    "  脚本候选未达到优先分数线 %s，采用当前最高分方案: hook=%s score=%s",
                    early_accept_score,
                    best_script.get("selected_hook_type"),
                    best_score,
                )
            return best_script

        raise RuntimeError("爆款脚本生成为空，已中止以避免浪费视频额度")

    def _create_thumbnail_with_video_fallback(
        self,
        pack: DouyinContentPack,
        *,
        topic: str,
        content_type: str,
        output_path: Path,
        image_quota_available: bool,
    ) -> Path:
        thumbnail_prompt = (
            f"{topic}, {content_type}, vibrant colors, high contrast, "
            "eye-catching, vertical 9:16 format, cinematic composition, 4K"
        )
        if image_quota_available:
            try:
                thumbnail_path = self.image_api.create_thumbnail(
                    prompt=thumbnail_prompt,
                    output_path=str(output_path),
                )
                self._apply_image_stage_metadata(
                    pack,
                    stage="thumbnail",
                    output_path=thumbnail_path,
                )
                return thumbnail_path
            except Exception as exc:
                fallback_video_path = pack.final_video_path or pack.video_path
                if fallback_video_path:
                    logger.warning(f"缩略图生成失败，回退到视频截帧封面: {exc}")
                    fallback_path = self.composer.set_video_cover(
                        video_path=str(fallback_video_path),
                        output_path=str(output_path),
                    )
                    pack.apply_generation_metadata(
                        "thumbnail",
                        {
                            "status": "fallback_frame",
                            "fallback_source": "video_frame",
                            "fallback_reason": str(exc),
                            "requested_model": self.settings.models.image_model,
                            "applied_model": None,
                            "output_path": str(fallback_path),
                        },
                    )
                    pack.cover_path = fallback_path
                    return fallback_path
                raise

        fallback_video_path = pack.final_video_path or pack.video_path
        if fallback_video_path:
            logger.warning("图片额度不可用，回退到视频截帧封面")
            fallback_path = self.composer.set_video_cover(
                video_path=str(fallback_video_path),
                output_path=str(output_path),
            )
            pack.apply_generation_metadata(
                "thumbnail",
                {
                    "status": "fallback_frame",
                    "fallback_source": "video_frame",
                    "fallback_reason": "image_quota_unavailable",
                    "requested_model": self.settings.models.image_model,
                    "applied_model": None,
                    "output_path": str(fallback_path),
                },
            )
            pack.cover_path = fallback_path
            return fallback_path

        raise QuotaExceededError("image", "（无图片额度且当前无可截帧视频）")

    def _normalize_script_candidate(
        self,
        *,
        script: Dict[str, Any],
        topic: str,
        content_type: str,
    ) -> Dict[str, Any]:
        normalized = dict(script)
        existing_tags = [
            tag.strip()
            for tag in normalized.get("hashtags", [])
            if isinstance(tag, str) and tag.strip()
        ]
        merged_tags: List[str] = []
        for tag in existing_tags + self._generate_hashtags(topic, content_type):
            normalized_tag = tag if tag.startswith("#") else f"#{tag.lstrip('#')}"
            if normalized_tag not in merged_tags:
                merged_tags.append(normalized_tag)
            if len(merged_tags) >= 8:
                break

        quality_warnings = [
            str(item).strip()
            for item in normalized.get("quality_warnings", [])
            if str(item).strip()
        ]
        if len(existing_tags) < len(merged_tags):
            quality_warnings.append("已自动补齐话题标签")

        normalized["hashtags"] = merged_tags
        normalized["quality_warnings"] = list(dict.fromkeys(quality_warnings))
        return normalized

    def _set_quality_gate_status(
        self,
        pack: DouyinContentPack,
        *,
        actual_score: int,
        min_score_threshold: Optional[int],
        candidate_scores: Optional[List[Dict[str, Any]]] = None,
    ) -> None:
        if min_score_threshold is None:
            pack.quality_gate_passed = True
            status = "not_enforced"
            reason = "no_threshold_configured"
        else:
            pack.quality_gate_passed = actual_score >= min_score_threshold
            status = "passed" if pack.quality_gate_passed else "skipped"
            reason = None if pack.quality_gate_passed else "score_below_threshold"

        pack.generation_metadata["quality_gate"] = {
            "status": status,
            "min_score_threshold": min_score_threshold,
            "actual_score": actual_score,
            "reason": reason,
            "selected_hook_type": pack.hook_type_used,
            "candidate_count": len(candidate_scores or []),
        }

    def generate_daily_content(
        self, count: Optional[int] = None, content_types: Optional[List[str]] = None
    ) -> List[DouyinContentPack]:
        """
        生成每日内容（自动选择热门话题）

        Args:
            count: 生成数量
            content_types: 内容类型列表

        Returns:
            内容包列表
        """
        resolved_count = count or self.settings.auto.content_strategy.daily_count
        logger.info(f"开始生成每日内容，数量: {resolved_count}")

        packs = []

        # 如果没有指定类型，自动分配
        if content_types is None:
            content_types = self.settings.auto.content_strategy.default_types

        type_plan = [content_types[i % len(content_types)] for i in range(resolved_count)]

        # 获取与内容类型对齐的热门话题（尽量去重）
        topics = self.strategy.get_trending_topics_for_types(type_plan)

        for i, topic in enumerate(topics):
            content_type = type_plan[i]

            try:
                pack = self.generate_douyin_content(
                    topic=topic,
                    content_type=content_type,
                    duration=self.settings.auto.content_strategy.default_duration,
                    voice=self.settings.auto.content_strategy.default_voice,
                    generate_video=self.settings.auto.content_strategy.auto_generate_video,
                    generate_music=self.settings.auto.content_strategy.auto_generate_music,
                    generate_thumbnail=self.settings.auto.content_strategy.auto_generate_thumbnail,
                    pack_index=i + 1,
                    min_score_threshold=self.settings.auto.autopilot.min_score,
                    script_max_attempts=self.settings.auto.autopilot.script_attempts,
                    script_accept_score=self.settings.auto.autopilot.script_accept_score,
                )
                packs.append(pack)

            except Exception as e:
                logger.error(f"生成 '{topic}' 失败: {str(e)}")
                continue

        logger.info(f"每日内容生成完成，成功: {len(packs)}/{resolved_count}")

        return packs

    def generate_weekly_plan(
        self, custom_topics: Optional[List[str]] = None
    ) -> List[Dict[str, Any]]:
        """
        生成一周内容计划

        Args:
            custom_topics: 自定义主题列表

        Returns:
            内容日历
        """
        logger.info("生成一周内容计划...")

        calendar = self.strategy.generate_content_calendar(
            days=7,
            topics=custom_topics,
            publish_strategy=self.settings.auto.publish_strategy,
        )

        # 保存计划
        plan_filename = f"weekly_plan_{datetime.now().strftime('%Y%m%d')}.json"
        plan_path = self.file_manager.save_json(
            {"calendar": calendar}, plan_filename, "reports"
        )

        logger.info(f"一周内容计划已保存: {plan_path}")

        return calendar

    def _generate_hashtags(self, topic: str, content_type: str) -> List[str]:
        """
        生成话题标签

        Args:
            topic: 主题
            content_type: 内容类型

        Returns:
            标签列表
        """
        # 基础标签
        tags = [f"#{topic}"]

        # 根据内容类型添加标签
        type_tags = {
            "生活技巧": ["#生活小妙招", "#实用技巧", "#省钱攻略"],
            "情感共鸣": ["#治愈系", "#暖心", "#情感"],
            "知识科普": ["#涨知识", "#科普", "#冷知识"],
            "娱乐搞笑": ["#搞笑", "#沙雕", "#快乐源泉"],
            "美食探店": ["#美食", "#探店", "#吃货"],
            "旅行vlog": ["#旅行", "#vlog", "#风景"],
            "萌宠日常": ["#萌宠", "#宠物", "#治愈"],
        }

        tags.extend(type_tags.get(content_type, []))

        # 添加通用热门标签
        tags.extend(["#抖音", "#短视频", "#推荐"])

        return tags[:8]  # 最多8个标签

    def _get_best_post_time(self) -> str:
        """
        获取最佳发布时间

        Returns:
            最佳发布时间
        """
        # 根据当前星期几返回最佳发布时间
        weekday = datetime.now().weekday()

        if weekday < 5:
            return self.settings.auto.publish_strategy.weekday_best_time
        return self.settings.auto.publish_strategy.weekend_best_time

    def _get_emotion_for_content_type(self, content_type: str) -> str:
        """
        根据内容类型获取情感

        Args:
            content_type: 内容类型

        Returns:
            情感类型
        """
        emotion_map = {
            "生活技巧": "neutral",
            "情感共鸣": "sad",
            "知识科普": "neutral",
            "娱乐搞笑": "happy",
            "美食探店": "happy",
            "旅行vlog": "happy",
            "萌宠日常": "happy",
        }

        return emotion_map.get(content_type, "neutral")

    def _compose_final_douyin_video(
        self, pack: DouyinContentPack, duration: int, content_dir: Path
    ) -> Optional[Path]:
        """
        将所有素材合成为最终抖音视频

        工作流：视频 + 语音 + 背景音乐 + 字幕 → 最终视频

        Args:
            pack:    抖音内容包
            duration: 视频时长
            content_dir: 内容输出目录

        Returns:
            最终视频路径（合成失败返回 None）
        """
        if not pack.video_path:
            logger.warning("没有视频素材，跳过合成")
            return None

        try:
            # 1. 生成 SRT 字幕（输出到 content_dir）
            srt_path = None
            if pack.narration:
                logger.info("生成字幕...")
                audio_duration = (
                    self.composer.get_media_duration(str(pack.audio_path))
                    if pack.audio_path
                    else None
                )
                srt_path = self.subtitle_gen.generate_srt(
                    text=pack.narration,
                    output_path=str(content_dir / "subtitle.srt"),
                    speed=5.5,
                    target_duration=audio_duration,
                )
                subtitle_engine = self.settings.auto.content_strategy.subtitle_engine
                if subtitle_engine == "whisperx" and pack.audio_path:
                    srt_path = self.subtitle_gen.generate_srt_from_audio(
                        audio_path=str(pack.audio_path),
                        text_fallback=pack.narration,
                        output_path=str(content_dir / "subtitle.srt"),
                        engine=subtitle_engine,
                    )
                if pack.video_plan:
                    pack.video_plan.subtitles["path"] = str(srt_path)
                    pack.video_plan.record_asset(
                        "subtitle",
                        srt_path,
                        source_stage="subtitle",
                    )
                    self._sync_video_plan_for_pack(pack)

            # 2. 合成最终视频（输出到 content_dir/final.mp4）
            logger.info("合成最终视频...")
            if pack.audio_path:
                final_path = self.composer.compose_with_voice_mixing(
                    video_path=str(pack.video_path),
                    audio_path=str(pack.audio_path),
                    music_path=str(pack.music_path) if pack.music_path else None,
                    srt_path=str(srt_path) if srt_path else None,
                    output_path=str(content_dir / "final.mp4"),
                    voice_volume=1.0,
                    music_volume=0.25,  # 背景音乐低声，不干扰语音
                    subtitle_style="douyin",
                )
            else:
                final_path = self.composer.compose_final_video(
                    video_path=str(pack.video_path),
                    music_path=str(pack.music_path) if pack.music_path else None,
                    srt_path=str(srt_path) if srt_path else None,
                    output_path=str(content_dir / "final.mp4"),
                    video_volume=0.0,
                    subtitle_style="douyin",
                )

            return final_path

        except Exception as e:
            logger.error(f"最终视频合成失败: {str(e)}")
            pack.errors.append(f"视频合成失败: {str(e)}")
            return None

    def generate_ready_to_upload_package(
        self, topic: str, content_type: str = "生活技巧", duration: int = 6, **kwargs
    ) -> Dict[str, Any]:
        """
        生成完整的可上传抖音的内容包

        Returns:
            包含以下内容的字典：
            - final_video: 最终视频路径
            - cover: 封面图路径
            - title: 推荐标题
            - hashtags: 话题标签
            - best_post_time: 最佳发布时间
            - description: 推荐描述文案
        """
        logger.info(f"生成可上传内容包: {topic}")

        # 生成完整内容
        pack = self.generate_douyin_content(
            topic=topic, content_type=content_type, duration=duration, **kwargs
        )

        # 构建上传包
        description = self._build_description(pack)

        package = {
            "final_video": str(pack.final_video_path)
            if pack.final_video_path
            else None,
            "cover": str(pack.cover_path) if pack.cover_path else None,
            "title": pack.titles[0] if pack.titles else topic,
            "description": description,
            "hashtags": pack.hashtags,
            "best_post_time": pack.best_post_time,
            "viral_score": pack.viral_score,
            "topic": topic,
            "content_type": content_type,
            "pack_dict": pack.to_dict(),
        }

        return package

    def _build_description(self, pack: DouyinContentPack) -> str:
        """构建抖音发布文案"""
        parts = []

        # 标题（第一行）
        if pack.titles:
            parts.append(pack.titles[0])

        # CTA + 互动问题
        if pack.cta:
            parts.append(pack.cta)

        if pack.engagement_question:
            parts.append(f"💬 {pack.engagement_question}")

        # 话题标签（每行一个，避免被截断）
        if pack.hashtags:
            parts.append("")
            parts.append(" ".join(pack.hashtags))

        return "\n".join(parts)
