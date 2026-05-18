from __future__ import annotations

import sys
from pathlib import Path

import pytest

from config.settings import Settings
from config.token_plan import TokenPlanQuotaTracker


PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))


@pytest.fixture(autouse=True)
def reset_settings_singleton(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    monkeypatch.chdir(tmp_path)
    monkeypatch.delenv("MINIMAX_TOKEN_PLAN_TIER", raising=False)
    monkeypatch.delenv("MINIMAX_TOKEN_PLAN_KEY", raising=False)
    monkeypatch.delenv("MINIMAX_TOKEN_PLAN_KEY2", raising=False)
    monkeypatch.setattr(
        Settings,
        "refresh_quota_remains",
        lambda self, tiers=None: {},
    )
    monkeypatch.setattr(
        TokenPlanQuotaTracker,
        "refresh_remote_remains",
        lambda self, tier, timeout=5.0: None,
    )
    Settings._instance = None
    yield
    Settings._instance = None
