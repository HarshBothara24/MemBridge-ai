from typing import Dict, Any

# Rule-based mappings
CONNECTIONS = {
    "income": {
        "affects": ["loan_eligibility", "emi_capacity"]
    },
    "co_applicant": {
        "affects": ["combined_income"]
    },
    "co_applicant_income": {
        "affects": ["combined_income", "emi_capacity"]
    },
    "loan_amount": {
        "affects": ["emi"]
    },
    "property_value": {
        "affects": ["loan_eligibility", "ltv_ratio"]
    }
}

def attach_relationships(fact: Dict[str, Any]) -> Dict[str, Any]:
    """
    Attach relationships to each memory.
    Runs AFTER extraction and BEFORE DB insert.
    """
    key = fact.get("key", "").lower()
    
    mapping = CONNECTIONS.get(key, {})
    
    fact["affects"] = mapping.get("affects", [])
    fact["used_for"] = mapping.get("used_for", [])
    fact["relations"] = mapping.get("relations", [])
    
    return fact
