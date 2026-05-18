# -*- coding: utf-8 -*-
"""
视频合成模块

功能：
1. 将视频、音频、音乐、字幕合并为最终成品
2. 支持视频封面设置
3. 自动输出抖音适配规格

用法：
>>> from src.video_editor import VideoComposer
>>> composer = VideoComposer()
>>> final = composer.compose_final_video(
...     video_path="some_run/001/xxx.mp4",
...     audio_path="some_run/001/xxx.mp3",
...     music_path="some_run/001/music.mp3",
...     srt_path="some_run/001/subtitle.srt",
...     output_path="some_run/001/final.mp4"
... )
"""

import subprocess
import logging
import shutil
from fractions import Fraction
from pathlib import Path
from typing import Optional

from .subtitle import SubtitleGenerator
from config.settings import get_settings


logger = logging.getLogger(__name__)


class VideoComposer:
    """
    视频合成器

    将多个素材（视频、语音、音乐、字幕）合并为抖音-ready 的最终视频。

    支持的工作流：
    1. 视频 + 语音 → 替换/混合音频
    2. 视频 + 语音 + 背景音乐 → 混音（语音优先，背景音乐低声）
    3. 视频 + 语音 + 音乐 + 字幕 → 全套合成
    """

    def __init__(self, output_dir: Optional[Path] = None):
        self.settings = get_settings()
        self.output_dir = Path(output_dir) if output_dir else None
        self.subtitle_gen = SubtitleGenerator(output_dir=self.output_dir)

    def compose_final_video(
        self,
        video_path: str,
        audio_path: Optional[str] = None,
        music_path: Optional[str] = None,
        srt_path: Optional[str] = None,
        output_path: Optional[str] = None,
        video_volume: float = 0.0,
        voice_volume: float = 1.0,
        music_volume: float = 0.25,
        subtitle_style: str = "douyin",
        preset: str = "fast",
        crf: int = 23,
        **kwargs,
    ) -> Path:
        """
        合成最终视频

        Args:
            video_path:    原始视频路径
            audio_path:    语音旁白路径（MP3/WAV）
            music_path:    背景音乐路径（MP3/WAV）
            srt_path:      SRT 字幕文件路径
            output_path:   输出路径（自动生成 if None）
            video_volume:  原视频音量（0 = 无声，1 = 原始）
            voice_volume:  语音音量倍数（默认 1.0）
            music_volume:  背景音乐音量倍数（默认 0.25，较小避免干扰语音）
            subtitle_style: 字幕样式 ("douyin" / "simple" / "yellow")
            preset:        ffmpeg 编码速度（ultrafast, fast, medium, slow）
            crf:           视频质量（0 无损 → 51 最差，23 为默认）

        Returns:
            最终视频路径
        """
        video_path = Path(video_path)
        if not video_path.exists():
            raise FileNotFoundError(f"视频文件不存在: {video_path}")

        # 自动生成输出路径
        if output_path is None:
            base_dir = self.output_dir or video_path.parent
            output_path = base_dir / f"{video_path.stem}_final.mp4"
        else:
            output_path = Path(output_path)
        output_path.parent.mkdir(parents=True, exist_ok=True)
        temp_mix_path: Optional[Path] = None

        # 确定最终音频来源
        has_voice = audio_path and Path(audio_path).exists()
        has_music = music_path and Path(music_path).exists()

        try:
            if has_voice:
                # 需要混音：将语音和音乐混合
                if has_music:
                    logger.info("混音模式：语音 + 背景音乐")
                    temp_mix_path = (
                        output_path.parent / f"{output_path.stem}_mixed_audio.mp3"
                    )
                    mix_path = self._mix_audio(
                        voice_path=audio_path,
                        music_path=music_path,
                        voice_volume=voice_volume,
                        music_volume=music_volume,
                        output_path=temp_mix_path,
                    )
                    final_audio_path = mix_path
                else:
                    final_audio_path = audio_path

                # 用混音后的音频替换视频音轨（或混合）
                output_path = self._merge_video_audio(
                    video_path=str(video_path),
                    audio_path=final_audio_path,
                    video_volume=video_volume,
                    output_path=str(output_path),
                    preset=preset,
                    crf=crf,
                )
            else:
                # 纯视频（无语音）
                if has_music:
                    output_path = self._merge_video_audio(
                        video_path=str(video_path),
                        audio_path=music_path,
                        video_volume=video_volume,
                        output_path=str(output_path),
                        preset=preset,
                        crf=crf,
                    )
                else:
                    # 无需音频处理，直接复制视频
                    if Path(output_path) != video_path:
                        shutil.copy(video_path, output_path)
                    else:
                        output_path = video_path

            # 字幕烧录（最后一步，避免重新编码整个视频）
            if srt_path and Path(srt_path).exists():
                output_path = self.subtitle_gen.burn_subtitles(
                    video_path=str(output_path),
                    srt_path=srt_path,
                    output_path=str(output_path).replace(".mp4", "_subtitled.mp4"),
                    style=subtitle_style,
                )

            logger.info(f"最终视频已生成: {output_path}")
            return Path(output_path)
        finally:
            if temp_mix_path and temp_mix_path.exists():
                try:
                    temp_mix_path.unlink()
                except OSError:
                    logger.warning(f"临时混音文件清理失败: {temp_mix_path}")

    def compose_with_voice_mixing(
        self,
        video_path: str,
        audio_path: str,
        music_path: Optional[str] = None,
        srt_path: Optional[str] = None,
        output_path: Optional[str] = None,
        voice_volume: float = 1.0,
        music_volume: float = 0.25,
        subtitle_style: str = "douyin",
    ) -> Path:
        """
        以语音为主的混音模式（推荐用于配音类视频）

        语音音量为 100%，背景音乐始终低声（25%），不影响听感。
        """
        return self.compose_final_video(
            video_path=video_path,
            audio_path=audio_path,
            music_path=music_path,
            srt_path=srt_path,
            output_path=output_path,
            video_volume=0.0,
            voice_volume=voice_volume,
            music_volume=music_volume,
            subtitle_style=subtitle_style,
        )

    def _mix_audio(
        self,
        voice_path: str,
        music_path: str,
        voice_volume: float,
        music_volume: float,
        output_path: Path,
    ) -> Path:
        """
        使用 ffmpeg 混合语音和背景音乐

        Args:
            voice_path:    语音文件路径
            music_path:    背景音乐文件路径
            voice_volume:  语音音量
            music_volume:  背景音乐音量
            output_path:   输出文件路径

        Returns:
            混合后的音频文件路径
        """
        mix_output = Path(output_path)
        mix_output.parent.mkdir(parents=True, exist_ok=True)

        # 先把音乐延长/裁剪到与语音等长
        # 然后混合：语音在前，音乐低声铺底
        cmd = [
            "ffmpeg",
            "-y",
            "-i",
            str(voice_path),
            "-i",
            str(music_path),
            # 滤镜：调整音量后混合
            "-filter_complex",
            f"[1:a]volume={music_volume}[music];"
            f"[0:a]volume={voice_volume}[voice];"
            f"[voice][music]amix=inputs=2:duration=first:dropout_transition=2[aout]",
            "-map",
            "[aout]",
            "-c:a",
            "libmp3lame",
            "-q:a",
            "2",
            str(mix_output),
        ]

        logger.info(f"混音中: 语音 {voice_volume}x + 背景音乐 {music_volume}x")
        result = subprocess.run(
            cmd, capture_output=True, text=True, encoding="utf-8", errors="replace"
        )

        if result.returncode != 0:
            logger.error(f"混音失败: {result.stderr[-500:]}")
            raise RuntimeError(f"混音失败: {result.stderr[-300:]}")

        logger.info(f"混音完成: {mix_output}")
        return mix_output

    def _merge_video_audio(
        self,
        video_path: str,
        audio_path: str,
        video_volume: float,
        output_path: str,
        preset: str,
        crf: int,
    ) -> Path:
        """
        将音频与视频合并

        Args:
            video_path:  视频路径
            audio_path:  音频路径
            video_volume: 原视频音量（0 = 静音替换）
            output_path: 输出路径
            preset:      编码速度
            crf:         质量

        Returns:
            合并后的视频路径
        """
        output_path = Path(output_path)

        if video_volume == 0:
            # 替换音轨：移除原视频音频，替换为新音频
            cmd = [
                "ffmpeg",
                "-y",
                "-i",
                str(video_path),
                "-i",
                str(audio_path),
                "-map",
                "0:v",
                "-map",
                "1:a",
                "-c:v",
                "copy",
                "-c:a",
                "aac",
                "-b:a",
                "192k",
                "-shortest",
                str(output_path),
            ]
        else:
            # 混合音轨：新音频 + 原视频音频
            cmd = [
                "ffmpeg",
                "-y",
                "-i",
                str(video_path),
                "-i",
                str(audio_path),
                "-filter_complex",
                f"[0:a]volume={video_volume}[orig];[1:a][orig]amix=inputs=2:duration=first[aout]",
                "-map",
                "0:v",
                "-map",
                "[aout]",
                "-c:v",
                "copy",
                "-c:a",
                "aac",
                "-b:a",
                "192k",
                "-shortest",
                str(output_path),
            ]

        logger.info(f"合并视频+音频: {video_path} + {audio_path}")
        result = subprocess.run(
            cmd, capture_output=True, text=True, encoding="utf-8", errors="replace"
        )

        if result.returncode != 0:
            logger.warning(f"合并失败（尝试替代方案）: {result.stderr[-300:]}")
            # 备选：直接替换音轨
            cmd_fallback = [
                "ffmpeg",
                "-y",
                "-i",
                str(video_path),
                "-i",
                str(audio_path),
                "-map",
                "0:v",
                "-map",
                "1:a",
                "-c:v",
                "copy",
                "-c:a",
                "aac",
                "-b:a",
                "192k",
                "-shortest",
                str(output_path),
            ]
            result = subprocess.run(
                cmd_fallback,
                capture_output=True,
                text=True,
                encoding="utf-8",
                errors="replace",
            )
            if result.returncode != 0:
                raise RuntimeError(f"视频音频合并失败: {result.stderr[-300:]}")

        logger.info(f"视频合并完成: {output_path}")
        return output_path

    def set_video_cover(
        self,
        video_path: str,
        thumbnail_path: Optional[str] = None,
        timestamp: str = "00:00:01",
        output_path: Optional[str] = None,
    ) -> Path:
        """
        设置视频封面（抖音需要上传封面图）

        方式一：用指定的缩略图作为封面
        方式二：从视频指定时间点截取一帧作为封面

        Args:
            video_path:      视频路径
            thumbnail_path:  缩略图路径（方式一）
            timestamp:       截取时间点（方式二，格式 HH:MM:SS）
            output_path:    输出路径

        Returns:
            封面图路径
        """
        video_path = Path(video_path)
        if output_path is None:
            base_dir = self.output_dir or video_path.parent
            output_path = base_dir / f"{video_path.stem}_cover.jpg"
        else:
            output_path = Path(output_path)
        output_path.parent.mkdir(parents=True, exist_ok=True)

        if thumbnail_path:
            # 使用现成的缩略图
            thumbnail_file = Path(thumbnail_path)
            if thumbnail_file.resolve() == output_path.resolve():
                logger.info(f"封面已存在: {output_path}")
                return output_path
            shutil.copy(thumbnail_path, output_path)
            logger.info(f"封面已设置: {output_path}")
            return output_path

        # 从视频截取指定时间点的帧
        cmd = [
            "ffmpeg",
            "-y",
            "-ss",
            timestamp,
            "-i",
            str(video_path),
            "-vframes",
            "1",
            "-q:v",
            "2",
            "-y",
            str(output_path),
        ]

        result = subprocess.run(
            cmd, capture_output=True, text=True, encoding="utf-8", errors="replace"
        )

        if result.returncode != 0:
            raise RuntimeError(f"封面截取失败: {result.stderr[-300:]}")

        logger.info(f"封面已截取（{timestamp}）: {output_path}")
        return output_path

    def get_video_info(self, video_path: str) -> dict:
        """获取视频信息（时长、分辨率、帧率等）"""
        cmd = [
            "ffprobe",
            "-v",
            "quiet",
            "-print_format",
            "json",
            "-show_format",
            "-show_streams",
            str(video_path),
        ]

        result = subprocess.run(
            cmd, capture_output=True, text=True, encoding="utf-8", errors="replace"
        )

        if result.returncode != 0:
            return {}

        import json

        data = json.loads(result.stdout)

        video_stream = next(
            (s for s in data.get("streams", []) if s.get("codec_type") == "video"), {}
        )
        format_info = data.get("format", {})

        return {
            "duration": float(format_info.get("duration", 0)),
            "size": int(format_info.get("size", 0)),
            "width": int(video_stream.get("width", 0)),
            "height": int(video_stream.get("height", 0)),
            "fps": float(Fraction(video_stream.get("r_frame_rate", "0/1"))),
            "codec": video_stream.get("codec_name", ""),
        }

    def get_media_duration(self, media_path: str) -> float:
        """获取任意媒体文件时长（秒）。"""
        info = self.get_video_info(media_path)
        return float(info.get("duration", 0) or 0)
