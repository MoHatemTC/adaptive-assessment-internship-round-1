"""Re-export shared proctoring contracts for feature-local imports."""

from app.shared.schemas.proctoring import (
    IdentityVerifyRequest,
    IdentityVerifyResponse,
    ProctoringEventCreate,
    ProctoringEventRead,
    ProctoringPolicy,
    ProctoringSeverity,
    ProctoringEventType,
    SessionIntegritySummary,
    VerificationStatus,
)

__all__ = [
    "IdentityVerifyRequest",
    "IdentityVerifyResponse",
    "ProctoringEventCreate",
    "ProctoringEventRead",
    "ProctoringEventType",
    "ProctoringPolicy",
    "ProctoringSeverity",
    "SessionIntegritySummary",
    "VerificationStatus",
]
