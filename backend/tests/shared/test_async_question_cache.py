"""Tests for async question cache scheduling helpers."""

import time

from app.shared.async_question_cache import (
    generation_is_stale,
    generation_should_schedule,
)


def test_generation_should_schedule_idle_and_failed():
    assert generation_should_schedule({"status": "idle"}) is True
    assert generation_should_schedule({"status": "failed"}) is True
    assert generation_should_schedule({"status": "ready"}) is False


def test_generation_should_schedule_stale_generating():
    cache = {
        "status": "generating",
        "started_at": time.time() - 120,
    }
    assert generation_should_schedule(cache, stale_seconds=90) is True
    assert generation_is_stale(cache, stale_seconds=90) is True


def test_generation_should_not_reschedule_fresh_generating():
    cache = {
        "status": "generating",
        "started_at": time.time(),
    }
    assert generation_should_schedule(cache, stale_seconds=90) is False
    assert generation_is_stale(cache, stale_seconds=90) is False
