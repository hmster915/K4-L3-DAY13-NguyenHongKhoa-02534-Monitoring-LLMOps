from __future__ import annotations

import asyncio
import json
import re
from pathlib import Path

import httpx

from app import logging_config
from app.main import app


def _send_chat(
    *,
    headers: dict[str, str] | None = None,
    message: str = "Explain observability",
) -> httpx.Response:
    async def send_request() -> httpx.Response:
        transport = httpx.ASGITransport(app=app)
        async with httpx.AsyncClient(
            transport=transport, base_url="http://test"
        ) as client:
            return await client.post(
                "/chat",
                headers=headers,
                json={
                    "user_id": "student-01",
                    "session_id": "session-01",
                    "feature": "qa",
                    "message": message,
                },
            )

    return asyncio.run(send_request())


def test_chat_response_log_exposes_quality_for_dashboard(
    monkeypatch, tmp_path: Path
) -> None:
    log_path = tmp_path / "logs.jsonl"
    monkeypatch.setattr(logging_config, "LOG_PATH", log_path)

    response = _send_chat()

    assert response.status_code == 200
    events = [json.loads(line) for line in log_path.read_text(encoding="utf-8").splitlines()]
    response_event = next(event for event in events if event["event"] == "response_sent")
    assert response_event["quality_score"] == response.json()["quality_score"]
    assert response_event["ttft_ms"] == response.json()["ttft_ms"]
    assert response_event["tool_name"] == "retrieval"
    assert response_event["tool_success"] is True


def test_request_id_is_propagated_and_logs_are_enriched(
    monkeypatch, tmp_path: Path
) -> None:
    log_path = tmp_path / "logs.jsonl"
    monkeypatch.setattr(logging_config, "LOG_PATH", log_path)

    response = _send_chat(headers={"x-request-id": "req-abcdef12"})

    assert response.status_code == 200
    assert response.headers["x-request-id"] == "req-abcdef12"
    assert float(response.headers["x-response-time-ms"]) >= 0
    assert response.json()["correlation_id"] == "req-abcdef12"

    events = [json.loads(line) for line in log_path.read_text(encoding="utf-8").splitlines()]
    request_event = next(event for event in events if event["event"] == "request_received")
    assert request_event["correlation_id"] == "req-abcdef12"
    assert request_event["user_id_hash"]
    assert request_event["session_id"] == "session-01"
    assert request_event["feature"] == "qa"
    assert request_event["model"]
    assert request_event["env"]


def test_invalid_or_missing_request_id_is_replaced_without_context_leak(
    monkeypatch, tmp_path: Path
) -> None:
    log_path = tmp_path / "logs.jsonl"
    monkeypatch.setattr(logging_config, "LOG_PATH", log_path)

    first = _send_chat(headers={"x-request-id": "not-valid"})
    second = _send_chat()

    first_id = first.headers["x-request-id"]
    second_id = second.headers["x-request-id"]
    assert re.fullmatch(r"req-[0-9a-f]{8}", first_id)
    assert re.fullmatch(r"req-[0-9a-f]{8}", second_id)
    assert first_id != second_id


def test_pii_is_redacted_before_log_file_write(monkeypatch, tmp_path: Path) -> None:
    log_path = tmp_path / "logs.jsonl"
    monkeypatch.setattr(logging_config, "LOG_PATH", log_path)
    raw_values = (
        "student@vinuni.edu.vn",
        "090 123 4567",
        "001234567890",
        "4111 1111 1111 1111",
    )

    response = _send_chat(message=" | ".join(raw_values))

    assert response.status_code == 200
    log_text = log_path.read_text(encoding="utf-8")
    for raw_value in raw_values:
        assert raw_value not in log_text
    assert "REDACTED_EMAIL" in log_text
    assert "REDACTED_PHONE_VN" in log_text
    assert "REDACTED_CCCD" in log_text
    assert "REDACTED_CREDIT_CARD" in log_text
