import asyncio
import json
import uuid
import chromadb
from contextlib import asynccontextmanager
from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import StreamingResponse
from pydantic import BaseModel
from typing import Dict, Any, Optional, List
from langgraph.checkpoint.sqlite.aio import AsyncSqliteSaver

from src.graph import build_graph
from src.logger import print_system_msg
from src.registry import get_all_incidents, get_pending_approvals, get_stats

# Globals for async checkpointer and compiled graph
graph_app = None
checkpointer = None

class Broadcaster:
    """Manages global SSE broadcasting to multiple subscribers."""
    def __init__(self):
        self.subscribers = set()

    def subscribe(self) -> asyncio.Queue:
        queue = asyncio.Queue()
        self.subscribers.add(queue)
        return queue

    def unsubscribe(self, queue: asyncio.Queue):
        self.subscribers.discard(queue)

    async def broadcast(self, message: Dict[str, Any]):
        # Clean up any potential dead queues while broadcasting
        for queue in list(self.subscribers):
            try:
                queue.put_nowait(message)
            except asyncio.QueueFull:
                self.subscribers.discard(queue)

broadcaster = Broadcaster()

@asynccontextmanager
async def lifespan(app: FastAPI):
    global graph_app, checkpointer
    checkpointer = AsyncSqliteSaver.from_conn_string("data/checkpoints.sqlite")
    async with checkpointer as saver:
        workflow = build_graph()
        graph_app = workflow.compile(
            checkpointer=saver,
            interrupt_before=["approval"]
        )
        yield

app = FastAPI(title="Audit Aura Dashboard API", lifespan=lifespan)

class LogPayload(BaseModel):
    logs: List[Dict[str, Any]]
    incident_id: Optional[str] = None

class ResumePayload(BaseModel):
    approve: bool

async def run_workflow(incident_id: str, payload: Optional[Dict[str, Any]] = None):
    """
    The CORE engine that runs the LangGraph workflow independently.
    Broadcasts events to the global broadcaster but is NOT a generator.
    """
    config = {"configurable": {"thread_id": incident_id}}
    print_system_msg(f"⚙️  Workflow Execution Started: {incident_id}")
    
    # If payload is provided, it's a new run. Otherwise, it's a resumption.
    stream = graph_app.astream(payload, config=config) if payload else graph_app.astream(None, config=config)
    
    try:
        async for event in stream:
            if isinstance(event, dict):
                for node_name, state_update in event.items():
                    update_data = {}
                    if isinstance(state_update, dict):
                        # Capture only relevant dashboard updates
                        update_data = {k: v for k, v in state_update.items() if k in ["severity", "remediation_action", "execution_log", "narrative"]}
                    
                    message = {
                        "incident_id": incident_id,
                        "node": node_name,
                        "status": "completed",
                        "timestamp": asyncio.get_event_loop().time(),
                        "update": update_data
                    }
                    # Broadcast to everyone (Global and Specific streams)
                    await broadcaster.broadcast(message)
            
        # Check final state to broadcast pause/finish events
        state = await graph_app.aget_state(config)
        if state.next:
            await broadcaster.broadcast({
                "incident_id": incident_id, 
                "status": "paused", 
                "next": state.next[0], 
                "message": "Waiting for Human Approval"
            })
        else:
            await broadcaster.broadcast({
                "incident_id": incident_id, 
                "status": "finished", 
                "message": "Workflow completed successfully"
            })
            
    except Exception as e:
        print_system_msg(f"❌ Workflow Engine Error: {e}")
        await broadcaster.broadcast({
            "incident_id": incident_id, 
            "status": "error", 
            "message": str(e)
        })

