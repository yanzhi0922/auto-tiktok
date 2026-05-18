# -*- coding: utf-8 -*-
"""
MiniMax 音乐生成 API 客户端
支持 Token Plan 路径下的 music-2.6 音乐生成模型
"""

import logging
from typing import Optional, Dict, Any
from pathlib import Path

from .base import BaseAPIClient
from config.settings import get_settings


logger = logging.getLogger(__name__)


class MusicAPI(BaseAPIClient):
    """音乐生成 API 客户端"""
    
    # 支持的音乐结构标签
    STRUCTURE_TAGS = [
        "[Intro]",        # 前奏
        "[Verse]",        # 主歌
        "[Pre Chorus]",   # 导歌
        "[Chorus]",       # 副歌
        "[Interlude]",    # 间奏
        "[Bridge]",       # 桥段
        "[Outro]",        # 尾奏
        "[Post Chorus]",  # 后副歌
        "[Transition]",   # 过渡
        "[Break]",        # 间奏
        "[Hook]",         # 钩子
        "[Build Up]",     # 铺垫
        "[Inst]",         # 器乐
        "[Solo]",         # 独奏
    ]
    
    def __init__(self, api_key: Optional[str] = None):
        """
        初始化音乐 API 客户端
        
        Args:
            api_key: API 密钥
        """
        super().__init__(api_key)
        self.settings = get_settings()
    
    def generate(
        self,
        prompt: str,
        lyrics: Optional[str] = None,
        model: Optional[str] = None,
        is_instrumental: bool = False,
        lyrics_optimizer: bool = False,
        format: str = "mp3",
        sample_rate: int = 44100,
        bitrate: int = 256000,
        stream: bool = False,
        **kwargs
    ) -> Dict[str, Any]:
        """
        生成音乐
        
        Args:
            prompt: 音乐描述（风格、情绪、场景）
            lyrics: 歌词（使用 \n 分行）
            model: 模型名称
            is_instrumental: 是否生成纯音乐（当前 Token Plan 不支持）
            lyrics_optimizer: 是否自动生成歌词
            format: 音频格式（mp3, wav, flac）
            sample_rate: 采样率
            bitrate: 比特率
            stream: 是否流式输出
            **kwargs: 其他参数
            
        Returns:
            API 响应数据，包含音频的 hex 编码或 URL
            
        Example:
            >>> api = MusicAPI()
            >>> result = api.generate(
            ...     prompt="流行音乐, 欢快, 活力",
            ...     lyrics="[Verse]\\n阳光洒在脸上\\n心情格外舒畅"
            ... )
        """
        requested_model = model or self.settings.models.music_model

        if not requested_model:
            raise RuntimeError("当前配置未启用音乐模型，请在生成流程中关闭音乐或更新模型配置")

        if is_instrumental and not self.settings.models.supports_music_instrumental():
            raise ValueError(
                "当前 Token Plan 音乐仅支持 music-2.6 歌曲生成，不支持纯音乐；"
                "请提供歌词或启用歌词自动生成，自动化背景音乐应直接跳过。"
            )

        # 验证参数
        if not is_instrumental and not lyrics and not lyrics_optimizer:
            raise ValueError("非纯音乐必须提供歌词或启用歌词自动生成")
        
        def build_payload(tier: str):
            applied_model = self.settings.models.normalize_music_model(
                requested_model
            )
            if not applied_model:
                raise RuntimeError("当前配置未启用音乐模型，请在生成流程中关闭音乐或更新模型配置")
            data = {
                "model": applied_model,
                "prompt": prompt,
                "audio_setting": {
                    "sample_rate": sample_rate,
                    "bitrate": bitrate,
                    "format": format,
                },
                "stream": stream,
            }
            if lyrics:
                data["lyrics"] = lyrics
            if is_instrumental:
                data["is_instrumental"] = True
            if lyrics_optimizer:
                data["lyrics_optimizer"] = True
            data.update(kwargs)
            return data, {
                "requested_model": requested_model,
                "applied_model": applied_model,
            }

        logger.info(f"调用音乐生成 API，请求模型: {requested_model}, 纯音乐: {is_instrumental}")

        request_timeout = max(float(self.timeout), 300.0)
        result = self.execute_tiered_request(
            "POST",
            "/v1/music_generation",
            build_payload=build_payload,
            resource="music",
            refresh_remote=True,
            timeout=request_timeout,
        )

        # 兼容双重 JSON 编码（MiniMax API 中间件行为）
        raw_data = result.get("data")
        if isinstance(raw_data, str):
            import json as _json
            try:
                result["data"] = _json.loads(raw_data)
            except Exception:
                pass

        return result
    
    def generate_to_file(
        self,
        prompt: str,
        output_path: str,
        lyrics: Optional[str] = None,
        is_instrumental: bool = False,
        format: str = "mp3",
        **kwargs
    ) -> Path:
        """
        生成音乐并保存到文件
        
        Args:
            prompt: 音乐描述
            output_path: 输出文件路径
            lyrics: 歌词
            is_instrumental: 是否纯音乐
            format: 音频格式
            **kwargs: 其他参数
            
        Returns:
            保存的文件路径
            
        Example:
            >>> api = MusicAPI()
            >>> music_path = api.generate_to_file(
            ...     prompt="流行音乐, 欢快",
            ...     output_path="output/music/happy.mp3",
            ...     lyrics_optimizer=True
            ... )
        """
        result = self.generate(
            prompt=prompt,
            lyrics=lyrics,
            is_instrumental=is_instrumental,
            format=format,
            **kwargs
        )

        # 获取音频数据（generate() 已处理双重 JSON 编码）
        audio_data = result.get("data", {})
        if isinstance(audio_data, dict):
            audio_hex = audio_data.get("audio", "")
        elif isinstance(audio_data, str):
            audio_hex = audio_data
        else:
            raise ValueError(f"音乐生成响应格式异常: {result}")

        if not audio_hex:
            raise ValueError(f"音乐生成响应中未找到 audio 字段: {result}")
        
        # 将 hex 转换为字节
        audio_bytes = bytes.fromhex(audio_hex)
        
        # 确保输出目录存在
        output_file = Path(output_path)
        output_file.parent.mkdir(parents=True, exist_ok=True)
        
        # 保存文件
        with open(output_file, "wb") as f:
            f.write(audio_bytes)
        
        # 获取音乐信息
        extra_info = result.get("extra_info", {})
        duration_ms = extra_info.get("music_duration", 0)
        duration_sec = duration_ms / 1000
        
        logger.info(f"音乐已保存到: {output_file}, 时长: {duration_sec:.1f}秒")
        
        return output_file
    
    def generate_instrumental(
        self,
        prompt: str,
        output_path: str,
        format: str = "mp3",
        **kwargs
    ) -> Path:
        """
        生成纯音乐（无人声）

        当前 Token Plan 默认模型仅支持 `music-2.6`，该模式不支持纯音乐，
        因此此方法在默认配置下会抛出明确错误。

        Args:
            prompt: 音乐描述
            output_path: 输出文件路径
            format: 音频格式
            **kwargs: 其他参数
            
        Returns:
            保存的文件路径
            
        Example:
            >>> api = MusicAPI()
            >>> music_path = api.generate_instrumental(
            ...     prompt="古典管弦, 史诗, 壮丽",
            ...     output_path="output/music/epic.mp3"
            ... )
        """
        return self.generate_to_file(
            prompt=prompt,
            output_path=output_path,
            is_instrumental=True,
            format=format,
            **kwargs
        )
    
    def generate_with_auto_lyrics(
        self,
        prompt: str,
        output_path: str,
        format: str = "mp3",
        **kwargs
    ) -> Path:
        """
        自动生成歌词并创作音乐
        
        Args:
            prompt: 音乐描述（会根据此自动生成歌词）
            output_path: 输出文件路径
            format: 音频格式
            **kwargs: 其他参数
            
        Returns:
            保存的文件路径
            
        Example:
            >>> api = MusicAPI()
            >>> music_path = api.generate_with_auto_lyrics(
            ...     prompt="流行音乐, 爱情, 甜蜜",
            ...     output_path="output/music/love_song.mp3"
            ... )
        """
        return self.generate_to_file(
            prompt=prompt,
            output_path=output_path,
            lyrics_optimizer=True,
            format=format,
            **kwargs
        )
    
    def format_lyrics(
        self,
        verses: list,
        chorus: str = None,
        intro: str = None,
        outro: str = None,
        bridge: str = None
    ) -> str:
        """
        格式化歌词，添加结构标签
        
        Args:
            verses: 主歌歌词列表
            chorus: 副歌歌词
            intro: 前奏描述
            outro: 尾奏描述
            bridge: 桥段歌词
            
        Returns:
            格式化后的歌词
            
        Example:
            >>> api = MusicAPI()
            >>> lyrics = api.format_lyrics(
            ...     verses=["第一段主歌", "第二段主歌"],
            ...     chorus="这是副歌部分",
            ...     bridge="这是桥段"
            ... )
        """
        parts = []
        
        if intro:
            parts.append(f"[Intro]\n{intro}")
        
        for i, verse in enumerate(verses, 1):
            parts.append(f"[Verse {i}]\n{verse}")
        
        if chorus:
            parts.append(f"[Chorus]\n{chorus}")
        
        if bridge:
            parts.append(f"[Bridge]\n{bridge}")
        
        if outro:
            parts.append(f"[Outro]\n{outro}")
        
        return "\n\n".join(parts)
    
    def create_style_prompt(
        self,
        genre: str,
        mood: str,
        scene: str = None,
        tempo: str = None
    ) -> str:
        """
        创建音乐风格描述
        
        Args:
            genre: 音乐类型（流行、电子、古典等）
            mood: 情绪（欢快、悲伤、激情等）
            scene: 场景（咖啡馆、夜晚、海滩等）
            tempo: 节奏（快、中、慢）
            
        Returns:
            格式化的风格描述
            
        Example:
            >>> api = MusicAPI()
            >>> prompt = api.create_style_prompt(
            ...     genre="流行音乐",
            ...     mood="欢快",
            ...     scene="夏日海滩",
            ...     tempo="中速"
            ... )
        """
        parts = [genre, mood]
        
        if scene:
            parts.append(scene)
        
        if tempo:
            parts.append(tempo)
        
        return ", ".join(parts)
