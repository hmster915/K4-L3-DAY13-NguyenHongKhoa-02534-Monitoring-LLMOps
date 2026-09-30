from __future__ import annotations

import html
import json
import os
from collections import Counter, defaultdict
from datetime import datetime, timedelta, timezone
from pathlib import Path
from statistics import mean
from typing import Any

import yaml

from .metrics import percentile


LOG_PATH = Path(os.getenv("LOG_PATH", "data/logs.jsonl"))
CONFIG_PATH = Path("config/dashboard.yaml")


def load_recent_records(
    path: Path | None = None,
    *,
    window_minutes: int = 60,
    now: datetime | None = None,
) -> list[dict[str, Any]]:
    log_path = path or LOG_PATH
    if not log_path.exists():
        return []

    current_time = now or datetime.now(timezone.utc)
    start_time = current_time - timedelta(minutes=window_minutes)
    records: list[dict[str, Any]] = []
    for line in log_path.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        try:
            record = json.loads(line)
            timestamp = datetime.fromisoformat(str(record["ts"]).replace("Z", "+00:00"))
        except (json.JSONDecodeError, KeyError, TypeError, ValueError):
            continue
        if start_time <= timestamp <= current_time:
            records.append(record)
    return records


def build_dashboard_snapshot(records: list[dict[str, Any]]) -> dict[str, Any]:
    requests = [record for record in records if record.get("event") == "request_received"]
    responses = [record for record in records if record.get("event") == "response_sent"]
    failures = [record for record in records if record.get("event") == "request_failed"]

    latencies = [int(record["latency_ms"]) for record in responses if "latency_ms" in record]
    ttfts = [int(record["ttft_ms"]) for record in responses if "ttft_ms" in record]
    costs = [float(record.get("cost_usd", 0)) for record in responses]
    tokens_in = sum(int(record.get("tokens_in", 0)) for record in responses)
    tokens_out = sum(int(record.get("tokens_out", 0)) for record in responses)
    qualities = [float(record["quality_score"]) for record in responses if "quality_score" in record]

    error_rate = (len(failures) / len(requests) * 100) if requests else 0.0
    retrieval_events = [
        record
        for record in records
        if record.get("tool_name") == "retrieval" and record.get("tool_success") is not None
    ]
    retrieval_success = (
        sum(record.get("tool_success") is True for record in retrieval_events)
        / len(retrieval_events)
        * 100
        if retrieval_events
        else 0.0
    )

    timestamps = []
    for record in requests:
        try:
            timestamps.append(datetime.fromisoformat(str(record["ts"]).replace("Z", "+00:00")))
        except (KeyError, TypeError, ValueError):
            continue
    active_minutes = 1.0
    if len(timestamps) > 1:
        active_minutes = max(1.0, (max(timestamps) - min(timestamps)).total_seconds() / 60)

    traffic_by_minute: Counter[str] = Counter()
    cost_by_minute: defaultdict[str, float] = defaultdict(float)
    for record in requests:
        minute = str(record.get("ts", ""))[:16]
        traffic_by_minute[minute] += 1
    for record in responses:
        minute = str(record.get("ts", ""))[:16]
        cost_by_minute[minute] += float(record.get("cost_usd", 0))

    return {
        "records": len(records),
        "latency_p50": percentile(latencies, 50),
        "latency_p95": percentile(latencies, 95),
        "latency_p99": percentile(latencies, 99),
        "ttft_p95": percentile(ttfts, 95),
        "request_count": len(requests),
        "requests_per_minute": round(len(requests) / active_minutes, 2),
        "traffic_series": dict(sorted(traffic_by_minute.items())),
        "error_rate_pct": round(error_rate, 2),
        "error_breakdown": dict(Counter(record.get("error_type", "unknown") for record in failures)),
        "retrieval_success_rate_pct": round(retrieval_success, 2),
        "cost_total_usd": round(sum(costs), 6),
        "cost_series": {key: round(value, 6) for key, value in sorted(cost_by_minute.items())},
        "tokens_in_total": tokens_in,
        "tokens_out_total": tokens_out,
        "quality_avg": round(mean(qualities), 3) if qualities else 0.0,
    }


def _status(value: float, *, operator: str, threshold: float) -> tuple[str, str]:
    healthy = value <= threshold if operator == "lte" else value >= threshold
    return ("healthy", "Within SLO") if healthy else ("alert", "Threshold breached")


