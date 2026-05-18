from __future__ import annotations

from pathlib import Path

import pytest

from config.settings import Settings
from src.pipeline.douyin_pipeline import DouyinPipeline


def _score_payload(score: int, level: str = "A级", level_desc: str = "可发布") -> dict:
    return {
        "score": score,
        "level": level,
        "level_desc": level_desc,
        "reasons": [],
        "warnings": [],
        "max_score": 100,
    }


def test_douyin_pipeline_selects_best_hook_and_scores_with_completed_hashtags(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
):
    monkeypatch.setenv("MINIMAX_TOKEN_PLAN_KEY", "ultra-key")
    monkeypatch.setenv("MINIMAX_TOKEN_PLAN_KEY2", "max-key")
    Settings._instance = None

    pipeline = DouyinPipeline(output_dir=str(tmp_path / "output"))
    attempts: list[str] = []

    def fake_generate(**kwargs):
        hook_type = kwargs["hook_type"]
        attempts.append(hook_type)
        pipeline.text_api.last_request_metadata = {
            "key_tier_used": "ultra",
            "requested_model": "MiniMax-M2.7-highspeed",
            "applied_model": "MiniMax-M2.7-highspeed",
        }
        return {
            "hook": hook_type,
            "narration": "这是一个足够长的高质量旁白内容",
            "video_description": "usable prompt",
            "engagement_question": "你遇到过这种情况吗？",
            "cta": "关注我看更多",
            "hashtags": [],
            "raw_content": f"脚本 {hook_type}",
            "quality_warnings": [],
        }

    def fake_score(payload):
        assert len(payload["hashtags"]) >= 5
        score_map = {
            "curiosity": 78,
            "shock": 91,
            "mystery": 74,
        }
        return _score_payload(score_map[payload["hook"]], "S级" if payload["hook"] == "shock" else "A级")

    def fake_tts(*args, **kwargs):
        output_path = Path(kwargs["output_path"])
        output_path.write_bytes(b"audio")
        pipeline.speech_api.last_request_metadata = {
            "key_tier_used": "ultra",
            "requested_model": "speech-2.8-hd",
            "applied_model": "speech-2.8-hd",
        }
        return output_path

    monkeypatch.setattr(pipeline.viral_gen, "generate", fake_generate)
    monkeypatch.setattr(pipeline.viral_gen, "calculate_content_score", fake_score)
    monkeypatch.setattr(
        pipeline.text_api,
        "generate_titles",
        lambda **kwargs: ["标题1", "标题2"],
    )
    monkeypatch.setattr(pipeline.speech_api, "synthesize_to_file", fake_tts)

    pack = pipeline.generate_douyin_content(
        topic="身份证冷知识",
        content_type="知识科普",
        duration=6,
        generate_video=False,
        generate_music=False,
        generate_thumbnail=False,
        min_score_threshold=80,
        pack_index=1,
    )

    assert attempts == ["curiosity", "shock", "mystery"]
    assert pack.hook_type_used == "shock"
    assert pack.quality_gate_passed is True
    assert len(pack.hashtags) >= 5
    assert pack.generation_metadata["quality_gate"]["status"] == "passed"
    assert pack.generation_metadata["quality_gate"]["selected_hook_type"] == "shock"

    manifest = pipeline.file_manager.load_json(pack.content_dir / "content_manifest.json")
    score_json = pipeline.file_manager.load_json(pack.content_dir / "score.json")
    script_json = pipeline.file_manager.load_json(pack.content_dir / "script.json")

    assert manifest["pack"]["hook_type_used"] == "shock"
    assert manifest["pack"]["quality_gate_passed"] is True
    assert score_json["selected_hook_type"] == "shock"
    assert script_json["selected_hook_type"] == "shock"

    pipeline.close()


