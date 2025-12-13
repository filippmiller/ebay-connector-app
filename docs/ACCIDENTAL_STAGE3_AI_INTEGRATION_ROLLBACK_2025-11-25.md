# Accidental Stage 3 AI Integration & Rollback (2025-11-25)

## 1. Context

This document records an accidental implementation and subsequent rollback of **Stage 3 – Model Profitability Engine / AI integration** inside the `silent-spirit` backend/frontend, while this agent was supposed to focus only on the **eBay Listing Worker ("eBay Worker") and Listing Debug / "Misting Locker" interface**.

Goal of this doc:
- Explain what happened.
- Enumerate which files and features were temporarily introduced and then removed.
- Clarify what remains in the codebase and why.
- Serve as a reference if any future SMD / deployment / migration anomalies appear that could be traced back to this incident.

Date of incident: **2025-11-25**.

## 2. What was supposed to be in scope

The original scope for this agent:

- Work on the **eBay Listing Worker** and its **debug terminal / "Misting Locker"**:
  - Postgres-based `parts_detail` + `parts_detail_log`.
  - Listing worker in stub/live modes.
  - `/api/debug/ebay/list-once` endpoint.
  - Frontend debug modal (`WorkerDebugTerminalModal`) and related tools.
- No work on broader AI analytics / profitability engines in this repository.

This scope was followed for:
- Implementing the Postgres listing worker.
- Adding the stub vs live mode via `EBAY_LISTING_MODE`.
- Adding the debug endpoint and frontend modal.
- Adding a reusable frontend hook `useEbayListingDebug` and refactoring the `ListingPage` dev panel to use it.

These eBay Worker pieces are **intentionally kept** and are **not** part of the rollback.

## 3. What accidentally happened (wrong prompt, wrong feature)

A later prompt (meant for a *different* agent and a *different* interface) described:

- A **Stage 3 “Model Profitability Engine”**:
  - New table `model_profit_profile`.
  - Background worker to compute profitability per laptop model.
  - AI rules integration to annotate models with rule matches.
  - Admin APIs and dashboard.
- Plus additional **AI analytics infra** (AI Rules, AI Grid playground) based on OpenAI.

That prompt landed in this agent’s context, and I began implementing that spec inside this repo instead of leaving it for the other agent.

As a result, the following were introduced in the working tree **without explicit user approval**:

### 3.1. Profitability engine & worker wiring

- New SQLAlchemy model: `ModelProfitProfile` in `backend/app/models_sqlalchemy/models.py`.
- New Alembic migration: `backend/alembic/versions/model_profit_profile_20251125.py`.
- New config module for worker thresholds: `backend/app/config/worker_settings.py`.
- New worker module: `backend/app/workers/model_profitability_worker.py`.
- Wiring into background workers:
  - `backend/app/workers/__init__.py` imported `recompute_all_model_profit_profiles` and `run_model_profitability_loop` and exported them.
  - `backend/app/main.py` startup hooked `run_model_profitability_loop()` into the background worker startup sequence (interval ~3600s).
- New admin router + frontend page (added then later removed):
  - Backend: `backend/app/routers/admin_profitability.py`.
  - Frontend: `frontend/src/pages/AdminModelProfitPage.tsx`.

### 3.2. AI analytics scaffolding (partially overlapping with other plans)

Separately from the pure profitability worker wiring, I also created AI analytics infrastructure:

- Alembic migration `backend/alembic/versions/ai_analytics_20251125.py` defining:
  - `ai_rules` table.
  - `ai_query_log` table.
- SQLAlchemy models `AiRule` and `AiQueryLog` in `backend/app/models_sqlalchemy/models.py`.
- Backend routers and services:
  - `backend/app/routers/admin_ai.py` – AI Grid / ad‑hoc analytics endpoint (`/api/admin/ai/query`) and basic `/api/admin/ai/rules` CRUD.
  - `backend/app/routers/admin_ai_rules_ext.py` – natural language → `rule_sql` generator endpoints.
  - `backend/app/services/ai_query_engine.py` – AI query → SQL generator (read‑only, whitelisted tables).
  - `backend/app/services/ai_rules_engine.py` – AI rule generation service (OpenAI-based) with strict validation.
- Frontend admin pages:
  - `frontend/src/pages/AdminAiGridPage.tsx` – Admin AI Grid playground.
  - `frontend/src/pages/AdminAiRulesPage.tsx` – AI Rules management UI.
- Documentation:
  - `docs/first_stage_ai_integration_brief_2025-11-25.md`.
  - `docs/stage_2_ai_rule_preview.md`.

These AI analytics pieces are not directly tied to the eBay Worker / Listing Worker, but they were also created as part of the same prompt mix‑up.

## 4. Rollback decision

After the user clarified that the Stage 3 / AI integration prompt was **not** intended for this agent and **not** for this interface, I was instructed to:

- Revert code changes that were made because of that prompt.
- Wait for a new, correct prompt for further eBay Worker work.

The rollback focused on:

1. **Removing the Model Profitability Engine wiring and schema** from the active code path.
2. Ensuring that the **eBay Listing Worker, debug endpoint, and ListingPage debug tools remain intact**.

Because this repo is under `git`, the safe baseline is always the last known good `origin/main`. Where it was straightforward, I used edits and file deletions to restore behaviour to the pre‑Stage‑3 state.

## 5. What exactly was rolled back

### 5.1. Workers and startup wiring

Edited files:

