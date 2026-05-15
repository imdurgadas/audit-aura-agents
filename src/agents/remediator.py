import subprocess
import os
from datetime import datetime
from src.state import GraphState
from src.logger import log_agent_action

def remediator_node(state: GraphState) -> GraphState:
    """
    The Remediation Agent node. Executes scripts to fix violations.
    """
    evaluations = state.get("evaluations", [])
    if not evaluations:
        return {"remediation_action": "None"}
        
    latest_eval = evaluations[-1]
    recommended_action = latest_eval.get("RecommendedAction", "close_s3_bucket.py")
    
    if recommended_action == "None":
        return {"remediation_action": "None"}

    script_path = os.path.join(os.getcwd(), "scripts", recommended_action)
    action_taken = "None"
    status = "Success"
    
    if os.path.exists(script_path):
        try:
            result = subprocess.run(["python", script_path], capture_output=True, text=True, check=True)
            msg = f"Applied fix via {recommended_action}. Output: {result.stdout.strip()[:100]}..."
            log_agent_action("remediator", "Fix Applied", msg)
            action_taken = f"Executed {recommended_action} successfully."
        except subprocess.CalledProcessError as e:
            msg = f"Failed to apply fix via {recommended_action}: {e.stderr}"
            log_agent_action("remediator", "Execution Failed", msg)
            action_taken = f"Failed to execute {recommended_action}."
            status = "Failed"
    else:
        msg = f"Script {recommended_action} not found. Mocking success."
        log_agent_action("remediator", "Mock Fix", msg)
        action_taken = f"Mock Executed {recommended_action}"

    execution_entry = {
        "node": "remediator",
        "message": msg,
        "timestamp": datetime.now().isoformat(),
        "details": {"script": recommended_action, "status": status}
    }
        
    return {
        "remediation_action": action_taken,
        "execution_log": [execution_entry]
    }
