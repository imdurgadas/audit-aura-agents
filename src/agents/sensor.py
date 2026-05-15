from datetime import datetime
from typing import Dict, Any, List
from src.state import GraphState
from src.logger import log_agent_action

def normalize_log(raw_log: Dict[str, Any]) -> Dict[str, Any]:
    """
    Attempts to normalize raw JSON logs. If already standard, returns as is.
    """
    # Check if already normalized
    if all(k in raw_log for k in ["event_source", "event_type", "resource_id"]):
        return raw_log
        
    # Heuristic normalization for common patterns
    normalized = {
        "event_source": raw_log.get("source") or raw_log.get("eventSource") or "unknown",
        "event_type": raw_log.get("type") or raw_log.get("eventName") or "unknown",
        "resource_id": raw_log.get("resource") or raw_log.get("requestParameters", {}).get("bucketName") or "unknown",
        "user_identity": raw_log.get("user") or raw_log.get("userIdentity", {}).get("arn") or "unknown",
        "timestamp": raw_log.get("time") or raw_log.get("eventTime") or datetime.now().isoformat(),
        "action": raw_log.get("action") or raw_log.get("eventName") or "unknown",
        "raw_details": raw_log
    }
    return normalized

def sensor_node(state: GraphState) -> GraphState:
    """
    The Sensor Agent node. Ingests raw platform logs and prepares them for the Auditor.
    """
    raw_logs = state.get("logs", [])
    normalized_logs = [normalize_log(log) for log in raw_logs]
    
    msg = f"Ingested {len(raw_logs)} raw log(s) from platform streams. Partial normalization applied."
    log_agent_action("sensor", "Log Ingestion", msg)
    
    execution_entry = {
        "node": "sensor",
        "message": msg,
        "timestamp": datetime.now().isoformat(),
        "details": {"raw_count": len(raw_logs)}
    }
    
    return {
        "logs": normalized_logs,
        "execution_log": [execution_entry]
    }
