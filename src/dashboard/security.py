# -*- coding: utf-8 -*-
"""Dashboard 登录、会话与 CSRF 防护。"""

from __future__ import annotations

import hmac
import os
import secrets
import time
from dataclasses import dataclass
from http.cookies import SimpleCookie
from typing import Dict, Optional


def _coerce_bool(value: str | None, default: bool = False) -> bool:
    if value is None:
        return default
    return value.strip().lower() in {"1", "true", "yes", "y", "on"}


@dataclass
class DashboardSession:
    session_id: str
    csrf_token: str
    authenticated: bool
    created_at: float
    expires_at: float


class DashboardSecurity:
    """内存会话管理。适合单进程本地 Dashboard。"""

    session_cookie_name = "auto_tiktok_session"
    csrf_cookie_name = "auto_tiktok_csrf"

    def __init__(
        self,
        *,
        token: Optional[str] = None,
        session_timeout_seconds: int = 24 * 3600,
        secure_cookies: bool = False,
    ):
        self.token = token or os.getenv("AUTO_TIKTOK_DASHBOARD_TOKEN", "")
        self.session_timeout_seconds = session_timeout_seconds
        self.secure_cookies = secure_cookies
        self.sessions: Dict[str, DashboardSession] = {}

    @property
    def auth_required(self) -> bool:
        return bool(self.token)

    @classmethod
    def from_env(cls) -> "DashboardSecurity":
        timeout = int(os.getenv("AUTO_TIKTOK_DASHBOARD_SESSION_SECONDS", "86400"))
        secure = _coerce_bool(os.getenv("AUTO_TIKTOK_DASHBOARD_SECURE_COOKIES"), False)
        return cls(session_timeout_seconds=timeout, secure_cookies=secure)

    def create_session(self, *, authenticated: bool) -> DashboardSession:
        now = time.time()
        session = DashboardSession(
            session_id=secrets.token_urlsafe(32),
            csrf_token=secrets.token_urlsafe(32),
            authenticated=authenticated,
            created_at=now,
            expires_at=now + self.session_timeout_seconds,
        )
        self.sessions[session.session_id] = session
        return session

    def get_session(self, cookie_header: str | None) -> Optional[DashboardSession]:
        if not cookie_header:
            return None
        cookie = SimpleCookie()
        cookie.load(cookie_header)
        morsel = cookie.get(self.session_cookie_name)
        if not morsel:
            return None
        session = self.sessions.get(morsel.value)
        if not session:
            return None
        if session.expires_at < time.time():
            self.sessions.pop(session.session_id, None)
            return None
        return session

    def ensure_session(self, cookie_header: str | None) -> tuple[DashboardSession, bool]:
        session = self.get_session(cookie_header)
        if session:
            return session, False
        return self.create_session(authenticated=not self.auth_required), True

    def authenticate(self, submitted_token: str) -> DashboardSession:
        if not self.token:
            return self.create_session(authenticated=True)
        if not hmac.compare_digest(submitted_token or "", self.token):
            raise PermissionError("登录失败")
        return self.create_session(authenticated=True)

    def clear_session(self, cookie_header: str | None) -> None:
        session = self.get_session(cookie_header)
        if session:
            self.sessions.pop(session.session_id, None)

    def is_authenticated(self, session: Optional[DashboardSession]) -> bool:
        if not self.auth_required:
            return True
        return bool(session and session.authenticated)

    def validate_csrf(
        self,
        *,
        session: Optional[DashboardSession],
        header_value: str | None,
        cookie_header: str | None,
    ) -> bool:
        if not session:
            return False
        cookie = SimpleCookie()
        if cookie_header:
            cookie.load(cookie_header)
        cookie_value = cookie.get(self.csrf_cookie_name)
        return bool(
            header_value
            and cookie_value
            and hmac.compare_digest(header_value, session.csrf_token)
            and hmac.compare_digest(cookie_value.value, session.csrf_token)
        )

    def session_headers(self, session: DashboardSession) -> list[tuple[str, str]]:
        return [
            ("Set-Cookie", self._cookie(self.session_cookie_name, session.session_id, http_only=True)),
            ("Set-Cookie", self._cookie(self.csrf_cookie_name, session.csrf_token, http_only=False)),
        ]

    def clear_headers(self) -> list[tuple[str, str]]:
        return [
            ("Set-Cookie", self._cookie(self.session_cookie_name, "", max_age=0, http_only=True)),
            ("Set-Cookie", self._cookie(self.csrf_cookie_name, "", max_age=0, http_only=False)),
        ]

    def _cookie(
        self,
        name: str,
        value: str,
        *,
        max_age: Optional[int] = None,
        http_only: bool,
    ) -> str:
        parts = [f"{name}={value}", "Path=/", "SameSite=Lax"]
        if http_only:
            parts.append("HttpOnly")
        if self.secure_cookies:
            parts.append("Secure")
        if max_age is not None:
            parts.append(f"Max-Age={max_age}")
        return "; ".join(parts)
