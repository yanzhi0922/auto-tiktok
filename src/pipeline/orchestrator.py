# -*- coding: utf-8 -*-
"""
Pipeline 协调器
整合所有 API 模块，提供一站式素材生产工作流
"""

import logging
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path
from typing import Optional, Dict, Any, List
from datetime import datetime

from src.api import TextAPI, SpeechAPI, VideoAPI, MusicAPI, ImageAPI
from src.pipeline.video_plan import VideoPlan, update_plan_from_pack
from src.utils.file_manager import FileManager
from src.utils.logger import TaskLogger
from config.settings import get_settings


logger = logging.getLogger(__name__)


class QuotaExceededError(Exception):
    """配额超限异常"""

    def __init__(self, resource: str, detail: str = ""):
        self.resource = resource
        self.detail = detail
        super().__init__(f"配额已用尽: {resource} {detail}")


class ContentPack:
    """内容包，包含一个完整短视频所需的所有素材"""

    def __init__(self, topic: str):
        """
        初始化内容包

        Args:
            topic: 内容主题
        """
        self.topic = topic
        self.created_at = datetime.now()

        # 文本内容
        self.script: Optional[str] = None
        self.titles: List[str] = []
        self.video_description: Optional[str] = None
        self.narration: Optional[str] = None

        # 媒体文件路径
        self.audio_path: Optional[Path] = None
        self.video_path: Optional[Path] = None
        self.music_path: Optional[Path] = None
        self.thumbnail_path: Optional[Path] = None
        self.images: List[Path] = []

        # 最终成品
        self.final_video_path: Optional[Path] = None  # 合成后的成品视频
        self.cover_path: Optional[Path] = None  # 封面图

        # 目录归属
        self.content_dir: Optional[Path] = None
        self.content_index: Optional[int] = None
        self.video_plan_path: Optional[Path] = None
        self.video_plan: Optional[VideoPlan] = None

        # 错误记录
        self.errors: List[str] = []
        self.quality_gate_passed: Optional[bool] = None
        self.key_tier_used: Optional[str] = None
        self.requested_model: Optional[str] = None
        self.applied_model: Optional[str] = None
        self.requested_video_spec: Optional[Dict[str, Any]] = None
        self.applied_video_spec: Optional[Dict[str, Any]] = None
        self.cross_tier_fallback: bool = False
        self.generation_metadata: Dict[str, Dict[str, Any]] = {}

    def apply_generation_metadata(
        self,
        stage: str,
        metadata: Optional[Dict[str, Any]],
    ) -> None:
        if not metadata:
            return

        normalized = dict(metadata)
        self.generation_metadata[stage] = normalized

        should_promote = stage == "video" or self.key_tier_used is None
        if not should_promote:
            return

        self.key_tier_used = normalized.get("key_tier_used", self.key_tier_used)
        self.requested_model = normalized.get("requested_model", self.requested_model)
        self.applied_model = normalized.get("applied_model", self.applied_model)
        self.requested_video_spec = normalized.get(
            "requested_video_spec",
            self.requested_video_spec,
        )
        self.applied_video_spec = normalized.get(
            "applied_video_spec",
            self.applied_video_spec,
        )
        self.cross_tier_fallback = bool(
            normalized.get("cross_tier_fallback", self.cross_tier_fallback)
        )

    def to_dict(self) -> Dict[str, Any]:
        """转换为字典"""
        return {
            "topic": self.topic,
            "created_at": self.created_at.isoformat(),
            "script": self.script,
            "titles": self.titles,
            "video_description": self.video_description,
            "narration": self.narration,
            "audio_path": str(self.audio_path) if self.audio_path else None,
            "video_path": str(self.video_path) if self.video_path else None,
            "music_path": str(self.music_path) if self.music_path else None,
            "thumbnail_path": str(self.thumbnail_path) if self.thumbnail_path else None,
            "images": [str(p) for p in self.images],
            "final_video_path": str(self.final_video_path)
            if self.final_video_path
            else None,
            "cover_path": str(self.cover_path) if self.cover_path else None,
            "content_dir": str(self.content_dir) if self.content_dir else None,
            "content_index": self.content_index,
            "video_plan_path": str(self.video_plan_path)
            if self.video_plan_path
            else None,
            "errors": self.errors,
            "quality_gate_passed": self.quality_gate_passed,
            "key_tier_used": self.key_tier_used,
            "requested_model": self.requested_model,
            "applied_model": self.applied_model,
            "requested_video_spec": self.requested_video_spec,
            "applied_video_spec": self.applied_video_spec,
            "cross_tier_fallback": self.cross_tier_fallback,
            "generation_metadata": self.generation_metadata,
        }


