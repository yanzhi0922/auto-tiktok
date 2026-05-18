from __future__ import annotations

import json
import time
import zipfile
from pathlib import Path

from ops import backup_project, migrate_output_manifests
from src.dashboard.security import DashboardSecurity
from src.pipeline.video_plan import AssetPlan, VideoPlan
from src.publish.publisher import (
    MAX_TIKTOK_CHUNK_SIZE,
    MIN_TIKTOK_CHUNK_SIZE,
    ManualExportPublisher,
    TikTokContentPostingPublisher,
)
from src.tasks.queue import TaskQueue
from src.utils.redaction import redact_text


def test_redaction_masks_api_keys_and_bearer_tokens():
    text = "Authorization: Bearer abc.def.ghi key=sk-cp-secret-value"

    redacted = redact_text(text)

    assert "abc.def.ghi" not in redacted
    assert "sk-cp-secret-value" not in redacted
    assert "***" in redacted


def test_dashboard_security_requires_login_and_csrf_cookie():
    security = DashboardSecurity(token="dashboard-token")

    session = security.authenticate("dashboard-token")
    cookie_header = "; ".join(header.split(";")[0] for _, header in security.session_headers(session))

    assert security.auth_required is True
    assert security.is_authenticated(security.get_session(cookie_header)) is True
    assert security.validate_csrf(
        session=session,
        header_value=session.csrf_token,
        cookie_header=cookie_header,
    )
    assert not security.validate_csrf(
        session=session,
        header_value="wrong",
        cookie_header=cookie_header,
    )


def test_task_queue_executes_and_persists_redacted_results(tmp_path: Path):
    queue = TaskQueue(base_dir=tmp_path / "output")
    queue.handlers["noop"] = lambda payload: {"ok": True, "token": "sk-cp-secret"}

    task = queue.enqueue("noop", {"message": "hello"})
    queue.start()
    try:
        for _ in range(40):
            current = queue.get_task(task.id)
            if current and current["status"] == "succeeded":
                break
            time.sleep(0.05)
    finally:
        queue.stop()

    current = queue.get_task(task.id)
    state = (tmp_path / "output" / "_system" / "tasks" / "tasks.json").read_text(encoding="utf-8")

    assert current is not None
    assert current["status"] == "succeeded"
    assert current["result"]["token"] == "***"
    assert "sk-cp-secret" not in state


def test_manual_publisher_creates_publish_package(tmp_path: Path):
    content_dir = tmp_path / "content"
    content_dir.mkdir()
    video_path = content_dir / "final.mp4"
    video_path.write_bytes(b"video")
    plan = VideoPlan(
        topic="厨房技巧",
        content_type="生活技巧",
        content_dir=str(content_dir),
        titles=["厨房技巧别再错过"],
        hashtags=["#厨房", "#技巧"],
        assets={"final_video": AssetPlan(kind="final_video", path=str(video_path))},
    )
    plan_path = plan.save(content_dir / "video_plan.json")

    result = ManualExportPublisher().publish(plan_path=plan_path)
    package = json.loads(Path(result["package_path"]).read_text(encoding="utf-8"))

    assert result["status"] == "draft_ready"
    assert package["metadata"]["caption"].startswith("厨房技巧别再错过")
    assert package["metadata"]["video_path"] == str(video_path)


def test_tiktok_publisher_uses_valid_chunk_plan(tmp_path: Path):
    video_path = tmp_path / "big.mp4"
    with video_path.open("wb") as file:
        file.truncate(MAX_TIKTOK_CHUNK_SIZE + 1024 * 1024)

    payload = TikTokContentPostingPublisher(
        access_token="test-token",
    )._build_init_payload(
        metadata={"caption": "demo"},
        video_path=video_path,
    )

    source_info = payload["source_info"]
    assert source_info["video_size"] == video_path.stat().st_size
    assert source_info["total_chunk_count"] == 2
    assert MIN_TIKTOK_CHUNK_SIZE <= source_info["chunk_size"] <= MAX_TIKTOK_CHUNK_SIZE
    assert source_info["video_size"] // source_info["chunk_size"] == source_info["total_chunk_count"]


def test_ops_backup_excludes_root_env_and_migrate_repairs_manifest(tmp_path: Path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    (tmp_path / ".env").write_text("SECRET=sk-cp-secret", encoding="utf-8")
    output_dir = tmp_path / "output"
    logs_dir = tmp_path / "logs"
    content_dir = output_dir / "2026-05-18" / "run_demo" / "001"
    content_dir.mkdir(parents=True)
    logs_dir.mkdir()
    (logs_dir / "app.log").write_text("Authorization: Bearer secret", encoding="utf-8")

    migration = migrate_output_manifests(output_dir=output_dir)
    backup = backup_project(output_dir=output_dir, logs_dir=logs_dir, backup_dir=tmp_path / "backups")
    with zipfile.ZipFile(backup["backup_path"]) as archive:
        names = archive.namelist()

    assert migration["count"] == 1
    assert Path(migration["repaired"][0]).exists()
    assert ".env" not in names
