import sqlite3
import json
from datetime import datetime
from typing import List, Dict, Any, Optional

DB_PATH = "data/incidents.db"

def init_registry():
    """Initializes the incident registry database."""
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS incidents (
            incident_id TEXT PRIMARY KEY,
            status TEXT,
            severity TEXT,
            offending_entity TEXT,
            mapped_controls TEXT,
            incident_ticket_id TEXT,
            change_ticket_id TEXT,
            execution_history TEXT,
            created_at TIMESTAMP,
            updated_at TIMESTAMP
        )
    """)
    conn.commit()
    conn.close()

def upsert_incident(
    incident_id: str,
    status: Optional[str] = None,
    severity: Optional[str] = None,
    offending_entity: Optional[str] = None,
    mapped_controls: Optional[List[str]] = None,
    incident_ticket_id: Optional[str] = None,
    change_ticket_id: Optional[str] = None,
    execution_history: Optional[List[Dict[str, Any]]] = None
):
    """Inserts or updates an incident in the registry."""
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    
    # Check if exists
    cursor.execute("SELECT * FROM incidents WHERE incident_id = ?", (incident_id,))
    existing = cursor.fetchone()
    
    now = datetime.now().isoformat()
    
    if existing:
        # Update only provided fields
        fields = []
        values = []
        if status: fields.append("status = ?"); values.append(status)
        if severity: fields.append("severity = ?"); values.append(severity)
        if offending_entity: fields.append("offending_entity = ?"); values.append(offending_entity)
        if mapped_controls: fields.append("mapped_controls = ?"); values.append(json.dumps(mapped_controls))
        if incident_ticket_id: fields.append("incident_ticket_id = ?"); values.append(incident_ticket_id)
        if change_ticket_id: fields.append("change_ticket_id = ?"); values.append(change_ticket_id)
        if execution_history: fields.append("execution_history = ?"); values.append(json.dumps(execution_history))
        
        fields.append("updated_at = ?")
        values.append(now)
        values.append(incident_id)
        
        query = f"UPDATE incidents SET {', '.join(fields)} WHERE incident_id = ?"
        cursor.execute(query, tuple(values))
    else:
        # Insert new
        cursor.execute("""
            INSERT INTO incidents (
                incident_id, status, severity, offending_entity, 
                mapped_controls, incident_ticket_id, change_ticket_id, 
                execution_history, created_at, updated_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (
            incident_id, 
            status or "Open", 
            severity or "None", 
            offending_entity or "None",
            json.dumps(mapped_controls or []),
            incident_ticket_id,
            change_ticket_id,
            json.dumps(execution_history or []),
            now,
            now
        ))
    
    conn.commit()
    conn.close()

def get_all_incidents() -> List[Dict[str, Any]]:
    """Retrieves all incidents from the registry."""
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM incidents ORDER BY created_at DESC")
    rows = cursor.fetchall()
    
    result = []
    for row in rows:
        d = dict(row)
        d["mapped_controls"] = json.loads(d["mapped_controls"])
        d["execution_history"] = json.loads(d["execution_history"] or "[]")
        result.append(d)
        
    conn.close()
    return result

def get_pending_approvals() -> List[Dict[str, Any]]:
    """Retrieves incidents waiting for human approval."""
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM incidents WHERE status = 'Waiting for Approval' ORDER BY created_at DESC")
    rows = cursor.fetchall()
    
    result = []
    for row in rows:
        d = dict(row)
        d["mapped_controls"] = json.loads(d["mapped_controls"])
        d["execution_history"] = json.loads(d["execution_history"] or "[]")
        result.append(d)
        
    conn.close()
    return result

def get_stats() -> Dict[str, Any]:
    """Retrieves high-level incident statistics."""
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    
    stats = {}
    
    cursor.execute("SELECT COUNT(*) FROM incidents")
    stats["total_incidents"] = cursor.fetchone()[0]
    
    cursor.execute("SELECT COUNT(*) FROM incidents WHERE severity = 'Critical'")
    stats["critical_incidents"] = cursor.fetchone()[0]
    
    cursor.execute("SELECT COUNT(*) FROM incidents WHERE status = 'Resolved'")
    stats["resolved_incidents"] = cursor.fetchone()[0]
    
    cursor.execute("SELECT COUNT(*) FROM incidents WHERE status = 'Waiting for Approval'")
    stats["pending_approvals"] = cursor.fetchone()[0]
    
    conn.close()
    return stats

if __name__ == "__main__":
    init_registry()
