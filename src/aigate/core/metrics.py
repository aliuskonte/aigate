"""Prometheus metrics for AIGate."""

from __future__ import annotations

from prometheus_client import Counter, Histogram

# Chat completions
aigate_requests_total = Counter(
    "aigate_requests_total",
    "Total chat completion requests",
    ["provider", "model", "stream", "status"],
)
aigate_request_duration_seconds = Histogram(
    "aigate_request_duration_seconds",
    "Chat completion request duration in seconds",
    ["provider", "model", "stream"],
    buckets=(0.1, 0.25, 0.5, 1.0, 2.5, 5.0, 10.0, 30.0, 60.0),
)
aigate_errors_total = Counter(
    "aigate_errors_total",
    "Total chat completion errors by status",
    ["provider", "model", "status"],
)
aigate_billed_cost_total = Counter(
    "aigate_billed_cost_total",
    "Total billed cost in USD",
    ["provider", "model"],
)
