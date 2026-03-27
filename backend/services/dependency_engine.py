from typing import List

# Dependency Map: tracks what fields rely on a given memory key
DEPENDENCY_MAP = {
    "income": ["eligibility", "emi_capacity"],
    "co_applicant": ["combined_income"],
    "co_applicant_income": ["combined_income", "eligibility"],
    "loan_amount": ["emi", "eligibility"],
    "tenure": ["emi", "eligibility"],
}

def track_dependencies(updated_keys: List[str]) -> List[str]:
    """
    When a memory is updated, identify dependent fields and return notes
    to append to the context/response so the system is aware they are stale.
    """
    stale_fields = set()
    notes = []
    
    for key in updated_keys:
        if key in DEPENDENCY_MAP:
            for dep in DEPENDENCY_MAP[key]:
                stale_fields.add(dep)
                
    if stale_fields:
        fields_str = ", ".join(stale_fields)
        notes.append(f"Dependencies flagged for recalculation: {fields_str}")
        
    return notes
