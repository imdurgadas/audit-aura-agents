import os
import json
from datetime import datetime
from langchain_openai import ChatOpenAI
from langchain_core.prompts import PromptTemplate
from langchain_core.output_parsers import StrOutputParser
from src.state import GraphState
from src.logger import log_agent_action

def narrator_node(state: GraphState) -> GraphState:
    """
    The Narrator Agent node. Generates and PERSISTS a comprehensive Evidence Report.
    """
    llm = ChatOpenAI(model="google/gemma-4-e4b", temperature=0.7)
    
    retry_count = state.get("retry_count", 0)
    validation_status = state.get("validation_status", "Unknown")
    
    # If it failed after retries, customize the prompt
    final_status = validation_status
    if validation_status == "Failed" and retry_count >= 3:
        final_status = "FAILED - Needs manual remediation"

    prompt = PromptTemplate(
        template="""You are a Senior Compliance Auditor and Forensic Expert.
        Generate a professional, high-fidelity 'Incident Evidence Report' in Markdown format.
        
        CRITICAL: Do NOT trim the logs. Use the full technical data provided.
        
        If the Validation Status is 'FAILED - Needs manual remediation', emphasize this in the title and summary, indicating that autonomous remediation was exhausted.
        
        The report must include:
        1. # Incident Report: {incident_id}
        2. ## Overall Status: {final_status}
        3. ## Summary
        4. ## Detection & Identification (Labels: Severity, Platform, Entity)
        5. ## Auditor Reasoning & Compliance Gaps
        6. ## Remediation Actions & Change Ticket: {change_ticket}
        7. ## Validation Proof & Final Conclusion (Attempts: {retry_count})
        8. ## Raw Forensic Logs (DUMP FULL JSON HERE)
        
        Technical Context:
        - Logs: {logs_str}
        - Evaluations: {evaluations}
        - Severity: {severity}
        - Remediation: {remediation_action}
        - Validation: {validation_status}
        - Entity: {offending_entity}
        - Final Status: {final_status}
        
        Write the final report:
        """,
        input_variables=["incident_id", "logs_str", "evaluations", "severity", "remediation_action", "validation_status", "offending_entity", "change_ticket", "final_status", "retry_count"]
    )
    
    chain = prompt | llm | StrOutputParser()
    
    try:
        narrative = chain.invoke({
            "incident_id": incident_id,
            "logs_str": full_logs_str,
            "evaluations": state.get("evaluations", []),
            "severity": state.get("severity", "Unknown"),
            "remediation_action": state.get("remediation_action", "None"),
            "validation_status": state.get("validation_status", "Unknown"),
            "offending_entity": state.get("offending_entity", "Unknown"),
            "change_ticket": state.get("change_ticket_id", "None"),
            "final_status": final_status,
            "retry_count": retry_count
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
