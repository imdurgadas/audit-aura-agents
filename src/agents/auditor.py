import os
import json
import chromadb
from datetime import datetime
from typing import Dict, Any, List
from langchain_openai import ChatOpenAI
from langchain_core.prompts import PromptTemplate
from langchain_core.output_parsers import JsonOutputParser
from pydantic import BaseModel, Field
from src.state import GraphState
from src.logger import log_agent_action
from src.registry import upsert_incident

# Configure for LM Studio
os.environ["OPENAI_API_BASE"] = "http://127.0.0.1:1234/v1"
os.environ["OPENAI_API_KEY"] = "lm-studio"

class IndividualEvaluation(BaseModel):
    LogIndex: int = Field(description="The index of the log in the provided list.")
    Thought: str = Field(description="Step-by-step reasoning explaining the compliance check.")
    ViolationDetected: bool = Field(description="True if a violation was detected.")
    Severity: str = Field(description="Severity: 'None', 'Low', 'Medium', 'Critical'.")
    Framework: str = Field(description="Compliance Framework: 'SOC2', 'HIPAA', 'C5', or 'Internal'.")
    MappedControls: List[str] = Field(description="List of EXACT control IDs identified (e.g., 'CC6.1', 'AC-2').")
    RecommendedAction: str = Field(description="Remediation script filename, or 'None'.")

class BulkAuditorEvaluation(BaseModel):
    Evaluations: List[IndividualEvaluation] = Field(description="A list of evaluations for each log.")

def get_relevant_controls(logs_text: str) -> str:
    """Queries ChromaDB for controls relevant to the entire batch of logs."""
    client = chromadb.PersistentClient(path="data/chroma_db")
    collection = client.get_or_create_collection(name="compliance_controls")
    results = collection.query(query_texts=[logs_text], n_results=5)
    
    controls = []
    if results and results['documents']:
        for doc in results['documents'][0]:
            controls.append(doc)
    return "\n".join(controls)

def perform_bulk_audit(logs: List[Dict[str, Any]]) -> List[IndividualEvaluation]:
    """
    Utility function to perform a bulk audit using the LLM.
    Used by the API to efficiently process logs before splitting into incidents.
    """
    llm = ChatOpenAI(model="google/gemma-4-e4b", temperature=0.1)
    parser = JsonOutputParser(pydantic_object=BulkAuditorEvaluation)
    
    scripts_dir = os.path.join(os.getcwd(), "scripts")
    available_scripts = [f for f in os.listdir(scripts_dir) if f.endswith(".py")] if os.path.exists(scripts_dir) else []
    scripts_list_str = ", ".join(available_scripts) if available_scripts else "None"
    
    prompt = PromptTemplate(
        template="""You are an expert Cloud Compliance Auditor.
        Review the following list of logs against the provided compliance controls.
        
        Use ReAct reasoning to evaluate EACH log individually.
        
        CRITICAL INSTRUCTIONS:
        1. If NO violation is detected for a log, set ViolationDetected=False.
        2. If a violation is detected, select the most appropriate remediation script from the list.
        3. Be specific about which Control IDs are violated.
        
        Available Scripts: [{scripts_list}]
        
        Controls:
        {controls}
        
        Logs to Audit:
        {log_data}
        
        {format_instructions}
        """,
        input_variables=["controls", "log_data", "scripts_list"],
        partial_variables={"format_instructions": parser.get_format_instructions()},
    )
    
    logs_str = "\n".join([f"Log {i}: {json.dumps(l)}" for i, l in enumerate(logs)])
    controls_text = get_relevant_controls(logs_str)
    
    chain = prompt | llm | parser
    try:
        result = chain.invoke({
            "controls": controls_text,
            "log_data": logs_str,
            "scripts_list": scripts_list_str
        })
        return result.get("Evaluations", [])
    except Exception as e:
        print(f"❌ Bulk Audit Error: {e}")
        return []

def auditor_node(state: GraphState) -> GraphState:
    """
    The Auditor Agent node. Processes logs to identify violations.
    If evaluations are already present (from API split), it uses them.
    """
    evaluations = state.get("evaluations", [])
    logs = state.get("logs", [])
    
    # If no evaluations present, perform audit (fallback/standalone mode)
    if not evaluations and logs:
        evaluations = perform_bulk_audit(logs)
    
    execution_entries = []
    violations = []
    
    for ev in evaluations:
        idx = ev.get("LogIndex", 0)
        if ev.get("ViolationDetected"):
            violations.append(ev)
            msg = f"Violation Found: {ev.get('Severity')} - {ev.get('Thought')[:150]}..."
            log_agent_action("auditor", "Violation Detected", msg)
        else:
            msg = f"Compliance Pass: {ev.get('Thought')[:100]}..."
            log_agent_action("auditor", "Pass", msg)
            
        execution_entries.append({
            "node": "auditor",
            "message": msg,
            "timestamp": datetime.now().isoformat(),
            "details": ev
        })

    # Determine overall status and highest severity
    highest_severity = "None"
    offending_entity = "unknown"
    mapped_controls = []
    framework = "Internal"
    
    if violations:
        sev_map = {"Critical": 3, "Medium": 2, "Low": 1, "None": 0}
        violations.sort(key=lambda x: sev_map.get(x.get("Severity", "None"), 0), reverse=True)
        highest_severity = violations[0].get("Severity")
        framework = violations[0].get("Framework", "Internal")
        
        top_idx = violations[0].get("LogIndex", 0)
        top_log = logs[top_idx] if top_idx < len(logs) else {}
        
        # Robust entity extraction
        offending_entity = (
            top_log.get("resource_id") or 
            top_log.get("resource") or 
            top_log.get("user_identity") or 
            top_log.get("user") or 
            "unknown"
        )
        
        for v in violations:
            mapped_controls.extend(v.get("MappedControls", []))

    # Update incident registry
    incident_id = state.get("incident_id")
    if incident_id:
        status = "Closed"
        if highest_severity == "Critical":
            status = "Waiting for Approval"
        elif highest_severity != "None":
            status = "In Progress"
            
        upsert_incident(
            incident_id=incident_id,
            status=status,
            severity=highest_severity,
            offending_entity=offending_entity,
            mapped_controls=list(set(mapped_controls)),
            execution_history=state.get("execution_log", []) + execution_entries
        )
            
    return {
        "evaluations": violations,
        "severity": highest_severity,
        "offending_entity": offending_entity,
        "mapped_controls": list(set(mapped_controls)),
        "framework": framework,
        "control_id": mapped_controls[0] if mapped_controls else None,
        "execution_log": execution_entries
    }
