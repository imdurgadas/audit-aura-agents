import sqlite3
import json
import os
import pymysql
from datetime import datetime
from typing import List, Dict, Any, Optional

DB_PATH = "data/incidents.db"

def get_connection():
    """Returns a database connection based on environment variables."""
    db_host = os.getenv("DB_HOST")
    if db_host:
        # RDS / MySQL path
        return pymysql.connect(
            host=db_host,
            user=os.getenv("DB_USER"),
            password=os.getenv("DB_PASSWORD"),
            database=os.getenv("DB_NAME"),
            port=int(os.getenv("DB_PORT", 3306)),
            cursorclass=pymysql.cursors.DictCursor
        )
    else:
        # Local SQLite fallback
        conn = sqlite3.connect(DB_PATH)
        conn.row_factory = sqlite3.Row
        return conn

def init_registry():
    """Initializes the incident registry database."""
    conn = get_connection()
    cursor = conn.cursor()
    
    # SQL slightly different for MySQL vs SQLite, but this is compatible
    create_sql = """
        CREATE TABLE IF NOT EXISTS incidents (
            incident_id VARCHAR(100) PRIMARY KEY,
            status VARCHAR(50),
            severity VARCHAR(50),
            offending_entity VARCHAR(255),
            mapped_controls TEXT,
            incident_ticket_id VARCHAR(100),
            change_ticket_id VARCHAR(100),
            execution_history TEXT,
            created_at TEXT,
            updated_at TEXT
        )
    """
    cursor.execute(create_sql)
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
    conn = get_connection()
    cursor = conn.cursor()
    is_mysql = os.getenv("DB_HOST") is not None
    p = "%s" if is_mysql else "?"
    
    # Check if exists
    cursor.execute(f"SELECT * FROM incidents WHERE incident_id = {p}", (incident_id,))
    existing = cursor.fetchone()
    
    now = datetime.now().isoformat()
    
    if existing:
        fields = []
        values = []
        if status: fields.append(f"status = {p}"); values.append(status)
        if severity: fields.append(f"severity = {p}"); values.append(severity)
        if offending_entity: fields.append(f"offending_entity = {p}"); values.append(offending_entity)
        if mapped_controls: fields.append(f"mapped_controls = {p}"); values.append(json.dumps(mapped_controls))
        if incident_ticket_id: fields.append(f"incident_ticket_id = {p}"); values.append(incident_ticket_id)
        if change_ticket_id: fields.append(f"change_ticket_id = {p}"); values.append(change_ticket_id)
        if execution_history: fields.append(f"execution_history = {p}"); values.append(json.dumps(execution_history))
        
        fields.append(f"updated_at = {p}")
        values.append(now)
        values.append(incident_id)
        
        query = f"UPDATE incidents SET {', '.join(fields)} WHERE incident_id = {p}"
        cursor.execute(query, tuple(values))
    else:
        cursor.execute(f"""
            INSERT INTO incidents (
                incident_id, status, severity, offending_entity, 
                mapped_controls, incident_ticket_id, change_ticket_id, 
                execution_history, created_at, updated_at
            ) VALUES ({p}, {p}, {p}, {p}, {p}, {p}, {p}, {p}, {p}, {p})
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
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM incidents ORDER BY created_at DESC")
    rows = cursor.fetchall()
    
    result = []
    for row in rows:
        d = dict(row)
        d["mapped_controls"] = json.loads(d["mapped_controls"] or "[]")
        d["execution_history"] = json.loads(d["execution_history"] or "[]")
        result.append(d)
        
    conn.close()
    return result

def get_pending_approvals() -> List[Dict[str, Any]]:
    """Retrieves incidents waiting for human approval."""
    conn = get_connection()
    cursor = conn.cursor()
    is_mysql = os.getenv("DB_HOST") is not None
    p = "%s" if is_mysql else "?"
    
    cursor.execute(f"SELECT * FROM incidents WHERE status = {p} ORDER BY created_at DESC", ("Waiting for Approval",))
    rows = cursor.fetchall()
    
    result = []
    for row in rows:
        d = dict(row)
        d["mapped_controls"] = json.loads(d["mapped_controls"] or "[]")
        d["execution_history"] = json.loads(d["execution_history"] or "[]")
        result.append(d)
        
    conn.close()
    return result

def get_stats() -> Dict[str, Any]:
    """Retrieves high-level incident statistics."""
    conn = get_connection()
    cursor = conn.cursor()
    is_mysql = os.getenv("DB_HOST") is not None
    p = "%s" if is_mysql else "?"
    
    stats = {}
    
    cursor.execute("SELECT COUNT(*) as count FROM incidents")
    row = cursor.fetchone()
    stats["total_incidents"] = row["count"] if is_mysql else row[0]
    
    cursor.execute(f"SELECT COUNT(*) as count FROM incidents WHERE severity = {p}", ("Critical",))
    row = cursor.fetchone()
    stats["critical_incidents"] = row["count"] if is_mysql else row[0]
    
    cursor.execute(f"SELECT COUNT(*) as count FROM incidents WHERE status = {p}", ("Resolved",))
    row = cursor.fetchone()
    stats["resolved_incidents"] = row["count"] if is_mysql else row[0]
    
    cursor.execute(f"SELECT COUNT(*) as count FROM incidents WHERE status = {p}", ("Waiting for Approval",))
    row = cursor.fetchone()
    stats["pending_approvals"] = row["count"] if is_mysql else row[0]
    
    conn.close()
    return stats

if __name__ == "__main__":
    init_registry()
