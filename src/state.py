import operator
from typing import TypedDict, List, Dict, Any, Optional, Annotated

class GraphState(TypedDict):
    """
    Represents the state of our compliance workflow graph.
    """
    incident_id: Optional[str]
    logs: List[Dict[str, Any]]
    evaluations: Annotated[List[Dict[str, Any]], operator.add]
    severity: Optional[str]
    remediation_action: Optional[str]
    validation_status: Optional[str]
    narrative: Optional[str]
    offending_entity: Optional[str]
    incident_ticket_id: Optional[str]
    change_ticket_id: Optional[str]
    mapped_controls: Optional[List[str]]
    execution_log: Annotated[List[Dict[str, Any]], operator.add]
