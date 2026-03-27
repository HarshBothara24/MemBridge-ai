from typing import Dict, Any, List
import re

def detect_conflicts(extracted_facts: List[Dict[str, Any]], active_profile: Dict[str, Any]) -> List[str]:
    """
    Detect logical conflicts between newly extracted facts and existing profile.
    e.g. low income + high loan request.
    """
    warnings = []
    
    # We combine current facts and newly extracted facts to form a "prospect" profile
    prospect = active_profile.copy()
    for f in extracted_facts:
        prospect[f["key"]] = f["value"]

    # Try mapping to float for comparisons
    def get_num(key: str) -> float:
        val = prospect.get(key)
        if isinstance(val, dict):
            val = val.get("value")
        if val is None:
            return 0.0
        if isinstance(val, (int, float)):
            return float(val)
        try:
            cleaned = re.sub(r'[^\d.]', '', str(val))
            return float(cleaned) if cleaned else 0.0
        except:
            return 0.0

    income = get_num("income")
    loan_amount = get_num("loan_amount")
    
    # Conflict Rule 1: Income vs Loan Amount 
    if income > 0 and loan_amount > 0:
        if loan_amount > income * 60:
            warnings.append(f"Warning: High loan request relative to recorded income.")
            
    # Conflict Rule 2: Co-applicant mismatch
    co_app_status = prospect.get("co_applicant")
    # If they clearly say NO co-applicant, but a co_applicant_income exists
    if isinstance(co_app_status, dict):
        co_app_status = str(co_app_status.get("value", "")).lower()
    else:
        co_app_status = str(co_app_status).lower()

    if co_app_status in ["no", "none", "false"] and get_num("co_applicant_income") > 0:
        warnings.append("Conflict: Co-applicant income is recorded, but co-applicant presence is listed as 'No'.")

    return warnings
