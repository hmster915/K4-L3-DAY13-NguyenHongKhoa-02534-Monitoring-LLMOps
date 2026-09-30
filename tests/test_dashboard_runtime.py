from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path

from app.dashboard import build_dashboard_snapshot, load_recent_records, render_dashboard_html


def test_dashboard_snapshot_uses_structured_log_contract() -> None:
    records = [
        {"event": "request_received", "ts": "2026-09-30T03:00:00Z"},
        {"event": "request_received", "ts": "2026-09-30T03:00:30Z"},
        {
            "event": "response_sent",
            "ts": "2026-09-30T03:00:01Z",
            "latency_ms": 100,
            "ttft_ms": 25,
            "cost_usd": 0.001,
            "tokens_in": 20,
            "tokens_out": 80,
            "quality_score": 0.8,
            "tool_name": "retrieval",
            "tool_success": True,
        },
        {
            "event": "request_failed",
            "ts": "2026-09-30T03:00:31Z",
            "error_type": "RuntimeError",
            "tool_name": "retrieval",
            "tool_success": False,
        },
    ]

    snapshot = build_dashboard_snapshot(records)

    assert snapshot["request_count"] == 2
    assert snapshot["latency_p95"] == 100
    assert snapshot["ttft_p95"] == 25
    assert snapshot["error_rate_pct"] == 50
    assert snapshot["retrieval_success_rate_pct"] == 50
    assert snapshot["tokens_in_total"] == 20
    assert snapshot["tokens_out_total"] == 80
    assert snapshot["quality_avg"] == 0.8


def test_dashboard_renders_six_named_runtime_panels() -> None:
    rendered = render_dashboard_html(
        records=[],
        filter_label="feature=monitoring",
        latency_threshold_ms=2000,
    )

    for panel_id in ("latency", "traffic", "errors", "cost", "tokens", "quality"):
        assert f'id="panel-{panel_id}"' in rendered
    assert "last 60 minutes" in rendered
    assert "Refresh: 30 seconds" in rendered
    assert "Source: data/logs.jsonl" in rendered
    assert "Filter: feature=monitoring" in rendered
    assert "Active threshold: P95 ≤ 2000 ms" in rendered


def test_recent_log_reader_ignores_old_and_invalid_records(tmp_path: Path) -> None:
    path = tmp_path / "logs.jsonl"
    path.write_text(
        "{\"event\":\"request_received\",\"ts\":\"2026-09-30T03:30:00Z\"}\n"
        "not-json\n"
        "{\"event\":\"request_received\",\"ts\":\"2026-09-30T01:00:00Z\"}\n",
        encoding="utf-8",
    )

    records = load_recent_records(
        path,
        now=datetime(2026, 9, 30, 4, 0, tzinfo=timezone.utc),
    )

    assert len(records) == 1
    assert records[0]["ts"] == "2026-09-30T03:30:00Z"
