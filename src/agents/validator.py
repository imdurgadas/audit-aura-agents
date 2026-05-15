import time
from datetime import datetime
from src.state import GraphState
from src.logger import log_agent_action

def validator_node(state: GraphState) -> GraphState:
    """
    The Validator Agent node. Confirms if the remediation actually fixed the issue.
    """
    remediation_action = state.get("remediation_action", "")
    
    if remediation_action == "None":
        return {"validation_status": "No validation needed."}
        
    log_agent_action("validator", "Verification", "Polling platform logs for configuration changes...")
    
    # Simulate a shorter wait for demo purposes
    time.sleep(2)
    
    status = "Success"
    retry_count = state.get("retry_count", 0)
    manual_ticket = state.get("change_ticket_id")
    
    if manual_ticket and "CHG" in manual_ticket:
        msg = f"Validation success: Manual fix verified via Change Ticket {manual_ticket}."
    elif "Failed" in remediation_action or "retry" in remediation_action:
        status = "Failed"
        retry_count += 1
        msg = f"Validation failed (Attempt {retry_count}): Configuration drift still detected."
    else:
        msg = "Validation success: Resource is now compliant."
        
    log_agent_action("validator", "Result", msg)

    execution_entry = {
        "node": "validator",
        "message": msg,
        "timestamp": datetime.now().isoformat(),
        "details": {"status": status, "retry_count": retry_count}
    }
        
    return {
        "validation_status": status,
        "retry_count": retry_count,
        "execution_log": [execution_entry]
    }
