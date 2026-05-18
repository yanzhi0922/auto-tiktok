from __future__ import annotations

from pathlib import Path

from config.settings import Settings
from src.pipeline.autopilot import AutopilotService, TopicProvider


class FakeResponse:
    def __init__(self, payload):
        self._payload = payload
        self.text = ""

    def json(self):
        return self._payload

    def raise_for_status(self):
        return None


def test_topic_provider_merges_external_topics_by_content_type(monkeypatch):
    settings = Settings()
    settings.auto.autopilot.topic_source_urls = ["https://example.test/topics.json"]

    provider = TopicProvider(
        settings,
        http_get=lambda *args, **kwargs: FakeResponse(
            [{"topic": "外部热榜冷知识", "content_type": "knowledge"}]
        ),
    )

    plan = provider.build_plan(count=2, content_types=["知识科普"])

    assert plan[0].topic == "外部热榜冷知识"
    assert plan[0].content_type == "知识科普"
    assert plan[0].source == "https://example.test/topics.json"
    assert plan[1].topic


class FakePack:
    def __init__(
        self,
        *,
        topic: str,
        score: int,
        passed: bool,
        content_dir: Path,
    ):
        self.topic = topic
        self.content_type = "知识科普"
        self.viral_score = {"score": score, "level": "A级"}
        self.quality_gate_passed = passed
        self.content_dir = content_dir
        self.video_path = content_dir / "video.mp4"
        self.final_video_path = content_dir / "final.mp4" if passed else None
        self.cover_path = content_dir / "cover.jpg" if passed else None
        self.thumbnail_path = self.cover_path
        self.video_plan_path = content_dir / "video_plan.json"
        self.video_path.write_bytes(b"video")
        if self.final_video_path:
            self.final_video_path.write_bytes(b"final")
        if self.cover_path:
            self.cover_path.write_bytes(b"cover")
        self.video_plan_path.write_text("{}", encoding="utf-8")


class FakePipeline:
    def __init__(self, *, file_manager):
        self.file_manager = file_manager
        self.calls = 0

    def generate_douyin_content(self, **kwargs):
        self.calls += 1
        _, content_dir = self.file_manager.reserve_content_slot(kwargs["pack_index"])
        if self.calls == 1:
            return FakePack(
                topic=kwargs["topic"],
                score=40,
                passed=False,
                content_dir=content_dir,
            )
        return FakePack(
            topic=kwargs["topic"],
            score=88,
            passed=True,
            content_dir=content_dir,
        )

    def close(self):
        return None


class FakePublisher:
    def __init__(self):
        self.calls = []

    def publish(self, *, plan_path: str, provider: str):
        self.calls.append((plan_path, provider))
        return {"status": "draft_ready", "provider": provider, "plan_path": plan_path}


def test_autopilot_skips_low_score_and_publishes_next_candidate(tmp_path: Path):
    settings = Settings()
    settings.auto.autopilot.max_topic_attempts = 2
    settings.auto.autopilot.default_count = 1
    settings.auto.autopilot.asset_retries = []
    settings.auto.content_strategy.auto_generate_video = False
    settings.auto.content_strategy.auto_generate_thumbnail = False
    publisher = FakePublisher()

    def pipeline_factory(*, output_dir: str, file_manager):
        return FakePipeline(file_manager=file_manager)

    service = AutopilotService(
        settings=settings,
        output_dir=tmp_path / "output",
        pipeline_factory=pipeline_factory,
        publisher=publisher,
    )

    result = service.run(
        count=1,
        content_types=["知识科普"],
        min_score=65,
        publish_provider="manual",
    )

    assert result["status"] == "succeeded"
    assert result["skipped_count"] == 1
    assert result["success_count"] == 1
    assert result["final_videos"][0]["score"] == 88
    assert result["publications"][0]["provider"] == "manual"
    assert publisher.calls
    assert Path(result["report_path"]).exists()


def test_task_queue_accepts_autopilot_payload(tmp_path: Path, monkeypatch):
    from src.tasks import queue as queue_module

    class FakeAutopilot:
        def __init__(self, output_dir):
            self.output_dir = output_dir

        def run(self, **kwargs):
            return {"status": "succeeded", "kwargs": kwargs}

    monkeypatch.setattr(queue_module, "AutopilotService", FakeAutopilot)
    task_queue = queue_module.TaskQueue(base_dir=tmp_path / "output")

    result = task_queue._handle_autopilot_run(
        {
            "count": 1,
            "content_types": "知识科普",
            "min_score": 70,
            "publish_provider": "manual",
        }
    )

    assert result["status"] == "succeeded"
    assert result["kwargs"]["content_types"] == ["知识科普"]
    assert result["kwargs"]["min_score"] == 70
