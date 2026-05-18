# -*- coding: utf-8 -*-
"""
MiniMax 语音合成 API 客户端
支持 Speech-2.8 等高质量语音合成模型
"""

import logging
import json
from typing import Optional, Dict, Any
from pathlib import Path

from .base import BaseAPIClient
from config.settings import get_settings


logger = logging.getLogger(__name__)


class SpeechAPI(BaseAPIClient):
    """语音合成 API 客户端"""

    # 预设音色 ID（参考 MiniMax 官方音色列表）
    # 男声
    VOICES = {
        "male_young": "male-qn-qingse",      # 青年男声-青涩
        "male_mature": "male-qn-jingying",   # 青年男声-精英
        "male_warm": "male-qn-qingxin",      # 青年男声-清新
    }

    # 女声（中文音色）- Token Plan 可用音色
    _FEMALE_VOICES = {
        "female_shaonv": "female-shaonv",     # 少女音 ✅
        "female_tianmei": "female-tianmei",   # 甜美女声 ✅
        "female_chengshu": "female-chengshu", # 成熟女声 ✅
        # 以下音色需要额外权限或不在当前套餐
        # "female_wenrou": "female-wenrou",     # 温柔女声 ❌ 无权限
        # "female_breeze": "female-qn-breeze",  # 轻语女声 ❌ 不存在
        # "female_jingying": "female-qn-jingying", # 知性女声 ❌ 不存在
    }

    # 合并所有音色
    VOICES.update(_FEMALE_VOICES)

    # 情感类型（仅 speech-2.8 支持）
    EMOTIONS = [
        "happy",      # 开心
        "sad",        # 悲伤
        "angry",      # 愤怒
        "fearful",    # 恐惧
        "surprised",  # 惊讶
        "disgusted",  # 厌恶
        "neutral",    # 中性
    ]

    # 默认音色（使用官方示例中的音色）
    DEFAULT_VOICE = "female-tianmei"

    def __init__(self, api_key: Optional[str] = None):
        """
        初始化语音 API 客户端

        Args:
            api_key: API 密钥
        """
        super().__init__(api_key)
        self.settings = get_settings()

    def synthesize(
        self,
        text: str,
        model: Optional[str] = None,
        voice_id: Optional[str] = None,
        speed: float = 1.0,
        vol: float = 1.0,
        pitch: float = 0,
        emotion: Optional[str] = None,
        format: str = "mp3",
        sample_rate: int = 32000,
        bitrate: int = 128000,
        stream: bool = False,
        **kwargs
    ) -> Dict[str, Any]:
        """
        同步语音合成

        Args:
            text: 要合成的文本（最大10000字符）
            model: 模型名称，默认使用配置中的模型
            voice_id: 音色 ID 或预设名称（如 "female_wenrou"）
            speed: 语速 (0.5-2.0)
            vol: 音量 (0.1-2.0)
            pitch: 音调 (-12 到 12)
            emotion: 情感（仅 speech-2.8 支持）
            format: 音频格式（mp3, wav, flac）
            sample_rate: 采样率
            bitrate: 比特率
            stream: 是否流式输出
            **kwargs: 其他参数

        Returns:
            API 响应数据，包含音频的 hex 编码或 URL

        Example:
            >>> api = SpeechAPI()
            >>> result = api.synthesize("你好，欢迎使用语音合成")
            >>> audio_hex = result["data"]["audio"]
        """
        requested_model = model or self.settings.models.speech_model

        if not self.settings.check_quota("tts", amount=len(text)):
            status = self.settings.get_quota_status()["tts"]
            raise RuntimeError(
                "TTS 配额已用尽，"
                f"剩余 {status['remaining']} 字符，当前请求 {len(text)} 字符"
            )

        # 解析 voice_id（支持预设名称）
        resolved_voice_id = self.get_voice_id(voice_id or self.DEFAULT_VOICE)

        # 检查文本长度
        if len(text) > 10000:
            logger.warning(f"文本长度 {len(text)} 超过推荐值，建议使用异步合成")

        def build_payload(tier: str):
            applied_model = self.settings.models.normalize_speech_model(
                requested_model
            )
            data = {
                "model": applied_model,
                "text": text,
                "stream": stream,
                "voice_setting": {
                    "voice_id": resolved_voice_id,
                    "speed": speed,
                    "vol": vol,
                    "pitch": pitch,
                },
                "audio_setting": {
                    "sample_rate": sample_rate,
                    "bitrate": bitrate,
                    "format": format,
                    "channel": 1,
                },
            }
            if emotion and "2.8" in applied_model:
                data["voice_setting"]["emotion"] = emotion
            data.update(kwargs)
            return data, {
                "requested_model": requested_model,
                "applied_model": applied_model,
            }

        logger.info(
            f"调用语音合成 API，请求模型: {requested_model}, 音色: {resolved_voice_id}, 文本长度: {len(text)}"
        )

        result = self.execute_tiered_request(
            "POST",
            "/v1/t2a_v2",
            build_payload=build_payload,
            resource="tts",
            amount=len(text),
            refresh_remote=True,
        )

        raw_data = result.get("data")
        if isinstance(raw_data, str):
            try:
                result["data"] = json.loads(raw_data)
            except json.JSONDecodeError:
                pass

        return result

    def synthesize_to_file(
        self,
        text: str,
        output_path: str,
        voice_id: Optional[str] = None,
        emotion: Optional[str] = None,
        format: str = "mp3",
        **kwargs
    ) -> Path:
        """
        合成语音并保存到文件

        Args:
            text: 要合成的文本
            output_path: 输出文件路径
            voice_id: 音色 ID 或预设名称
            emotion: 情感
            format: 音频格式
            **kwargs: 其他参数

        Returns:
            保存的文件路径

        Example:
            >>> api = SpeechAPI()
            >>> file_path = api.synthesize_to_file(
            ...     text="你好世界",
            ...     output_path="output/hello.mp3"
            ... )
        """
        result = self.synthesize(
            text=text,
            voice_id=voice_id,
            emotion=emotion,
            format=format,
            **kwargs
        )

        data = result.get("data", {})
        if isinstance(data, str):
            try:
                data = json.loads(data)
                result["data"] = data
            except json.JSONDecodeError:
                data = {}

        # 获取音频数据（优先从 data.audio，兼容不同响应格式）
        audio_hex = data.get("audio") if isinstance(data, dict) else None
        if not audio_hex:
            audio_hex = result.get("audio")
        if not audio_hex and isinstance(data, dict):
            audio_hex = data.get("audio_data")

        if not audio_hex:
            raise ValueError(f"API 响应中未找到音频数据，响应: {result}")

        # 将 hex 转换为字节
        audio_bytes = bytes.fromhex(audio_hex)

        # 确保输出目录存在
        output_file = Path(output_path)
        output_file.parent.mkdir(parents=True, exist_ok=True)

        # 保存文件
        with open(output_file, "wb") as f:
            f.write(audio_bytes)

        logger.info(f"音频已保存到: {output_file}")

        # 提取额外信息（时长、字幕时间戳等）
        extra_info = result.get("extra_info", {})
        audio_length_ms = float(extra_info.get("audio_length", 0) or 0)
        subtitle_info = {
            "audio_length_ms": audio_length_ms,
            "word_count": extra_info.get("word_count", 0),
            "usage_characters": extra_info.get("usage_characters", 0),
            "sample_rate": extra_info.get("audio_sample_rate", 32000),
            # 异步接口返回句级时间戳，同步接口通过 subtitle_enable 可获取基本信息
            "has_timestamps": "subtitle" in str(result).lower(),
        }

        logger.info(f"音频信息: 时长={subtitle_info['audio_length_ms']/1000:.1f}s, "
                    f"字数={subtitle_info['word_count']}, 字符={subtitle_info['usage_characters']}")

        return output_file

    def get_voice_id(self, voice_name: str) -> str:
        """
        根据预设名称获取音色 ID

        Args:
            voice_name: 预设音色名称（支持 key 名或原始 voice_id）

        Returns:
            音色 ID

        Example:
            >>> api = SpeechAPI()
            >>> voice_id = api.get_voice_id("female_wenrou")
            >>> # "female-wenrou"
            >>> voice_id = api.get_voice_id("female-wenrou")
            >>> # "female-wenrou"（直接返回）
        """
        if voice_name in self.VOICES:
            return self.VOICES[voice_name]
        else:
            # 假设直接传入了音色 ID（原样返回）
            return voice_name

    def list_voices(self) -> Dict[str, str]:
        """
        获取所有预设音色列表

        Returns:
            音色名称到 ID 的映射字典
        """
        return self.VOICES.copy()

    def add_emotion_tags(self, text: str, emotion: str = "happy") -> str:
        """
        在文本中添加语气词标签（仅 speech-2.8 支持）

        Args:
            text: 原始文本
            emotion: 情感类型

        Returns:
            添加了语气词标签的文本

        Example:
            >>> api = SpeechAPI()
            >>> text = api.add_emotion_tags("今天是不是很开心呀", "happy")
            >>> # "今天是不是很开心呀(laughs)"
        """
        emotion_tags = {
            "happy": "(laughs)",
            "sad": "(sighs)",
            "surprised": "(gasps)",
            "neutral": "",
        }

        tag = emotion_tags.get(emotion, "")

        if tag:
            return f"{text}{tag}"

        return text

    def estimate_duration(self, text: str, speed: float = 1.0) -> float:
        """
        估算语音合成后的时长

        Args:
            text: 文本内容
            speed: 语速

        Returns:
            估算时长（秒）
        """
        # 粗略估算：中文约 400字/分钟，英文约 150词/分钟
        chinese_chars = sum(1 for c in text if '\u4e00' <= c <= '\u9fff')
        other_chars = len(text) - chinese_chars
        estimated_minutes = (chinese_chars / 400 + other_chars / 150) / speed
        return estimated_minutes * 60
