# -*- coding: utf-8 -*-
"""
MiniMax API 基础客户端
提供统一的 HTTP 请求处理、错误重试和响应解析功能
"""

import time
import logging
from typing import Optional, Dict, Any, List
from functools import wraps
import requests
from requests.exceptions import RequestException, Timeout, ConnectionError, HTTPError

from config.settings import get_settings
from src.utils.redaction import redact_text


# 配置日志
logger = logging.getLogger(__name__)


NON_IDEMPOTENT_POST_ENDPOINTS = {
    "/v1/t2a_v2",
    "/v1/image_generation",
    "/v1/music_generation",
    "/v1/video_generation",
}


class MiniMaxAPIError(RequestException):
    """带状态码和重试建议的 MiniMax API 业务异常。"""

    def __init__(
        self,
        status_code: int,
        status_msg: str,
        *,
        should_retry: bool = False,
        category: str = "unknown",
        tier: Optional[str] = None,
    ):
        self.status_code = int(status_code)
        self.status_msg = status_msg
        self.should_retry = should_retry
        self.category = category
        self.tier = tier
        super().__init__(f"API 错误[{self.status_code}]: {self.status_msg}")


def _is_retryable_http_error(exc: BaseException) -> bool:
    if isinstance(exc, MiniMaxAPIError):
        return exc.should_retry

    if isinstance(exc, HTTPError):
        response = exc.response
        status_code = response.status_code if response is not None else None
        return bool(status_code in {408, 409, 429} or (status_code and status_code >= 500))

    if isinstance(exc, (Timeout, ConnectionError)):
        return True

    if isinstance(exc, RequestException):
        return bool(getattr(exc, "should_retry", True))

    return False


def _is_non_idempotent_request(method: str, endpoint: str) -> bool:
    return method.upper() == "POST" and endpoint in NON_IDEMPOTENT_POST_ENDPOINTS


def retry_on_failure(max_retries: int = None, delay: float = None, backoff: float = None):
    """
    错误重试装饰器
    
    Args:
        max_retries: 最大重试次数，None则使用配置值
        delay: 初始延迟（秒），None则使用配置值
        backoff: 退避倍数，None则使用配置值
        
    Returns:
        装饰器函数
    """
    def decorator(func):
        @wraps(func)
        def wrapper(*args, **kwargs):
            settings = get_settings()
            _max_retries = max_retries or settings.api.max_retries
            _delay = delay or settings.api.retry_delay
            _backoff = backoff or settings.api.retry_backoff
            method = str(args[1]) if len(args) > 1 else str(kwargs.get("method", ""))
            endpoint = str(args[2]) if len(args) > 2 else str(kwargs.get("endpoint", ""))
            non_idempotent_request = _is_non_idempotent_request(method, endpoint)
            
            last_exception = None
            
            for attempt in range(_max_retries + 1):
                try:
                    return func(*args, **kwargs)
                except (RequestException, Timeout, ConnectionError) as e:
                    last_exception = e
                    should_retry = _is_retryable_http_error(e)
                    if non_idempotent_request:
                        should_retry = False

                    if attempt < _max_retries and should_retry:
                        wait_time = _delay * (_backoff ** attempt)
                        logger.warning(
                            f"API 调用失败 (尝试 {attempt + 1}/{_max_retries + 1}): {str(e)}"
                        )
                        logger.info(f"等待 {wait_time:.1f} 秒后重试...")
                        time.sleep(wait_time)
                    else:
                        logger.error(f"API 调用失败，已达最大重试次数: {str(e)}")
                        break
                        
            raise last_exception
        return wrapper
    return decorator