def _series_text(series: dict[str, Any], unit: str) -> str:
    if not series:
        return "No time-series points yet"
    return " · ".join(
        f"{html.escape(key[-5:])}: {value} {html.escape(unit)}"
        for key, value in list(series.items())[-8:]
    )


def render_dashboard_html(
    records: list[dict[str, Any]] | None = None,
    *,
    config_path: Path = CONFIG_PATH,
    filter_label: str = "all features",
    latency_threshold_ms: int | None = None,
) -> str:
    contract = yaml.safe_load(config_path.read_text(encoding="utf-8"))["dashboard"]
    snapshot = build_dashboard_snapshot(records if records is not None else load_recent_records())
    panels = {panel["id"]: panel for panel in contract["panels"]}

    effective_latency_threshold = (
        latency_threshold_ms
        if latency_threshold_ms is not None
        else panels["latency"]["threshold"]["value"]
    )
    latency_status = _status(
        snapshot["latency_p95"],
        operator=panels["latency"]["threshold"]["operator"],
        threshold=effective_latency_threshold,
    )
    traffic_status = _status(
        snapshot["requests_per_minute"],
        operator=panels["traffic"]["threshold"]["operator"],
        threshold=panels["traffic"]["threshold"]["value"],
    )
    error_status = _status(
        snapshot["error_rate_pct"],
        operator=panels["errors"]["threshold"]["operator"],
        threshold=panels["errors"]["threshold"]["value"],
    )
    if snapshot["retrieval_success_rate_pct"] < 90:
        error_status = ("alert", "Threshold breached")
    cost_status = _status(
        snapshot["cost_total_usd"],
        operator=panels["cost"]["threshold"]["operator"],
        threshold=panels["cost"]["threshold"]["value"],
    )
    token_status = _status(
        max(snapshot["tokens_in_total"], snapshot["tokens_out_total"]),
        operator=panels["tokens"]["threshold"]["operator"],
        threshold=panels["tokens"]["threshold"]["value"],
    )
    quality_status = _status(
        snapshot["quality_avg"],
        operator=panels["quality"]["threshold"]["operator"],
        threshold=panels["quality"]["threshold"]["value"],
    )

    def badge(status: tuple[str, str]) -> str:
        return f'<span class="badge {status[0]}">{status[1]}</span>'

    return f"""<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <meta http-equiv="refresh" content="{contract['refresh_seconds']}">
  <title>{html.escape(contract['title'])}</title>
  <style>
    :root {{ color-scheme: dark; --bg:#07111f; --card:#101d2f; --line:#26364d; --text:#edf5ff; --muted:#9eb0c7; --cyan:#48d7ff; --green:#54e3a4; --red:#ff7d8e; }}
    * {{ box-sizing:border-box; }} body {{ margin:0; background:radial-gradient(circle at top right,#173052 0,#07111f 42%); color:var(--text); font:15px/1.45 Inter,Segoe UI,sans-serif; }}
    main {{ max-width:1400px; margin:auto; padding:28px; }} header {{ display:flex; justify-content:space-between; gap:24px; align-items:end; margin-bottom:22px; }}
    h1 {{ margin:0; font-size:29px; letter-spacing:-.5px; }} .subtitle,.meta,.series {{ color:var(--muted); }} .meta {{ text-align:right; }}
    .grid {{ display:grid; grid-template-columns:repeat(3,minmax(0,1fr)); gap:16px; }} .panel {{ background:linear-gradient(145deg,rgba(20,35,56,.97),rgba(11,25,42,.97)); border:1px solid var(--line); border-radius:16px; padding:18px; min-height:225px; box-shadow:0 14px 34px rgba(0,0,0,.22); }}
    .panel-head {{ display:flex; justify-content:space-between; gap:12px; align-items:start; }} h2 {{ font-size:16px; margin:0 0 16px; }} .badge {{ border-radius:999px; padding:4px 9px; font-size:11px; white-space:nowrap; }} .healthy {{ color:var(--green); background:rgba(84,227,164,.1); }} .alert {{ color:var(--red); background:rgba(255,125,142,.12); }}
    .metrics {{ display:grid; grid-template-columns:repeat(2,1fr); gap:12px; }} .metric {{ padding:10px 0; }} .value {{ color:var(--cyan); font-size:25px; font-weight:750; }} .label {{ color:var(--muted); font-size:12px; text-transform:uppercase; letter-spacing:.8px; }}
    .threshold {{ border-top:1px solid var(--line); margin-top:14px; padding-top:12px; color:#c9d6e6; font-size:12px; }} .series {{ margin-top:10px; font-size:11px; min-height:32px; }} footer {{ margin-top:20px; color:var(--muted); font-size:12px; }}
    @media(max-width:1000px) {{ .grid {{ grid-template-columns:repeat(2,1fr); }} }} @media(max-width:680px) {{ .grid {{ grid-template-columns:1fr; }} header {{ align-items:start; flex-direction:column; }} .meta {{ text-align:left; }} }}
  </style>
</head>
<body><main>
  <header><div><h1>{html.escape(contract['title'])}</h1><div class="subtitle">Production signals from structured application logs</div></div><div class="meta">Time range: last {contract['time_range_minutes']} minutes<br>Filter: {html.escape(filter_label)}<br>Refresh: {contract['refresh_seconds']} seconds · Source: data/logs.jsonl<br>Records in window: {snapshot['records']}</div></header>
  <div class="grid">
    <section class="panel" id="panel-latency"><div class="panel-head"><h2>Latency percentiles and TTFT</h2>{badge(latency_status)}</div><div class="metrics"><div class="metric"><div class="value">{snapshot['latency_p50']:.0f} ms</div><div class="label">Latency P50</div></div><div class="metric"><div class="value">{snapshot['latency_p95']:.0f} ms</div><div class="label">Latency P95</div></div><div class="metric"><div class="value">{snapshot['latency_p99']:.0f} ms</div><div class="label">Latency P99</div></div><div class="metric"><div class="value">{snapshot['ttft_p95']:.0f} ms</div><div class="label">TTFT P95</div></div></div><div class="threshold">Active threshold: P95 ≤ {effective_latency_threshold} ms</div></section>
    <section class="panel" id="panel-traffic"><div class="panel-head"><h2>Request traffic</h2>{badge(traffic_status)}</div><div class="metrics"><div class="metric"><div class="value">{snapshot['request_count']}</div><div class="label">Requests</div></div><div class="metric"><div class="value">{snapshot['requests_per_minute']}</div><div class="label">Requests/min</div></div></div><div class="series">{_series_text(snapshot['traffic_series'], 'req')}</div><div class="threshold">Expected traffic: ≥ 1 request/min while workload is active</div></section>
    <section class="panel" id="panel-errors"><div class="panel-head"><h2>Error rate and retrieval success</h2>{badge(error_status)}</div><div class="metrics"><div class="metric"><div class="value">{snapshot['error_rate_pct']:.2f}%</div><div class="label">Error rate</div></div><div class="metric"><div class="value">{snapshot['retrieval_success_rate_pct']:.2f}%</div><div class="label">Retrieval success</div></div></div><div class="series">Error breakdown: {html.escape(json.dumps(snapshot['error_breakdown'], ensure_ascii=False))}</div><div class="threshold">SLO thresholds: errors ≤ 2% · retrieval ≥ 90%</div></section>
    <section class="panel" id="panel-cost"><div class="panel-head"><h2>Cost over time</h2>{badge(cost_status)}</div><div class="metrics"><div class="metric"><div class="value">${snapshot['cost_total_usd']:.6f}</div><div class="label">Window total</div></div></div><div class="series">{_series_text(snapshot['cost_series'], 'USD')}</div><div class="threshold">Budget threshold: total ≤ $2.50</div></section>
    <section class="panel" id="panel-tokens"><div class="panel-head"><h2>Input and output tokens</h2>{badge(token_status)}</div><div class="metrics"><div class="metric"><div class="value">{snapshot['tokens_in_total']}</div><div class="label">Input tokens</div></div><div class="metric"><div class="value">{snapshot['tokens_out_total']}</div><div class="label">Output tokens</div></div></div><div class="threshold">Guardrail: each token series ≤ 50,000 tokens</div></section>
    <section class="panel" id="panel-quality"><div class="panel-head"><h2>Quality proxy</h2>{badge(quality_status)}</div><div class="metrics"><div class="metric"><div class="value">{snapshot['quality_avg']:.3f}</div><div class="label">Mean score (0–1)</div></div></div><div class="threshold">Quality threshold: mean ≥ 0.75</div></section>
  </div>
  <footer>Operational path: Metrics → Logs → Traces → Root cause · Correlate requests using correlation_id.</footer>
</main></body></html>"""
