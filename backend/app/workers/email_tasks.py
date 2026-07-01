"""Celery tasks: email radar report PDF to learner and admin via Resend."""

from __future__ import annotations

from datetime import datetime
from typing import Any

import resend
from weasyprint import HTML

from app.config import get_settings
from app.core.logging import get_logger
from app.workers.celery_app import celery_app

_logger = get_logger(__name__)


def _resend_configured() -> bool:
    settings = get_settings()
    return bool(settings.RESEND_API_KEY.get_secret_value().strip())


def _score_bar(score: int | None) -> str:
    if score is None:
        return '<div class="bar"><div class="bar-fill" style="width:0%"></div></div>'
    pct = max(0, min(100, score * 10))
    return f'<div class="bar"><div class="bar-fill" style="width:{pct}%"></div></div>'


def _build_report_html(report: dict[str, Any]) -> str:
    """Build an HTML document from the radar report data for PDF conversion."""
    dims = report.get("dimensions", [])
    dim_rows = "".join(
        f"""<tr>
          <td style="padding:8px 12px;border-bottom:1px solid #e5e7eb;font-weight:500">{d.get("label", d.get("name", ""))}</td>
          <td style="padding:8px 12px;border-bottom:1px solid #e5e7eb;text-align:center">{d.get("score", "—")}/10</td>
          <td style="padding:8px 12px;border-bottom:1px solid #e5e7eb">{_score_bar(d.get("score"))}</td>
        </tr>"""
        for d in dims
    )

    strengths = report.get("strengths", [])
    growth = report.get("growth_areas", [])
    highlights = report.get("evidence_highlights", [])
    tools = report.get("tools_used", [])
    overall = report.get("overall_score")
    questions = report.get("questions_answered", 0)

    strengths_html = (
        "<ul>" + "".join(f"<li>{s}</li>" for s in strengths) + "</ul>"
        if strengths
        else '<p style="color:#9ca3af">None identified</p>'
    )
    growth_html = (
        "<ul>" + "".join(f"<li>{g}</li>" for g in growth) + "</ul>"
        if growth
        else '<p style="color:#9ca3af">None identified</p>'
    )
    highlights_html = (
        "<ul>" + "".join(f"<li>{h}</li>" for h in highlights) + "</ul>"
        if highlights
        else '<p style="color:#9ca3af">No highlights recorded</p>'
    )

    tools_str = ", ".join(tools) if tools else "assessment"

    return f"""<!DOCTYPE html>
<html lang="en">
<head><meta charset="utf-8">
<style>
  @page {{ margin: 2cm; }}
  body {{ font-family: 'DejaVu Sans', sans-serif; color: #1f2937; font-size: 11pt; line-height: 1.5; }}
  h1 {{ font-size: 18pt; color: #111827; margin-bottom: 4px; }}
  .subtitle {{ color: #6b7280; font-size: 10pt; margin-bottom: 20px; }}
  h2 {{ font-size: 14pt; color: #111827; border-bottom: 2px solid #3b82f6; padding-bottom: 4px; margin-top: 24px; }}
  table {{ width: 100%; border-collapse: collapse; margin: 8px 0; }}
  th {{ background: #f3f4f6; padding: 8px 12px; text-align: left; font-weight: 600; font-size: 10pt; }}
  .bar {{ height: 10px; border-radius: 5px; background: #e5e7eb; }}
  .bar-fill {{ height: 10px; border-radius: 5px; background: #3b82f6; }}
  .overall {{ font-size: 16pt; font-weight: 700; color: #2563eb; }}
  ul {{ margin: 4px 0; padding-left: 20px; }}
  li {{ margin: 2px 0; }}
  .footer {{ margin-top: 30px; color: #9ca3af; font-size: 8pt; border-top: 1px solid #e5e7eb; padding-top: 8px; }}
</style>
</head><body>
<h1>Masaar Assessment Report</h1>
<p class="subtitle">Session {report.get("session_id", "")[:8]}&#x2026; &middot; Generated {datetime.now().strftime("%B %d, %Y")}</p>

<h2>Overall Score</h2>
<p class="overall">{overall}/10</p>
<p>{report.get("summary", "")}</p>

<h2>Skill Dimensions</h2>
<table><thead><tr><th style="width:40%">Dimension</th><th style="width:20%">Score</th><th style="width:40%"></th></tr></thead>
<tbody>{dim_rows}</tbody></table>

<h2>Key Insights</h2>
<table><tr><td style="width:50%;vertical-align:top">
  <p style="font-weight:600;color:#059669">Strengths</p>
  {strengths_html}</td>
<td style="width:50%;vertical-align:top">
  <p style="font-weight:600;color:#d97706">Areas to Develop</p>
  {growth_html}</td></tr></table>

<h2>Evidence Highlights</h2>
{highlights_html}

<p style="margin-top:12px;color:#6b7280;font-size:9pt">{questions} questions across {tools_str} tools.</p>

<div class="footer">Masaar &middot; Adaptive Assessment Platform</div>
</body></html>"""


