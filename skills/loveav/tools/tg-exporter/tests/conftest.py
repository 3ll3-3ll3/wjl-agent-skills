from __future__ import annotations

import pytest


@pytest.fixture(autouse=True)
def isolate_daemon_metadata(monkeypatch, tmp_path):
    """测试永远不读写用户真实 APPDATA 中的 daemon 任务与检查点。"""

    monkeypatch.setattr(
        "telegram_exporter.export_coordinator.daemon_job_state_path",
        lambda: tmp_path / "daemon_jobs.json",
    )
    monkeypatch.setattr(
        "telegram_exporter.export_coordinator.state_path",
        lambda: tmp_path / "local_state.json",
    )
