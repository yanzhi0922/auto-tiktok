from __future__ import annotations

from requests.exceptions import HTTPError

import pytest

from src.api.base import BaseAPIClient, MiniMaxAPIError


class FakeResponse:
    def __init__(self, payload: dict, status_code: int = 200, text: str = ""):
        self._payload = payload
        self.status_code = status_code
        self.text = text

    def raise_for_status(self) -> None:
        if self.status_code >= 400:
            raise HTTPError(response=self)

    def json(self) -> dict:
        return self._payload


def test_model_unsupported_does_not_switch_to_backup(monkeypatch: pytest.MonkeyPatch):
    client = BaseAPIClient(api_key="primary")
    client.backup_api_key = "backup"
    calls: list[str] = []

    def fake_request(**_: object) -> FakeResponse:
        calls.append("called")
        return FakeResponse(
            {
                "base_resp": {
                    "status_code": 2061,
                    "status_msg": "your current token plan not support model",
                }
            }
        )

    monkeypatch.setattr(client.session, "request", fake_request)

    with pytest.raises(MiniMaxAPIError) as exc_info:
        client.post("/v1/video_generation", data={"prompt": "test"})

    assert exc_info.value.status_code == 2061
    assert client.api_key == "primary"
    assert len(calls) == 1


def test_invalid_primary_key_switches_once_to_backup(
    monkeypatch: pytest.MonkeyPatch,
):
    client = BaseAPIClient(api_key="primary")
    client.backup_api_key = "backup"
    calls: list[str] = []

    responses = iter(
        [
            FakeResponse(
                {
                    "base_resp": {
                        "status_code": 2049,
                        "status_msg": "invalid api key",
                    }
                }
            ),
            FakeResponse({"base_resp": {"status_code": 0}, "data": {"ok": True}}),
        ]
    )

    def fake_request(**_: object) -> FakeResponse:
        calls.append(client.api_key)
        return next(responses)

    monkeypatch.setattr(client.session, "request", fake_request)

    result = client.post("/v1/text/chatcompletion_v2", data={"messages": []})

    assert result["data"]["ok"] is True
    assert calls == ["primary", "backup"]
    assert client.api_key == "backup"


def test_execute_tiered_request_does_not_swallow_keyboard_interrupt(
    monkeypatch: pytest.MonkeyPatch,
):
    client = BaseAPIClient(api_key="primary")
    monkeypatch.setattr(
        client.settings.api,
        "tier_order",
        ["ultra"],
    )
    monkeypatch.setattr(
        client.settings.api,
        "get_api_key",
        lambda tier: "primary",
    )

    def fake_request(*_: object, **__: object):
        raise KeyboardInterrupt()

    monkeypatch.setattr(client, "_request_with_tier", fake_request)

    with pytest.raises(KeyboardInterrupt):
        client.execute_tiered_request(
            "POST",
            "/v1/text/chatcompletion_v2",
            build_payload=lambda tier: {"messages": []},
            resource="text",
        )
