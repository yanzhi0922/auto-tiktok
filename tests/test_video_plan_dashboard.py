from __future__ import annotations

import json
from pathlib import Path

from config.settings import Settings
from src.dashboard.state import get_run_detail, list_runs
from src.pipeline.orchestrator import ContentPack
from src.pipeline.video_plan import VideoPlan, update_plan_from_pack
from src.utils.file_manager import FileManager
from src.video_editor.subtitle import SubtitleGenerator


def test_video_plan_records_pack_state(tmp_path: Path):
    settings = Settings()
    content_dir = tmp_path / "output" / "2026-05-18" / "run_demo" / "001"
    content_dir.mkdir(parents=True)
    plan = VideoPlan.create(
        topic="厨房技巧",
        content_dir=content_dir,
        run_id="demo",
        content_index=1,
        duration=6,
        voice="female_tianmei",
        settings=settings,
        content_type="生活技巧",
        generate_video=True,
        generate_music=False,
        generate_thumbnail=True,
    )

    pack = ContentPack("厨房技巧")
    pack.content_index = 1
    pack.content_dir = content_dir
    pack.narration = "这是一个厨房技巧"
    pack.video_description = "close-up kitchen cleaning trick"
    pack.titles = ["厨房技巧别再错过"]
    pack.audio_path = content_dir / "audio.mp3"
    pack.apply_generation_metadata(
        "tts",
        {"key_tier_used": "max", "requested_model": "speech-2.8-hd"},
    )

    update_plan_from_pack(plan, pack)
    saved_path = plan.save()
    saved = json.loads(saved_path.read_text(encoding="utf-8"))

    assert saved["topic"] == "厨房技巧"
    assert saved["script"]["narration"] == "这是一个厨房技巧"
    assert saved["titles"] == ["厨房技巧别再错过"]
    assert saved["assets"]["audio"]["path"].endswith("audio.mp3")
    assert saved["model_calls"]["tts"]["tier"] == "max"


def test_file_manager_restores_existing_slots_in_run_manifest(tmp_path: Path):
    manager = FileManager(base_dir=tmp_path / "output", date_suffix="2026-05-18", run_id="demo")
    manager.reserve_content_slot(1)
    manager.reserve_content_slot(2)

    restored = FileManager(base_dir=tmp_path / "output", date_suffix="2026-05-18", run_id="demo")
    manifest = json.loads(restored.run_manifest_path.read_text(encoding="utf-8"))

    assert [item["index"] for item in manifest["content_slots"]] == [1, 2]


def test_dashboard_lists_runs_and_content_with_video_plan(tmp_path: Path):
    manager = FileManager(base_dir=tmp_path / "output", date_suffix="2026-05-18", run_id="demo")
    _, content_dir = manager.reserve_content_slot(1)
    manager.write_json_to_path(
        content_dir / "content_manifest.json",
        {
            "status": "failed",
            "error": "video failed",
            "pack": {
                "topic": "厨房技巧",
                "content_type": "生活技巧",
                "viral_score": {"score": 82},
            },
        },
    )
    manager.write_json_to_path(
        content_dir / "video_plan.json",
        {
            "topic": "厨房技巧",
            "content_type": "生活技巧",
            "assets": {"video": {"status": "failed", "path": None}},
            "errors": ["video failed"],
        },
    )

    runs = list_runs(tmp_path / "output")
    detail = get_run_detail(base_dir=tmp_path / "output", date="2026-05-18", run_id="demo")

    assert runs[0]["run_id"] == "demo"
    assert detail["contents"][0]["status"] == "failed"
    assert detail["contents"][0]["score"] == 82
    assert detail["contents"][0]["video_plan_path"].endswith("video_plan.json")


def test_subtitle_generator_accepts_whisperx_json(tmp_path: Path):
    payload = {
        "segments": [
            {
                "text": "你好世界",
                "start": 0.0,
                "end": 1.0,
                "words": [
                    {"word": "你", "start": 0.0, "end": 0.2},
                    {"word": "好", "start": 0.2, "end": 0.4},
                    {"word": "世界", "start": 0.4, "end": 1.0},
                ],
            }
        ]
    }
    json_path = tmp_path / "whisperx.json"
    json_path.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")

    output_path = tmp_path / "subtitle.srt"
    SubtitleGenerator().generate_srt_from_whisperx_json(
        str(json_path),
        output_path=str(output_path),
    )

    content = output_path.read_text(encoding="utf-8")
    assert "你好世界" in content
    assert "00:00:00,000 --> 00:00:01,000" in content
