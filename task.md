# Execution Plan: Advanced Memory Intelligence

- [x] **Database Upgrades**: Update `backend/db.py` with `affects`, `used_for`, and `relations` JSONB arrays.
- [x] **Create `services/memory_connections.py`**: Rule-based mapping layer running pre-upsert mapping `affects` arrays.
- [x] **Create `services/dependency_engine.py`**: Tracking engine tagging cascaded dependencies on memory updates.
- [x] **Create `services/consistency.py`**: Logical conflict detector returning warning arrays.
- [x] **Update `backend/temporal.py`**: Add lightweight labels generator (`"today"`, `"recently"`, `"earlier"`).
- [x] **Upgrade `backend/context_builder.py`**: Integrate temporal labels, cap strict limit at 5, order by importance score.
- [x] **Upgrade `backend/memory_engine.py`**: Modify the `calculate_importance()` math formula.
- [x] **Upgrade `backend/main.py`**:
  - Implement soft clarification for conf < 0.7 without crashing response explicitly.
  - Return dynamic memory payload (`used_memory`, `reason`, `warnings`, `suggestions`).
  - Route extracted facts through the `memory_connections` layer BEFORE inserting to DB.