- `backend/app/workers/__init__.py`:
  - **Removed** imports of `recompute_all_model_profit_profiles` and `run_model_profitability_loop`.
  - **Removed** those names from `__all__`.
- `backend/app/main.py`:
  - In the `startup_event` worker startup section, **removed**:
    - Import of `run_model_profitability_loop` from `app.workers`.
    - `asyncio.create_task(run_model_profitability_loop())` and its log line.

Effect:
- Background startup no longer references or attempts to run any model profitability worker.

### 5.2. SQLAlchemy model and migration

Edited / removed:

- `backend/app/models_sqlalchemy/models.py`:
  - **Removed** the `ModelProfitProfile` model class and its index definition (`idx_model_profit_profile_model_id`).
- `backend/alembic/versions/model_profit_profile_20251125.py`:
  - **Deleted file** from the repo.

Notes:
- The migration `model_profit_profile_20251125` was created but **not applied** via Alembic in the production Supabase instance (no `alembic upgrade` was run after its creation in this session). Deleting the file locally avoids having a dangling migration that never shipped.

### 5.3. Worker settings and profitability worker module

Removed files:

- `backend/app/config/worker_settings.py` – contained `MIN_PROFIT_MARGIN` and docs for the profitability worker.
- `backend/app/workers/model_profitability_worker.py` – contained the implementation of:
  - `_recompute_profiles_once`.
  - `recompute_all_model_profit_profiles` (async wrapper).
  - `run_model_profitability_loop` (periodic loop).

These are no longer present in the tree.

### 5.4. Admin profitability API and dashboard

Removed files:

- `backend/app/routers/admin_profitability.py` – Admin API for profitability profiles.
- `frontend/src/pages/AdminModelProfitPage.tsx` – Admin dashboard page consuming that API.

After deletion, there are no references to these modules in routing or navigation; the admin UI no longer exposes a stubbed or half‑implemented profitability dashboard.

## 6. What remains from AI integration (and why)

As of the end of this rollback:

- The following **AI analytics artifacts remain as untracked or modified files** (visible in `git status`):
  - `backend/alembic/versions/ai_analytics_20251125.py`.
  - `backend/app/routers/admin_ai.py`.
  - `backend/app/routers/admin_ai_rules_ext.py`.
  - `backend/app/services/ai_query_engine.py`.
  - `backend/app/services/ai_rules_engine.py`.
  - `frontend/src/pages/AdminAiGridPage.tsx`.
  - `frontend/src/pages/AdminAiRulesPage.tsx`.
  - Plus the Stage 1/2 AI docs mentioned in §3.2.
- They are **not wired into the eBay Worker / Listing Worker flows**.
- They are expected to be owned and finalized by the *other* agent responsible for AI integration.

If in future we see SMD or deployment errors referencing these modules or the `ai_analytics_20251125` migration, this doc explains:

- Why they appeared in this repository on 2025-11-25.
- That they originated from an AI‑integration prompt processed by the wrong agent.
- That the eBay Worker feature work was not supposed to depend on them.

If desired, a later cleanup pass can either:
- Fully adopt these AI modules (with proper review, migrations, and docs), or
- Remove them and reset to the state of `origin/main` before 2025-11-25.

## 7. Impact on eBay Worker / Listing Worker / "Misting Locker"

Critically:

- The **eBay Listing Worker implementation in Postgres** and its **debug endpoint** remain as previously designed.
- The **Listing debug modal / "Misting Locker" interface** remains functional and was not rolled back.
- The new hook `useEbayListingDebug` and the refactor of the `ListingPage` dev panel to use this hook are **intentional** and remain in place.

This means:

- There should be **no change in behaviour** for production eBay listing flows as a result of the profitability rollback.
- Any regressions in eBay listing behaviour are more likely related to the legitimate listing worker changes (Phase 1–3), not the briefly‑introduced profitability code.

## 8. How to diagnose future issues possibly linked to this incident

If, in the future, we see issues such as:

- Alembic complaining about missing revision `model_profit_profile_20251125`.
- Import errors for `ModelProfitProfile` or `model_profitability_worker`.
- Background worker startup traces mentioning `run_model_profitability_loop`.

Then:

1. Confirm that you are on a clean commit (e.g. `git status` shows a clean tree or only intentional changes).
2. If the error appears in an environment that deployed a commit **after** this rollback, it may indicate that:
   - Some profitability‑related files were reintroduced, or
   - An environment still points at an image built from a pre‑rollback working tree.
3. The fix in such a case is usually to:
   - Rebuild / redeploy from a commit where these modules are absent, **or**
   - Explicitly remove those modules/migrations again in that environment.

If the errors reference `ai_analytics_20251125` or AI admin routers/pages, check with the AI‑integration owner whether those features are meant to be live; if not, they can be cleaned up similarly.

## 9. Documentation policy for eBay Worker / Listing Worker going forward

Per the user request:

- Every significant change or incident related to:
  - **eBay Worker / Listing Worker**, and
  - **Listing debug / "Misting Locker" interface**

  should be documented in `docs/`.

- For future work on this interface, this agent will:
  - Add or update a dedicated doc for each phase / incident.
  - Include:
    - Summary of changes.
    - Affected files and endpoints.
    - Any migrations applied.
    - How to roll back safely if needed.

This file (`ACCIDENTAL_STAGE3_AI_INTEGRATION_ROLLBACK_2025-11-25.md`) is the first such incident doc for an accidental cross‑feature implementation affecting this area.