async def incident_event_generator(incident_id: str):
    """
    Observer-only generator for a specific incident.
    Listens to the broadcaster and filters for its ID.
    """
    queue = broadcaster.subscribe()
    print_system_msg(f"📡 Observer attached to incident: {incident_id}")
    try:
        while True:
            data = await queue.get()
            if data.get("incident_id") == incident_id:
                yield f"data: {json.dumps(data)}\n\n"
                if data.get("status") in ["finished", "error", "aborted"]:
                    break
    finally:
        broadcaster.unsubscribe(queue)

@app.post("/api/logs")
async def ingest_logs(payload: LogPayload):
    """
    Ingests raw logs, performs a bulk audit, and splits violations into individual incidents.
    Automatically triggers background execution for each spawned incident.
    """
    from src.agents.auditor import perform_bulk_audit
    
    # 1. Perform efficient bulk audit
    all_evaluations = perform_bulk_audit(payload.logs)
    
    # 2. Identify violations
    violations = [ev for ev in all_evaluations if ev.get("ViolationDetected")]
    
    if not violations:
        return {"status": "success", "message": "No violations detected in the provided logs.", "incident_ids": []}
    
    # 3. Create individual threads for each violation
    import random
    incident_ids = []
    for ev in violations:
        # Align incident ID with GIT Ticket ID format as requested
        thread_id = f"GIT-INC-{random.randint(1000, 9999)}"
        log_item = payload.logs[ev.get("LogIndex", 0)]
        
        # Initial state for this thread
        thread_payload = {
            "logs": [log_item],
            "evaluations": [ev],
            "incident_id": thread_id
        }
        
        # Trigger background execution immediately
        asyncio.create_task(run_workflow(thread_id, thread_payload))
        incident_ids.append(thread_id)
    
    return {
        "status": "accepted",
        "message": f"Detected {len(violations)} violations. Started {len(incident_ids)} background analysis threads.",
        "incident_ids": incident_ids,
        "stream_urls": [f"/api/events/{tid}" for tid in incident_ids]
    }

@app.get("/api/events")
async def global_events(request: Request):
    """Global SSE endpoint to stream all events across all incidents."""
    async def stream():
        queue = broadcaster.subscribe()
        try:
            while True:
                if await request.is_disconnected():
                    break
                data = await queue.get()
                yield f"data: {json.dumps(data)}\n\n"
        finally:
            broadcaster.unsubscribe(queue)
    return StreamingResponse(stream(), media_type="text/event-stream")

@app.get("/api/events/{incident_id}")
async def stream_events(incident_id: str, request: Request):
    """Observer SSE endpoint to stream the progress of a specific incident."""
    return StreamingResponse(incident_event_generator(incident_id), media_type="text/event-stream")

@app.post("/api/resume/{incident_id}")
async def resume_workflow(incident_id: str, payload: ResumePayload):
    """Resume a paused workflow and trigger background execution."""
    if not payload.approve:
        # Update incident status to 'Aborted' if rejected
        from src.registry import upsert_incident
        upsert_incident(incident_id=incident_id, status="Aborted")
        return {"status": "aborted", "message": "Remediation rejected."}
    
    # Trigger the workflow in the background. 
    # It will broadcast updates to the global /api/events stream.
    asyncio.create_task(run_workflow(incident_id))
    
    return {
        "status": "resumed",
        "message": f"Workflow {incident_id} has been approved and is running in the background.",
        "stream_url": f"/api/events/{incident_id}"
    }

@app.get("/api/incidents")
async def list_incidents():
    return get_all_incidents()

@app.get("/api/approvals")
async def list_approvals():
    return get_pending_approvals()

@app.get("/api/stats")
async def dashboard_stats():
    return get_stats()

@app.get("/api/controls")
async def list_controls():
    client = chromadb.PersistentClient(path="data/chroma_db")
    collection = client.get_or_create_collection(name="compliance_controls")
    results = collection.get()
    
    controls = []
    if results and results["ids"]:
        for i in range(len(results["ids"])):
            controls.append({
                "id": results["ids"][i],
                "text": results["documents"][i],
                "metadata": results["metadatas"][i]
            })
    return controls
