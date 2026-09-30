from __future__ import annotations

from pathlib import Path

import yaml


REPO_ROOT = Path(__file__).resolve().parents[1]


def test_slo_has_consistent_error_budget() -> None:
    config = yaml.safe_load((REPO_ROOT / "config" / "slo.yaml").read_text(encoding="utf-8"))
    slo = config["primary_slo"]

    assert slo["target_percent"] == 99.5
    assert slo["error_budget_percent"] == 100 - slo["target_percent"]
    assert "10,000" in slo["error_budget_example"]
    assert "50" in slo["error_budget_example"]


def test_three_alerts_have_routable_runbooks() -> None:
    config = yaml.safe_load(
        (REPO_ROOT / "config" / "alert_rules.yaml").read_text(encoding="utf-8")
    )
    alerts = config["alerts"]
    runbook = (REPO_ROOT / "docs" / "alerts.md").read_text(encoding="utf-8")

    assert len(alerts) == 3
    for index, alert in enumerate(alerts, start=1):
        assert alert["type"] == "symptom-based"
        assert alert["severity"] in {"warning", "critical"}
        assert alert["duration"].endswith("m")
        assert alert["channel"] == "slack:#k4-l3b-alerts"
        assert alert["owner"] == "student-02534"
        assert alert["condition"]
        assert alert["runbook"] == f"docs/alerts.md#alert-{index}"
        assert f"## Alert {index}" in runbook

    assert "TODO" not in (REPO_ROOT / "config" / "alert_rules.yaml").read_text(
        encoding="utf-8"
    )
