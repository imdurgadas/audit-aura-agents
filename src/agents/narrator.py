import os
import json
from datetime import datetime
from langchain_openai import ChatOpenAI
from langchain_core.prompts import PromptTemplate
from langchain_core.output_parsers import StrOutputParser
from src.state import GraphState
from src.logger import log_agent_action
from src.llm_config import get_llm

def narrator_node(state: GraphState) -> GraphState:
    """
    The Narrator Agent node. Generates and PERSISTS a comprehensive Evidence Report.
    """
    model_name = os.getenv("MODEL_NAME", "google/gemma-2b-it")
    llm = get_llm(model_name, temperature=0.7)
    
    incident_id = state.get("incident_id", "Unknown")
    logs = state.get("logs", [])
    full_logs_str = json.dumps(logs, indent=2)
    
    retry_count = state.get("retry_count", 0)
    validation_status = state.get("validation_status", "Unknown")
    
    # If it failed after retries, customize the prompt
    final_status = validation_status
    if validation_status == "Failed" and retry_count >= 3:
        final_status = "FAILED - Needs manual remediation"

    prompt = PromptTemplate(
        template="""You are a Senior Compliance Auditor and Forensic Expert.
        Generate a professional, high-fidelity 'Incident Evidence Report' in Markdown format.
        
        - Entity: {offending_entity}
        - Final Status: {final_status}
        
        Write the final report:
        """,
        input_variables=["incident_id", "logs_str", "evaluations", "severity", "remediation_action", "validation_status", "offending_entity", "change_ticket", "final_status", "retry_count"]
    )
    
    evals = state.get("evaluations", [])
    latest_eval = evals[-1] if evals else {}
    
    audit_type = latest_eval.get("Framework", "Internal")
    controls = ", ".join(latest_eval.get("MappedControls", ["Unknown"]))
    description = latest_eval.get("Thought", "Compliance violation detected.")
    
    first_log = logs[0] if logs else {}
    when_detected = first_log.get("timestamp", datetime.now().isoformat())

    chain = prompt | llm | StrOutputParser()
    
    try:
        narrative = chain.invoke({
            "incident_id": incident_id,
            "final_status": final_status,
            "audit_type": audit_type,
            "controls": controls,
            "description": description,
            "offending_entity": state.get("offending_entity", "Unknown"),
            "severity": state.get("severity", "Unknown"),
            "when_detected": when_detected,
            "remediation_action": state.get("remediation_action", "None"),
            "change_ticket": state.get("change_ticket_id", "None"),
            "retry_count": retry_count,
            "validation_status": state.get("validation_status", "Unknown"),
            "logs_str": full_logs_str
        })
        
        # Save the physical evidence file
        evidence_dir = "data/evidence"
        os.makedirs(evidence_dir, exist_ok=True)
        file_path = os.path.join(evidence_dir, f"{incident_id}.md")
        with open(file_path, "w") as f:
            f.write(narrative)
            
        log_agent_action("narrator", "Evidence Persisted", f"Full report saved to {file_path}")
        
    except Exception as e:
        narrative = f"Failed to generate narrative: {e}"
        log_agent_action("narrator", "Error", narrative)

    execution_entry = {
        "node": "narrator",
        "message": f"Compliance evidence report persisted for {incident_id}.",
        "timestamp": datetime.now().isoformat(),
        "details": {"file": f"data/evidence/{incident_id}.md"}
    }
        
    return {
        "narrative": narrative,
        "execution_log": [execution_entry]
    }