def generate_radar_pdf(report: dict[str, Any]) -> bytes:
    """Render the radar report as a PDF byte string."""
    html_str = _build_report_html(report)
    return HTML(string=html_str).write_pdf()


@celery_app.task(name="reports.email_session_report")
def send_session_report_email(
    report: dict[str, Any],
    *,
    learner_email: str | None = None,
    admin_email: str | None = None,
) -> dict[str, str]:
    """Email PDF radar report via Resend.

    Skips when the session is ``pending_admin_review`` (HITL judge gate — grades
    must be admin-approved before the learner is emailed) or when
    ``RESEND_API_KEY`` is unset.
    """
    session_id = report.get("session_id", "unknown")
    if report.get("status") == "pending_admin_review":
        _logger.info(
            "email_task_skipped",
            reason="pending_admin_review",
            session_id=session_id,
        )
        return {
            "session_id": session_id,
            "status": "skipped",
            "reason": "pending_admin_review",
        }
    if not _resend_configured():
        _logger.warning(
            "email_task_skipped", reason="RESEND_API_KEY not set", session_id=session_id
        )
        return {
            "session_id": session_id,
            "status": "skipped",
            "reason": "resend_not_configured",
        }

    recipients = [addr for addr in (learner_email, admin_email) if addr]
    if not recipients:
        _logger.warning(
            "email_task_skipped", reason="no recipients", session_id=session_id
        )
        return {
            "session_id": session_id,
            "status": "skipped",
            "reason": "no_recipients",
        }

    try:
        pdf_bytes = generate_radar_pdf(report)
    except Exception as exc:
        _logger.exception(
            "pdf_generation_failed", session_id=session_id, error=str(exc)
        )
        return {
            "session_id": session_id,
            "status": "failed",
            "reason": f"pdf_generation_error: {exc}",
        }

    settings = get_settings()
    resend.api_key = settings.RESEND_API_KEY.get_secret_value()
    from_addr = settings.RESEND_FROM

    try:
        response = resend.Emails.send(
            {
                "from": from_addr,
                "to": recipients,
                "subject": "Your Masaar Assessment Report",
                "html": "<p>Your assessment report is attached.</p>",
                "attachments": [
                    {
                        "filename": "masaar-report.pdf",
                        "content": list(pdf_bytes),
                    }
                ],
            }
        )
    except Exception as exc:
        _logger.exception("email_task_failed", session_id=session_id, error=str(exc))
        raise

    _logger.info(
        "email_task_sent",
        session_id=session_id,
        recipients=recipients,
        resend_id=response.get("id"),
    )
    return {
        "session_id": session_id,
        "status": "sent",
        "recipients": ",".join(recipients),
    }


def schedule_post_completion_pipeline(
    session_id: str,
    *,
    learner_email: str | None = None,
) -> None:
    """Chain report build then email (called from complete_session)."""
    settings = get_settings()
    admin_email = settings.ADMIN_REPORT_EMAIL.strip() or None
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
    settings = get_settings()
    admin_email = settings.ADMIN_REPORT_EMAIL.strip() or None
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
