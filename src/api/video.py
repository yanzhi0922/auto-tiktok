# -*- coding: utf-8 -*-
"""
MiniMax 视频生成 API 客户端
支持 Hailuo-2.3 等视频生成模型（异步任务模式）
"""

import base64
import time
import logging
import mimetypes
from typing import Optional, Dict, Any, Callable
from pathlib import Path
from enum import Enum

import requests

from .base import BaseAPIClient
from config.settings import get_settings
from src.utils.redaction import redact_text


logger = logging.getLogger(__name__)


class VideoStatus(str, Enum):
    """
    视频任务状态（MiniMax 官方 API 定义）

    注意：MiniMax API 使用大写开头：
    - Preparing   → 准备中
    - Queueing   → 队列中
    - Processing  → 生成中
    - Success    → 成功
    - Fail       → 失败
    """

    PREPARING = "Preparing"
    QUEUEING = "Queueing"
    PROCESSING = "Processing"
    SUCCESS = "Success"
    FAILED = "Fail"


class VideoAPI(BaseAPIClient):
    """视频生成 API 客户端"""

    # Token Plan 路径固定收敛到官方支持组合
    RESOLUTIONS = ["768P"]
    DURATIONS = [6]
    SUPPORTED_MODELS = {
        "MiniMax-Hailuo-2.3",
        "MiniMax-Hailuo-2.3-Fast",
    }

    def __init__(self, api_key: Optional[str] = None):
        """
        初始化视频 API 客户端

        Args:
            api_key: API 密钥
        """
        super().__init__(api_key)
        self.settings = get_settings()

    def _normalize_video_spec(
        self, duration: int, resolution: str
    ) -> tuple[Dict[str, Any], Dict[str, Any]]:
        requested = {
            "duration": duration,
            "resolution": resolution,
        }
        applied = {
            "duration": 6,
            "resolution": "768P",
        }
        return requested, applied

    def _resolve_model_for_tier(
        self,
        tier: str,
        requested_model: Optional[str],
        *,
        mode: str,
    ) -> str:
        if mode == "text_to_video":
            if requested_model == self.settings.models.video_model:
                return self.settings.models.video_model
            return self.settings.models.video_model
        if requested_model in self.SUPPORTED_MODELS:
            return requested_model
        return self.settings.models.video_model_fast

    def _resource_for_model(self, model_name: str) -> str:
        return (
            "video_fast"
            if model_name == self.settings.models.video_model_fast
            else "video_standard"
        )

    def _normalize_first_frame_image(self, first_frame_image: str) -> str:
        candidate = Path(first_frame_image)
        if candidate.exists() and candidate.is_file():
            mime_type, _ = mimetypes.guess_type(candidate.name)
            resolved_mime = mime_type or "image/jpeg"
            encoded = base64.b64encode(candidate.read_bytes()).decode("ascii")
            return f"data:{resolved_mime};base64,{encoded}"
        return first_frame_image

    def create_text_to_video(
        self,
        prompt: str,
        model: Optional[str] = None,
        duration: int = 6,
        resolution: str = "768P",
        prompt_optimizer: bool = True,
        fast_pretreatment: bool = False,
        callback_url: Optional[str] = None,
        **kwargs,
    ) -> str:
        """
        创建文生视频任务

        Args:
            prompt: 视频描述文本（最大2000字符）
                   Token Plan 路径下仅使用 Hailuo-2.3 系列，支持 [指令] 语法控制运镜：
                   - 左右移: [左移], [右移]
                   - 左右摇: [左摇], [右摇]
                   - 推拉: [推进], [拉远]
                   - 升降: [上升], [下降]
                   - 上下摇: [上摇], [下摇]
                   - 变焦: [变焦推近], [变焦拉远]
                   - 其他: [晃动], [跟随], [固定]
                   - 组合运镜: [左摇,上升]（同一组内多个指令同时生效）
                   - 顺序运镜: "...[推进], 然后...[拉远]"
            model: 模型名称，仅允许 `MiniMax-Hailuo-2.3` / `MiniMax-Hailuo-2.3-Fast`
            duration: 请求视频时长；Token Plan 路径会归一化为 6 秒
            resolution: 请求分辨率；Token Plan 路径会归一化为 `768P`
            prompt_optimizer: 是否自动优化 prompt
            fast_pretreatment: 是否缩短优化耗时（仅 Hailuo-2.3 系列）
            callback_url: 回调 URL
            **kwargs: 其他参数

        Returns:
            任务 ID

        Example:
            >>> api = VideoAPI()
            >>> task_id = api.create_text_to_video(
            ...     prompt="一个人在咖啡馆看书 [推进]",
            ...     duration=6,
            ...     resolution="768P"
            ... )
        """
        requested_model = model or self.settings.models.video_model_fast
        requested_spec, applied_spec = self._normalize_video_spec(duration, resolution)

        def build_payload(tier: str):
            applied_model = self._resolve_model_for_tier(
                tier,
                requested_model,
                mode="text_to_video",
            )
            data = {
                "model": applied_model,
                "prompt": prompt,
                "duration": applied_spec["duration"],
                "resolution": applied_spec["resolution"],
                "prompt_optimizer": prompt_optimizer,
            }
            if fast_pretreatment:
                data["fast_pretreatment"] = True
            if callback_url:
                data["callback_url"] = callback_url
            data.update(kwargs)
            return data, {
                "requested_model": requested_model,
                "applied_model": applied_model,
                "resource_used": self._resource_for_model(applied_model),
                "requested_video_spec": requested_spec,
                "applied_video_spec": applied_spec,
                "requested_generation_mode": "text_to_video",
                "applied_generation_mode": "text_to_video",
            }

        logger.info(
            "创建视频生成任务，请求模型: %s, 请求规格: %ss/%s, 应用规格: %ss/%s",
            requested_model,
            requested_spec["duration"],
            requested_spec["resolution"],
            applied_spec["duration"],
            applied_spec["resolution"],
        )
        logger.debug(f"Prompt: {prompt[:100]}...")

        result = self.execute_tiered_request(
            "POST",
            "/v1/video_generation",
            build_payload=build_payload,
            resource="video",
            refresh_remote=True,
        )

        task_id = result["task_id"]
        self.remember_task_metadata(task_id, self.last_request_metadata)
        logger.info(f"视频任务已创建，ID: {task_id}")

        return task_id

    def create_image_to_video(
        self,
        prompt: str,
        first_frame_image: str,
        model: Optional[str] = None,
        duration: int = 6,
        resolution: str = "768P",
        **kwargs,
    ) -> str:
        """
        创建图生视频任务

        Args:
            prompt: 视频描述文本
            first_frame_image: 首帧图片（URL 或 base64）
            model: 模型名称
            duration: 视频时长
            resolution: 分辨率
            **kwargs: 其他参数

        Returns:
            任务 ID
        """
        requested_model = model or self.settings.models.video_model_fast
        requested_spec, applied_spec = self._normalize_video_spec(duration, resolution)
        normalized_first_frame = self._normalize_first_frame_image(first_frame_image)

        def build_payload(tier: str):
            applied_model = self._resolve_model_for_tier(
                tier,
                requested_model,
                mode="image_to_video",
            )
            data = {
                "model": applied_model,
                "prompt": prompt,
                "first_frame_image": normalized_first_frame,
                "duration": applied_spec["duration"],
                "resolution": applied_spec["resolution"],
            }
            data.update(kwargs)
            return data, {
                "requested_model": requested_model,
                "applied_model": applied_model,
                "resource_used": self._resource_for_model(applied_model),
                "requested_video_spec": requested_spec,
                "applied_video_spec": applied_spec,
                "requested_generation_mode": "image_to_video",
                "applied_generation_mode": "image_to_video",
            }

        logger.info(f"创建图生视频任务，请求模型: {requested_model}")

        result = self.execute_tiered_request(
            "POST",
            "/v1/video_generation",
            build_payload=build_payload,
            resource="video",
            refresh_remote=True,
        )

        task_id = result["task_id"]
        self.remember_task_metadata(task_id, self.last_request_metadata)
        return task_id

    def query_task(self, task_id: str) -> Dict[str, Any]:
        """
        查询视频生成任务状态

        Args:
            task_id: 任务 ID

        Returns:
            任务状态信息，包含：
            - task_id: 任务 ID
            - status: 状态（pending/processing/success/failed）
            - file_id: 文件 ID（成功时）
            - download_url: 视频下载 URL（成功时）
            - base_resp: 响应状态

        Example:
            >>> api = VideoAPI()
            >>> status = api.query_task("123456")
            >>> print(status["status"])
        """
        task_metadata = self.get_task_metadata(task_id)
        tier = task_metadata.get("key_tier_used")
        if tier:
            result = self._request_with_tier(
                "GET",
                "/v1/query/video_generation",
                tier=tier,
                params={"task_id": task_id},
            )
        else:
            result = self.execute_tiered_request(
                "GET",
                "/v1/query/video_generation",
                build_payload=lambda current_tier: (
                    {"task_id": task_id},
                    {"requested_model": None, "applied_model": None},
                ),
            )

        status = result.get("status", "")
        logger.debug(f"任务 {task_id} 状态: {status}")

        return result

    def wait_for_completion(
        self,
        task_id: str,
        poll_interval: Optional[float] = None,
        max_wait: Optional[float] = None,
        on_progress: Optional[Callable[[float, Optional[str]], None]] = None,
    ) -> Dict[str, Any]:
        """
        等待视频生成完成

        Args:
            task_id: 任务 ID
            poll_interval: 轮询间隔（秒）
            max_wait: 最大等待时间（秒）
            on_progress: 进度回调函数，接收 (elapsed, status) 参数

        Returns:
            最终任务状态

        Raises:
            TimeoutError: 超时
            RuntimeError: 生成失败
        """
        if poll_interval is None:
            poll_interval = self.settings.api.video_poll_interval
        if max_wait is None:
            max_wait = self.settings.api.video_max_wait

        start_time = time.time()

        logger.info(f"开始等待视频任务 {task_id} 完成...")

        while True:
            # 检查超时
            elapsed = time.time() - start_time
            if elapsed > max_wait:
                raise TimeoutError(f"视频生成超时（{max_wait}秒）")

            # 查询状态
            status_info = self.query_task(task_id)
            status = status_info.get("status")

            # 触发进度回调
            if on_progress:
                try:
                    on_progress(elapsed, status)
                except Exception:
                    pass

            if status == VideoStatus.SUCCESS.value:
                task_metadata = self.get_task_metadata(task_id)
                if task_metadata:
                    self.last_request_metadata = task_metadata
                    status_info.setdefault("_routing", task_metadata.copy())
                logger.info(f"视频生成成功，文件 ID: {status_info.get('file_id')}")
                return status_info

            elif status == VideoStatus.FAILED.value:
                error_msg = status_info.get("base_resp", {}).get(
                    "status_msg", "未知错误"
                )
                raise RuntimeError(f"视频生成失败: {error_msg}")

            elif status in [
                VideoStatus.PREPARING.value,
                VideoStatus.QUEUEING.value,
                VideoStatus.PROCESSING.value,
            ]:
                logger.debug(f"视频生成中... 状态={status} ({elapsed:.1f}秒)")
                time.sleep(poll_interval)

            else:
                logger.warning(f"未知状态: {status}")
                time.sleep(poll_interval)

    def download_video(
        self,
        file_id: Optional[str] = None,
        download_url: Optional[str] = None,
        output_path: Optional[str] = None,
        status_info: Optional[Dict[str, Any]] = None,
    ) -> Path:
        """
        下载生成的视频

        优先使用以下顺序获取下载链接：
        1. 直接传入的 download_url
        2. 从 status_info 中提取 download_url（API 返回的成功结果）
        3. 使用 file_id 通过 API 获取下载链接

        Args:
            file_id: 文件 ID（可选，已废弃，推荐使用 download_url）
            download_url: 直接可用的下载 URL（推荐）
            output_path: 输出路径（可选，内部自动生成）
            status_info: 查询任务返回的完整状态信息（包含 download_url）

        Returns:
            保存的文件路径
        """
        # 优先从 status_info 提取 download_url
        resolved_url = download_url
        if resolved_url is None and status_info:
            logger.debug(f"status_info keys: {list(status_info.keys())}")
            resolved_url = status_info.get("download_url")
            # 兼容不同的响应格式
            if not resolved_url and "data" in status_info:
                resolved_url = status_info.get("data", {}).get("download_url")
            # 从 status_info 中提取 file_id 作为备选
            if not file_id:
                file_id = status_info.get("file_id")

        # 如果既没有 download_url 也没有 status_info，通过 file_id 调用官方接口获取
        if resolved_url is None and file_id:
            logger.info(f"通过 file_id {file_id} 从 MiniMax API 获取下载链接")
            routing = (status_info or {}).get("_routing", {}) if status_info else {}
            tier = routing.get("key_tier_used") or self.last_request_metadata.get(
                "key_tier_used"
            )
            if tier:
                file_info = self._request_with_tier(
                    "GET",
                    "/v1/files/retrieve",
                    tier=tier,
                    params={"file_id": file_id},
                )
            else:
                file_info = self.execute_tiered_request(
                    "GET",
                    "/v1/files/retrieve",
                    build_payload=lambda current_tier: (
                        {"file_id": file_id},
                        {"requested_model": None, "applied_model": None},
                    ),
                )
            resolved_url = file_info.get("file", {}).get("download_url")

        if resolved_url is None:
            raise ValueError(
                "download_video 需要 download_url 参数，"
                "或者传入包含 download_url 的 status_info，"
                "或者传入 file_id"
            )

        logger.info("下载视频，URL: %s", redact_text(resolved_url)[:80])

        # 自动生成输出路径
        if output_path is None:
            ext = "mp4"
            output_path = str(
                self.settings.output.base_dir
                / self.settings.output.video_dir
                / f"video_{file_id or 'download'}.{ext}"
            )

        output_file = Path(output_path)
        output_file.parent.mkdir(parents=True, exist_ok=True)

        download_timeout = getattr(
            self, "timeout", self.settings.api.request_timeout * 2
        )
        with requests.Session() as session:
            session.trust_env = False
            response = session.get(
                resolved_url,
                timeout=download_timeout,
                allow_redirects=True,
                stream=True,
            )
            response.raise_for_status()

            with open(output_file, "wb") as f:
                for chunk in response.iter_content(chunk_size=1024 * 1024):
                    if chunk:
                        f.write(chunk)

        logger.info(f"视频已保存到: {output_file}")
        return output_file

    def generate_video(
        self,
        prompt: str,
        output_path: Optional[str] = None,
        model: Optional[str] = None,
        duration: int = 6,
        resolution: str = "768P",
        **kwargs,
    ) -> Path:
        """
        一站式视频生成（创建任务 + 等待完成 + 下载）

        Args:
            prompt: 视频描述
            output_path: 输出路径（可选，自动生成）
            model: 模型名称
            duration: 视频时长
            resolution: 分辨率
            **kwargs: 其他参数

        Returns:
            保存的视频文件路径

        Example:
            >>> api = VideoAPI()
            >>> video_path = api.generate_video(
            ...     prompt="夕阳下的海滩 [左摇]",
            ...     output_path="output/videos/beach.mp4"
            ... )
        """
        # 创建任务
        task_id = self.create_text_to_video(
            prompt=prompt,
            model=model,
            duration=duration,
            resolution=resolution,
            **kwargs,
        )

        # 等待完成
        result = self.wait_for_completion(task_id)

        # 下载视频（优先使用 API 返回的 download_url）
        video_path = self.download_video(output_path=output_path, status_info=result)
        task_metadata = self.get_task_metadata(task_id)
        if task_metadata:
            self.last_request_metadata = task_metadata

        return video_path

    def generate_video_from_image(
        self,
        prompt: str,
        first_frame_image: str,
        output_path: Optional[str] = None,
        model: Optional[str] = None,
        duration: int = 6,
        resolution: str = "768P",
        **kwargs,
    ) -> Path:
        """
        一站式图生视频生成（创建任务 + 等待完成 + 下载）。

        `first_frame_image` 支持 MiniMax 官方允许的 URL / base64，也支持本地文件路径；
        本地文件会自动转为 data URL 后提交。
        """
        task_id = self.create_image_to_video(
            prompt=prompt,
            first_frame_image=first_frame_image,
            model=model,
            duration=duration,
            resolution=resolution,
            **kwargs,
        )

        result = self.wait_for_completion(task_id)
        video_path = self.download_video(output_path=output_path, status_info=result)
        task_metadata = self.get_task_metadata(task_id)
        if task_metadata:
            self.last_request_metadata = task_metadata

        return video_path

    def generate_video_async(
        self,
        prompt: str,
        model: Optional[str] = None,
        duration: int = 6,
        resolution: str = "768P",
        **kwargs,
    ) -> str:
        """
        异步提交视频生成任务（不等待结果，返回 task_id）

        适用于需要并发生成多个视频的场景。

        Args:
            prompt: 视频描述
            model: 模型名称
            duration: 视频时长
            resolution: 分辨率
            **kwargs: 其他参数

        Returns:
            任务 ID（后续用 query_task + download_video 获取结果）

        Example:
            >>> api = VideoAPI()
            >>> task_id = api.generate_video_async(prompt="日出")
            >>> # ... 同时提交其他任务 ...
            >>> # 统一等待: api.wait_for_completion(task_id)
        """
        task_id = self.create_text_to_video(
            prompt=prompt,
            model=model,
            duration=duration,
            resolution=resolution,
            **kwargs,
        )
        logger.info(f"异步任务已提交，ID: {task_id}")
        return task_id
