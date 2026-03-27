# Feature 2 Execution: Importance Scoring & Ranker

- [x] Add `access_count` and `last_accessed_at` columns to the `memory_facts` schema in `db.py`.
- [x] Implement `calculate_importance(fact)` algorithm in `memory_engine.py`.
- [x] Update `get_active_facts` and `get_facts_by_keys` to dynamically update read contexts (incrementing access count and recalculating importance).
- [x] Add `get_relevant_facts` in `memory_engine.py` to fetch explicitly the Top-K facts by importance score.
- [x] Replace naive fetching in `main.py` to utilize `get_relevant_facts(..., limit=8)` for context injection.
- [x] **Bonus**: Update the LLM System prompts in `context_builder.py` to explicitly default to English, only use Hindi if spoken to, act naturally, and optionally explain reasoning when citing memory facts.