class PipelineOrchestrator:
    """Pipeline 协调器"""

    def __init__(
        self,
        output_dir: str = "output",
        file_manager: Optional[FileManager] = None,
    ):
        """
        初始化 Pipeline 协调器

        Args:
            output_dir: 输出目录
        """
        self.settings = get_settings()
        self.file_manager = file_manager or FileManager(output_dir)

        # 初始化各 API 客户端
        self.text_api = TextAPI()
        self.speech_api = SpeechAPI()
        self.video_api = VideoAPI()
        self.music_api = MusicAPI()
        self.image_api = ImageAPI()

        logger.info("Pipeline 协调器初始化完成")

    def _create_video_plan_for_pack(
        self,
        pack: ContentPack,
        *,
        platform: str,
        duration: int,
        voice: Optional[str],
        content_type: Optional[str] = None,
        style: Optional[str] = None,
        generate_video: bool = True,
        generate_music: bool = True,
        generate_thumbnail: bool = True,
    ) -> None:
        if not pack.content_dir or pack.content_index is None:
            return

        plan = VideoPlan.create(
            topic=pack.topic,
            content_dir=pack.content_dir,
            run_id=self.file_manager.run_id,
            content_index=pack.content_index,
            duration=duration,
            voice=voice,
            settings=self.settings,
            platform=platform,
            content_type=content_type,
            style=style,
            generate_video=generate_video,
            generate_music=generate_music,
            generate_thumbnail=generate_thumbnail,
        )
        pack.video_plan = plan
        pack.video_plan_path = plan.save()

    def _sync_video_plan_for_pack(self, pack: ContentPack) -> None:
        if not pack.video_plan and pack.video_plan_path and pack.video_plan_path.exists():
            pack.video_plan = VideoPlan.load(pack.video_plan_path)
        if not pack.video_plan:
            return

        update_plan_from_pack(pack.video_plan, pack)
        pack.video_plan_path = pack.video_plan.save(pack.video_plan_path)

    def _save_pack_manifest(
        self,
        pack: ContentPack,
        *,
        status: str,
        error: Optional[str] = None,
    ) -> None:
        if pack.content_index is None:
            return

        payload: Dict[str, Any] = {
            "status": status,
            "saved_at": datetime.now().isoformat(),
            "run_id": self.file_manager.run_id,
            "pack": pack.to_dict(),
        }
        if error:
            payload["error"] = error
            if pack.video_plan:
                pack.video_plan.record_error(error)
        self._sync_video_plan_for_pack(pack)
        self.file_manager.save_content_manifest(pack.content_index, payload)

    def _check_quota(self, resource: str) -> None:
        """
        检查配额并抛出异常（如果配额不足）

        Args:
            resource: 资源类型 ("video", "music", "image")

        Raises:
            QuotaExceededError: 配额已用尽
        """
        if not self.settings.check_quota(resource):
            status = self.settings.get_quota_status()
            remaining = status.get(resource, {}).get("remaining", 0)
            raise QuotaExceededError(resource, f"（剩余 {remaining} 个）")

    def _music_skip_reason_for_automation(self) -> Optional[str]:
        if not self.settings.models.music_model:
            return "当前配置未启用音乐模型"
        if not self.settings.models.supports_music_instrumental():
            return (
                "Token Plan 不支持纯音乐背景音乐生成，仅支持带歌词歌曲；自动流程跳过背景音乐，"
                "建议上传到平台后使用平台曲库。"
            )
        return None

    def _record_music_skip(self, pack: ContentPack, reason: str) -> None:
        pack.apply_generation_metadata(
            "music",
            {
                "status": "skipped",
                "skip_reason": reason,
                "requested_model": self.settings.models.music_model,
                "applied_model": None,
                "requested_music_mode": "instrumental",
                "applied_music_mode": "skipped",
            },
        )

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
            style or "",
            "high-impact first frame for vertical short video",
            "one dominant subject, strong focal point, premium mobile cover image",
            enriched_prompt,
        ]
        return ", ".join(part for part in prompt_parts if part)

    def _enhance_video_prompt(
        self,
        video_prompt: str,
        *,
        style: Optional[str] = None,
        content_type: Optional[str] = None,
    ) -> str:
        cleaned_prompt = (video_prompt or "").strip()
        style_hint = (style or "").strip()
        global_hints = (
            "vertical 9:16 short-video framing, one clear subject, strong first-second hook, "
            "cinematic lighting, layered depth, crisp facial detail, realistic hands, stable anatomy, "
            "high contrast focal subject, clean motion, no text overlay, no subtitles, no watermark, no collage"
        )
        type_hints = {
            "生活技巧": "clear hand action, satisfying micro-detail, practical transformation, bright premium lifestyle aesthetic",
            "情感共鸣": "expressive face, intimate close-up, emotional atmosphere, subtle cinematic motion, believable human emotion",
            "知识科普": "smart visual metaphor, premium studio polish, visually surprising but clean composition, confident presenter energy",
            "娱乐搞笑": "strong comic timing, exaggerated but realistic reaction, readable body language, playful dynamic framing",
            "美食探店": "mouth-watering texture, steam, glossy highlights, appetizing color contrast, luxury food cinematography",
            "旅行vlog": "epic scale, premium travel ad aesthetic, atmospheric depth, golden or neon light accents, cinematic motion reveal",
            "萌宠日常": "adorable eye contact, expressive pet action, soft fur detail, playful motion, high emotional warmth",
        }
        prompt_parts = [cleaned_prompt]
        if style_hint:
            prompt_parts.append(style_hint)
        if content_type and type_hints.get(content_type):
            prompt_parts.append(type_hints[content_type])
        prompt_parts.append(global_hints)
        return ", ".join(part for part in prompt_parts if part)

    def _ensure_video_seed_image(
        self,
        pack: ContentPack,
        *,
        topic_prefix: str,
        seed_prompt: str,
        generate_thumbnail: bool,
        filename: Optional[str] = None,
    ) -> Path:
        if pack.thumbnail_path and Path(pack.thumbnail_path).exists():
            return Path(pack.thumbnail_path)

        output_name = (
            filename
            if filename
            else (
                "cover.jpg"
                if generate_thumbnail
                else self.file_manager.generate_filename(
                prefix=topic_prefix,
                extension="jpg",
                suffix="seed",
                )
            )
        )
        output_path = pack.content_dir / output_name
        seed_path = self.image_api.create_thumbnail(
            prompt=seed_prompt,
            output_path=str(output_path),
        )
        metadata_stage = "thumbnail" if generate_thumbnail else "video_seed"
        if generate_thumbnail:
            pack.thumbnail_path = seed_path
        elif seed_path not in pack.images:
            pack.images.append(seed_path)
        self._apply_image_stage_metadata(
            pack,
            stage=metadata_stage,
            output_path=seed_path,
        )
        return seed_path

    def _apply_image_stage_metadata(
        self,
        pack: ContentPack,
        *,
        stage: str,
        output_path: Path,
    ) -> None:
        metadata = dict(self.image_api.last_request_metadata or {})
        metadata["output_path"] = str(output_path)
        pack.apply_generation_metadata(stage, metadata)

    def _generate_video_with_hybrid_routing(
        self,
        pack: ContentPack,
        *,
        topic: str,
        topic_prefix: str,
        video_prompt: str,
        duration: int,
        requested_model: str,
        requested_resolution: str,
        generate_thumbnail: bool,
        style: Optional[str] = None,
        content_type: Optional[str] = None,
        video_kwargs: Optional[Dict[str, Any]] = None,
    ) -> Path:
        video_kwargs = dict(video_kwargs or {})
        final_video_prompt = self._enhance_video_prompt(
            video_prompt,
            style=style,
            content_type=content_type,
        )
        output_path = pack.content_dir / self.file_manager.generate_filename(
            prefix=topic_prefix,
            extension="mp4",
        )
        fast_available = self.settings.check_quota(
            "video_fast",
            refresh_remote=True,
        )
        standard_available = self.settings.check_quota(
            "video_standard",
            refresh_remote=not fast_available,
        )

        if fast_available:
            if not self.settings.check_quota("image", refresh_remote=True):
                logger.warning("Fast 视频额度可用，但图片额度不足，回退到标准文生视频")
            else:
                try:
                    seed_prompt = self._build_video_seed_prompt(
                        topic=topic,
                        video_prompt=final_video_prompt,
                        style=style,
                        content_type=content_type,
                    )
                    seed_image_path = self._ensure_video_seed_image(
                        pack,
                        topic_prefix=topic_prefix,
                        seed_prompt=seed_prompt,
                        generate_thumbnail=generate_thumbnail,
                    )
                except Exception as exc:
                    logger.warning(f"Fast 首帧图准备失败，回退到标准文生视频: {exc}")
                else:
                    logger.info("  视频路由: 图生视频 Fast 优先")
                    video_path = self.video_api.generate_video_from_image(
                        prompt=final_video_prompt,
                        first_frame_image=str(seed_image_path),
                        output_path=str(output_path),
                        model=self.settings.models.video_model_fast,
                        duration=duration,
                        resolution=requested_resolution,
                        **video_kwargs,
                    )
                    pack.apply_generation_metadata("video", self.video_api.last_request_metadata)
                    return video_path

        if not standard_available:
            raise QuotaExceededError("video", "（Fast/Standard 视频额度均不可用）")

        logger.info("  视频路由: 标准文生视频")
        video_path = self.video_api.generate_video(
            prompt=final_video_prompt,
            output_path=str(output_path),
            model=requested_model,
            duration=duration,
            resolution=requested_resolution,
            **video_kwargs,
        )
        pack.apply_generation_metadata("video", self.video_api.last_request_metadata)
        return video_path

    def generate_content_pack(
        self,
        topic: str,
        style: str = "轻松幽默",
        duration: int = 6,
        voice: Optional[str] = None,
        music_style: str = "流行音乐, 欢快",
        generate_video: bool = True,
        generate_music: bool = True,
        generate_thumbnail: bool = True,
        **kwargs,
    ) -> ContentPack:
        """
        生成完整的内容包（一站式生产所有素材）

        Args:
            topic: 内容主题
            style: 视频风格
            duration: 视频时长（秒）
            voice: 语音音色
            music_style: 音乐风格描述
            generate_video: 是否生成视频
            generate_music: 是否生成音乐
            generate_thumbnail: 是否生成缩略图
            **kwargs: 其他参数

        Returns:
            内容包对象

        Raises:
            QuotaExceededError: 配额不足时抛出

        Example:
            >>> pipeline = PipelineOrchestrator()
            >>> pack = pipeline.generate_content_pack(
            ...     topic="咖啡文化",
            ...     style="文艺清新",
            ...     duration=6
            ... )
        """
        task_logger = TaskLogger(f"content_pack_{topic}")
        task_logger.start(f"开始生成内容包: {topic}")

        # 创建内容包
        pack = ContentPack(topic=topic)
        content_index = kwargs.pop("content_index", None)
        content_index, content_dir = self.file_manager.reserve_content_slot(
            index=content_index
        )
        pack.content_index = content_index
        pack.content_dir = content_dir
        topic_prefix = self.file_manager.sanitize_component(topic)
        resolved_voice = voice or self.settings.auto.content_strategy.default_voice
        self._create_video_plan_for_pack(
            pack,
            platform="generic",
            duration=duration,
            voice=resolved_voice,
            style=style,
            generate_video=generate_video,
            generate_music=generate_music,
            generate_thumbnail=generate_thumbnail,
        )

        try:
            # 步骤1: 生成脚本（文本不占配额，放行）
            task_logger.step("生成脚本", "进行中")
            script_data = self.text_api.generate_script(
                topic=topic, style=style, duration=duration
            )
            pack.script = script_data.get("raw_content", "")
            pack.video_description = script_data.get("video_description", "")
            pack.narration = script_data.get("narration", "")
            pack.apply_generation_metadata("script", self.text_api.last_request_metadata)
            self._sync_video_plan_for_pack(pack)
            task_logger.step("生成脚本", "完成", f"长度: {len(pack.script)}")

            # 步骤2: 生成标题
            task_logger.step("生成标题", "进行中")
            pack.titles = self.text_api.generate_titles(topic=topic, count=5)
            pack.apply_generation_metadata("titles", self.text_api.last_request_metadata)
            self._sync_video_plan_for_pack(pack)
            task_logger.step("生成标题", "完成", f"数量: {len(pack.titles)}")

            # 步骤3: 生成语音（不计视频配额）
            if pack.narration:
                task_logger.step("生成语音", "进行中")
                audio_filename = self.file_manager.generate_filename(
                    prefix=topic_prefix, extension="mp3"
                )
                pack.audio_path = self.speech_api.synthesize_to_file(
                    text=pack.narration,
                    output_path=str(content_dir / audio_filename),
                    voice_id=resolved_voice,
                )
                pack.apply_generation_metadata("tts", self.speech_api.last_request_metadata)
                self._sync_video_plan_for_pack(pack)
                task_logger.step("生成语音", "完成", str(pack.audio_path))

            # 步骤4: 生成视频（需检查配额）
            if generate_video and pack.video_description:
                task_logger.step("生成视频", "进行中")
                pack.video_path = self._generate_video_with_hybrid_routing(
                    pack,
                    topic=topic,
                    topic_prefix=topic_prefix,
                    video_prompt=pack.video_description,
                    duration=duration,
                    requested_model=self.settings.models.video_model_fast,
                    requested_resolution="768P",
                    generate_thumbnail=generate_thumbnail,
                    style=style,
                    video_kwargs=kwargs,
                )
                self._sync_video_plan_for_pack(pack)
                task_logger.step("生成视频", "完成", str(pack.video_path))

            # 步骤5: 生成音乐（需检查配额）
            if generate_music:
                music_skip_reason = self._music_skip_reason_for_automation()
                if music_skip_reason:
                    task_logger.step("生成音乐", "跳过", music_skip_reason)
                    self._record_music_skip(pack, music_skip_reason)
                elif self.settings.models.music_model:
                    self._check_quota("music")
                    task_logger.step("生成音乐", "进行中")
                    music_filename = self.file_manager.generate_filename(
                        prefix=topic_prefix, extension="mp3"
                    )
                    pack.music_path = self.music_api.generate_instrumental(
                        prompt=music_style,
                        output_path=str(content_dir / music_filename),
                    )
                    pack.apply_generation_metadata("music", self.music_api.last_request_metadata)
                    self._sync_video_plan_for_pack(pack)
                    task_logger.step("生成音乐", "完成", str(pack.music_path))
                else:
                    task_logger.step("生成音乐", "跳过", "当前配置未启用音乐模型")

            # 步骤6: 生成缩略图（需检查配额）
            if generate_thumbnail and not pack.thumbnail_path:
                self._check_quota("image")
                task_logger.step("生成缩略图", "进行中")
                thumbnail_filename = self.file_manager.generate_filename(
                    prefix=topic_prefix, extension="png"
                )
                pack.thumbnail_path = self.image_api.create_thumbnail(
                    prompt=f"{topic}, {style}",
                    output_path=str(content_dir / thumbnail_filename),
                )
                self._apply_image_stage_metadata(
                    pack,
                    stage="thumbnail",
                    output_path=pack.thumbnail_path,
                )
                self._sync_video_plan_for_pack(pack)
                task_logger.step("生成缩略图", "完成", str(pack.thumbnail_path))
            elif generate_thumbnail and pack.thumbnail_path:
                task_logger.step("生成缩略图", "复用", str(pack.thumbnail_path))

            task_logger.complete("内容包生成完成")
            self._save_pack_manifest(pack, status="succeeded")

        except QuotaExceededError as e:
            self._save_pack_manifest(pack, status="failed", error=str(e))
            task_logger.error(f"配额不足: {e.resource} {e.detail}", e)
            raise
        except Exception as e:
            self._save_pack_manifest(pack, status="failed", error=str(e))
            task_logger.error(f"内容包生成失败: {str(e)}", e)
            raise

        return pack

    def generate_video_series(
        self,
        topics: List[str],
        style: str = "轻松幽默",
        duration: int = 6,
        max_concurrent: int = 1,
        **kwargs,
    ) -> List[ContentPack]:
        """
        批量生成视频系列

        支持串行（max_concurrent=1）和并发（max_concurrent>1）两种模式。
        并发模式下多个视频任务会同时提交和轮询，提高效率。

        Args:
            topics: 主题列表
            style: 视频风格
            duration: 视频时长
            max_concurrent: 最大并发数（默认1为串行模式）
            **kwargs: 其他参数（传给 generate_content_pack）

        Returns:
            内容包列表（只包含成功的，失败的 topic 记录在日志）

        Example:
            >>> pipeline = PipelineOrchestrator()
            >>> packs = pipeline.generate_video_series(
            ...     topics=["咖啡", "旅行", "美食"],
            ...     max_concurrent=3
            ... )
        """
        logger.info(f"开始批量生成 {len(topics)} 个视频，并发数: {max_concurrent}")

        if max_concurrent <= 1:
            # 串行模式：逐个处理
            return self._generate_series_sequential(topics, style, duration, **kwargs)
        else:
            # 并发模式：同时处理多个
            return self._generate_series_concurrent(
                topics, style, duration, max_concurrent, **kwargs
            )

    def _generate_series_sequential(
        self, topics: List[str], style: str, duration: int, **kwargs
    ) -> List[ContentPack]:
        """串行批量生成"""
        packs = []
        for i, topic in enumerate(topics, 1):
            logger.info(f"处理第 {i}/{len(topics)} 个主题: {topic}")
            try:
                pack = self.generate_content_pack(
                    topic=topic, style=style, duration=duration, **kwargs
                )
                packs.append(pack)
            except QuotaExceededError as e:
                logger.error(f"主题 '{topic}' 配额不足，停止生成: {e}")
                break
            except Exception as e:
                logger.error(f"主题 '{topic}' 生成失败: {str(e)}")
                continue

            # 批量限速：每次生成后休息一段时间，避免高频触发 API 限制
            batch_delay = self.settings.api.batch_delay
            if batch_delay > 0:
                logger.debug(f"等待 {batch_delay} 秒后继续...")
                time.sleep(batch_delay)

        logger.info(f"批量生成完成，成功: {len(packs)}/{len(topics)}")
        return packs

    def _generate_series_concurrent(
        self,
        topics: List[str],
        style: str,
        duration: int,
        max_concurrent: int,
        **kwargs,
    ) -> List[ContentPack]:
        """
        并发批量生成（仅视频任务并发，文本/语音串行）

        策略：
        1. 先串行生成所有文本+语音+音乐（AI 文本模型不受并发影响）
        2. 再同时提交多个视频生成任务
        3. 并发轮询等待所有视频完成
        """
        logger.info(
            f"并发模式：文本/语音串行，视频任务并发（最多 {max_concurrent} 个）"
        )

        # ---- 阶段1：串行生成文本 + 语音 + 非视频资源 ----
        packs: List[ContentPack] = []

        for i, topic in enumerate(topics, 1):
            logger.info(f"[阶段1/2] 第 {i}/{len(topics)} 个主题（文本+语音）: {topic}")
            try:
                # 跳过视频，串行生成内容包的其他部分
                stage1_kwargs = dict(kwargs)
                stage1_kwargs["generate_video"] = False
                pack = self.generate_content_pack(
                    topic=topic, style=style, duration=duration, **stage1_kwargs
                )
                packs.append(pack)
            except QuotaExceededError as e:
                logger.error(f"主题 '{topic}' 配额不足，跳过: {e}")
                continue
            except Exception as e:
                logger.error(f"主题 '{topic}' 生成失败: {str(e)}")
                continue

            # 批量限速
            batch_delay = self.settings.api.batch_delay
            if batch_delay > 0:
                time.sleep(batch_delay)

        # ---- 阶段2：并发提交视频任务 ----
        if packs and any(p.video_description for p in packs):
            logger.info(
                f"[阶段2/2] 开始并发提交 {len(packs)} 个视频生成任务（最多 {max_concurrent} 并发）"
            )

            # 限制并发数，分批处理
            for batch_start in range(0, len(packs), max_concurrent):
                batch_packs = packs[batch_start : batch_start + max_concurrent]

                # 构建这批的视频任务
                batch_tasks = []
                for pack in batch_packs:
                    if not pack.video_description:
                        continue
                    if not self.settings.check_quota("video"):
                        logger.warning("视频配额已用尽，停止提交更多视频任务")
                        break

                    try:
                        task_id = self.video_api.generate_video_async(
                            prompt=pack.video_description, duration=duration
                        )
                        batch_tasks.append(
                            {
                                "pack": pack,
                                "task_id": task_id,
                                "duration": duration,
                                "routing_metadata": self.video_api.get_task_metadata(
                                    task_id
                                ),
                            }
                        )
                        logger.info(f"视频任务已提交: {pack.topic} -> {task_id}")
                    except Exception as e:
                        logger.error(f"视频任务提交失败 ({pack.topic}): {str(e)}")
                        pack.errors.append(f"视频提交失败: {e}")
                        continue

                # 并发等待这批视频完成
                if batch_tasks:
                    self._wait_video_batch(batch_tasks)

        logger.info(f"批量生成完成，成功: {len(packs)}/{len(topics)}")
        return packs

    def _wait_video_batch(self, tasks: List[Dict[str, Any]]):
        """
        并发轮询等待一组视频任务完成

        Args:
            tasks: 任务列表，每个包含 pack, task_id, duration
        """
        logger.info(f"开始等待 {len(tasks)} 个视频任务完成...")

        def poll_one(task_info: Dict[str, Any]):
            """线程函数：轮询单个任务"""
            pack = task_info["pack"]
            task_id = task_info["task_id"]
            routing_metadata = dict(task_info.get("routing_metadata") or {})
            video_api = VideoAPI()
            if routing_metadata:
                video_api.remember_task_metadata(task_id, routing_metadata)

            try:
                result = video_api.wait_for_completion(task_id)

                # 下载视频
                video_filename = self.file_manager.generate_filename(
                    prefix=pack.topic, extension="mp4"
                )
                output_path = (
                    pack.content_dir / video_filename
                    if pack.content_dir
                    else self.file_manager.get_output_path(
                        "videos",
                        video_filename,
                        content_index=pack.content_index,
                    )
                )
                video_path = video_api.download_video(
                    status_info=result, output_path=str(output_path)
                )
                pack.video_path = video_path
                pack.apply_generation_metadata("video", video_api.last_request_metadata)
                self._save_pack_manifest(pack, status="succeeded")
                logger.info(f"视频下载完成: {pack.topic} -> {video_path}")
                return True, pack, None
            except TimeoutError as e:
                logger.error(f"视频生成超时: {pack.topic} ({task_id})")
                pack.errors.append(f"视频超时: {e}")
                self._save_pack_manifest(pack, status="failed", error=str(e))
                return False, pack, str(e)
            except Exception as e:
                logger.error(f"视频生成失败: {pack.topic} ({task_id}): {str(e)}")
                pack.errors.append(f"视频失败: {e}")
                self._save_pack_manifest(pack, status="failed", error=str(e))
                return False, pack, str(e)
            finally:
                video_api.close()

        # 使用线程池并发轮询
        with ThreadPoolExecutor(max_workers=len(tasks)) as executor:
            futures = {executor.submit(poll_one, task): task for task in tasks}
            for future in as_completed(futures):
                try:
                    success, pack, error = future.result()
                    if not success:
                        logger.warning(f"视频任务失败: {pack.topic} - {error}")
                except Exception as e:
                    logger.error(f"线程执行异常: {str(e)}")

        logger.info("视频批量轮询完成")

    def get_quota_status(self) -> Dict[str, Any]:
        """获取当前配额状态"""
        return self.settings.get_quota_status()

    def generate_text_only(
        self, topic: str, style: str = "轻松幽默", duration: int = 6
    ) -> ContentPack:
        """
        仅生成文本内容（脚本和标题）

        Args:
            topic: 内容主题
            style: 视频风格
            duration: 视频时长

        Returns:
            内容包（仅包含文本）
        """
        pack = ContentPack(topic=topic)

        # 生成脚本
        script_data = self.text_api.generate_script(
            topic=topic, style=style, duration=duration
        )
        pack.script = script_data.get("raw_content", "")
        pack.video_description = script_data.get("video_description", "")
        pack.narration = script_data.get("narration", "")

        # 生成标题
        pack.titles = self.text_api.generate_titles(topic=topic, count=5)

        return pack

    def generate_audio_only(
        self,
        text: str,
        voice: Optional[str] = None,
        output_filename: Optional[str] = None,
    ) -> Path:
        """
        仅生成语音

        Args:
            text: 要合成的文本
            voice: 音色
            output_filename: 输出文件名

        Returns:
            音频文件路径
        """
        if output_filename is None:
            output_filename = self.file_manager.generate_filename(
                prefix="audio", extension="mp3"
            )

        return self.speech_api.synthesize_to_file(
            text=text,
            output_path=str(
                self.file_manager.get_output_path("audios", output_filename)
            ),
            voice_id=voice or self.settings.auto.content_strategy.default_voice,
        )

    def generate_video_only(
        self,
        prompt: str,
        duration: int = 6,
        resolution: str = "768P",
        output_filename: Optional[str] = None,
    ) -> Path:
        """
        仅生成视频（检查配额）

        Args:
            prompt: 视频描述
            duration: 视频时长
            resolution: 分辨率
            output_filename: 输出文件名

        Returns:
            视频文件路径

        Raises:
            QuotaExceededError: 视频配额不足
        """
        self._check_quota("video")

        if output_filename is None:
            output_filename = self.file_manager.generate_filename(
                prefix="video", extension="mp4"
            )

        path = self.video_api.generate_video(
            prompt=prompt,
            output_path=str(
                self.file_manager.get_output_path("videos", output_filename)
            ),
            duration=duration,
            resolution=resolution,
        )
        return path

    def generate_music_only(
        self,
        prompt: str,
        lyrics: Optional[str] = None,
        is_instrumental: bool = False,
        output_filename: Optional[str] = None,
    ) -> Path:
        """
        仅生成音乐（检查配额）

        Args:
            prompt: 音乐描述
            lyrics: 歌词
            is_instrumental: 是否纯音乐
            output_filename: 输出文件名

        Returns:
            音乐文件路径

        Raises:
            QuotaExceededError: 音乐配额不足
        """
        if is_instrumental and not self.settings.models.supports_music_instrumental():
            raise ValueError(
                "当前 Token Plan 音乐仅支持 music-2.6 歌曲生成，不支持纯音乐。"
            )

        self._check_quota("music")

        if output_filename is None:
            output_filename = self.file_manager.generate_filename(
                prefix="music", extension="mp3"
            )

        if is_instrumental:
            path = self.music_api.generate_instrumental(
                prompt=prompt,
                output_path=str(
                    self.file_manager.get_output_path("music", output_filename)
                ),
            )
        else:
            path = self.music_api.generate_to_file(
                prompt=prompt,
                lyrics=lyrics,
                output_path=str(
                    self.file_manager.get_output_path("music", output_filename)
                ),
            )
        return path

    def generate_image_only(
        self,
        prompt: str,
        aspect_ratio: str = "1:1",
        output_filename: Optional[str] = None,
    ) -> Path:
        """
        仅生成图片（检查配额）

        Args:
            prompt: 图片描述
            aspect_ratio: 图片比例
            output_filename: 输出文件名

        Returns:
            图片文件路径

        Raises:
            QuotaExceededError: 图片配额不足
        """
        self._check_quota("image")

        if output_filename is None:
            output_filename = self.file_manager.generate_filename(
                prefix="image", extension="png"
            )

        path = self.image_api.generate_to_file(
            prompt=prompt,
            output_path=str(
                self.file_manager.get_output_path("images", output_filename)
            ),
            aspect_ratio=aspect_ratio,
        )
        return path

    def close(self):
        """关闭所有 API 客户端"""
        self.text_api.close()
        self.speech_api.close()
        self.video_api.close()
        self.music_api.close()
        self.image_api.close()

        logger.info("Pipeline 协调器已关闭")

    def __enter__(self):
        """上下文管理器入口"""
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        """上下文管理器出口"""
        self.close()
