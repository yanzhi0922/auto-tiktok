# -*- coding: utf-8 -*-
"""
MiniMax 图片生成 API 客户端
支持 image-01 等图片生成模型
"""

import logging
import requests
from typing import Optional, Dict, Any
from pathlib import Path

from .base import BaseAPIClient
from config.settings import get_settings


logger = logging.getLogger(__name__)


class ImageAPI(BaseAPIClient):
    """图片生成 API 客户端"""

    MAX_PROMPT_CHARS = 1450

    # 支持的图片比例
    ASPECT_RATIOS = {
        "square": "1:1",       # 正方形
        "portrait": "2:3",     # 竖版
        "landscape": "3:2",    # 横版
        "story": "9:16",       # 竖屏故事
        "wide": "16:9",        # 宽屏
    }

    def __init__(self, api_key: Optional[str] = None):
        """
        初始化图片 API 客户端
        
        Args:
            api_key: API 密钥
        """
        super().__init__(api_key)
        self.settings = get_settings()

    def _normalize_prompt(self, prompt: str) -> tuple[str, Dict[str, Any]]:
        cleaned_prompt = " ".join(str(prompt).split())
        if len(cleaned_prompt) < self.MAX_PROMPT_CHARS:
            return cleaned_prompt, {
                "prompt_truncated": False,
                "original_prompt_length": len(cleaned_prompt),
                "applied_prompt_length": len(cleaned_prompt),
            }

        keep_chars = self.MAX_PROMPT_CHARS - 5
        head_chars = int(keep_chars * 0.75)
        tail_chars = keep_chars - head_chars
        truncated_prompt = (
            f"{cleaned_prompt[:head_chars].rstrip()} ... "
            f"{cleaned_prompt[-tail_chars:].lstrip()}"
        )
        logger.warning(
            "图片提示词过长，已截断以适配官方长度限制: "
            f"{len(cleaned_prompt)} -> {len(truncated_prompt)}"
        )
        return truncated_prompt, {
            "prompt_truncated": True,
            "original_prompt_length": len(cleaned_prompt),
            "applied_prompt_length": len(truncated_prompt),
        }

    def generate(
        self,
        prompt: str,
        model: Optional[str] = None,
        aspect_ratio: str = "1:1",
        n: int = 1,
        response_format: str = "url",
        **kwargs
    ) -> Dict[str, Any]:
        """
        文生图：根据文本描述生成图片

        Args:
            prompt: 图片描述文本
            model: 模型名称
                   - image-01: 标准版（支持 width/height 自定义，最新规格见官方文档）
                   - image-01-live: 生活化风格版（支持 style 参数，适合人物和真实场景）
            aspect_ratio: 图片比例（1:1, 2:3, 3:2, 9:16, 16:9, 3:4, 4:3, 21:9）
            n: 生成数量（1-9）
            response_format: 返回格式（url 或 base64）
                             ⚠️ url 有效期 24 小时，请及时下载
            **kwargs: 其他参数（如 style 仅 image-01-live 支持）

        Returns:
            API 响应数据，包含生成的图片 URL 或 base64

        Example:
            >>> api = ImageAPI()
            >>> result = api.generate(
            ...     prompt="一只可爱的橘猫在阳光下打盹",
            ...     aspect_ratio="1:1"
            ... )
        """
        requested_model = model or self.settings.models.image_model
        image_count = max(int(n), 1)
        normalized_prompt, prompt_metadata = self._normalize_prompt(prompt)

        def build_payload(tier: str):
            applied_model = self.settings.models.normalize_image_model(
                requested_model
            )
            data = {
                "model": applied_model,
                "prompt": normalized_prompt,
                "aspect_ratio": aspect_ratio,
                "n": image_count,
                "response_format": response_format,
            }
            data.update(kwargs)
            return data, {
                "requested_model": requested_model,
                "applied_model": applied_model,
                **prompt_metadata,
            }

        logger.info(
            f"调用图片生成 API，请求模型: {requested_model}, 比例: {aspect_ratio}, 数量: {image_count}"
        )

        result = self.execute_tiered_request(
            "POST",
            "/v1/image_generation",
            build_payload=build_payload,
            resource="image",
            amount=image_count,
            refresh_remote=True,
        )

        # 生成型 POST 不能在 data=null 时盲目重试，否则可能重复扣费/重复出图。
        if result.get("data") is None and result.get("base_resp", {}).get("status_code") == 0:
            raise RuntimeError(
                "图片生成接口返回成功但 data 为空；为避免重复扣费，当前不会自动重试，请稍后人工复核后再重试。"
            )

        # 兼容双重 JSON 编码（MiniMax API 中间件有时会将 data 字段再次序列化为字符串）
        data = result.get("data")
        if isinstance(data, str):
            import json as _json
            try:
                data = _json.loads(data)
                result["data"] = data  # 回写，下次无需再次解析
            except Exception:
                pass  # 解析失败，保留原值

        return result
    
    def generate_with_reference(
        self,
        prompt: str,
        reference_image: str,
        model: Optional[str] = None,
        aspect_ratio: str = "1:1",
        **kwargs
    ) -> Dict[str, Any]:
        """
        图生图：基于参考图片生成新图片
        
        Args:
            prompt: 图片描述文本
            reference_image: 参考图片（URL 或 base64）
            model: 模型名称
            aspect_ratio: 图片比例
            **kwargs: 其他参数
            
        Returns:
            API 响应数据
            
        Example:
            >>> api = ImageAPI()
            >>> result = api.generate_with_reference(
            ...     prompt="将这张图片转换为水彩画风格",
            ...     reference_image="https://example.com/image.jpg"
            ... )
        """
        requested_model = model or self.settings.models.image_model
        normalized_prompt, prompt_metadata = self._normalize_prompt(prompt)

        def build_payload(tier: str):
            applied_model = self.settings.models.normalize_image_model(
                requested_model
            )
            data = {
                "model": applied_model,
                "prompt": normalized_prompt,
                "image": reference_image,
                "aspect_ratio": aspect_ratio,
            }
            data.update(kwargs)
            return data, {
                "requested_model": requested_model,
                "applied_model": applied_model,
                **prompt_metadata,
            }

        logger.info(f"调用图生图 API，请求模型: {requested_model}")

        return self.execute_tiered_request(
            "POST",
            "/v1/image_generation",
            build_payload=build_payload,
            resource="image",
            refresh_remote=True,
        )
    
    def generate_to_file(
        self,
        prompt: str,
        output_path: str,
        aspect_ratio: str = "1:1",
        **kwargs
    ) -> Path:
        """
        生成图片并保存到文件
        
        Args:
            prompt: 图片描述
            output_path: 输出文件路径
            aspect_ratio: 图片比例
            **kwargs: 其他参数
            
        Returns:
            保存的文件路径
            
        Example:
            >>> api = ImageAPI()
            >>> image_path = api.generate_to_file(
            ...     prompt="夕阳下的海滩，金色阳光洒在沙滩上",
            ...     output_path="output/images/beach.png"
            ... )
        """
        result = self.generate(
            prompt=prompt,
            aspect_ratio=aspect_ratio,
            response_format="url",
            **kwargs
        )

        # 获取图片 URL（兼容多种响应格式）
        data = result.get("data")
        # generate() 已处理双重 JSON 编码，此处直接取值
        image_url = ""
        if isinstance(data, dict) and "image_urls" in data:
            urls = data["image_urls"]
            if urls:
                first = urls[0]
                # image_urls 可能是 ["url_string"] 或 [{"url": "..."}]
                image_url = first if isinstance(first, str) else first.get("url", "")
        elif isinstance(data, list) and len(data) > 0:
            first = data[0]
            image_url = first if isinstance(first, str) else first.get("url", "")
        elif isinstance(data, str):
            image_url = data

        if not image_url:
            raise ValueError(f"图片生成响应格式异常: {result}")
        
        # 下载图片（使用独立 session，避免携带 API auth headers）
        download_session = requests.Session()
        download_session.trust_env = False
        response = download_session.get(image_url, timeout=self.timeout)
        response.raise_for_status()
        
        # 确保输出目录存在
        output_file = Path(output_path)
        output_file.parent.mkdir(parents=True, exist_ok=True)
        
        # 保存文件
        with open(output_file, "wb") as f:
            f.write(response.content)
        
        logger.info(f"图片已保存到: {output_file}")
        
        return output_file
    
    def generate_batch(
        self,
        prompts: list,
        output_dir: str,
        aspect_ratio: str = "1:1",
        prefix: str = "image",
        **kwargs
    ) -> list:
        """
        批量生成图片
        
        Args:
            prompts: 图片描述列表
            output_dir: 输出目录
            aspect_ratio: 图片比例
            prefix: 文件名前缀
            **kwargs: 其他参数
            
        Returns:
            保存的文件路径列表
            
        Example:
            >>> api = ImageAPI()
            >>> paths = api.generate_batch(
            ...     prompts=["一只猫", "一只狗", "一只鸟"],
            ...     output_dir="output/images",
            ...     prefix="animal"
            ... )
        """
        output_directory = Path(output_dir)
        output_directory.mkdir(parents=True, exist_ok=True)
        
        saved_paths = []
        
        for i, prompt in enumerate(prompts, 1):
            output_path = output_directory / f"{prefix}_{i:03d}.png"
            
            try:
                path = self.generate_to_file(
                    prompt=prompt,
                    output_path=str(output_path),
                    aspect_ratio=aspect_ratio,
                    **kwargs
                )
                saved_paths.append(path)
            except Exception as e:
                logger.error(f"生成图片 {i} 失败: {str(e)}")
                continue
        
        logger.info(f"批量生成完成，成功: {len(saved_paths)}/{len(prompts)}")
        
        return saved_paths
    
    def get_aspect_ratio(self, ratio_name: str) -> str:
        """
        根据预设名称获取图片比例
        
        Args:
            ratio_name: 比例名称（square, portrait, landscape, story, wide）
            
        Returns:
            比例字符串
        """
        return self.ASPECT_RATIOS.get(ratio_name, ratio_name)
    
    def create_thumbnail(
        self,
        prompt: str,
        output_path: str,
        style: str = "吸引眼球",
        **kwargs
    ) -> Path:
        """
        创建视频缩略图（9:16竖屏）
        
        Args:
            prompt: 图片描述
            output_path: 输出路径
            style: 风格描述
            **kwargs: 其他参数
            
        Returns:
            保存的文件路径
        """
        full_prompt = f"{prompt}, {style}, 高质量, 吸引注意力"
        
        return self.generate_to_file(
            prompt=full_prompt,
            output_path=output_path,
            aspect_ratio="9:16",
            **kwargs
        )
    
    def create_cover(
        self,
        title: str,
        theme: str,
        output_path: str,
        **kwargs
    ) -> Path:
        """
        创建视频封面图
        
        Args:
            title: 标题文本
            theme: 主题描述
            output_path: 输出路径
            **kwargs: 其他参数
            
        Returns:
            保存的文件路径
        """
        prompt = f"{theme}, 适合作为视频封面, 视觉冲击力强, {title}"
        
        return self.generate_to_file(
            prompt=prompt,
            output_path=output_path,
            aspect_ratio="9:16",
            **kwargs
        )
