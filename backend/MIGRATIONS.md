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
