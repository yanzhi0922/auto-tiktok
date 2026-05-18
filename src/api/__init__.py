# -*- coding: utf-8 -*-
"""API 模块初始化"""

from .base import BaseAPIClient, MiniMaxAPIError
from .text import TextAPI
from .speech import SpeechAPI
from .video import VideoAPI
from .music import MusicAPI
from .image import ImageAPI

__all__ = [
    "BaseAPIClient",
    "MiniMaxAPIError",
    "TextAPI",
    "SpeechAPI",
    "VideoAPI",
    "MusicAPI",
    "ImageAPI",
]
