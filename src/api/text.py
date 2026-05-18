# -*- coding: utf-8 -*-
"""
MiniMax 文本生成 API 客户端
支持 M2.7-highspeed 等文本模型的对话补全功能
"""

import logging
from typing import Optional, List, Dict, Any

from .base import BaseAPIClient
from config.settings import get_settings


logger = logging.getLogger(__name__)


class TextAPI(BaseAPIClient):
    """文本生成 API 客户端"""

    def __init__(self, api_key: Optional[str] = None):
        """
        初始化文本 API 客户端

        Args:
            api_key: API 密钥
        """
        super().__init__(api_key)
        self.settings = get_settings()

    def chat_completion(
        self,
        messages: List[Dict[str, str]],
        model: Optional[str] = None,
        temperature: float = 1.0,
        top_p: float = 0.95,
        max_tokens: Optional[int] = None,
        stream: bool = False,
        **kwargs
    ) -> Dict[str, Any]:
        """
        文本对话补全

        Args:
            messages: 对话消息列表，格式：[{"role": "user", "content": "..."}]
            model: 模型名称，默认使用配置中的模型
            temperature: 温度系数 (0, 1]，越高越随机
            top_p: 采样策略 (0, 1]
            max_tokens: 最大生成 token 数
            stream: 是否流式输出
            **kwargs: 其他参数

        Returns:
            API 响应数据

        Example:
            >>> api = TextAPI()
            >>> result = api.chat_completion([
            ...     {"role": "system", "content": "你是一个助手"},
            ...     {"role": "user", "content": "你好"}
            ... ])
            >>> print(result["choices"][0]["message"]["content"])
        """
        requested_model = model or self.settings.models.text_model_ultra

        if not self.settings.check_quota("text"):
            status = self.settings.get_quota_status()["text_5h"]
            raise RuntimeError(
                "文本请求配额已用尽，"
                f"剩余 {status['remaining']} 次，"
                f"窗口剩余 {status['window_seconds_remaining']} 秒"
            )

        def resolve_model_for_tier(tier: str) -> str:
            return self.settings.models.normalize_text_model_for_tier(
                tier,
                requested_model,
            )

        def build_payload(tier: str):
            applied_model = resolve_model_for_tier(tier)
            data = {
                "model": applied_model,
                "messages": messages,
                "temperature": temperature,
                "top_p": top_p,
                "stream": stream,
            }
            if max_tokens is not None:
                data["max_completion_tokens"] = max_tokens
            data.update(kwargs)
            return data, {
                "requested_model": requested_model,
                "applied_model": applied_model,
                "resource": "text",
            }

        logger.info(f"调用文本生成 API，请求模型: {requested_model}")

        result = self.execute_tiered_request(
            "POST",
            "/v1/text/chatcompletion_v2",
            build_payload=build_payload,
            resource="text",
        )
        return result

    def generate_text(
        self,
        prompt: str,
        system_prompt: Optional[str] = None,
        model: Optional[str] = None,
        temperature: float = 1.0,
        max_tokens: Optional[int] = None,
        **kwargs
    ) -> str:
        """
        简化的文本生成接口

        Args:
            prompt: 用户提示词
            system_prompt: 系统提示词
            model: 模型名称
            temperature: 温度系数
            max_tokens: 最大生成 token 数
            **kwargs: 其他参数

        Returns:
            生成的文本内容

        Example:
            >>> api = TextAPI()
            >>> text = api.generate_text(
            ...     prompt="写一个关于春天的短诗",
            ...     system_prompt="你是一位诗人"
            ... )
        """
        messages = []

        if system_prompt:
            messages.append({
                "role": "system",
                "content": system_prompt
            })

        messages.append({
            "role": "user",
            "content": prompt
        })

        result = self.chat_completion(
            messages=messages,
            model=model,
            temperature=temperature,
            max_tokens=max_tokens,
            **kwargs
        )

        # 提取生成的文本
        content = result["choices"][0]["message"]["content"]

        logger.info(f"文本生成完成，长度: {len(content)}")

        return content

    def generate_script(
        self,
        topic: str,
        style: str = "轻松幽默",
        duration: int = 6,
        audience: str = "年轻人",
        **kwargs
    ) -> Dict[str, str]:
        """
        生成短视频脚本

        Args:
            topic: 视频主题
            style: 视频风格
            duration: 视频时长（秒）
            audience: 目标受众
            **kwargs: 其他参数

        Returns:
            包含视频描述、旁白文案和画面建议的字典

        Example:
            >>> api = TextAPI()
            >>> script = api.generate_script(
            ...     topic="咖啡文化",
            ...     style="文艺清新",
            ...     duration=6
            ... )
        """
        system_prompt = """你是一位专业的短视频脚本编剧，擅长创作吸引人的抖音/短视频内容。
你的脚本应该：
1. 开头3秒抓住观众注意力
2. 内容紧凑，节奏明快
3. 结尾有强烈的行动号召
4. 适合6-10秒的视频时长

请按以下格式输出：
【视频描述】（用于视频生成的英文描述）
【旁白文案】（用于语音合成的中文文案）
【画面建议】（画面构图和运镜建议）"""

        user_prompt = f"""请为以下主题创作一个{duration}秒的短视频脚本：
主题：{topic}
风格：{style}
目标受众：{audience}"""

        result = self.generate_text(
            prompt=user_prompt,
            system_prompt=system_prompt,
            **kwargs
        )

        # 解析脚本内容
        script = {
            "raw_content": result,
            "video_description": "",
            "narration": "",
            "visual_suggestions": ""
        }

        # 简单的内容提取
        lines = result.split("\n")
        current_section = None

        for line in lines:
            line = line.strip()
            if "【视频描述】" in line or "视频描述" in line:
                current_section = "video_description"
            elif "【旁白文案】" in line or "旁白文案" in line:
                current_section = "narration"
            elif "【画面建议】" in line or "画面建议" in line:
                current_section = "visual_suggestions"
            elif current_section and line:
                script[current_section] += line + "\n"

        # 清理多余空白
        for key in ["video_description", "narration", "visual_suggestions"]:
            script[key] = script[key].strip()

        logger.info(f"脚本生成完成，主题: {topic}")

        return script

    def generate_titles(
        self,
        topic: str,
        content_type: str = "短视频",
        count: int = 5,
        **kwargs
    ) -> List[str]:
        """
        生成爆款标题

        Args:
            topic: 内容主题
            content_type: 内容类型
            count: 生成数量
            **kwargs: 其他参数

        Returns:
            标题列表

        Example:
            >>> api = TextAPI()
            >>> titles = api.generate_titles(
            ...     topic="咖啡文化",
            ...     count=5
            ... )
        """
        system_prompt = """你是一位短视频标题专家，擅长创作吸引点击的标题。
你的标题应该：
1. 使用数字和符号增加视觉冲击
2. 制造好奇心或情感共鸣
3. 包含热门关键词
4. 控制在20字以内

请直接输出标题列表，每行一个，不要编号。"""

        user_prompt = f"""请为以下内容生成{count}个爆款标题：
内容主题：{topic}
内容类型：{content_type}"""

        result = self.generate_text(
            prompt=user_prompt,
            system_prompt=system_prompt,
            **kwargs
        )

        # 提取标题列表
        # 过滤掉常见的结构性前缀，保留可能是标题的行
        titles = []
        skip_prefixes = (
            "请", "以下", "标题", "内容", "——", "...",
            "主题", "生成", "输出", "示例", "例子"
        )
        for line in result.split("\n"):
            line = line.strip()
            # 跳过空行、指令性文字、过短的行
            if not line or len(line) < 5:
                continue
            if line.startswith(skip_prefixes):
                continue
            # 跳过明显的编号列表（但保留含数字的正常标题，如"10个技巧"）
            # 只过滤纯数字开头的行，如 "1. xxx" 或 "1 xxx"
            import re
            if re.match(r"^\d+[.、:：\s]", line):
                # 去掉编号前缀，保留实际内容
                line = re.sub(r"^\d+[.、:：\s]+", "", line).strip()
            if line and len(line) >= 5:
                titles.append(line)

        logger.info(f"标题生成完成，数量: {len(titles)}")

        return titles