class BaseAPIClient:
    """MiniMax API 基础客户端类"""

    AUTH_ERROR_CODES = {2049, 401, 403}
    MODEL_UNSUPPORTED_CODES = {2061}
    CAPACITY_ERROR_CODES = {1002, 1008, 2045, 2056, 429}
    RETRYABLE_MINIMAX_ERROR_CODES = {
        1001,
        1002,
        2045,
        2056,
        3001,
    }
    
    def __init__(self, api_key: Optional[str] = None):
        """
        初始化 API 客户端
        
        Args:
            api_key: API 密钥，None则从配置读取
        """
        self.settings = get_settings()
        self.api_key = api_key or self.settings.api.api_key
        self.backup_api_key = self.settings.api.backup_api_key
        self.base_url = self.settings.api.base_url
        self.backup_base_url = self.settings.api.backup_base_url
        self.timeout = self.settings.api.request_timeout
        self.last_request_metadata: Dict[str, Any] = {}
        self.last_request_result: Optional[Dict[str, Any]] = None
        self._task_metadata: Dict[str, Dict[str, Any]] = {}
        
        # 初始化 HTTP 会话
        self.session = requests.Session()
        self.session.headers.update({
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
        })
        
        if not self.api_key:
            logger.warning("API Key 未设置，请检查环境变量 MINIMAX_TOKEN_PLAN_KEY")

    def _switch_to_backup_key(self):
        """切换到备用 API Key"""
        if self.backup_api_key and self.api_key != self.backup_api_key:
            logger.warning("主 API Key 失败，切换到备用 Key...")
            self.api_key = self.backup_api_key
            self.session.headers.update({
                "Authorization": f"Bearer {self.api_key}",
            })
            return True
        return False

    def _maybe_switch_on_auth_error(self, status_code: int) -> bool:
        if status_code in self.AUTH_ERROR_CODES:
            return self._switch_to_backup_key()
        return False

    def _classify_status_code(self, status_code: int) -> str:
        if status_code in self.AUTH_ERROR_CODES:
            return "auth"
        if status_code in self.MODEL_UNSUPPORTED_CODES:
            return "unsupported"
        if status_code in self.CAPACITY_ERROR_CODES:
            return "capacity"
        if status_code in self.RETRYABLE_MINIMAX_ERROR_CODES or status_code >= 500:
            return "temporary"
        return "unknown"

    def _classify_exception(self, exc: BaseException) -> str:
        if isinstance(exc, MiniMaxAPIError):
            return exc.category
        if isinstance(exc, (Timeout, ConnectionError)):
            return "temporary"
        if isinstance(exc, HTTPError):
            response = exc.response
            status_code = response.status_code if response is not None else 0
            return self._classify_status_code(int(status_code or 0))
        return "unknown"

    def _should_try_next_tier(
        self,
        exc: BaseException,
        *,
        method: Optional[str] = None,
        endpoint: Optional[str] = None,
    ) -> bool:
        category = self._classify_exception(exc)
        if method and endpoint and _is_non_idempotent_request(method, endpoint):
            if category == "temporary":
                return False
        return category in {"auth", "unsupported", "capacity", "temporary"}

    def _raise_minimax_error(
        self,
        status_code: int,
        status_msg: str,
        *,
        tier: Optional[str] = None,
    ) -> None:
        logger.error(f"MiniMax API 错误: {status_code} - {status_msg}")
        raise MiniMaxAPIError(
            status_code,
            status_msg or "未知错误",
            should_retry=status_code in self.RETRYABLE_MINIMAX_ERROR_CODES,
            category=self._classify_status_code(status_code),
            tier=tier,
        )
    
    def _build_url(self, endpoint: str, use_backup: bool = False) -> str:
        """
        构建完整的 API URL
        
        Args:
            endpoint: API 端点路径
            use_backup: 是否使用备用地址
            
        Returns:
            完整的 URL
        """
        base = self.backup_base_url if use_backup else self.base_url
        return f"{base}{endpoint}"

    def _build_headers(self, api_key: Optional[str] = None) -> Dict[str, str]:
        resolved_api_key = api_key or self.api_key
        return {
            "Authorization": f"Bearer {resolved_api_key}",
            "Content-Type": "application/json",
        }

    def _raise_http_status_error(
        self, response: requests.Response, tier: Optional[str] = None
    ) -> None:
        status_code = int(response.status_code)
        status_text = redact_text(response.text or response.reason or "HTTP 错误")
        if status_code in {401, 403, 429} or status_code >= 500:
            raise MiniMaxAPIError(
                status_code,
                status_text,
                should_retry=status_code in {429} or status_code >= 500,
                category=self._classify_status_code(status_code),
                tier=tier,
            )
        response.raise_for_status()

    @retry_on_failure()
    def _request_once(
        self,
        method: str,
        endpoint: str,
        *,
        api_key: Optional[str] = None,
        data: Optional[Dict[str, Any]] = None,
        params: Optional[Dict[str, Any]] = None,
        use_backup: bool = False,
        tier: Optional[str] = None,
        **kwargs,
    ) -> Dict[str, Any]:
        url = self._build_url(endpoint, use_backup)
        timeout = kwargs.pop("timeout", self.timeout)
        headers = self._build_headers(api_key)

        logger.debug(f"发送 {method} 请求到 {url}")

        try:
            response = self.session.request(
                method=method,
                url=url,
                json=data,
                params=params,
                timeout=timeout,
                headers=headers,
                **kwargs,
            )
            if response.status_code >= 400:
                self._raise_http_status_error(response, tier=tier)

            result = response.json()
            if "base_resp" in result:
                status_code = int(result["base_resp"].get("status_code", 0) or 0)
                status_msg = result["base_resp"].get("status_msg", "")
                if status_code != 0:
                    self._raise_minimax_error(status_code, status_msg, tier=tier)

            return result
        except requests.exceptions.JSONDecodeError as exc:
            logger.error(f"JSON 解析错误: {str(exc)}")
            parse_error = RequestException(f"响应解析失败: {str(exc)}")
            setattr(parse_error, "should_retry", False)
            raise parse_error

    def _request_with_tier(
        self,
        method: str,
        endpoint: str,
        *,
        tier: str,
        data: Optional[Dict[str, Any]] = None,
        params: Optional[Dict[str, Any]] = None,
        **kwargs,
    ) -> Dict[str, Any]:
        return self._request_once(
            method,
            endpoint,
            api_key=self.settings.api.get_api_key(tier),
            data=data,
            params=params,
            tier=tier,
            **kwargs,
        )
    
    @retry_on_failure()
    def _request(
        self,
        method: str,
        endpoint: str,
        data: Optional[Dict[str, Any]] = None,
        params: Optional[Dict[str, Any]] = None,
        use_backup: bool = False,
        allow_backup_switch: bool = True,
        **kwargs
    ) -> Dict[str, Any]:
        """
        发送 HTTP 请求
        
        Args:
            method: HTTP 方法（GET, POST等）
            endpoint: API 端点
            data: 请求体数据
            params: URL 参数
            use_backup: 是否使用备用地址
            **kwargs: 其他 requests 参数
            
        Returns:
            API 响应数据
            
        Raises:
            RequestException: 请求失败
        """
        url = self._build_url(endpoint, use_backup)
        timeout = kwargs.pop("timeout", self.timeout)
        
        logger.debug(f"发送 {method} 请求到 {url}")
        
        try:
            response = self.session.request(
                method=method,
                url=url,
                json=data,
                params=params,
                timeout=timeout,
                **kwargs
            )

            if (
                response.status_code in {401, 403}
                and allow_backup_switch
                and self._switch_to_backup_key()
            ):
                return self._request(
                    method,
                    endpoint,
                    data,
                    params,
                    use_backup=use_backup,
                    allow_backup_switch=False,
                    **kwargs,
                )
            
            # 检查 HTTP 状态码
            response.raise_for_status()
            
            # 解析 JSON 响应
            result = response.json()
            
            # 检查 MiniMax API 特有的错误码
            if "base_resp" in result:
                status_code = result["base_resp"].get("status_code", 0)
                status_msg = result["base_resp"].get("status_msg", "")
                
                if status_code != 0:
                    if (
                        allow_backup_switch
                        and self._maybe_switch_on_auth_error(status_code)
                    ):
                        return self._request(
                            method,
                            endpoint,
                            data,
                            params,
                            use_backup=use_backup,
                            allow_backup_switch=False,
                            **kwargs,
                        )
                    self._raise_minimax_error(status_code, status_msg)
            
            return result
            
        except requests.exceptions.HTTPError as e:
            logger.error(
                "HTTP 错误: %s - %s",
                e.response.status_code,
                redact_text(e.response.text),
            )
            raise
        except requests.exceptions.JSONDecodeError as e:
            logger.error(f"JSON 解析错误: {str(e)}")
            parse_error = RequestException(f"响应解析失败: {str(e)}")
            setattr(parse_error, "should_retry", False)
            raise parse_error

    def execute_tiered_request(
        self,
        method: str,
        endpoint: str,
        *,
        build_payload,
        resource: Optional[str] = None,
        amount: int = 1,
        tiers: Optional[List[str]] = None,
        refresh_remote: bool = False,
        **kwargs,
    ) -> Dict[str, Any]:
        route = tiers or self.settings.api.resolve_route()
        attempts: List[Dict[str, Any]] = []
        last_error: Optional[BaseException] = None

        for tier in route:
            if not self.settings.api.get_api_key(tier):
                continue

            payload_info = build_payload(tier)
            if isinstance(payload_info, tuple):
                payload, meta = payload_info
            else:
                payload, meta = payload_info, {}
            resource_key = (
                meta.get("resource_used", meta.get("resource", resource))
                if isinstance(meta, dict)
                else resource
            )

            if resource_key and not self.settings.check_quota(
                resource_key,
                amount=amount,
                tier=tier,
                refresh_remote=refresh_remote,
            ):
                last_error = MiniMaxAPIError(
                    2056,
                    f"{tier} 套餐 {resource_key} 配额不足",
                    should_retry=False,
                    category="capacity",
                    tier=tier,
                )
                attempts.append(
                    {
                        "tier": tier,
                        "category": "capacity",
                        "error": str(last_error),
                    }
                )
                continue

            try:
                result = self._request_with_tier(
                    method,
                    endpoint,
                    tier=tier,
                    data=payload if method.upper() != "GET" else None,
                    params=payload if method.upper() == "GET" else None,
                    **kwargs,
                )
                if resource_key:
                    self.settings.record_usage(resource_key, amount=amount, tier=tier)

                metadata = {
                    "key_tier_used": tier,
                    "tier_used": tier,
                    "resource_used": resource_key,
                    "requested_model": meta.get("requested_model"),
                    "applied_model": meta.get("applied_model", payload.get("model")),
                    "requested_video_spec": meta.get("requested_video_spec"),
                    "applied_video_spec": meta.get("applied_video_spec"),
                    "cross_tier_fallback": bool(attempts),
                    "attempted_tiers": [item["tier"] for item in attempts] + [tier],
                }
                metadata.update(
                    {
                        key: value
                        for key, value in meta.items()
                        if key
                        not in {
                            "requested_model",
                            "applied_model",
                            "requested_video_spec",
                            "applied_video_spec",
                        }
                    }
                )
                self.last_request_metadata = metadata
                self.last_request_result = result
                if isinstance(result, dict):
                    result.setdefault("_routing", metadata.copy())
                return result
            except Exception as exc:
                last_error = exc
                attempts.append(
                    {
                        "tier": tier,
                        "category": self._classify_exception(exc),
                        "error": str(exc),
                    }
                )
                if not self._should_try_next_tier(
                    exc,
                    method=method,
                    endpoint=endpoint,
                ):
                    break

        self.last_request_metadata = {
            "failed": True,
            "attempts": attempts,
        }
        if last_error:
            raise last_error
        raise RuntimeError("没有可用的 Token Plan 套餐层级")

    def remember_task_metadata(self, task_id: str, metadata: Dict[str, Any]) -> None:
        self._task_metadata[task_id] = metadata.copy()

    def get_task_metadata(self, task_id: str) -> Dict[str, Any]:
        return self._task_metadata.get(task_id, {}).copy()
    
    def get(
        self,
        endpoint: str,
        params: Optional[Dict[str, Any]] = None,
        **kwargs
    ) -> Dict[str, Any]:
        """
        发送 GET 请求
        
        Args:
            endpoint: API 端点
            params: URL 参数
            **kwargs: 其他参数
            
        Returns:
            API 响应数据
        """
        return self._request("GET", endpoint, params=params, **kwargs)
    
    def post(
        self,
        endpoint: str,
        data: Optional[Dict[str, Any]] = None,
        **kwargs
    ) -> Dict[str, Any]:
        """
        发送 POST 请求
        
        Args:
            endpoint: API 端点
            data: 请求体数据
            **kwargs: 其他参数
            
        Returns:
            API 响应数据
        """
        return self._request("POST", endpoint, data=data, **kwargs)
    
    def close(self):
        """关闭 HTTP 会话"""
        self.session.close()
    
    def __enter__(self):
        """上下文管理器入口"""
        return self
    
    def __exit__(self, exc_type, exc_val, exc_tb):
        """上下文管理器出口"""
        self.close()
