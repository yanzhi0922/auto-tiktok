# -*- coding: utf-8 -*-
"""
视频编辑模块
负责：字幕生成、视频合成（ffmpeg）、最终成品输出
"""

from .subtitle import SubtitleGenerator
from .composer import VideoComposer

__all__ = ["SubtitleGenerator", "VideoComposer"]
