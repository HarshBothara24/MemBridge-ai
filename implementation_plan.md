# Importance Scoring & Relevance Ranking Implementation Plan

This plan addresses Feature 2: implementing the mathematical `importance` score formula, tracking read accesses, and returning the top-K facts so we don't overwhelm the LLM with all memories.

## User Review Required

> [!IMPORTANT]
> The prompt specified the following formula: `importance = w1 * category_weight + w2 * recency + w3 * frequency + w4 * access_count`
> I plan to define the weights and proxies as follows:
> - **Category Weight (`w1`)**: Financial = 1.0, Profile = 0.8, Preference = 0.5, Event = 0.3.
> - **Recency (`w2`)**: Calculated as `1.0 / (1.0 + days_since_updated)`. Diminishes smoothly over time.
> - **Frequency (`w3`)**: Calculated as `access_count / (days_since_created + 1)`.
> - **Access Count (`w4`)**: Normalized raw number of times accessed.
> To handle the constraint to "Store and update this dynamically", I will execute a background `UPDATE` mathematically recalculating everyone's importance score instantly whenever a memory is retrieved.

## Proposed Changes

### Database Schema (`backend/db.py`)
- **[MODIFY]** `backend/db.py`
  - Safely add new tracking columns to the `memory_facts` table:
    ```sql
    ALTER TABLE memory_facts ADD COLUMN IF NOT EXISTS access_count INTEGER DEFAULT 0;
    ALTER TABLE memory_facts ADD COLUMN IF NOT EXISTS last_accessed_at TIMESTAMP DEFAULT NOW();
    ```

### Scoring Logic (`backend/memory_engine.py`)
- **[MODIFY]** `backend/memory_engine.py`
  - **`calculate_importance`**: Introduce a private python method measuring `w1 * category + w2 * recency + w3 * freq + w4 * access`.
  - **Tracking on Retrieval**: Update `get_facts_by_keys` and `get_active_facts` to increment `access_count` on all fetched rows, update `last_accessed_at`, and recalculate the `importance_score`. 
  - **Ranking (Top-K)**: Introduce a `get_relevant_facts(user_id, intent_keys, limit=10)` method. This strictly orders the results by `importance_score DESC` and guarantees we only inject the most critically relevant memories to the agent context.

### Inference Layer (`backend/main.py`)
- **[MODIFY]** `backend/main.py`
  - In our `/chat` and `/chat/stream` endpoints, replace direct `get_facts_by_keys` with the new Top-K `get_relevant_facts(..., limit=8)`. This satisfies the constraint: "Retrieve and inject *only relevant* memory".

## Open Questions

1. **Top-K Limit:** I am planning to cap the memory context to the top `8` most mathematically relevant facts. Do you want a different explicit cap for the context limit?
2. **Weights Selection:** Are you okay with the generic decimal weights I've outlined above for the categories, or do you have a specific preference (e.g., setting Financial to 2.0)?

## Verification Plan

### Automated Tests
1. Add a fact and fetch it.
2. Read the database directly to confirm `access_count` increments from 0 to 1, and the `importance_score` gets recomputed dynamically.
3. Check the prompt context length limits to ensure we are successfully slicing the memory context rather than injecting indiscriminate tables.
