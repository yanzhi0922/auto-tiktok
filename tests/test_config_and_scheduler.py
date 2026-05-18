from __future__ import annotations

from pathlib import Path

from auto_scheduler import WindowsTaskScheduler, _build_topic_plan
from config.settings import AutoConfig
from src.pipeline.douyin_pipeline import DouyinPipeline
from src.strategy.douyin_strategy import DouyinContentStrategy


def test_auto_config_loads_yaml_values(tmp_path: Path):
    config_file = tmp_path / "auto_config.yaml"
    config_file.write_text(
        """
content_strategy:
  daily_count: 5
  default_voice: "female_shaonv"
  auto_generate_music: true
automation:
  schedule: "0 18 * * *"
  output_dir: "custom_output"
  log_dir: "custom_logs"
autopilot:
  default_count: 4
  min_score: 72
  publish_provider: "auto"
""".strip(),
        encoding="utf-8",
    )

    config = AutoConfig.load(config_file)

    assert config.content_strategy.daily_count == 5
    assert config.content_strategy.default_voice == "female_shaonv"
    assert config.content_strategy.auto_generate_music is True
    assert config.automation.daily_time == "18:00"
    assert config.automation.output_dir == "custom_output"
    assert config.automation.log_dir == "custom_logs"
    assert config.autopilot.default_count == 4
    assert config.autopilot.min_score == 72
    assert config.autopilot.publish_provider == "auto"


def test_windows_task_scheduler_includes_runtime_args(
    tmp_path: Path, monkeypatch
):
    (tmp_path / "run_daily.py").write_text("print('ok')", encoding="utf-8")
    scheduler = WindowsTaskScheduler(str(tmp_path))
    captured: dict[str, list[str]] = {}

    def fake_build_task_xml(
        self,
        task_name: str,
        command: list[str],
        start_time: str | None = None,
        days_interval: int = 1,
        enabled: bool = True,
    ) -> str:
        captured["command"] = command
        return "<Task/>"

    class FakeCompletedProcess:
        def __init__(self):
            self.returncode = 0
            self.stderr = ""
            self.stdout = ""

    monkeypatch.setattr(
        WindowsTaskScheduler, "_build_task_xml", fake_build_task_xml
    )
    monkeypatch.setattr(
        "auto_scheduler.subprocess.run",
        lambda *args, **kwargs: FakeCompletedProcess(),
    )

    ok = scheduler.create_daily_task(
        "daily_content",
        run_time="08:30",
        count=4,
        min_score=70,
        max_concurrent=2,
        content_types=["生活技巧", "知识科普"],
        log_level="DEBUG",
    )

    assert ok is True
    command = captured["command"]
    assert "--count" in command and "4" in command
    assert "--min-score" in command and "70" in command
    assert "--concurrent" in command and "2" in command
    assert "--types" in command and "生活技巧,知识科普" in command
    assert "--log-level" in command and "DEBUG" in command


def test_windows_task_scheduler_can_install_autopilot_task(tmp_path: Path, monkeypatch):
    (tmp_path / "autopilot.py").write_text("print('ok')", encoding="utf-8")
    scheduler = WindowsTaskScheduler(str(tmp_path))
    captured: dict[str, list[str]] = {}

    def fake_build_task_xml(self, task_name, command, **kwargs):
        captured["command"] = command
        return "<Task/>"

    monkeypatch.setattr(WindowsTaskScheduler, "_build_task_xml", fake_build_task_xml)

    class FakeCompletedProcess:
        returncode = 0
        stderr = ""
        stdout = ""

    monkeypatch.setattr(
        "auto_scheduler.subprocess.run",
        lambda *args, **kwargs: FakeCompletedProcess(),
    )

    ok = scheduler.create_daily_task(
        "autopilot",
        autopilot=True,
        publish_provider="auto",
    )

    assert ok is True
    command = captured["command"]
    assert str(tmp_path / "autopilot.py") in command
    assert "run" in command
    assert "--provider" in command and "auto" in command
    assert "--concurrent" not in command


def test_build_topic_plan_aligns_topic_with_requested_content_type():
    strategy = DouyinContentStrategy()
    pipeline = type("PipelineStub", (), {"strategy": strategy})()
    requested_types = ["知识科普", "萌宠日常", "旅行vlog", "知识科普"]

    plan = _build_topic_plan(
        content_count=len(requested_types),
        content_types=requested_types,
        pipeline=pipeline,
    )

    assert [item["content_type"] for item in plan] == requested_types
    for item in plan:
        assert item["topic"] in strategy.TRENDING_TOPICS[item["content_type"]]


def test_douyin_generate_daily_content_uses_type_aligned_topics(
    tmp_path: Path,
    monkeypatch,
):
    pipeline = DouyinPipeline(output_dir=str(tmp_path / "output"))
    captured: list[tuple[str, str]] = []

    def fake_generate_douyin_content(*, topic: str, content_type: str, **kwargs):
        captured.append((topic, content_type))
        return type("PackStub", (), {"topic": topic, "content_type": content_type})()

    monkeypatch.setattr(pipeline, "generate_douyin_content", fake_generate_douyin_content)

    pipeline.generate_daily_content(count=3, content_types=["知识科普"])

    assert len(captured) == 3
    for topic, content_type in captured:
        assert content_type == "知识科普"
        assert topic in pipeline.strategy.TRENDING_TOPICS["知识科普"]

    pipeline.close()
