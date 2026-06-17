#!/usr/bin/env python3
"""Exercise the full adaptive loop against a running backend with a live LLM.

Usage (from repo root, backend container running with valid LITELLM_* env):

    docker exec masaar-assessment-platform-backend-1 \\
      python scripts/try_live_adaptive_cycle.py

Requires E2B_API_KEY and working LITELLM credentials in the backend environment.
"""

from __future__ import annotations

import json
import sys
import uuid
import urllib.error
import urllib.request

API_BASE = "http://localhost:8000"
FIXTURE_PATH = "/app/tests/fixtures/code/reverse_string.json"


def _post(path: str, payload: dict) -> dict:
    req = urllib.request.Request(
        f"{API_BASE}{path}",
        data=json.dumps(payload).encode(),
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    with urllib.request.urlopen(req, timeout=180) as resp:
        return json.loads(resp.read())


def main() -> int:
    fixture = json.load(open(FIXTURE_PATH))
    session_id = str(uuid.uuid4())

    print("1) Probing LLM connectivity…")
    from app.core.llm import test_llm_connection

    if not __import__("asyncio").run(test_llm_connection()):
        print("   FAIL — LITELLM is not reachable. Check LITELLM_API_KEY / LITELLM_BASE_URL.")
        return 1
    print("   OK")

    print("2) Creating challenge with test cases…")
    challenge = _post(
        "/api/v1/code/challenges",
        {
            "title": fixture["title"] + " (live cycle)",
            "description": fixture["description"],
            "starter_code": fixture["starter_code"],
            "language": "python",
            "time_limit_seconds": 20,
            "test_cases": fixture["test_cases"],
        },
    )
    print(f"   challenge_id={challenge['id']}")

    print("3) POST /api/v1/code/adaptive-submit (E2B + LLM layers 1–4)…")
    try:
        result = _post(
            "/api/v1/code/adaptive-submit",
            {
                "challenge_id": challenge["id"],
                "session_id": session_id,
                "assessment_id": "live-cycle-smoke",
                "submitted_code": fixture["correct_solution"],
                "question_index": 0,
                "difficulty": "intermediate",
            },
        )
    except urllib.error.HTTPError as exc:
        body = exc.read().decode()
        print(f"   HTTP {exc.code}: {body[:600]}")
        return 1

    contract = result.get("contract", {})
    print("   submission_id:", result.get("submission_id"))
    print("   sandbox passed:", result.get("passed"), "score:", result.get("score"))
    print("   contract.tool_type:", contract.get("tool_type"))
    print("   contract.difficulty:", contract.get("difficulty"))
    print("   contract.focus_dimension:", contract.get("focus_dimension"))
    print("   contract.stop:", contract.get("stop"))
    print("   contract.memory_summary:", contract.get("memory_summary", "")[:120])
    print("\nLive adaptive cycle completed successfully.")
    return 0


if __name__ == "__main__":
    sys.path.insert(0, "/app")
    raise SystemExit(main())
