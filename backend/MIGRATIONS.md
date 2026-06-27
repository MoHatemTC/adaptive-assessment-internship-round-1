# Database migrations

Supabase is the **single source of truth** for team development. Before authoring a new Alembic revision:

1. Run `alembic current` against the shared Supabase instance (not only local Postgres).
2. Ensure your new `down_revision` matches that head — do not renumber or fork history locally.
3. Keep migrations forward-only with a real `downgrade()`, and never re-create an existing enum/type.

## 2026-06: `0012_examiner_state_column` fork

Production Supabase was stamped at `0012_examiner_state_column` before that file existed in `main`. Diagram SVG rebuild was merged as a conflicting `0012_diagram_svg_rebuild`. Resolution:

- `0012_examiner_state_column` — restores the production revision (adds `examiner_state_json`).
- `0013_diagram_svg_rebuild` — diagram rebuild, child of `0012_examiner_state_column`.

After pulling this change, run `alembic upgrade head` once against Supabase; no manual stamping should be required.

## 2026-06: `0014_proctoring_status_column`

Adds `proctoring_status` (`not_started` / `active` / `stopped`) on `assessment_sessions` for platform-wide proctoring lifecycle (WP-2).

## 2026-06: `0015_memory_card_foreign_keys` (WP-3)

Links `code_memory_cards` and `voice_memory_cards` to `memory_cards` (and voice sessions) with FK constraints. Extension tables are **kept** — they store tool-specific evidence (sandbox results, communication signals) that the platform `memory_cards` row does not duplicate.

Run `python scripts/audit_db_normalization.py` before and after upgrade to verify row counts and orphan checks.

## Migration numbering (historical quirk)

Early sprint migrations use parallel `0001_*` roots (`0001_code`, `0001_voice`, `0001_mcq`, `0001_diagram`) that merge at `0003_platform_sessions`. There is no `0007_*` revision — apply order follows `down_revision` chains, not numeric prefixes. **Do not renumber** migrations already applied to Supabase; document new work as `0016_*`, `0017_*`, etc.

## Memory model (WP-3 audit)

| Table | Role |
|-------|------|
| `memory_cards` | Canonical cross-tool evidence card (written by `memory_agent` / evaluation layers) |
| `code_memory_cards` | Code-only extension: sandbox scores, test results, rubric feedback |
| `voice_memory_cards` | Voice-only extension: competency label, rubric + communication JSON |
| `diagram_responses` | Canonical diagram learner answers (`diagram_answers` removed in `0013`) |

Diagram, MCQ, and voice evaluation write to `memory_cards` via `run_memory_agent`; code writes platform + `code_memory_cards` in one transaction.
