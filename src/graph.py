from typing import Literal
from langgraph.graph import StateGraph, START, END
from langgraph.checkpoint.sqlite.aio import AsyncSqliteSaver

from datetime import datetime
from src.state import GraphState
from src.agents.sensor import sensor_node
from src.agents.auditor import auditor_node
from src.agents.remediator import remediator_node
from src.agents.validator import validator_node
from src.agents.narrator import narrator_node
from src.agents.ticketer import create_incident_node, create_change_node, resolve_incident_node
from src.logger import print_system_msg, log_agent_action
from src.registry import upsert_incident

def route_after_auditor(state: GraphState) -> Literal["incident", "narrator", "__end__"]:
    severity = state.get("severity", "None")
    
    if severity == "None":
        print_system_msg("Routing: No violation, going to END.")
        return "__end__"
    
    # Go to incident creation
    print_system_msg(f"Routing: Severity is {severity}, going to incident creation.")
    return "incident"

def route_after_validator(state: GraphState) -> Literal["remediator", "resolve"]:
    status = state.get("validation_status", "")
    if status == "Failed":
        print_system_msg("Routing: Validation Failed, cycling back to Remediator.")
        return "remediator"
    
    print_system_msg("Routing: Validation Succeeded, going to resolve incident.")
    return "resolve"

def approval_node(state: GraphState) -> GraphState:
    """
    Mock approval node. In real use, this would be a placeholder for the interrupt.
    """
    msg = "Awaiting Human-in-the-Loop approval for Critical violation."
    log_agent_action("system", "Approval Required", msg)
    return {"execution_log": [{"node": "approval", "message": msg, "timestamp": datetime.now().isoformat()}]}

def route_to_remediation(state: GraphState) -> Literal["approval", "remediator"]:
    severity = state.get("severity", "None")
    if severity == "Critical":
        print_system_msg("Routing: Critical severity detected. Redirecting to Approval.")
        return "approval"
    
    print_system_msg(f"Routing: {severity} severity. Proceeding to Auto-Remediation.")
    return "remediator"

def build_graph():
    # 1. Initialize StateGraph
    workflow = StateGraph(GraphState)
    
    # 2. Add Nodes (Agents)
    workflow.add_node("sensor", sensor_node)
    workflow.add_node("auditor", auditor_node)
    workflow.add_node("incident", create_incident_node)
    workflow.add_node("approval", approval_node)
    workflow.add_node("remediator", remediator_node)
    workflow.add_node("change", create_change_node)
    workflow.add_node("validator", validator_node)
    workflow.add_node("resolve", resolve_incident_node)
    workflow.add_node("narrator", narrator_node)
    
    # 3. Define Edges
    workflow.add_edge(START, "sensor")
    workflow.add_edge("sensor", "auditor")
    
    # Conditional edge after Auditor
    workflow.add_conditional_edges(
        "auditor",
        route_after_auditor,
        {
            "incident": "incident",
            "narrator": "narrator",
            "__end__": END
        }
    )
    
    # Conditional edge to either Approval or direct Remediation
    workflow.add_conditional_edges(
        "incident",
        route_to_remediation,
        {
            "approval": "approval",
            "remediator": "remediator"
        }
    )
    
    workflow.add_edge("approval", "remediator")
    workflow.add_edge("remediator", "change")
    workflow.add_edge("change", "validator")
    
    # Conditional edge after Validator (Cyclic Edge)
    workflow.add_conditional_edges(
        "validator",
        route_after_validator,
        {
            "remediator": "remediator", # The Cycle
            "resolve": "resolve"
        }
    )
    
    workflow.add_edge("resolve", "narrator")
    workflow.add_edge("narrator", END)
    
    return workflow
