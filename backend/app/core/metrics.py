"""Prometheus metrics definitions for the Masaar backend.

Defines the process-wide metric objects and two convenience recorders. The
request middleware records HTTP metrics; the LLM gateway and agent nodes record
LLM metrics; Celery tasks record task metrics. This module only *defines* the
metrics — exposing them (a ``/metrics`` endpoint) and the Prometheus/Grafana
infrastructure are deliberately out of scope.

All metrics register against the default Prometheus registry at import time, so
this module must be imported exactly once per process (it is, via the kernel).
"""

from prometheus_client import Counter, Gauge, Histogram

#: Total HTTP requests handled, partitioned by method, route, and status code.
http_requests_total = Counter(
    "http_requests_total",
    "Total number of HTTP requests handled.",
    labelnames=("method", "endpoint", "status_code"),
)

#: HTTP request latency in seconds, partitioned by method and route.
http_request_duration_seconds = Histogram(
    "http_request_duration_seconds",
    "HTTP request duration in seconds.",
    labelnames=("method", "endpoint"),
)

#: Total LLM calls, partitioned by model, invoking tool, and outcome status.
llm_calls_total = Counter(
    "llm_calls_total",
    "Total number of LLM calls made through the gateway.",
    labelnames=("model", "tool", "status"),
)

#: LLM call latency in seconds, partitioned by model and invoking tool.
llm_call_duration_seconds = Histogram(
    "llm_call_duration_seconds",
    "LLM call duration in seconds.",
    labelnames=("model", "tool"),
)

#: Currently active assessment sessions. Incremented on session start,
#: decremented on session end.
active_sessions = Gauge(
    "active_sessions",
    "Number of currently active assessment sessions.",
)

#: Total Celery background tasks executed, partitioned by task name and status.
celery_tasks_total = Counter(
    "celery_tasks_total",
    "Total number of Celery tasks executed.",
    labelnames=("task_name", "status"),
)


def record_request(
    method: str,
    endpoint: str,
    status_code: int,
    duration: float,
) -> None:
    """Record a completed HTTP request.

    Args:
        method: HTTP method (for example ``"GET"``, ``"POST"``).
        endpoint: Route path or template (for example ``"/api/v1/sessions"``).
        status_code: HTTP response status code.
        duration: Request duration in seconds.

    Returns:
        None.
    """
    http_requests_total.labels(
        method=method,
        endpoint=endpoint,
        status_code=str(status_code),
    ).inc()
    http_request_duration_seconds.labels(
        method=method,
        endpoint=endpoint,
    ).observe(duration)


def record_llm_call(
    model: str,
    tool: str,
    status: str,
    duration: float,
) -> None:
    """Record a completed LLM call.

    Args:
        model: Model identifier used for the call.
        tool: Invoking tool/node name (for example ``"grader"``, ``"health"``).
        status: Outcome status (for example ``"success"``, ``"error"``).
        duration: Call duration in seconds.

    Returns:
        None.
    """
    llm_calls_total.labels(model=model, tool=tool, status=status).inc()
    llm_call_duration_seconds.labels(model=model, tool=tool).observe(duration)


__all__ = [
    "http_requests_total",
    "http_request_duration_seconds",
    "llm_calls_total",
    "llm_call_duration_seconds",
    "active_sessions",
    "celery_tasks_total",
    "record_request",
    "record_llm_call",
]
