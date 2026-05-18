from __future__ import annotations

from pathlib import Path
from time import monotonic, sleep

import pytest
import requests

from config.settings import Settings
from config.token_plan import (
    DEFAULT_TOKEN_PLAN_QUOTAS,
    TokenPlanQuotaTracker,
    build_default_tiers,
)
from src.api.base import MiniMaxAPIError
from src.api.image import ImageAPI
from src.api.music import MusicAPI
from src.api.speech import SpeechAPI
from src.api.text import TextAPI
from src.api.video import VideoAPI
from src.pipeline.douyin_pipeline import DouyinPipeline
from src.pipeline.orchestrator import ContentPack, PipelineOrchestrator
from src.pipeline.report import ReportGenerator


def test_text_api_prefers_ultra_highspeed(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setenv("MINIMAX_TOKEN_PLAN_KEY", "ultra-key")
    monkeypatch.setenv("MINIMAX_TOKEN_PLAN_KEY2", "max-key")
    Settings._instance = None

    api = TextAPI()
    calls: list[tuple[str, str]] = []

    def fake_request(method: str, endpoint: str, *, tier: str, data=None, **kwargs):
        calls.append((tier, data["model"]))
        return {
            "base_resp": {"status_code": 0},
            "choices": [{"message": {"content": "ok"}}],
        }

    monkeypatch.setattr(api, "_request_with_tier", fake_request)

    result = api.chat_completion(messages=[{"role": "user", "content": "hi"}])

    assert result["choices"][0]["message"]["content"] == "ok"
    assert calls == [("ultra", "MiniMax-M2.7-highspeed")]
    assert api.last_request_metadata["key_tier_used"] == "ultra"
    assert api.last_request_metadata["applied_model"] == "MiniMax-M2.7-highspeed"


def test_text_api_falls_back_to_max_on_unsupported(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setenv("MINIMAX_TOKEN_PLAN_KEY", "ultra-key")
    monkeypatch.setenv("MINIMAX_TOKEN_PLAN_KEY2", "max-key")
    Settings._instance = None

    api = TextAPI()
    calls: list[tuple[str, str]] = []

    def fake_request(method: str, endpoint: str, *, tier: str, data=None, **kwargs):
        calls.append((tier, data["model"]))
        if tier == "ultra":
            raise MiniMaxAPIError(
                2061,
                "your current token plan not support model",
                should_retry=False,
                category="unsupported",
                tier=tier,
            )
        return {
            "base_resp": {"status_code": 0},
            "choices": [{"message": {"content": "fallback"}}],
        }

    monkeypatch.setattr(api, "_request_with_tier", fake_request)

    result = api.chat_completion(messages=[{"role": "user", "content": "hi"}])

    assert result["choices"][0]["message"]["content"] == "fallback"
    assert calls == [
        ("ultra", "MiniMax-M2.7-highspeed"),
        ("max", "MiniMax-M2.7"),
    ]
    assert api.last_request_metadata["key_tier_used"] == "max"
    assert api.last_request_metadata["cross_tier_fallback"] is True


def test_text_api_normalizes_explicit_incompatible_model(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setenv("MINIMAX_TOKEN_PLAN_KEY", "ultra-key")
    monkeypatch.setenv("MINIMAX_TOKEN_PLAN_KEY2", "max-key")
    Settings._instance = None

    api = TextAPI()
    calls: list[tuple[str, str]] = []

    def fake_request(method: str, endpoint: str, *, tier: str, data=None, **kwargs):
        calls.append((tier, data["model"]))
        return {
            "base_resp": {"status_code": 0},
            "choices": [{"message": {"content": "ok"}}],
        }

    monkeypatch.setattr(api, "_request_with_tier", fake_request)

    api.chat_completion(
        messages=[{"role": "user", "content": "hi"}],
        model="MiniMax-M2.7",
    )

    assert calls == [("ultra", "MiniMax-M2.7-highspeed")]
    assert api.last_request_metadata["requested_model"] == "MiniMax-M2.7"
    assert api.last_request_metadata["applied_model"] == "MiniMax-M2.7-highspeed"


def test_settings_accept_max_only_key(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.delenv("MINIMAX_TOKEN_PLAN_KEY", raising=False)
    monkeypatch.setenv("MINIMAX_TOKEN_PLAN_KEY2", "max-key")
    Settings._instance = None

    settings = Settings()

    assert settings.api.api_key == "max-key"
    assert settings.api.has_available_key() is True
    assert settings.api.resolve_route() == ["ultra", "max"]
    assert settings.api.get_api_key("ultra") == ""
    assert settings.api.get_api_key("max") == "max-key"


def test_settings_can_force_max_tier_with_single_primary_key(
    monkeypatch: pytest.MonkeyPatch,
):
    monkeypatch.setenv("MINIMAX_TOKEN_PLAN_TIER", "max")
    monkeypatch.setenv("MINIMAX_TOKEN_PLAN_KEY", "max-key")
    monkeypatch.delenv("MINIMAX_TOKEN_PLAN_KEY2", raising=False)
    Settings._instance = None

    settings = Settings()

    assert settings.api.api_key == "max-key"
    assert settings.api.backup_api_key == ""
    assert settings.api.has_available_key() is True
    assert settings.api.tier_order == ["max"]
    assert settings.api.resolve_route() == ["max"]
    assert settings.api.resolve_route("ultra") == ["max"]
    assert settings.api.get_api_key("ultra") == ""
    assert settings.api.get_api_key("max") == "max-key"


def test_quota_status_handles_no_enabled_text_tier(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.delenv("MINIMAX_TOKEN_PLAN_KEY", raising=False)
    monkeypatch.delenv("MINIMAX_TOKEN_PLAN_KEY2", raising=False)
    Settings._instance = None

    settings = Settings()
    status = settings.get_quota_status()["text_5h"]

    assert status["remaining"] == 0
    assert status["limit"] == 0
    assert status["used_in_window"] == 0
    assert status["window_seconds_remaining"] == 0


def test_video_request_is_normalized_to_token_plan_spec(
    monkeypatch: pytest.MonkeyPatch,
):
    monkeypatch.setenv("MINIMAX_TOKEN_PLAN_KEY", "ultra-key")
    monkeypatch.setenv("MINIMAX_TOKEN_PLAN_KEY2", "max-key")
    Settings._instance = None

    api = VideoAPI()
    calls: list[tuple[str, str, int, str]] = []

    def fake_request(method: str, endpoint: str, *, tier: str, data=None, **kwargs):
        calls.append((tier, data["model"], data["duration"], data["resolution"]))
        return {
            "base_resp": {"status_code": 0},
            "task_id": "task-1",
        }

    monkeypatch.setattr(api, "_request_with_tier", fake_request)

    task_id = api.create_text_to_video(
        prompt="demo",
        model="Legacy-Unsupported-Video-Model",
        duration=10,
        resolution="1080P",
    )

    metadata = api.get_task_metadata(task_id)

    assert calls == [("ultra", "MiniMax-Hailuo-2.3", 6, "768P")]
    assert metadata["requested_model"] == "Legacy-Unsupported-Video-Model"
    assert metadata["applied_model"] == "MiniMax-Hailuo-2.3"
    assert metadata["requested_video_spec"] == {
        "duration": 10,
        "resolution": "1080P",
    }
    assert metadata["applied_video_spec"] == {
        "duration": 6,
        "resolution": "768P",
    }


def test_image_quota_counts_requested_images(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setenv("MINIMAX_TOKEN_PLAN_KEY", "ultra-key")
    monkeypatch.setenv("MINIMAX_TOKEN_PLAN_KEY2", "max-key")
    Settings._instance = None

    api = ImageAPI()

    def fake_request(method: str, endpoint: str, *, tier: str, data=None, **kwargs):
        assert tier == "ultra"
        assert data["n"] == 3
        return {
            "base_resp": {"status_code": 0},
            "data": {"image_urls": ["https://example.invalid/demo.png"]},
        }

    monkeypatch.setattr(api, "_request_with_tier", fake_request)

    api.generate(prompt="demo", n=3)

    status = api.settings.get_quota_status()
    assert status["tiers"]["ultra"]["image"]["used"] == 3
    assert status["tiers"]["ultra"]["image"]["remaining"] == (
        DEFAULT_TOKEN_PLAN_QUOTAS["ultra"]["image_per_day"] - 3
    )


def test_speech_api_normalizes_unsupported_model(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setenv("MINIMAX_TOKEN_PLAN_KEY", "ultra-key")
    monkeypatch.setenv("MINIMAX_TOKEN_PLAN_KEY2", "max-key")
    Settings._instance = None

    api = SpeechAPI()
    calls: list[tuple[str, str]] = []

    def fake_request(method: str, endpoint: str, *, tier: str, data=None, **kwargs):
        calls.append((tier, data["model"]))
        return {
            "base_resp": {"status_code": 0},
            "data": {"audio": "00"},
        }

    monkeypatch.setattr(api, "_request_with_tier", fake_request)

    api.synthesize(text="你好", model="speech-legacy")

    assert calls == [("ultra", "speech-2.8-hd")]
    assert api.last_request_metadata["requested_model"] == "speech-legacy"
    assert api.last_request_metadata["applied_model"] == "speech-2.8-hd"


def test_image_api_normalizes_unsupported_model(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setenv("MINIMAX_TOKEN_PLAN_KEY", "ultra-key")
    monkeypatch.setenv("MINIMAX_TOKEN_PLAN_KEY2", "max-key")
    Settings._instance = None

    api = ImageAPI()
    calls: list[tuple[str, str]] = []

    def fake_request(method: str, endpoint: str, *, tier: str, data=None, **kwargs):
        calls.append((tier, data["model"]))
        return {
            "base_resp": {"status_code": 0},
            "data": {"image_urls": ["https://example.invalid/demo.png"]},
        }

    monkeypatch.setattr(api, "_request_with_tier", fake_request)

    api.generate(prompt="demo", model="image-live-unsupported")

    assert calls == [("ultra", "image-01")]
    assert api.last_request_metadata["requested_model"] == "image-live-unsupported"
    assert api.last_request_metadata["applied_model"] == "image-01"


def test_image_api_truncates_overlong_prompt(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setenv("MINIMAX_TOKEN_PLAN_KEY", "ultra-key")
    monkeypatch.setenv("MINIMAX_TOKEN_PLAN_KEY2", "max-key")
    Settings._instance = None

    api = ImageAPI()
    long_prompt = "视觉冲击 " * 400

    def fake_request(method: str, endpoint: str, *, tier: str, data=None, **kwargs):
        assert tier == "ultra"
        assert len(data["prompt"]) < 1500
        return {
            "base_resp": {"status_code": 0},
            "data": {"image_urls": ["https://example.invalid/demo.png"]},
        }

    monkeypatch.setattr(api, "_request_with_tier", fake_request)

    api.generate(prompt=long_prompt)

    assert api.last_request_metadata["prompt_truncated"] is True
    assert api.last_request_metadata["original_prompt_length"] > api.last_request_metadata["applied_prompt_length"]
    assert api.last_request_metadata["applied_prompt_length"] < 1500


def test_music_api_normalizes_unsupported_model(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setenv("MINIMAX_TOKEN_PLAN_KEY", "ultra-key")
    monkeypatch.setenv("MINIMAX_TOKEN_PLAN_KEY2", "max-key")
    Settings._instance = None

    api = MusicAPI()
    calls: list[tuple[str, str]] = []

    def fake_request(method: str, endpoint: str, *, tier: str, data=None, **kwargs):
        calls.append((tier, data["model"]))
        return {
            "base_resp": {"status_code": 0},
            "data": {"audio": "00"},
        }

    monkeypatch.setattr(api, "_request_with_tier", fake_request)

    api.generate(
        prompt="轻快流行",
        model="Music-Legacy",
        lyrics_optimizer=True,
    )

    assert calls == [("ultra", "music-2.6")]
    assert api.last_request_metadata["requested_model"] == "Music-Legacy"
    assert api.last_request_metadata["applied_model"] == "music-2.6"


def test_music_api_rejects_instrumental_for_token_plan(
    monkeypatch: pytest.MonkeyPatch,
):
    monkeypatch.setenv("MINIMAX_TOKEN_PLAN_KEY", "ultra-key")
    monkeypatch.setenv("MINIMAX_TOKEN_PLAN_KEY2", "max-key")
    Settings._instance = None

    api = MusicAPI()

    with pytest.raises(ValueError, match="不支持纯音乐"):
        api.generate(
            prompt="轻柔钢琴",
            is_instrumental=True,
        )


def test_music_api_does_not_fallback_tiers_on_temporary_timeout(
    monkeypatch: pytest.MonkeyPatch,
):
    monkeypatch.setenv("MINIMAX_TOKEN_PLAN_KEY", "ultra-key")
    monkeypatch.setenv("MINIMAX_TOKEN_PLAN_KEY2", "max-key")
    Settings._instance = None

    api = MusicAPI()
    calls: list[str] = []

    def fake_request(method: str, endpoint: str, *, tier: str, data=None, **kwargs):
        calls.append(tier)
        raise requests.exceptions.Timeout("simulated timeout")

    monkeypatch.setattr(api, "_request_with_tier", fake_request)

    with pytest.raises(requests.exceptions.Timeout):
        api.generate(
            prompt="轻快流行",
            lyrics_optimizer=True,
        )

    assert calls == ["ultra"]


def test_pipeline_skips_auto_music_when_token_plan_lacks_instrumental(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
):
    monkeypatch.setenv("MINIMAX_TOKEN_PLAN_KEY", "ultra-key")
    monkeypatch.setenv("MINIMAX_TOKEN_PLAN_KEY2", "max-key")
    Settings._instance = None

    pipeline = PipelineOrchestrator(output_dir=str(tmp_path / "output"))

    monkeypatch.setattr(
        pipeline.text_api,
        "generate_script",
        lambda **kwargs: {
            "raw_content": "脚本",
            "video_description": "",
            "narration": "",
        },
    )
    monkeypatch.setattr(
        pipeline.text_api,
        "generate_titles",
        lambda **kwargs: ["标题1", "标题2"],
    )
    monkeypatch.setattr(
        pipeline.music_api,
        "generate_instrumental",
        lambda *args, **kwargs: (_ for _ in ()).throw(
            AssertionError("不应调用纯音乐生成")
        ),
    )

    pack = pipeline.generate_content_pack(
        topic="测试主题",
        generate_video=False,
        generate_music=True,
        generate_thumbnail=False,
    )

    assert pack.music_path is None
    assert pack.generation_metadata["music"]["status"] == "skipped"
    assert "不支持" in pack.generation_metadata["music"]["skip_reason"]
    manifest = pipeline.file_manager.load_json(pack.content_dir / "content_manifest.json")
    assert manifest["status"] == "succeeded"
    assert manifest["pack"]["music_path"] is None
    assert manifest["pack"]["generation_metadata"]["music"]["status"] == "skipped"

    pipeline.close()


def test_douyin_pipeline_skips_auto_music_when_token_plan_lacks_instrumental(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
):
    monkeypatch.setenv("MINIMAX_TOKEN_PLAN_KEY", "ultra-key")
    monkeypatch.setenv("MINIMAX_TOKEN_PLAN_KEY2", "max-key")
    Settings._instance = None

    pipeline = DouyinPipeline(output_dir=str(tmp_path / "output"))

    monkeypatch.setattr(
        pipeline.viral_gen,
        "generate",
        lambda **kwargs: {
            "hook": "开头",
            "narration": "",
            "video_description": "",
            "engagement_question": "你怎么看？",
            "cta": "关注我",
            "hashtags": ["#测试"],
            "raw_content": "脚本内容",
            "quality_warnings": [],
        },
    )
    monkeypatch.setattr(
        pipeline.viral_gen,
        "calculate_content_score",
        lambda payload: {
            "score": 88,
            "level": "A",
            "level_desc": "通过",
        },
    )
    monkeypatch.setattr(
        pipeline.text_api,
        "generate_titles",
        lambda **kwargs: ["标题1", "标题2"],
    )
    monkeypatch.setattr(
        pipeline,
        "_compose_final_douyin_video",
        lambda *args, **kwargs: None,
    )
    monkeypatch.setattr(
        pipeline.music_api,
        "generate_instrumental",
        lambda *args, **kwargs: (_ for _ in ()).throw(
            AssertionError("不应调用纯音乐生成")
        ),
    )

    pack = pipeline.generate_douyin_content(
        topic="测试抖音主题",
        content_type="生活技巧",
        duration=6,
        generate_video=False,
        generate_music=True,
        generate_thumbnail=False,
        pack_index=1,
    )

    assert pack.music_path is None
    assert pack.generation_metadata["music"]["status"] == "skipped"
    assert "不支持纯音乐" in pack.generation_metadata["music"]["skip_reason"]
    manifest = pipeline.file_manager.load_json(pack.content_dir / "content_manifest.json")
    assert manifest["status"] == "succeeded"
    assert manifest["pack"]["generation_metadata"]["music"]["status"] == "skipped"

    pipeline.close()


def test_douyin_pipeline_skips_high_cost_stages_below_threshold(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
):
    monkeypatch.setenv("MINIMAX_TOKEN_PLAN_KEY", "ultra-key")
    monkeypatch.setenv("MINIMAX_TOKEN_PLAN_KEY2", "max-key")
    Settings._instance = None

    pipeline = DouyinPipeline(output_dir=str(tmp_path / "output"))

    monkeypatch.setattr(
        pipeline.viral_gen,
        "generate",
        lambda **kwargs: {
            "hook": "开头",
            "narration": "太短",
            "video_description": "usable prompt",
            "engagement_question": "",
            "cta": "",
            "hashtags": [],
            "raw_content": "脚本内容",
            "quality_warnings": [],
        },
    )
    monkeypatch.setattr(
        pipeline.viral_gen,
        "calculate_content_score",
        lambda payload: {
            "score": 20,
            "level": "D级",
            "level_desc": "不建议发布",
            "reasons": [],
            "warnings": [],
            "max_score": 100,
        },
    )
    monkeypatch.setattr(
        pipeline.text_api,
        "generate_titles",
        lambda **kwargs: ["标题1", "标题2"],
    )
    monkeypatch.setattr(
        pipeline.speech_api,
        "synthesize_to_file",
        lambda *args, **kwargs: (_ for _ in ()).throw(
            AssertionError("低分内容不应继续生成语音")
        ),
    )
    monkeypatch.setattr(
        pipeline.video_api,
        "generate_video",
        lambda *args, **kwargs: (_ for _ in ()).throw(
            AssertionError("低分内容不应继续生成视频")
        ),
    )
    monkeypatch.setattr(
        pipeline.image_api,
        "create_thumbnail",
        lambda *args, **kwargs: (_ for _ in ()).throw(
            AssertionError("低分内容不应继续生成缩略图")
        ),
    )

    pack = pipeline.generate_douyin_content(
        topic="低分主题",
        content_type="生活技巧",
        duration=6,
        generate_video=True,
        generate_music=True,
        generate_thumbnail=True,
        min_score_threshold=65,
        pack_index=1,
    )

    assert pack.quality_gate_passed is False
    assert pack.audio_path is None
    assert pack.video_path is None
    assert pack.thumbnail_path is None
    assert pack.generation_metadata["quality_gate"]["status"] == "skipped"

    manifest = pipeline.file_manager.load_json(pack.content_dir / "content_manifest.json")
    assert manifest["status"] == "skipped"
    assert manifest["pack"]["quality_gate_passed"] is False

    pipeline.close()


def test_douyin_pipeline_marks_quality_gate_passed_on_success(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
):
    monkeypatch.setenv("MINIMAX_TOKEN_PLAN_KEY", "ultra-key")
    monkeypatch.setenv("MINIMAX_TOKEN_PLAN_KEY2", "max-key")
    Settings._instance = None

    pipeline = DouyinPipeline(output_dir=str(tmp_path / "output"))

    monkeypatch.setattr(
        pipeline.viral_gen,
        "generate",
        lambda **kwargs: {
            "hook": "开头",
            "narration": "",
            "video_description": "",
            "engagement_question": "你怎么看？",
            "cta": "关注我",
            "hashtags": ["#测试"],
            "raw_content": "脚本内容",
            "quality_warnings": [],
        },
    )
    monkeypatch.setattr(
        pipeline.viral_gen,
        "calculate_content_score",
        lambda payload: {
            "score": 88,
            "level": "A级",
            "level_desc": "通过",
            "reasons": [],
            "warnings": [],
            "max_score": 100,
        },
    )
    monkeypatch.setattr(
        pipeline.text_api,
        "generate_titles",
        lambda **kwargs: ["标题1", "标题2"],
    )
    monkeypatch.setattr(
        pipeline,
        "_compose_final_douyin_video",
        lambda *args, **kwargs: None,
    )

    pack = pipeline.generate_douyin_content(
        topic="达标主题",
        content_type="知识科普",
        duration=6,
        generate_video=False,
        generate_music=False,
        generate_thumbnail=False,
        pack_index=1,
        min_score_threshold=65,
    )

    assert pack.quality_gate_passed is True
    assert pack.generation_metadata["quality_gate"]["status"] == "passed"
    manifest = pipeline.file_manager.load_json(pack.content_dir / "content_manifest.json")
    assert manifest["status"] == "succeeded"
    assert manifest["pack"]["quality_gate_passed"] is True

    pipeline.close()


def test_douyin_pipeline_fails_fast_on_empty_script_response(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
):
    monkeypatch.setenv("MINIMAX_TOKEN_PLAN_KEY", "ultra-key")
    monkeypatch.setenv("MINIMAX_TOKEN_PLAN_KEY2", "max-key")
    Settings._instance = None

    pipeline = DouyinPipeline(output_dir=str(tmp_path / "output"))
    attempts: list[str] = []

    def fake_generate(**kwargs):
        attempts.append(kwargs["hook_type"])
        return {
            "hook": "",
            "narration": "",
            "video_description": "",
            "engagement_question": "",
            "cta": "",
            "hashtags": [],
            "raw_content": "",
            "quality_warnings": [],
        }

    monkeypatch.setattr(pipeline.viral_gen, "generate", fake_generate)
    monkeypatch.setattr(
        pipeline.video_api,
        "generate_video",
        lambda *args, **kwargs: (_ for _ in ()).throw(
            AssertionError("空脚本不应继续生成视频")
        ),
    )
    monkeypatch.setattr(
        pipeline.image_api,
        "create_thumbnail",
        lambda *args, **kwargs: (_ for _ in ()).throw(
            AssertionError("空脚本不应继续生成缩略图")
        ),
    )

    with pytest.raises(RuntimeError, match="脚本生成为空"):
        pipeline.generate_douyin_content(
            topic="空脚本主题",
            content_type="生活技巧",
            duration=6,
            generate_video=True,
            generate_music=False,
            generate_thumbnail=True,
            pack_index=1,
        )

    assert attempts == ["practical", "curiosity", "shock"]
    manifest = pipeline.file_manager.load_json(
        pipeline.file_manager.get_content_dir(1) / "content_manifest.json"
    )
    assert manifest["status"] == "failed"
    assert "脚本生成为空" in manifest["error"]

    pipeline.close()


def test_douyin_pipeline_selects_best_hook_candidate(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
):
    monkeypatch.setenv("MINIMAX_TOKEN_PLAN_KEY", "ultra-key")
    monkeypatch.setenv("MINIMAX_TOKEN_PLAN_KEY2", "max-key")
    Settings._instance = None

    pipeline = DouyinPipeline(output_dir=str(tmp_path / "output"))
    attempts: list[str] = []
    scores = {
        "practical": 62,
        "curiosity": 91,
        "shock": 78,
    }

    def fake_generate(**kwargs):
        hook_type = kwargs["hook_type"]
        attempts.append(hook_type)
        return {
            "hook": f"{hook_type}-hook",
            "narration": "这是一段足够长的旁白内容，用于计算分数。",
            "video_description": "cinematic prompt",
            "engagement_question": "你会怎么选？",
            "cta": "关注我看更多",
            "hashtags": ["#测试", "#脚本", "#抖音", "#短视频", "#内容"],
            "raw_content": f"{hook_type}-script",
            "quality_warnings": [],
        }

    def fake_score(payload):
        hook_name = payload["hook"].replace("-hook", "")
        score = scores[hook_name]
        return {
            "score": score,
            "level": "S级" if score >= 85 else "A级",
            "level_desc": "ok",
            "reasons": [],
            "warnings": [],
            "max_score": 100,
        }

    monkeypatch.setattr(pipeline.viral_gen, "generate", fake_generate)
    monkeypatch.setattr(pipeline.viral_gen, "calculate_content_score", fake_score)

    script = pipeline._generate_viral_script_with_retry(
        topic="测试主题",
        content_type="生活技巧",
        duration=6,
    )

    assert attempts == ["practical", "curiosity", "shock"]
    assert script["selected_hook_type"] == "curiosity"
    assert script["precomputed_score"]["score"] == 91
    assert script["score_target"] is None
    assert script["candidate_scores"] == [
        {
            "attempt": 1,
            "hook_type": "practical",
            "status": "scored",
            "score": 62,
            "level": "A级",
            "selected": False,
        },
        {
            "attempt": 2,
            "hook_type": "curiosity",
            "status": "scored",
            "score": 91,
            "level": "S级",
            "selected": True,
        },
        {
            "attempt": 3,
            "hook_type": "shock",
            "status": "scored",
            "score": 78,
            "level": "A级",
            "selected": False,
        },
    ]

    pipeline.close()


def test_douyin_pipeline_persists_script_selection_metadata(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
):
    monkeypatch.setenv("MINIMAX_TOKEN_PLAN_KEY", "ultra-key")
    monkeypatch.setenv("MINIMAX_TOKEN_PLAN_KEY2", "max-key")
    Settings._instance = None

    pipeline = DouyinPipeline(output_dir=str(tmp_path / "output"))
    scores = {
        "practical": 62,
        "curiosity": 91,
        "shock": 78,
    }

    def fake_generate(**kwargs):
        hook_type = kwargs["hook_type"]
        return {
            "hook": f"{hook_type}-hook",
            "narration": "这是一段足够长的旁白内容，用于通过语音阶段。",
            "video_description": "",
            "engagement_question": "你会怎么选？",
            "cta": "关注我看更多",
            "hashtags": ["#测试", "#脚本", "#抖音", "#短视频", "#内容"],
            "raw_content": f"{hook_type}-script",
            "quality_warnings": [],
        }

    def fake_score(payload):
        hook_name = payload["hook"].replace("-hook", "")
        score = scores[hook_name]
        return {
            "score": score,
            "level": "S级" if score >= 85 else "A级",
            "level_desc": "ok",
            "reasons": [],
            "warnings": [],
            "max_score": 100,
        }

    audio_path = tmp_path / "output" / "selection-audio.mp3"
    audio_path.parent.mkdir(parents=True, exist_ok=True)
    audio_path.write_bytes(b"audio")

    monkeypatch.setattr(pipeline.viral_gen, "generate", fake_generate)
    monkeypatch.setattr(pipeline.viral_gen, "calculate_content_score", fake_score)
    monkeypatch.setattr(
        pipeline.text_api,
        "generate_titles",
        lambda **kwargs: ["标题1", "标题2"],
    )
    monkeypatch.setattr(
        pipeline.speech_api,
        "synthesize_to_file",
        lambda *args, **kwargs: audio_path,
    )
    monkeypatch.setattr(
        pipeline,
        "_compose_final_douyin_video",
        lambda *args, **kwargs: None,
    )

    pack = pipeline.generate_douyin_content(
        topic="脚本筛选主题",
        content_type="生活技巧",
        duration=6,
        generate_video=False,
        generate_music=False,
        generate_thumbnail=False,
        pack_index=1,
    )

    script_data = pipeline.file_manager.load_json(pack.content_dir / "script.json")
    manifest = pipeline.file_manager.load_json(pack.content_dir / "content_manifest.json")

    assert script_data["selected_hook_type"] == "curiosity"
    assert len(script_data["candidate_scores"]) == 3
    assert pack.generation_metadata["script_selection"]["selected_hook_type"] == "curiosity"
    assert manifest["pack"]["generation_metadata"]["script_selection"]["selected_hook_type"] == "curiosity"
    assert manifest["pack"]["quality_gate_passed"] is True

    pipeline.close()


def test_douyin_pipeline_uses_selected_script_request_metadata(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
):
    monkeypatch.setenv("MINIMAX_TOKEN_PLAN_KEY", "ultra-key")
    monkeypatch.setenv("MINIMAX_TOKEN_PLAN_KEY2", "max-key")
    Settings._instance = None

    pipeline = DouyinPipeline(output_dir=str(tmp_path / "output"))
    scores = {
        "practical": 80,
        "curiosity": 79,
        "shock": 78,
    }

    def fake_generate(**kwargs):
        hook_type = kwargs["hook_type"]
        pipeline.text_api.last_request_metadata = {
            "key_tier_used": hook_type,
            "requested_model": f"requested-{hook_type}",
            "applied_model": f"applied-{hook_type}",
        }
        return {
            "hook": f"{hook_type}-hook",
            "narration": "这是一段足够长的旁白内容，用于通过语音阶段。",
            "video_description": "",
            "engagement_question": "你会怎么选？",
            "cta": "关注我看更多",
            "hashtags": ["#测试", "#脚本", "#抖音", "#短视频", "#内容"],
            "raw_content": f"{hook_type}-script",
            "quality_warnings": [],
        }

    def fake_score(payload):
        hook_name = payload["hook"].replace("-hook", "")
        score = scores[hook_name]
        return {
            "score": score,
            "level": "A级",
            "level_desc": "ok",
            "reasons": [],
            "warnings": [],
            "max_score": 100,
        }

    audio_path = tmp_path / "output" / "selection-meta-audio.mp3"
    audio_path.parent.mkdir(parents=True, exist_ok=True)
    audio_path.write_bytes(b"audio")

    monkeypatch.setattr(pipeline.viral_gen, "generate", fake_generate)
    monkeypatch.setattr(pipeline.viral_gen, "calculate_content_score", fake_score)
    monkeypatch.setattr(
        pipeline.text_api,
        "generate_titles",
        lambda **kwargs: ["标题1", "标题2"],
    )
    monkeypatch.setattr(
        pipeline.speech_api,
        "synthesize_to_file",
        lambda *args, **kwargs: audio_path,
    )
    monkeypatch.setattr(
        pipeline,
        "_compose_final_douyin_video",
        lambda *args, **kwargs: None,
    )

    pack = pipeline.generate_douyin_content(
        topic="脚本元数据主题",
        content_type="生活技巧",
        duration=6,
        generate_video=False,
        generate_music=False,
        generate_thumbnail=False,
        pack_index=1,
    )

    manifest = pipeline.file_manager.load_json(pack.content_dir / "content_manifest.json")

    assert pack.hook_type_used == "practical"
    assert pack.generation_metadata["script"]["key_tier_used"] == "practical"
    assert pack.generation_metadata["script"]["applied_model"] == "applied-practical"
    assert manifest["pack"]["generation_metadata"]["script"]["applied_model"] == "applied-practical"

    pipeline.close()


def test_video_api_converts_local_seed_image_to_data_url(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
):
    monkeypatch.setenv("MINIMAX_TOKEN_PLAN_KEY", "ultra-key")
    monkeypatch.setenv("MINIMAX_TOKEN_PLAN_KEY2", "max-key")
    Settings._instance = None

    image_path = tmp_path / "seed.png"
    image_path.write_bytes(b"\x89PNG\r\n\x1a\nfake")

    api = VideoAPI()
    calls: list[tuple[str, str]] = []

    def fake_request(method: str, endpoint: str, *, tier: str, data=None, **kwargs):
        calls.append((tier, data["first_frame_image"]))
        return {
            "base_resp": {"status_code": 0},
            "task_id": "task-local-image",
        }

    monkeypatch.setattr(api, "_request_with_tier", fake_request)

    task_id = api.create_image_to_video(
        prompt="demo",
        first_frame_image=str(image_path),
    )

    metadata = api.get_task_metadata(task_id)
    assert calls[0][0] == "ultra"
    assert calls[0][1].startswith("data:image/png;base64,")
    assert metadata["requested_generation_mode"] == "image_to_video"


def test_pipeline_orchestrator_prefers_fast_image_to_video_when_available(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
):
    monkeypatch.setenv("MINIMAX_TOKEN_PLAN_KEY", "ultra-key")
    monkeypatch.setenv("MINIMAX_TOKEN_PLAN_KEY2", "max-key")
    Settings._instance = None

    pipeline = PipelineOrchestrator(output_dir=str(tmp_path / "output"))

    monkeypatch.setattr(
        pipeline.text_api,
        "generate_script",
        lambda **kwargs: {
            "raw_content": "脚本",
            "video_description": "cinematic demo scene",
            "narration": "",
        },
    )
    monkeypatch.setattr(
        pipeline.text_api,
        "generate_titles",
        lambda **kwargs: ["标题1", "标题2"],
    )

    seed_path = tmp_path / "output" / "seed.jpg"
    seed_path.parent.mkdir(parents=True, exist_ok=True)
    seed_path.write_bytes(b"seed")
    create_thumbnail_calls: list[str] = []

    def fake_create_thumbnail(*args, **kwargs):
        create_thumbnail_calls.append(kwargs["output_path"])
        pipeline.image_api.last_request_metadata = {
            "key_tier_used": "ultra",
            "requested_model": "image-01",
            "applied_model": "image-01",
        }
        return seed_path

    video_path = tmp_path / "output" / "video.mp4"
    video_path.write_bytes(b"video")
    i2v_calls: list[tuple[str, str, str]] = []

    def fake_generate_video_from_image(*args, **kwargs):
        i2v_calls.append(
            (
                kwargs["prompt"],
                kwargs["first_frame_image"],
                kwargs["model"],
            )
        )
        pipeline.video_api.last_request_metadata = {
            "key_tier_used": "ultra",
            "requested_model": "MiniMax-Hailuo-2.3-Fast",
            "applied_model": "MiniMax-Hailuo-2.3-Fast",
            "resource_used": "video_fast",
            "requested_generation_mode": "image_to_video",
            "applied_generation_mode": "image_to_video",
        }
        return video_path

    monkeypatch.setattr(pipeline.image_api, "create_thumbnail", fake_create_thumbnail)
    monkeypatch.setattr(
        pipeline.video_api,
        "generate_video_from_image",
        fake_generate_video_from_image,
    )
    monkeypatch.setattr(
        pipeline.video_api,
        "generate_video",
        lambda *args, **kwargs: (_ for _ in ()).throw(
            AssertionError("Fast 可用时不应回退到文生视频")
        ),
    )

    pack = pipeline.generate_content_pack(
        topic="测试主题",
        generate_video=True,
        generate_music=False,
        generate_thumbnail=True,
    )

    assert len(create_thumbnail_calls) == 1
    assert len(i2v_calls) == 1
    assert i2v_calls[0][1] == str(seed_path)
    assert i2v_calls[0][2] == "MiniMax-Hailuo-2.3-Fast"
    assert pack.thumbnail_path == seed_path
    assert pack.video_path == video_path
    assert pack.generation_metadata["video"]["requested_generation_mode"] == "image_to_video"

    pipeline.close()


def test_pipeline_orchestrator_falls_back_to_standard_t2v_when_fast_unavailable(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
):
    monkeypatch.setenv("MINIMAX_TOKEN_PLAN_KEY", "ultra-key")
    monkeypatch.setenv("MINIMAX_TOKEN_PLAN_KEY2", "max-key")
    Settings._instance = None

    pipeline = PipelineOrchestrator(output_dir=str(tmp_path / "output"))

    monkeypatch.setattr(
        pipeline.text_api,
        "generate_script",
        lambda **kwargs: {
            "raw_content": "脚本",
            "video_description": "cinematic demo scene",
            "narration": "",
        },
    )
    monkeypatch.setattr(
        pipeline.text_api,
        "generate_titles",
        lambda **kwargs: ["标题1", "标题2"],
    )

    original_check_quota = pipeline.settings.check_quota

    def fake_check_quota(resource: str, *args, **kwargs):
        if resource == "video_fast":
            return False
        if resource == "video_standard":
            return True
        return original_check_quota(resource, *args, **kwargs)

    monkeypatch.setattr(pipeline.settings, "check_quota", fake_check_quota)
    monkeypatch.setattr(
        pipeline.image_api,
        "create_thumbnail",
        lambda *args, **kwargs: (_ for _ in ()).throw(
            AssertionError("Fast 不可用时不应创建首帧图")
        ),
    )
    monkeypatch.setattr(
        pipeline.video_api,
        "generate_video_from_image",
        lambda *args, **kwargs: (_ for _ in ()).throw(
            AssertionError("Fast 不可用时不应走图生视频")
        ),
    )

    video_path = tmp_path / "output" / "video-standard.mp4"
    video_path.write_bytes(b"video")

    def fake_generate_video(*args, **kwargs):
        pipeline.video_api.last_request_metadata = {
            "key_tier_used": "max",
            "requested_model": "MiniMax-Hailuo-2.3-Fast",
            "applied_model": "MiniMax-Hailuo-2.3",
            "resource_used": "video_standard",
            "requested_generation_mode": "text_to_video",
            "applied_generation_mode": "text_to_video",
        }
        return video_path

    monkeypatch.setattr(pipeline.video_api, "generate_video", fake_generate_video)

    pack = pipeline.generate_content_pack(
        topic="测试主题",
        generate_video=True,
        generate_music=False,
        generate_thumbnail=False,
    )

    assert pack.video_path == video_path
    assert pack.thumbnail_path is None
    assert pack.generation_metadata["video"]["applied_generation_mode"] == "text_to_video"

    pipeline.close()


def test_douyin_pipeline_prefers_fast_image_to_video_when_available(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
):
    monkeypatch.setenv("MINIMAX_TOKEN_PLAN_KEY", "ultra-key")
    monkeypatch.setenv("MINIMAX_TOKEN_PLAN_KEY2", "max-key")
    Settings._instance = None

    pipeline = DouyinPipeline(output_dir=str(tmp_path / "output"))

    monkeypatch.setattr(
        pipeline.viral_gen,
        "generate",
        lambda **kwargs: {
            "hook": "开头",
            "narration": "",
            "video_description": "cinematic douyin prompt",
            "engagement_question": "你怎么看？",
            "cta": "关注我",
            "hashtags": ["#测试"],
            "raw_content": "脚本内容",
            "quality_warnings": [],
        },
    )
    monkeypatch.setattr(
        pipeline.viral_gen,
        "calculate_content_score",
        lambda payload: {
            "score": 88,
            "level": "A",
            "level_desc": "通过",
            "reasons": [],
            "warnings": [],
            "max_score": 100,
        },
    )
    monkeypatch.setattr(
        pipeline.text_api,
        "generate_titles",
        lambda **kwargs: ["标题1", "标题2"],
    )
    monkeypatch.setattr(
        pipeline,
        "_compose_final_douyin_video",
        lambda *args, **kwargs: None,
    )

    seed_path = tmp_path / "output" / "douyin-seed.jpg"
    seed_path.parent.mkdir(parents=True, exist_ok=True)
    seed_path.write_bytes(b"seed")
    create_thumbnail_calls: list[str] = []

    def fake_create_thumbnail(*args, **kwargs):
        create_thumbnail_calls.append(kwargs["output_path"])
        pipeline.image_api.last_request_metadata = {
            "key_tier_used": "ultra",
            "requested_model": "image-01",
            "applied_model": "image-01",
        }
        return seed_path

    video_path = tmp_path / "output" / "douyin-video.mp4"
    video_path.write_bytes(b"video")
    i2v_calls: list[tuple[str, str, str]] = []

    def fake_generate_video_from_image(*args, **kwargs):
        i2v_calls.append(
            (
                kwargs["prompt"],
                kwargs["first_frame_image"],
                kwargs["model"],
            )
        )
        pipeline.video_api.last_request_metadata = {
            "key_tier_used": "ultra",
            "requested_model": "MiniMax-Hailuo-2.3-Fast",
            "applied_model": "MiniMax-Hailuo-2.3-Fast",
            "resource_used": "video_fast",
            "requested_generation_mode": "image_to_video",
            "applied_generation_mode": "image_to_video",
        }
        return video_path

    monkeypatch.setattr(pipeline.image_api, "create_thumbnail", fake_create_thumbnail)
    monkeypatch.setattr(
        pipeline.video_api,
        "generate_video_from_image",
        fake_generate_video_from_image,
    )
    monkeypatch.setattr(
        pipeline.video_api,
        "generate_video",
        lambda *args, **kwargs: (_ for _ in ()).throw(
            AssertionError("Fast 可用时抖音流水线不应走文生视频")
        ),
    )

    pack = pipeline.generate_douyin_content(
        topic="测试抖音主题",
        content_type="生活技巧",
        duration=6,
        generate_video=True,
        generate_music=False,
        generate_thumbnail=True,
        pack_index=1,
    )

    assert len(create_thumbnail_calls) == 1
    assert len(i2v_calls) == 1
    assert i2v_calls[0][1] == str(seed_path)
    assert pack.thumbnail_path == seed_path
    assert pack.video_path == video_path
    assert pack.quality_gate_passed is True
    assert pack.generation_metadata["quality_gate"]["status"] == "not_enforced"
    assert pack.generation_metadata["video"]["applied_generation_mode"] == "image_to_video"

    manifest = pipeline.file_manager.load_json(pack.content_dir / "content_manifest.json")
    assert manifest["pack"]["quality_gate_passed"] is True

    pipeline.close()


def test_video_max_tier_downgrades_fast_model_for_text_to_video(
    monkeypatch: pytest.MonkeyPatch,
):
    monkeypatch.delenv("MINIMAX_TOKEN_PLAN_KEY", raising=False)
    monkeypatch.setenv("MINIMAX_TOKEN_PLAN_KEY2", "max-key")
    Settings._instance = None

    api = VideoAPI()
    calls: list[tuple[str, str]] = []

    def fake_request(method: str, endpoint: str, *, tier: str, data=None, **kwargs):
        calls.append((tier, data["model"]))
        return {
            "base_resp": {"status_code": 0},
            "task_id": "task-max-fast",
        }

    monkeypatch.setattr(api, "_request_with_tier", fake_request)

    task_id = api.create_text_to_video(
        prompt="demo",
        model="MiniMax-Hailuo-2.3-Fast",
    )

    metadata = api.get_task_metadata(task_id)
    assert calls == [("max", "MiniMax-Hailuo-2.3")]
    assert metadata["applied_model"] == "MiniMax-Hailuo-2.3"
    assert metadata["resource_used"] == "video_standard"


def test_video_ultra_tier_downgrades_fast_model_for_text_to_video(
    monkeypatch: pytest.MonkeyPatch,
):
    monkeypatch.setenv("MINIMAX_TOKEN_PLAN_KEY", "ultra-key")
    monkeypatch.delenv("MINIMAX_TOKEN_PLAN_KEY2", raising=False)
    Settings._instance = None

    api = VideoAPI()
    calls: list[tuple[str, str]] = []

    def fake_request(method: str, endpoint: str, *, tier: str, data=None, **kwargs):
        calls.append((tier, data["model"]))
        return {
            "base_resp": {"status_code": 0},
            "task_id": "task-ultra-fast",
        }

    monkeypatch.setattr(api, "_request_with_tier", fake_request)

    task_id = api.create_text_to_video(
        prompt="demo",
        model="MiniMax-Hailuo-2.3-Fast",
    )

    metadata = api.get_task_metadata(task_id)
    assert calls == [("ultra", "MiniMax-Hailuo-2.3")]
    assert metadata["applied_model"] == "MiniMax-Hailuo-2.3"
    assert metadata["resource_used"] == "video_standard"


def test_video_max_tier_keeps_fast_model_for_image_to_video(
    monkeypatch: pytest.MonkeyPatch,
):
    monkeypatch.delenv("MINIMAX_TOKEN_PLAN_KEY", raising=False)
    monkeypatch.setenv("MINIMAX_TOKEN_PLAN_KEY2", "max-key")
    Settings._instance = None

    api = VideoAPI()
    calls: list[tuple[str, str]] = []

    def fake_request(method: str, endpoint: str, *, tier: str, data=None, **kwargs):
        calls.append((tier, data["model"]))
        return {
            "base_resp": {"status_code": 0},
            "task_id": "task-max-fast-i2v",
        }

    monkeypatch.setattr(api, "_request_with_tier", fake_request)

    task_id = api.create_image_to_video(
        prompt="demo",
        first_frame_image="https://example.invalid/image.png",
        model="MiniMax-Hailuo-2.3-Fast",
    )

    metadata = api.get_task_metadata(task_id)
    assert calls == [("max", "MiniMax-Hailuo-2.3-Fast")]
    assert metadata["applied_model"] == "MiniMax-Hailuo-2.3-Fast"
    assert metadata["resource_used"] == "video_fast"


def test_video_query_task_reuses_recorded_tier(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setenv("MINIMAX_TOKEN_PLAN_KEY", "ultra-key")
    monkeypatch.setenv("MINIMAX_TOKEN_PLAN_KEY2", "max-key")
    Settings._instance = None

    api = VideoAPI()
    api.remember_task_metadata("task-1", {"key_tier_used": "max"})
    calls: list[tuple[str, str, dict]] = []

    def fake_request(method: str, endpoint: str, *, tier: str, params=None, **kwargs):
        calls.append((tier, endpoint, params or {}))
        return {
            "base_resp": {"status_code": 0},
            "task_id": "task-1",
            "status": "Success",
        }

    monkeypatch.setattr(api, "_request_with_tier", fake_request)

    result = api.query_task("task-1")

    assert result["status"] == "Success"
    assert calls == [("max", "/v1/query/video_generation", {"task_id": "task-1"})]


def test_video_download_reuses_recorded_tier_for_file_retrieve(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
):
    monkeypatch.setenv("MINIMAX_TOKEN_PLAN_KEY", "ultra-key")
    monkeypatch.setenv("MINIMAX_TOKEN_PLAN_KEY2", "max-key")
    Settings._instance = None

    api = VideoAPI()
    calls: list[tuple[str, str, dict]] = []

    def fake_request(method: str, endpoint: str, *, tier: str, params=None, **kwargs):
        calls.append((tier, endpoint, params or {}))
        return {"file": {"download_url": "https://example.invalid/video.mp4"}}

    class FakeResponse:
        def raise_for_status(self):
            return None

        def iter_content(self, chunk_size: int = 1024 * 1024):
            yield b"video-bytes"

    def fake_session_get(self, url: str, **kwargs):
        assert url == "https://example.invalid/video.mp4"
        return FakeResponse()

    monkeypatch.setattr(api, "_request_with_tier", fake_request)
    monkeypatch.setattr(requests.Session, "get", fake_session_get)

    output_path = tmp_path / "video.mp4"
    saved_path = api.download_video(
        file_id="file-1",
        output_path=str(output_path),
        status_info={"file_id": "file-1", "_routing": {"key_tier_used": "max"}},
    )

    assert saved_path == output_path
    assert output_path.read_bytes() == b"video-bytes"
    assert calls == [("max", "/v1/files/retrieve", {"file_id": "file-1"})]


def test_concurrent_video_wait_uses_per_task_client_and_persists_manifest(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
):
    monkeypatch.setenv("MINIMAX_TOKEN_PLAN_KEY", "ultra-key")
    monkeypatch.setenv("MINIMAX_TOKEN_PLAN_KEY2", "max-key")
    Settings._instance = None

    pipeline = PipelineOrchestrator(output_dir=str(tmp_path / "output"))

    pack_ultra = ContentPack("topic-ultra")
    pack_ultra.content_index, pack_ultra.content_dir = (
        pipeline.file_manager.reserve_content_slot(1)
    )
    pack_max = ContentPack("topic-max")
    pack_max.content_index, pack_max.content_dir = (
        pipeline.file_manager.reserve_content_slot(2)
    )

    created_clients: list["FakeVideoAPI"] = []

    class FakeVideoAPI:
        def __init__(self, *args, **kwargs):
            self._task_metadata = {}
            self.last_request_metadata = {}
            created_clients.append(self)

        def remember_task_metadata(self, task_id: str, metadata: dict) -> None:
            self._task_metadata[task_id] = dict(metadata)

        def wait_for_completion(self, task_id: str) -> dict:
            metadata = dict(self._task_metadata[task_id])
            self.last_request_metadata = metadata
            return {
                "task_id": task_id,
                "status": "Success",
                "_routing": metadata,
                "download_url": f"https://example.invalid/{task_id}.mp4",
            }

        def download_video(self, status_info=None, output_path=None, **kwargs):
            output = Path(output_path)
            output.parent.mkdir(parents=True, exist_ok=True)
            output.write_bytes(status_info["task_id"].encode("utf-8"))
            return output

        def close(self) -> None:
            return None

    monkeypatch.setattr("src.pipeline.orchestrator.VideoAPI", FakeVideoAPI)

    pipeline._wait_video_batch(
        [
            {
                "pack": pack_ultra,
                "task_id": "task-ultra",
                "routing_metadata": {
                    "key_tier_used": "ultra",
                    "applied_model": "MiniMax-Hailuo-2.3-Fast",
                    "requested_model": "MiniMax-Hailuo-2.3-Fast",
                },
            },
            {
                "pack": pack_max,
                "task_id": "task-max",
                "routing_metadata": {
                    "key_tier_used": "max",
                    "applied_model": "MiniMax-Hailuo-2.3",
                    "requested_model": "MiniMax-Hailuo-2.3-Fast",
                    "cross_tier_fallback": True,
                },
            },
        ]
    )

    assert len(created_clients) == 2
    assert pack_ultra.key_tier_used == "ultra"
    assert pack_max.key_tier_used == "max"
    assert pack_max.cross_tier_fallback is True

    manifest_ultra = pipeline.file_manager.load_json(
        pack_ultra.content_dir / "content_manifest.json"
    )
    manifest_max = pipeline.file_manager.load_json(
        pack_max.content_dir / "content_manifest.json"
    )
    assert manifest_ultra["status"] == "succeeded"
    assert manifest_ultra["pack"]["key_tier_used"] == "ultra"
    assert manifest_max["status"] == "succeeded"
    assert manifest_max["pack"]["key_tier_used"] == "max"
    assert manifest_max["pack"]["cross_tier_fallback"] is True

    pipeline.close()


def test_quota_tracker_and_report_keep_tier_metadata(tmp_path: Path):
    tracker = TokenPlanQuotaTracker(
        tiers=build_default_tiers("ultra-key", "max-key"),
        quotas_by_tier=DEFAULT_TOKEN_PLAN_QUOTAS,
        state_file=tmp_path / "quota.json",
    )
    tracker.record_usage("text", tier="ultra")
    tracker.record_usage("video", tier="max")

    status = tracker.get_status()
    assert status["tiers"]["ultra"]["text_5h"]["used_in_window"] == 1
    assert status["tiers"]["max"]["text_5h"]["used_in_window"] == 0
    assert status["tiers"]["max"]["video"]["used"] == 1
    assert status["tiers"]["ultra"]["video"]["used"] == 0

    pack = ContentPack("topic")
    pack.apply_generation_metadata(
        "video",
        {
            "key_tier_used": "max",
            "requested_model": "MiniMax-Hailuo-2.3-Fast",
            "applied_model": "MiniMax-Hailuo-2.3",
            "requested_video_spec": {"duration": 10, "resolution": "1080P"},
            "applied_video_spec": {"duration": 6, "resolution": "768P"},
            "cross_tier_fallback": True,
        },
    )

    report = ReportGenerator()
    serialized = report._serialize_pack(pack)

    assert serialized["key_tier_used"] == "max"
    assert serialized["requested_model"] == "MiniMax-Hailuo-2.3-Fast"
    assert serialized["applied_model"] == "MiniMax-Hailuo-2.3"
    assert serialized["requested_video_spec"]["resolution"] == "1080P"
    assert serialized["applied_video_spec"]["resolution"] == "768P"
    assert serialized["cross_tier_fallback"] is True


def test_remote_remains_parser_supports_model_remains_payload(tmp_path: Path):
    tracker = TokenPlanQuotaTracker(
        tiers=build_default_tiers("ultra-key", "max-key"),
        quotas_by_tier=DEFAULT_TOKEN_PLAN_QUOTAS,
        state_file=tmp_path / "quota.json",
    )
    payload = {
        "model_remains": [
            {
                "model_name": "MiniMax-M*",
                "current_interval_total_count": 4500,
                "current_interval_usage_count": 4499,
                "remains_time": 5491090,
            },
            {
                "model_name": "speech-hd",
                "current_interval_total_count": 11000,
                "current_interval_usage_count": 11000,
            },
            {
                "model_name": "MiniMax-Hailuo-2.3-Fast-6s-768p",
                "current_interval_total_count": 2,
                "current_interval_usage_count": 2,
            },
            {
                "model_name": "MiniMax-Hailuo-2.3-6s-768p",
                "current_interval_total_count": 2,
                "current_interval_usage_count": 1,
            },
            {
                "model_name": "music-2.6",
                "current_interval_total_count": 100,
                "current_interval_usage_count": 100,
            },
            {
                "model_name": "image-01",
                "current_interval_total_count": 120,
                "current_interval_usage_count": 119,
            },
        ],
        "base_resp": {"status_code": 0, "status_msg": "success"},
    }

    normalized = tracker._normalize_remote_remains_payload(payload, "max")

    assert normalized["text_5h"]["limit"] == 4500
    assert normalized["text_5h"]["remaining"] == 4499
    assert normalized["text_5h"]["window_seconds_remaining"] == 5491
    assert normalized["tts"]["remaining"] == 11000
    assert normalized["video_fast"]["remaining"] == 2
    assert normalized["video_standard"]["remaining"] == 1
    assert normalized["video"]["limit"] == 4
    assert normalized["video"]["remaining"] == 3
    assert normalized["music"]["remaining"] == 100
    assert normalized["image"]["remaining"] == 119


def test_refresh_remote_remains_times_out_without_blocking(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
):
    tracker = TokenPlanQuotaTracker(
        tiers=build_default_tiers("ultra-key", "max-key"),
        quotas_by_tier=DEFAULT_TOKEN_PLAN_QUOTAS,
        state_file=tmp_path / "quota.json",
    )

    def fake_get(*args, **kwargs):
        sleep(0.3)
        return None

    monkeypatch.setattr("config.token_plan.requests.get", fake_get)

    started = monotonic()
    result = tracker.refresh_remote_remains("max", timeout=0.05)
    elapsed = monotonic() - started

    assert result is None
    assert elapsed < 0.25


def test_refresh_remote_remains_keeps_previous_cache_on_empty_payload(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
):
    tracker = TokenPlanQuotaTracker(
        tiers=build_default_tiers("ultra-key", "max-key"),
        quotas_by_tier=DEFAULT_TOKEN_PLAN_QUOTAS,
        state_file=tmp_path / "quota.json",
    )
    tracker._remote_remains["max"] = {
        "status": {"music": {"limit": 4, "remaining": 2, "source": "remote"}},
        "raw": {"model_remains": []},
        "updated_at": "2026-04-02T00:00:00",
    }

    class FakeResponse:
        def raise_for_status(self):
            return None

        def json(self):
            return {"base_resp": {"status_code": 0}, "data": {"unexpected": True}}

    monkeypatch.setattr("config.token_plan.requests.get", lambda *args, **kwargs: FakeResponse())

    result = tracker.refresh_remote_remains("max", timeout=0.05)

    assert result is None
    assert tracker._remote_remains["max"]["status"]["music"]["remaining"] == 2


def test_image_api_does_not_retry_successful_null_data_response(
    monkeypatch: pytest.MonkeyPatch,
):
    monkeypatch.setenv("MINIMAX_TOKEN_PLAN_KEY", "ultra-key")
    monkeypatch.setenv("MINIMAX_TOKEN_PLAN_KEY2", "max-key")
    Settings._instance = None

    api = ImageAPI()
    calls: list[tuple[str, str]] = []

    def fake_request(method: str, endpoint: str, *, tier: str, data=None, **kwargs):
        calls.append((method, tier))
        return {
            "base_resp": {"status_code": 0},
            "data": None,
        }

    monkeypatch.setattr(api, "_request_with_tier", fake_request)

    with pytest.raises(RuntimeError, match="不会自动重试"):
        api.generate(prompt="demo")

    assert calls == [("POST", "ultra")]
