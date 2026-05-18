# -*- coding: utf-8 -*-
"""
字幕生成模块

功能：
1. 使用 MiniMax TTS 响应中的 word-level timestamps 生成 SRT 字幕
2. 使用 ffmpeg 将 SRT 字幕烧录（burn-in）到视频中

用法：
>>> from src.video_editor import SubtitleGenerator
>>> gen = SubtitleGenerator()
>>> srt_path = gen.generate_srt(text="旁白文本", output_path="some_run/001/subtitle.srt")
>>> burned = gen.burn_subtitles(video_path="some_run/001/final.mp4", srt_path=str(srt_path))
"""

import logging
import json
import re
import subprocess
from pathlib import Path
from typing import Optional, List, Dict, Any

from config.settings import get_settings


logger = logging.getLogger(__name__)


class SubtitleGenerator:
    """
    字幕生成器

    支持两种模式：
    1. word_timestamps 模式：使用 MiniMax TTS API 返回的词级时间戳（精度最高）
    2. estimate 模式：根据文本长度和语速估算每个字的时长（无需额外 API 调用）
    """

    # 每行字幕的字数上限（抖音最佳实践）
    CHARS_PER_LINE = 15

    # 每行字幕持续的最短秒数
    MIN_DURATION_PER_LINE = 1.0

    # 默认语速（字/秒），中文正常语速约 5-7 字/秒
    DEFAULT_SPEED = 5.5

    def __init__(self, output_dir: Optional[Path] = None):
        self.settings = get_settings()
        self.output_dir = Path(output_dir) if output_dir else None

    # ------------------------------------------------------------------ #
    #  公开 API
    # ------------------------------------------------------------------ #

    def generate_srt(
        self,
        text: str,
        output_path: Optional[str] = None,
        speed: Optional[float] = None,
        target_duration: Optional[float] = None,
        prefix: str = "subtitle",
    ) -> Path:
        """
        根据文本生成 SRT 字幕文件（估算模式）

        Args:
            text:       旁白文本
            output_path: 输出 .srt 文件路径（自动生成 if None）
            speed:      语速（字/秒），None 则使用默认
            prefix:     自动生成文件名时的前缀

        Returns:
            .srt 文件路径
        """
        if speed is None:
            speed = self.DEFAULT_SPEED

        if target_duration and target_duration > 0:
            effective_chars = max(
                1,
                len(re.sub(r"\s+", "", text or "")),
            )
            calibrated_speed = effective_chars / target_duration
            speed = max(2.0, min(calibrated_speed, 8.5))

        if output_path is None:
            if self.output_dir is not None:
                output_path = str(self.output_dir / f"{prefix}.srt")
            else:
                output_path = f"{prefix}.srt"

        segments = self._split_text_to_segments(text, speed)
        srt_content = self._build_srt(segments)

        Path(output_path).parent.mkdir(parents=True, exist_ok=True)
        with open(output_path, "w", encoding="utf-8") as f:
            f.write(srt_content)

        logger.info(
            f"SRT 字幕已生成: {output_path}（{len(segments)} 句, 语速 {speed:.2f} 字/秒）"
        )
        return Path(output_path)

    def generate_srt_from_timestamps(
        self,
        word_timestamps: List[Dict[str, Any]],
        output_path: Optional[str] = None,
        prefix: str = "subtitle",
    ) -> Path:
        """
        根据 MiniMax TTS 返回的词级时间戳生成 SRT 字幕（精度最高）

        Args:
            word_timestamps: MiniMax TTS 响应中每个词的时间戳列表
                             格式: [{"word": "你", "start": 0.0, "end": 0.3}, ...]
            output_path:     输出 .srt 文件路径
            prefix:          自动生成文件名时的前缀

        Returns:
            .srt 文件路径
        """
        if output_path is None:
            if self.output_dir is not None:
                output_path = str(self.output_dir / f"{prefix}.srt")
            else:
                output_path = f"{prefix}.srt"

        # 按行分组
        lines = self._group_words_into_lines(word_timestamps)
        segments = self._timestamps_to_segments(lines)
        srt_content = self._build_srt(segments)

        Path(output_path).parent.mkdir(parents=True, exist_ok=True)
        with open(output_path, "w", encoding="utf-8") as f:
            f.write(srt_content)

        logger.info(
            f"SRT 字幕已生成（时间戳模式）: {output_path}（{len(segments)} 句）"
        )
        return Path(output_path)

    def generate_srt_from_whisperx_json(
        self,
        json_path: str,
        output_path: Optional[str] = None,
        prefix: str = "subtitle",
    ) -> Path:
        """
        从 WhisperX 对齐结果 JSON 生成 SRT。

        兼容 WhisperX 常见结构：
        - {"segments": [{"words": [{"word": "...", "start": 0.1, "end": 0.3}]}]}
        - {"segments": [{"text": "...", "start": 0.1, "end": 1.2}]}
        """
        payload = json.loads(Path(json_path).read_text(encoding="utf-8"))
        return self.generate_srt_from_whisperx_result(
            payload,
            output_path=output_path,
            prefix=prefix,
        )

    def generate_srt_from_whisperx_result(
        self,
        result: Dict[str, Any],
        output_path: Optional[str] = None,
        prefix: str = "subtitle",
    ) -> Path:
        """从 WhisperX transcribe/align 结果生成 SRT。"""
        word_timestamps = self._extract_whisperx_word_timestamps(result)
        if word_timestamps:
            return self.generate_srt_from_timestamps(
                word_timestamps,
                output_path=output_path,
                prefix=prefix,
            )

        segments = self._extract_whisperx_segments(result)
        if not segments:
            raise ValueError("WhisperX 结果中没有可用的 words 或 segments")

        if output_path is None:
            if self.output_dir is not None:
                output_path = str(self.output_dir / f"{prefix}.srt")
            else:
                output_path = f"{prefix}.srt"

        srt_content = self._build_srt(segments)
        Path(output_path).parent.mkdir(parents=True, exist_ok=True)
        Path(output_path).write_text(srt_content, encoding="utf-8")
        logger.info(f"SRT 字幕已生成（WhisperX 段落模式）: {output_path}")
        return Path(output_path)

    def generate_srt_from_audio(
        self,
        audio_path: str,
        output_path: Optional[str] = None,
        text_fallback: Optional[str] = None,
        engine: str = "estimate",
        language: str = "zh",
        model_size: str = "base",
        device: str = "cpu",
    ) -> Path:
        """
        从音频生成字幕。

        `engine="whisperx"` 时会尝试使用本地安装的 whisperx；未安装或执行失败时，
        如果提供了 text_fallback，则回退到估算模式，避免自动流程整体失败。
        """
        resolved_engine = (engine or "estimate").strip().lower()
        if resolved_engine == "whisperx":
            try:
                result = self._transcribe_with_whisperx(
                    audio_path=audio_path,
                    language=language,
                    model_size=model_size,
                    device=device,
                )
                word_json_path = Path(output_path or "subtitle.srt").with_name(
                    "word_timestamps.json"
                )
                word_json_path.write_text(
                    json.dumps(result, ensure_ascii=False, indent=2),
                    encoding="utf-8",
                )
                return self.generate_srt_from_whisperx_result(
                    result,
                    output_path=output_path,
                )
            except Exception as exc:
                if not text_fallback:
                    raise
                logger.warning(
                    "WhisperX 字幕生成失败，回退到估算字幕: %s",
                    exc,
                )

        if not text_fallback:
            raise ValueError("估算字幕需要 text_fallback")
        return self.generate_srt(text=text_fallback, output_path=output_path)

    def generate_ass_karaoke_from_word_timestamps(
        self,
        word_timestamps: List[Dict[str, Any]],
        output_path: str,
        style: str = "douyin",
    ) -> Path:
        """
        生成带 ASS karaoke 标签的逐词高亮字幕草稿。

        这不会自动烧录视频，但为后续卡点/逐字高亮保留精确时间信息。
        """
        srt_path = Path(output_path).with_suffix(".srt")
        self.generate_srt_from_timestamps(word_timestamps, output_path=str(srt_path))
        ass_path = self._convert_srt_to_ass(srt_path, style=style)
        output = Path(output_path)
        if ass_path != output:
            output.write_text(ass_path.read_text(encoding="utf-8"), encoding="utf-8")
        return output

    def burn_subtitles(
        self,
        video_path: str,
        srt_path: str,
        output_path: Optional[str] = None,
        style: str = "douyin",
    ) -> Path:
        """
        将 SRT 字幕烧录到视频中（使用 ffmpeg）

        Args:
            video_path:  输入视频路径
            srt_path:    SRT 字幕文件路径
            output_path: 输出路径（自动为 video_path + "_with_subs.mp4"）
            style:       字幕样式预设
                         - "douyin": 白色大字，底部居中，抖音风格
                         - "simple": 简洁白色小字
                         - "yellow": 黄色描边

        Returns:
            烧录后的视频路径
        """
        video_path = Path(video_path)
        srt_path = Path(srt_path)

        if not video_path.exists():
            raise FileNotFoundError(f"视频文件不存在: {video_path}")
        if not srt_path.exists():
            raise FileNotFoundError(f"字幕文件不存在: {srt_path}")

        if output_path is None:
            output_path = video_path.parent / f"{video_path.stem}_with_subs.mp4"
        else:
            output_path = Path(output_path)

        # ffmpeg 字幕烧录滤镜
        # 使用 drawtext 将字幕绘制到视频上（ASS 格式支持换行和样式）
        ass_path = self._convert_srt_to_ass(srt_path, style=style)
        ass_filter_path = self._escape_filter_path(ass_path)

        cmd = [
            "ffmpeg",
            "-y",  # 覆盖输出文件
            "-i",
            str(video_path),  # 输入视频
            "-vf",
            f"ass='{ass_filter_path}'",  # 字幕滤镜
            "-c:a",
            "copy",  # 不重新编码音频
            "-preset",
            "fast",
            "-crf",
            "23",
            str(output_path),
        ]

        logger.info(f"烧录字幕到视频: {' '.join(cmd[:8])}...")
        result = subprocess.run(
            cmd, capture_output=True, text=True, encoding="utf-8", errors="replace"
        )

        if result.returncode != 0:
            logger.error(f"ffmpeg 烧录失败: {result.stderr[-500:]}")
            raise RuntimeError(f"ffmpeg 烧录失败: {result.stderr[-300:]}")

        logger.info(f"字幕已烧录: {output_path}")
        return output_path

    # ------------------------------------------------------------------ #
    #  内部方法
    # ------------------------------------------------------------------ #

    def _split_text_to_segments(self, text: str, speed: float) -> List[Dict[str, Any]]:
        """
        将长文本切分为字幕段落（估算模式）

        策略：
        - 按标点（。！？；）或空格切分句子
        - 每个句子根据字数估算持续时间
        - 超过 CHARS_PER_LINE 的长句进一步拆分
        """
        # 清理文本
        text = re.sub(r"[\r\n]+", " ", text)
        text = re.sub(r"\s+", " ", text).strip()

        # 按标点和空格切分句子
        sentence_pattern = re.compile(r"(?<=[。！？；.!?;])\s*")
        raw_sentences = sentence_pattern.split(text)

        segments = []
        current_time = 0.0

        for sentence in raw_sentences:
            sentence = sentence.strip()
            if not sentence:
                continue

            # 如果单句超过一行上限，按语义进一步拆分
            while len(sentence) > self.CHARS_PER_LINE:
                # 按语义（词语边界）拆分，优先在标点处截断
                chunk = sentence[: self.CHARS_PER_LINE]
                # 回溯找到最后一个合适断点
                break_pos = self._find_break_pos(chunk)
                if break_pos < 3:
                    break_pos = self.CHARS_PER_LINE  # 没有好断点则硬切

                line_text = sentence[:break_pos].strip()
                sentence = sentence[break_pos:].strip()

                char_count = len(line_text)
                duration = max(char_count / speed, self.MIN_DURATION_PER_LINE)
                segments.append(
                    {
                        "text": line_text,
                        "start": round(current_time, 2),
                        "end": round(current_time + duration, 2),
                    }
                )
                current_time += duration

            # 处理剩余句子
            if sentence:
                char_count = len(sentence)
                duration = max(char_count / speed, self.MIN_DURATION_PER_LINE)
                segments.append(
                    {
                        "text": sentence,
                        "start": round(current_time, 2),
                        "end": round(current_time + duration, 2),
                    }
                )
                current_time += duration

        return segments

    def _extract_whisperx_word_timestamps(
        self,
        result: Dict[str, Any],
    ) -> List[Dict[str, Any]]:
        words: List[Dict[str, Any]] = []
        for segment in result.get("segments", []) or []:
            for word_info in segment.get("words", []) or []:
                word = str(word_info.get("word") or word_info.get("text") or "").strip()
                start = word_info.get("start")
                end = word_info.get("end")
                if not word or start is None or end is None:
                    continue
                words.append({"word": word, "start": float(start), "end": float(end)})
        return words

    def _extract_whisperx_segments(
        self,
        result: Dict[str, Any],
    ) -> List[Dict[str, Any]]:
        segments: List[Dict[str, Any]] = []
        for segment in result.get("segments", []) or []:
            text = str(segment.get("text") or "").strip()
            start = segment.get("start")
            end = segment.get("end")
            if not text or start is None or end is None:
                continue
            segments.append(
                {
                    "text": text,
                    "start": round(float(start), 2),
                    "end": round(float(end), 2),
                }
            )
        return segments

    def _transcribe_with_whisperx(
        self,
        *,
        audio_path: str,
        language: str,
        model_size: str,
        device: str,
    ) -> Dict[str, Any]:
        try:
            import whisperx  # type: ignore
        except ImportError as exc:
            raise RuntimeError(
                "未安装 whisperx；如需启用，请在独立环境安装 whisperx 及其 PyTorch 依赖。"
            ) from exc

        audio = whisperx.load_audio(str(audio_path))
        model = whisperx.load_model(model_size, device, compute_type="float32")
        result = model.transcribe(audio, language=language)
        align_language = result.get("language") or language
        model_a, metadata = whisperx.load_align_model(
            language_code=align_language,
            device=device,
        )
        return whisperx.align(
            result["segments"],
            model_a,
            metadata,
            audio,
            device,
            return_char_alignments=False,
        )

    def _find_break_pos(self, text: str) -> int:
        """在文本末尾找到一个合适的断点（词语边界）"""
        # 标点符号优先
        punct_markers = ["，", "、", "：", ")", "）", "]", "】", "》", "—"]
        for i in range(len(text) - 1, -1, -1):
            if text[i] in punct_markers:
                return i + 1

        # 尝试找到空格断点
        for i in range(len(text) - 1, -1, -1):
            if text[i] == " ":
                return i

        return len(text)

    def _group_words_into_lines(
        self, word_timestamps: List[Dict[str, Any]]
    ) -> List[Dict[str, Any]]:
        """将词级时间戳合并为字幕行（每行不超过 CHARS_PER_LINE 字）"""
        lines: List[Dict[str, Any]] = []
        current_line_words: List[Dict[str, Any]] = []
        current_char_count = 0

        for word_info in word_timestamps:
            word = word_info.get("word", "")
            word_len = len(word.replace(" ", ""))

            if (
                current_char_count + word_len > self.CHARS_PER_LINE
                and current_line_words
            ):
                # 当前行已满，合并
                lines.append(self._merge_line(current_line_words))
                current_line_words = []
                current_char_count = 0

            current_line_words.append(word_info)
            current_char_count += word_len

        # 最后一行
        if current_line_words:
            lines.append(self._merge_line(current_line_words))

        return lines

    def _merge_line(self, words: List[Dict[str, Any]]) -> Dict[str, Any]:
        """将一组词合并为一行字幕"""
        text = "".join(w.get("word", "") for w in words)
        start = words[0].get("start", 0.0)
        end = words[-1].get("end", 0.0)
        return {"text": text.strip(), "start": start, "end": end}

    def _timestamps_to_segments(
        self, lines: List[Dict[str, Any]]
    ) -> List[Dict[str, Any]]:
        """将带时间戳的行转换为 SRT 段落"""
        # 时间戳模式不需要额外估算，直接用原始时间戳
        # 确保每段有最小持续时间
        segments = []
        for line in lines:
            start = float(line.get("start", 0))
            end = float(line.get("end", start + self.MIN_DURATION_PER_LINE))
            # 确保最小持续时间
            if end - start < self.MIN_DURATION_PER_LINE:
                end = start + self.MIN_DURATION_PER_LINE
            segments.append(
                {
                    "text": line["text"],
                    "start": round(start, 2),
                    "end": round(end, 2),
                }
            )
        return segments

    def _build_srt(self, segments: List[Dict[str, Any]]) -> str:
        """将字幕段落列表生成为 SRT 格式文本"""
        lines = []
        for i, seg in enumerate(segments, 1):
            start_ts = self._format_timestamp(seg["start"])
            end_ts = self._format_timestamp(seg["end"])
            lines.append(f"{i}")
            lines.append(f"{start_ts} --> {end_ts}")
            lines.append(seg["text"])
            lines.append("")
        return "\n".join(lines)

    def _format_timestamp(self, seconds: float) -> str:
        """将秒数格式化为 SRT 时间戳 HH:MM:SS,mmm"""
        hours = int(seconds // 3600)
        minutes = int((seconds % 3600) // 60)
        secs = int(seconds % 60)
        millis = int((seconds - int(seconds)) * 1000)
        return f"{hours:02d}:{minutes:02d}:{secs:02d},{millis:03d}"

    def _escape_filter_path(self, path: Path) -> str:
        normalized = path.resolve().as_posix()
        return (
            normalized.replace("\\", "/")
            .replace(":", r"\:")
            .replace("'", r"\'")
            .replace("[", r"\[")
            .replace("]", r"\]")
            .replace(",", r"\,")
        )

    def _convert_srt_to_ass(self, srt_path: Path, style: str = "douyin") -> Path:
        """
        将 SRT 转换为 ASS 格式（支持更多字幕样式）

        抖音风格：白色大字，底部居中，黑色描边
        """
        ass_path = srt_path.with_suffix(".ass")

        # ASS 字幕样式预设
        style_configs = {
            "douyin": {
                "font": "Microsoft YaHei",
                "fontsize": "52",
                "primary_color": "&H00FFFFFF",  # 白色
                "outline_color": "&H00000000",  # 黑色描边
                "outline": "2",
                "shadow": "1",
                "alignment": "2",  # 底部居中
                "margin_l": "20",
                "margin_r": "20",
                "margin_v": "20",
            },
            "simple": {
                "font": "Microsoft YaHei",
                "fontsize": "40",
                "primary_color": "&H00FFFFFF",
                "outline_color": "&H00000000",
                "outline": "1",
                "shadow": "0",
                "alignment": "2",
                "margin_l": "20",
                "margin_r": "20",
                "margin_v": "20",
            },
            "yellow": {
                "font": "Microsoft YaHei",
                "fontsize": "52",
                "primary_color": "&H00FFD700",  # 金黄色
                "outline_color": "&H00000000",
                "outline": "2",
                "shadow": "1",
                "alignment": "2",
                "margin_l": "20",
                "margin_r": "20",
                "margin_v": "20",
            },
        }

        cfg = style_configs.get(style, style_configs["douyin"])

        ass_header = f"""[Script Info]
Title: Douyin Auto Subtitle
ScriptType: v4.00+
WrapStyle: 0
ScaledBorderAndShadow: yes
YCbCr Matrix: None

[V4+ Styles]
Format: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, OutlineColour, BackColour, Bold, Italic, Underline, StrikeOut, ScaleX, ScaleY, Spacing, Angle, BorderStyle, Outline, Shadow, Alignment, MarginL, MarginR, MarginV, Encoding
Style: Default,{cfg["font"]},{cfg["fontsize"]},{cfg["primary_color"]},&H000000FF,{cfg["outline_color"]},&H80000000,0,0,0,0,100,100,0,0,1,{cfg["outline"]},{cfg["shadow"]},{cfg["alignment"]},{cfg["margin_l"]},{cfg["margin_r"]},{cfg["margin_v"]},134

[Events]
Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text
"""

        # 读取 SRT 内容
        with open(srt_path, "r", encoding="utf-8") as f:
            srt_content = f.read()

        # 解析 SRT 并转换为 ASS 事件
        ass_events = []
        in_entry = False
        start_time = ""
        end_time = ""
        text_lines = []

        for line in srt_content.split("\n"):
            line = line.strip()
            if not line:
                if in_entry and text_lines:
                    # 输出 ASS 事件行
                    text = "\\N".join(text_lines)  # \N = 硬换行
                    ass_events.append(
                        f"Dialogue: 0,{start_time},{end_time},Default,,0,0,0,,{text}"
                    )
                    text_lines = []
                    in_entry = False
                continue

            if re.match(r"^\d+$", line):
                in_entry = False
            elif "-->" in line:
                start_str, end_str = line.split("-->")
                start_time = self._srt_to_ass_time(start_str.strip())
                end_time = self._srt_to_ass_time(end_str.strip())
                in_entry = True
            elif in_entry:
                text_lines.append(self._escape_ass_text(line))

        # 最后一条
        if text_lines:
            text = "\\N".join(text_lines)
            ass_events.append(
                f"Dialogue: 0,{start_time},{end_time},Default,,0,0,0,,{text}"
            )

        ass_content = ass_header + "\n".join(ass_events) + "\n"

        with open(ass_path, "w", encoding="utf-8") as f:
            f.write(ass_content)

        logger.info(f"ASS 字幕已生成: {ass_path}")
        return ass_path

    def _escape_ass_text(self, text: str) -> str:
        return text.replace("\\", r"\\").replace("{", r"\{").replace("}", r"\}")

    def _srt_to_ass_time(self, srt_ts: str) -> str:
        """将 SRT 时间戳（HH:MM:SS,mmm）转换为 ASS 时间戳（HH:MM:SS.cc）"""
        # SRT: 00:00:01,500  →  ASS: 0:00:01.50
        ts = srt_ts.replace(",", ".")
        parts = ts.split(":")
        if len(parts) == 3:
            h, m, s = parts
            return f"{int(h)}:{m}:{s}"
        return ts
