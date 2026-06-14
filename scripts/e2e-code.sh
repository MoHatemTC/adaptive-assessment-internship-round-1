#!/usr/bin/env bash
# End-to-end verification for the E2B code feature (timed session flow).
# Usage: ./scripts/e2e-code.sh [API_BASE_URL]
set -euo pipefail

API_BASE="${1:-http://localhost:8000}"

echo "==> Health"
health=$(curl -sf "${API_BASE}/health")
echo "${health}" | python3 -m json.tool
echo "${health}" | python3 -c "import sys,json; d=json.load(sys.stdin); assert d.get('db') is True, 'db not healthy'"

echo ""
echo "==> Start timed session"
session=$(curl -sf -X POST "${API_BASE}/api/v1/code/sessions" \
  -H "Content-Type: application/json" \
  -d '{
    "name": "E2E Runner",
    "skills": ["Python"],
    "experience_level": "intermediate",
    "preferred_domains": ["Programming"],
    "learning_objectives": ["automated E2E test"]
  }')
session_id=$(echo "${session}" | python3 -c "import sys,json; print(json.load(sys.stdin)['session_id'])")
challenge_id=$(echo "${session}" | python3 -c "import sys,json; print(json.load(sys.stdin)['challenges'][0]['challenge_id'])")
title=$(echo "${session}" | python3 -c "import sys,json; print(json.load(sys.stdin)['challenges'][0]['title'])")
echo "Session ${session_id}, challenge #${challenge_id}: ${title}"

SOLUTION='def solution(s: str) -> str:\n    return s[::-1]'

echo ""
echo "==> Run (visible tests only)"
run=$(curl -sf -X POST "${API_BASE}/api/v1/code/runs" \
  -H "Content-Type: application/json" \
  -d "$(python3 -c "import json; print(json.dumps({
    'session_id': '${session_id}',
    'challenge_id': ${challenge_id},
    'submitted_code': '${SOLUTION}'
  }))")")
echo "${run}" | python3 -m json.tool | head -20

echo ""
echo "==> Submit for grading (E2B + evaluation)"
submit=$(curl -sf -X POST "${API_BASE}/api/v1/code/submissions" \
  -H "Content-Type: application/json" \
  -d "$(python3 -c "import json; print(json.dumps({
    'challenge_id': ${challenge_id},
    'session_id': '${session_id}',
    'submitted_code': '${SOLUTION}'
  }))")")
submission_id=$(echo "${submit}" | python3 -c "import sys,json; d=json.load(sys.stdin); print(d['id'])")
passed=$(echo "${submit}" | python3 -c "import sys,json; d=json.load(sys.stdin); print(d.get('passed'))")
score=$(echo "${submit}" | python3 -c "import sys,json; d=json.load(sys.stdin); print(d.get('evaluation_score') or int((d.get('score') or 0)*100))")

echo "Submission #${submission_id}: passed=${passed}, score=${score}"

echo ""
echo "==> Fetch submission by id"
curl -sf "${API_BASE}/api/v1/code/submissions/${submission_id}" | python3 -m json.tool | head -40

echo ""
echo "==> Session submissions"
curl -sf "${API_BASE}/api/v1/code/sessions/${session_id}/submissions" | python3 -m json.tool | head -25

echo ""
echo "==> Admin code config (read)"
curl -sf "${API_BASE}/api/v1/admin/code-config" | python3 -m json.tool | head -20

echo ""
echo "E2E timed code flow completed successfully."
