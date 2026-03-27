# Memory System Advanced Intelligence Upgrade Plan

This plan outlines a modular, non-destructive upgrade to evolve the current system from a "memory storage" engine into a "connected, reasoning-aware" memory architecture without introducing vector databases or extra LLM latency.

## User Review Required

> [!IMPORTANT]
> The prompt requires `clarification` responses when a fact has `< 0.7` confidence.
> This will essentially "short-circuit" the standard LLM chat completion. If an extracted fact has low confidence, the API will instantly return the `clarification` question instead of generating an LLM response based on the uncertain facts. Please confirm if this immediate short-circuiting behavior is acceptable for the user experience.

## Proposed Changes

### Database Upgrades (`backend/db.py`)
- **[MODIFY]** `backend/db.py`
  - Safely execute `ALTER TABLE memory_facts` commands within `init_db()` to append the new metadata columns: `affects` (JSONB), `used_for` (JSONB), and `relations` (JSONB).

### New Services Layer (`backend/services/`)
- **[NEW]** `backend/services/memory_connections.py`
  - Expose `attach_relationships(fact)`. Applies a static rule-base (e.g., `income` automatically flags `["loan_eligibility", "emi_capacity"]` in the `affects` column). Will be injected directly between fact extraction and DB upserting.
- **[NEW]** `backend/services/dependency_engine.py`
  - Expose `track_dependencies(updated_keys)`. Determines which downstream values become "stale" due to an updated memory (e.g., updating `co_applicant` dynamically flags `combined_income` as needing recalculation). These notes will be attached to the memory context.
- **[NEW]** `backend/services/consistency.py`
  - Expose `detect_conflicts(extracted_facts, active_profile)`. Runs logic gates (e.g., `extracted income < 40k` AND `requested loan > 10M` = **Warning**). This engine outputs raw warning strings that funnel directly into the API response schema.

### Core Logic Upgrades
- **[MODIFY]** `backend/memory_engine.py`
  - **Scoring Replacement**: Tweak `calculate_importance()` to follow the precise formula: `(0.5 * category) + (0.3 * recency) + (0.2 * min(access_count/5, 1))`.
- **[MODIFY]** `backend/context_builder.py`
  - **Temporal Phrasing**: Integrate the `temporal.py` recency calculator to convert bare timestamps into spoken phrases within the synthesized prompt (e.g., `"You mentioned today your income is 10L"` instead of `"Income: 10L"`).
  - Limit the builder explicitly to 5-6 memory items constraint.
- **[MODIFY]** `backend/temporal.py`
  - Export a lightweight `compute_recency_label(timestamp)` that buckets times into `"today"`, `"recently"`, and `"earlier"`.

### API & Response Modifications (`backend/main.py`)
- **[MODIFY]** `backend/main.py`
  - **Confidence Filter**: Add a gatekeeper post-extraction. If `confidence < 0.7`, abort the DB upsert, abort the LLM generation, and return a `ChatResponse` containing just the `"clarification"` property.
  - **Response Payload Changes**: Augment `ChatRequest`/`ChatResponse` models to strictly return the new `warnings` (from Consistency Engine), `used_memory` (keys injected into the prompt), and `reason` trackers.
  - **Proactive Suggestions**: Weave explicit rules (e.g., `has_co_applicant` -> `suggest enhanced eligibility`) into the `suggestions` response pipeline.

## Verification Plan

### Automated Tests
1. **Schema Integrity:** Verify database runs cleanly with old data alongside the new JSONB arrays.
2. **Confidence Lockout:** Inject a fuzzy message ("maybe I make 10 dollars"), force the extractor to give it `<0.7`, and verify the API returns the strict `clarification` payload without hallucinating a response.
3. **Consistency Warning:** Intentionally trigger an income/loan amount paradox to verify the `warnings` array populates properly in the response JSON.
