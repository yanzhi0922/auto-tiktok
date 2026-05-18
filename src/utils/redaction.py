# -*- coding: utf-8 -*-
"""敏感信息脱敏工具。"""

from __future__ import annotations

import json
import re
from typing import Any


SECRET_PATTERNS = [
    re.compile(r"sk-[A-Za-z0-9_\-]{12,}"),
    re.compile(r"(Bearer\s+)[A-Za-z0-9_\-\.=]{12,}", re.IGNORECASE),
    re.compile(r"((?:access_token|refresh_token|token|api_key|key)=)[^&\s]+", re.IGNORECASE),
    re.compile(r"(Authorization['\"]?\s*[:=]\s*['\"]?Bearer\s+)[^'\"\s,}]+", re.IGNORECASE),
]

SENSITIVE_KEYS = {
    "authorization",
    "api_key",
    "access_token",
    "refresh_token",
    "token",
    "key",
    "secret",
    "upload_url",
    "download_url",
}


def redact_text(value: Any) -> str:
    text = str(value)
    for pattern in SECRET_PATTERNS:
        text = pattern.sub(lambda match: f"{match.group(1)}***" if match.groups() else "***", text)
    return text


def redact_obj(value: Any) -> Any:
    if isinstance(value, dict):
        redacted = {}
        for key, item in value.items():
            key_text = str(key)
            if key_text.lower() in SENSITIVE_KEYS or any(part in key_text.lower() for part in ("token", "secret", "key")):
                redacted[key] = "***" if item else item
            else:
                redacted[key] = redact_obj(item)
        return redacted
    if isinstance(value, list):
        return [redact_obj(item) for item in value]
    if isinstance(value, tuple):
        return tuple(redact_obj(item) for item in value)
    if isinstance(value, str):
        return redact_text(value)
    return value


def redact_json(value: Any) -> str:
    return json.dumps(redact_obj(value), ensure_ascii=False, indent=2)
