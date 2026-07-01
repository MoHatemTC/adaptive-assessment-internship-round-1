"""Celery tasks: email radar report to learner and admin on completion."""

from __future__ import annotations

import json
import os
import smtplib
from email.message import EmailMessage

from app.core.logging import get_logger
from app.workers.celery_app import celery_app

_logger = get_logger(__name__)


def _smtp_configured() -> bool:
    return bool(os.environ.get("SMTP_HOST", "").strip())


@celery_app.task(name="reports.email_session_report")
def send_session_report_email(
    prior: dict[str, str] | str,
    *,
    learner_email: str | None = None,
    admin_email: str | None = None,
) -> dict[str, str]:
    """Email session summary after report build. Skips when SMTP is unset."""
    if isinstance(prior, dict):
        session_id = prior.get("session_id", "unknown")
        if prior.get("status") == "pending_admin_review":
            _logger.info(
                "email_task_skipped",
                reason="awaiting admin judge review",
                session_id=session_id,
            )
            return {
                "session_id": session_id,
                "status": "skipped",
                "reason": "pending_admin_review",
            }
    else:
        session_id = prior

    if not _smtp_configured():
        _logger.warning("email_task_skipped", reason="SMTP not configured", session_id=session_id)
        return {"session_id": session_id, "status": "skipped", "reason": "smtp_not_configured"}

    host = os.environ.get("SMTP_HOST", "")
    port = int(os.environ.get("SMTP_PORT", "587"))
    user = os.environ.get("SMTP_USER", "")
    password = os.environ.get("SMTP_PASSWORD", "")
    from_addr = os.environ.get("SMTP_FROM", user or "noreply@masaar.local")

    recipients = [addr for addr in (learner_email, admin_email) if addr]
    if not recipients:
        _logger.warning("email_task_skipped", reason="no recipients", session_id=session_id)
        return {"session_id": session_id, "status": "skipped", "reason": "no_recipients"}

    body = json.dumps(
        {
            "session_id": session_id,
            "message": "Your Masaar assessment report is ready.",
        },
        indent=2,
    )
    msg = EmailMessage()
    msg["Subject"] = "Masaar assessment report ready"
    msg["From"] = from_addr
    msg["To"] = ", ".join(recipients)
    msg.set_content(body)

    try:
        with smtplib.SMTP(host, port, timeout=30) as smtp:
            if user and password:
                smtp.starttls()
                smtp.login(user, password)
            smtp.send_message(msg)
    except Exception as exc:  # noqa: BLE001
        _logger.exception("email_task_failed", session_id=session_id, error=str(exc))
        raise

    _logger.info("email_task_sent", session_id=session_id, recipients=recipients)
    return {"session_id": session_id, "status": "sent", "recipients": ",".join(recipients)}


def schedule_post_completion_pipeline(
    session_id: str,
    *,
    learner_email: str | None = None,
) -> None:
    """Chain report build then email (called from complete_session)."""
    admin_email = os.environ.get("ADMIN_REPORT_EMAIL", "").strip() or None
    build = celery_app.signature("reports.build_session_radar", args=[session_id])
    email = celery_app.signature(
        "reports.email_session_report",
        kwargs={
            "learner_email": learner_email,
            "admin_email": admin_email,
        },
    )
    (build | email).apply_async()


def schedule_finalize_after_judge_approval(
    session_id: str,
    *,
    learner_email: str | None = None,
) -> None:
    """Chain report build + email after admin approves a held judge review."""
    admin_email = os.environ.get("ADMIN_REPORT_EMAIL", "").strip() or None
    finalize = celery_app.signature(
        "reports.finalize_approved_session",
        args=[session_id],
    )
    email = celery_app.signature(
        "reports.email_session_report",
        kwargs={
            "learner_email": learner_email,
            "admin_email": admin_email,
        },
    )
    (finalize | email).apply_async()


__all__ = [
    "schedule_finalize_after_judge_approval",
    "schedule_post_completion_pipeline",
    "send_session_report_email",
]