def test_douyin_pipeline_marks_quality_gate_not_enforced_without_threshold(
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
            "hook": "curiosity",
            "narration": "这是一个足够长的高质量旁白内容",
            "video_description": "usable prompt",
            "engagement_question": "你会怎么做？",
            "cta": "关注我看更多",
            "hashtags": ["#测试"],
            "raw_content": "脚本内容",
            "quality_warnings": [],
        },
    )
    monkeypatch.setattr(
        pipeline.viral_gen,
        "calculate_content_score",
        lambda payload: _score_payload(88, "S级", "强烈推荐"),
    )
    monkeypatch.setattr(
        pipeline.text_api,
        "generate_titles",
        lambda **kwargs: ["标题1", "标题2"],
    )
    monkeypatch.setattr(
        pipeline.speech_api,
        "synthesize_to_file",
        lambda *args, **kwargs: Path(kwargs["output_path"]),
    )

    pack = pipeline.generate_douyin_content(
        topic="无门槛主题",
        content_type="生活技巧",
        duration=6,
        generate_video=False,
        generate_music=False,
        generate_thumbnail=False,
        min_score_threshold=None,
        pack_index=1,
    )

    assert pack.quality_gate_passed is True
    assert pack.generation_metadata["quality_gate"]["status"] == "not_enforced"
    assert pack.generation_metadata["quality_gate"]["reason"] == "no_threshold_configured"

    manifest = pipeline.file_manager.load_json(pack.content_dir / "content_manifest.json")
    assert manifest["pack"]["quality_gate_passed"] is True
    assert manifest["pack"]["generation_metadata"]["quality_gate"]["status"] == "not_enforced"

    pipeline.close()


def test_douyin_pipeline_falls_back_to_video_frame_when_thumbnail_cannot_be_generated(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
):
    monkeypatch.setenv("MINIMAX_TOKEN_PLAN_KEY", "ultra-key")
    monkeypatch.setenv("MINIMAX_TOKEN_PLAN_KEY2", "max-key")
    Settings._instance = None

    pipeline = DouyinPipeline(output_dir=str(tmp_path / "output"))
    video_path = tmp_path / "output" / "video.mp4"
    video_path.parent.mkdir(parents=True, exist_ok=True)
    video_path.write_bytes(b"video")
    cover_path = tmp_path / "output" / "cover.jpg"

    monkeypatch.setattr(
        pipeline.viral_gen,
        "generate",
        lambda **kwargs: {
            "hook": "shock",
            "narration": "",
            "video_description": "usable prompt",
            "engagement_question": "你发现了吗？",
            "cta": "关注我看更多",
            "hashtags": ["#测试"],
            "raw_content": "脚本内容",
            "quality_warnings": [],
        },
    )
    monkeypatch.setattr(
        pipeline.viral_gen,
        "calculate_content_score",
        lambda payload: _score_payload(88, "S级", "强烈推荐"),
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
        pipeline,
        "_generate_video_with_hybrid_routing",
        lambda *args, **kwargs: video_path,
    )
    monkeypatch.setattr(
        pipeline.settings,
        "check_quota",
        lambda resource, refresh_remote=False: False if resource == "image" else True,
    )
    monkeypatch.setattr(
        pipeline.composer,
        "set_video_cover",
        lambda **kwargs: cover_path,
    )

    pack = pipeline.generate_douyin_content(
        topic="测试封面回退",
        content_type="知识科普",
        duration=6,
        generate_video=True,
        generate_music=False,
        generate_thumbnail=True,
        pack_index=1,
    )

    assert pack.video_path == video_path
    assert pack.thumbnail_path == cover_path
    assert pack.cover_path == cover_path
    assert pack.generation_metadata["thumbnail"]["status"] == "fallback_frame"
    assert (
        pack.generation_metadata["thumbnail"]["fallback_reason"]
        == "image_quota_unavailable"
    )

    manifest = pipeline.file_manager.load_json(pack.content_dir / "content_manifest.json")
    assert manifest["pack"]["generation_metadata"]["thumbnail"]["status"] == "fallback_frame"

    pipeline.close()
