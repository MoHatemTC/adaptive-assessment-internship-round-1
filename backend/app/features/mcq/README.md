# MCQ Feature

## Overview

The MCQ feature provides a minimal end-to-end vertical slice for multiple-choice assessment questions.

It allows the examiner agent or backend to present an MCQ question, receive the learner answer, grade it objectively against the correct option, and return or store the score silently.

## Sprint 1 Scope

This sprint focuses on a minimal working MCQ slice:

1. Define MCQ data models.
2. Define request and response schemas.
3. Expose FastAPI routes for MCQ.
4. Implement MCQ grading logic.
5. Provide an MCQ LangChain tools for agent integration.
6. Build a basic Next.js MCQ card component.
7. Add grading + DB persistence + tool contract.

## Files
backend/app/features/mcq/models.py 
backend/app/features/mcq/schemas.py
backend/app/features/mcq/api.py 
backend/app/features/mcq/service.py
backend/app/features/mcq/tool.py 
backend/app/features/mcq/README.md 
backend/migrations/versions/0001_mcq.py 
backend/tests/features/test_mcq.py
frontend/src/features/mcq/McqCard.tsx