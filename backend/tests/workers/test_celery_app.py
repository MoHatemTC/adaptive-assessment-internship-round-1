"""Tests for Celery worker bootstrap."""

from app.workers.celery_app import celery_app


def test_celery_app_name_and_broker():
    assert celery_app.main == "masaar"
    assert celery_app.conf.broker_url
    assert celery_app.conf.result_backend == celery_app.conf.broker_url
    assert "app.workers.pipeline_tasks" in celery_app.conf.include
    assert celery_app.conf.task_time_limit == 300
    assert celery_app.conf.task_soft_time_limit == 270
    assert celery_app.conf.task_annotations
    assert "*" in celery_app.conf.task_annotations
