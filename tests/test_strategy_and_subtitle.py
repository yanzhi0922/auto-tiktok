from __future__ import annotations

import re
from pathlib import Path

from src.strategy.douyin_strategy import DouyinContentStrategy
from src.video_editor.subtitle import SubtitleGenerator


def test_get_trending_topics_prefers_unique_results():
    strategy = DouyinContentStrategy()
    topics = strategy.get_trending_topics(7)

    assert len(topics) == 7
    assert len(set(topics)) == 7


def test_viral_score_is_not_artificially_maxed_for_mediocre_content():
    strategy = DouyinContentStrategy()
    score = strategy.calculate_viral_score(
        {
            "hook": "今天给大家分享一个知识点",
            "cta": "谢谢观看",
            "engagement_question": "",
            "content_type": "知识科普",
            "duration": 6,
            "music_style": "",
        }
    )

    assert score["score"] < 80
    assert score["level"] in {"B级（有潜力）", "C级（需要优化）", "D级（需重做）"}


def test_subtitle_target_duration_calibration(tmp_path: Path):
    generator = SubtitleGenerator()
    output_path = tmp_path / "subtitle.srt"
    generator.generate_srt(
        text="这是一次字幕时长校准测试，用来验证生成结果会贴近真实音频时长。",
        output_path=str(output_path),
        target_duration=4.0,
    )

    content = output_path.read_text(encoding="utf-8")
    matches = re.findall(r"(\d{2}:\d{2}:\d{2},\d{3}) --> (\d{2}:\d{2}:\d{2},\d{3})", content)
    assert matches

    last_end = matches[-1][1]
    hours, minutes, seconds, millis = last_end.replace(",", ":").split(":")
    duration = (
        int(hours) * 3600
        + int(minutes) * 60
        + int(seconds)
        + int(millis) / 1000
    )

    assert 3.2 <= duration <= 4.8
