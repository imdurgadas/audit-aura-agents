import asyncio
import json
import uuid
import os
import chromadb
from datetime import datetime
from contextlib import asynccontextmanager
from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import StreamingResponse, HTMLResponse
from pydantic import BaseModel
from typing import Dict, Any, Optional, List
from langgraph.checkpoint.sqlite.aio import AsyncSqliteSaver

from src.graph import build_graph
from src.logger import print_system_msg
from src.registry import get_all_incidents, get_pending_approvals, get_stats, upsert_incident

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

from fastapi.middleware.cors import CORSMiddleware

app = FastAPI(title="Audit Aura Dashboard API", lifespan=lifespan)

# Fully open CORS for hackathon deployment
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=False,
    allow_methods=["*"],
    allow_headers=["*"],
)

def get_app_url(request: Request, path: str):
    """Helper to preserve the 'app' query parameter required by Semicolons portal."""
    app_id = request.query_params.get("app")
    if app_id:
        separator = "&" if "?" in path else "?"
        return f"{path}{separator}app={app_id}"
    return path

class LogPayload(BaseModel):
    logs: List[Dict[str, Any]]
    incident_id: Optional[str] = None

class ResumePayload(BaseModel):
    approve: bool
    change_ticket: Optional[str] = None

async def run_workflow(incident_id: str, payload: Optional[Dict[str, Any]] = None):
    """
    The CORE engine that runs the LangGraph workflow independently.
    Broadcasts events to the global broadcaster but is NOT a generator.
    """
    config = {"configurable": {"thread_id": incident_id}}
    
    # Initial broadcast to set the stage on the dashboard
    entity_name = payload.get('offending_entity', 'unknown resource') if payload else 'existing incident'
    await broadcaster.broadcast({
        "incident_id": incident_id,
        "node": "sensor",
        "status": "active",
        "message": f"🕵️ Analysis initialized for {entity_name}...",
        "offending_entity": payload.get("offending_entity") if payload else None,
        "timestamp": asyncio.get_event_loop().time()
    })
    
    print_system_msg(f"⚙️  Workflow Execution Started: {incident_id}")
    
    # If payload is provided, it's a new run. Otherwise, it's a resumption.
    stream = graph_app.astream(payload, config=config) if payload else graph_app.astream(None, config=config)
    
    # Handle auto-remediation timer for demo
    async def auto_approve_timer():
        await asyncio.sleep(20)
        state = await graph_app.aget_state(config)
        if state.next and state.next[0] == "approval":
            print_system_msg(f"⏱️  Auto-Approving {incident_id} after 20s timeout.")
            await run_workflow(incident_id) # Recursive call with no payload to resume

    try:
        async for event in stream:
            if isinstance(event, dict):
                for node_name, state_update in event.items():
                    update_data = {}
                    if isinstance(state_update, dict):
                        # Capture only relevant dashboard updates
                        update_data = {k: v for k, v in state_update.items() if k in ["severity", "remediation_action", "execution_log", "narrative", "offending_entity"]}
                    
                    message = {
                        "incident_id": incident_id,
                        "node": node_name,
                        "status": "completed",
                        "timestamp": asyncio.get_event_loop().time(),
                        "update": update_data
                    }
                    await broadcaster.broadcast(message)
            
        # Check final state to broadcast pause/finish events
        state = await graph_app.aget_state(config)
        if state.next:
            await broadcaster.broadcast({
                "incident_id": incident_id, 
                "status": "paused", 
                "next": state.next[0], 
                "message": "Waiting for Human Approval (Auto-approving in 20s...)"
            })
            # Start the fallback timer
            asyncio.create_task(auto_approve_timer())
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
async def ingest_logs(payload: LogPayload, request: Request):
    """
    Ingests raw logs and orchestrates the audit process in the background.
    """
    async def process_batch():
        from src.agents.auditor import perform_bulk_audit
        
        # 1. Broadcast Ingestion Start
        await broadcaster.broadcast({
            "incident_id": "SYSTEM-INGEST",
            "node": "PIPELINE",
            "status": "active",
            "message": f"📥 Received {len(payload.logs)} raw log events. Initializing bulk compliance scan...",
            "timestamp": asyncio.get_event_loop().time()
        })
        
        # 2. Broadcast LLM Action
        await broadcaster.broadcast({
            "incident_id": "SYSTEM-AUDIT",
            "node": "LLM-ENGINE",
            "status": "active",
            "message": "🧠 Evaluating log patterns against compliance controls - LLM in action...",
            "timestamp": asyncio.get_event_loop().time()
        })
        
        # 3. Perform efficient bulk audit (in thread to avoid blocking)
        all_evaluations = await asyncio.to_thread(perform_bulk_audit, payload.logs)
        
        # 4. Identify violations
        violations = [ev for ev in all_evaluations if ev.get("ViolationDetected")]
        
        if not violations:
            await broadcaster.broadcast({
                "incident_id": "SYSTEM-AUDIT",
                "node": "LLM-ENGINE",
                "status": "finished",
                "message": "✅ Audit complete. No compliance violations detected in this batch.",
                "timestamp": asyncio.get_event_loop().time()
            })
            return
            
        # 5. Broadcast Detection
        await broadcaster.broadcast({
            "incident_id": "SYSTEM-AUDIT",
            "node": "ORCHESTRATOR",
            "status": "active",
            "message": f"⚠️ Detected {len(violations)} compliance violations. Spawning autonomous remediation threads...",
            "timestamp": asyncio.get_event_loop().time()
        })
        
        # 6. Create individual threads for each violation
        import random
        for ev in violations:
            thread_id = f"GIT-INC-{random.randint(1000, 9999)}"
            log_item = payload.logs[ev.get("LogIndex", 0)]
            thread_payload = {
                "logs": [log_item],
                "evaluations": [ev],
                "incident_id": thread_id,
                "offending_entity": (
                    log_item.get("resource_id") or 
                    log_item.get("resource") or 
                    log_item.get("user_identity") or 
                    log_item.get("user") or 
                    "unknown"
                ),
                "framework": ev.get("Framework", "Internal"),
                "control_id": ev.get("MappedControls", ["N/A"])[0]
            }
            asyncio.create_task(run_workflow(thread_id, thread_payload))
            
    # Trigger the background process
    asyncio.create_task(process_batch())
    
    return {
        "status": "accepted",
        "message": "Log batch accepted for compliance auditing.",
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
async def resume_workflow(incident_id: str, payload: ResumePayload, request: Request):
    """Resume a paused workflow and trigger background execution."""
    config = {"configurable": {"thread_id": incident_id}}
    state = await graph_app.aget_state(config)
    
    if not state.next:
        raise HTTPException(status_code=400, detail="Incident is not in a paused state.")
        
    current_node = state.next[0]

    if not payload.approve:
        # Update incident status to 'Aborted' if rejected
        from src.registry import upsert_incident
        upsert_incident(incident_id=incident_id, status="Aborted")
        return {"status": "aborted", "message": "Remediation rejected."}
    
    # If resuming from manual_fix, update state with the change ticket
    if current_node == "manual_fix" and payload.change_ticket:
        await graph_app.update_state(config, {
            "change_ticket_id": payload.change_ticket,
            "remediation_action": f"Manual Fix applied (Ticket: {payload.change_ticket})"
        })
    
    # Trigger the workflow in the background. 
    asyncio.create_task(run_workflow(incident_id))
    
    return {
        "status": "resumed",
        "message": f"Workflow {incident_id} has been resumed from {current_node}.",
        "stream_url": get_app_url(request, f"/api/events/{incident_id}")
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

@app.get("/api/simulate")
async def simulate_logs(request: Request):
    """Convenience endpoint to trigger a simulation of violations with mixed severities."""
    # We'll send 3 logs: 1 Critical (needs approval), 1 Low (auto-remediate), 1 Medium (auto-remediate)
    sample_logs = [
        {
            "event_source": "aws.s3",
            "event_type": "PutBucketPublicAccessBlock",
            "resource_id": "audit-aura-evidence-store",
            "user_identity": "contractor-99",
            "timestamp": datetime.now().isoformat(),
            "action": "s3.PublicAccessDisabled",
            "raw_details": {"PublicAccessBlock": "false", "RestrictPublicBuckets": "false"}
        },
        {
            "event_source": "ibm.iam",
            "event_type": "user.mfa.update",
            "resource_id": "crn:v1:bluemix:public:iam::::user:contractor@partner.com",
            "user_identity": "admin-system",
            "timestamp": datetime.now().isoformat(),
            "action": "iam-identity.user-mfa.update",
            "raw_details": {"mfa": "NONE"}
        },
        {
            "event_source": "kubernetes",
            "event_type": "CreateRoleBinding",
            "resource_id": "cluster-admin-binding",
            "user_identity": "service-account-a",
            "timestamp": datetime.now().isoformat(),
            "action": "rbac.authorization.k8s.io/create",
            "raw_details": {"role": "cluster-admin", "subject": "system:unauthenticated"}
        },
        {
            "event_source": "azure.compute",
            "event_type": "VirtualMachineCreate",
            "resource_id": "audit-aura-unencrypted-vm",
            "user_identity": "dev-user-01",
            "timestamp": datetime.now().isoformat(),
            "action": "Microsoft.Compute/virtualMachines/write",
            "raw_details": {"encryptionAtHost": "false", "disks": [{"encryptionSettings": {"enabled": "false"}}]}
        }
    ]
    
    # Designate the Azure VM as a "sticky" violation that fails validation 3 times
    # by ensuring the Auditor selects a script with ".retry." in its name.
    payload = LogPayload(logs=sample_logs)
    return await ingest_logs(payload, request)

@app.get("/api/evidence/{incident_id}")
async def get_evidence(incident_id: str):
    """Fetches the physical markdown evidence for an incident."""
    file_path = f"data/evidence/{incident_id}.md"
    if not os.path.exists(file_path):
        raise HTTPException(status_code=404, detail="Evidence not found.")
    with open(file_path, "r") as f:
        return {"content": f.read()}

@app.get("/", response_class=HTMLResponse)
async def dashboard(request: Request):
    app_id = request.query_params.get("app", "")
    app_param = f"?app={app_id}" if app_id else ""
    
    html_content = f"""
    <!DOCTYPE html>
    <html>
    <head>
        <title>Audit Aura | Unified SOC Console</title>
        <link href="https://fonts.googleapis.com/css2?family=Inter:wght@300;400;500;600&family=JetBrains+Mono&display=swap" rel="stylesheet">
        <script src="https://cdn.jsdelivr.net/npm/marked/marked.min.js"></script>
        <style>
            :root {{
                --bg: #0b0f1a;
                --sidebar-bg: #111827;
                --card: #1f2937;
                --card-hover: #374151;
                --accent: #38bdf8;
                --text: #f3f4f6;
                --sub: #9ca3af;
                --success: #10b981;
                --warning: #f59e0b;
                --error: #ef4444;
                --border: rgba(255,255,255,0.08);
            }}
            body {{
                background: var(--bg);
                color: var(--text);
                font-family: 'Inter', sans-serif;
                margin: 0;
                padding: 0;
                display: flex;
                flex-direction: column;
                height: 100vh;
                overflow: hidden;
            }}
            header {{
                background: var(--sidebar-bg);
                padding: 0.75rem 1.5rem;
                display: flex;
                justify-content: space-between;
                align-items: center;
                border-bottom: 1px solid var(--border);
                z-index: 100;
            }}
            h1 {{ font-size: 1.25rem; font-weight: 600; margin: 0; background: linear-gradient(to right, #38bdf8, #818cf8); -webkit-background-clip: text; -webkit-text-fill-color: transparent; }}
            
            main {{
                display: flex;
                flex: 1;
                overflow: hidden;
            }}
            
            /* Left Feed Area */
            #feed-container {{
                flex: 1;
                display: flex;
                flex-direction: column;
                padding: 1rem;
                overflow-y: auto;
                border-right: 1px solid var(--border);
            }}
            .section-header {{ display: flex; justify-content: space-between; align-items: center; margin-bottom: 1rem; }}
            .section-title {{ font-size: 0.85rem; font-weight: 600; color: var(--sub); text-transform: uppercase; letter-spacing: 0.05em; }}
            
            .event-card {{
                background: var(--card);
                border: 1px solid var(--border);
                border-radius: 8px;
                padding: 0.75rem 1rem;
                margin-bottom: 0.75rem;
                cursor: pointer;
                transition: all 0.2s;
                position: relative;
                animation: slideIn 0.3s ease-out;
            }}
            .event-card:hover {{ background: var(--card-hover); border-color: var(--accent); }}
            .event-card.active {{ border-left: 4px solid var(--accent); background: var(--card-hover); }}
            
            @keyframes slideIn {{ from {{ opacity: 0; transform: translateX(-10px); }} to {{ opacity: 1; transform: translateX(0); }} }}
            
            .card-top {{ display: flex; justify-content: space-between; align-items: flex-start; margin-bottom: 0.5rem; }}
            .incident-id {{ font-family: 'JetBrains Mono', monospace; font-size: 0.8rem; font-weight: 600; color: var(--accent); }}
            .timestamp {{ font-size: 0.7rem; color: var(--sub); }}
            .node-badge {{ font-size: 0.65rem; font-weight: 600; padding: 2px 6px; border-radius: 4px; text-transform: uppercase; }}
            .node-sensor {{ background: #4f46e5; color: white; }}
            .node-auditor {{ background: #9333ea; color: white; }}
            .node-ticketer {{ background: #0891b2; color: white; }}
            .node-remediator {{ background: #059669; color: white; }}
            .node-narrator {{ background: #db2777; color: white; }}
            
            .card-msg {{ font-size: 0.85rem; line-height: 1.4; color: #d1d5db; }}
            
            /* Right Sidebar */
            #sidebar {{
                width: 500px;
                background: var(--sidebar-bg);
                display: flex;
                flex-direction: column;
                overflow-y: hidden;
                box-shadow: -4px 0 15px rgba(0,0,0,0.3);
            }}
            .tabs {{
                display: flex;
                background: rgba(0,0,0,0.2);
                border-bottom: 1px solid var(--border);
            }}
            .tab {{
                flex: 1;
                padding: 1rem;
                text-align: center;
                font-size: 0.75rem;
                font-weight: 600;
                color: var(--sub);
                cursor: pointer;
                transition: all 0.2s;
            }}
            .tab.active {{ color: var(--accent); border-bottom: 2px solid var(--accent); background: rgba(255,255,255,0.03); }}
            
            .tab-content {{
                flex: 1;
                padding: 1.5rem;
                overflow-y: auto;
                display: none;
            }}
            .tab-content.active {{ display: block; }}
            
            .detail-section {{ margin-bottom: 1.5rem; }}
            .detail-label {{ font-size: 0.7rem; color: var(--sub); text-transform: uppercase; margin-bottom: 0.5rem; display: block; }}
            .detail-value {{ font-size: 0.95rem; font-weight: 500; color: var(--text); }}
            .ticket-header {{ border-bottom: 1px solid var(--border); padding-bottom: 1rem; margin-bottom: 1.5rem; }}
            
            .status-pill {{ display: inline-block; padding: 2px 8px; border-radius: 99px; font-size: 0.75rem; font-weight: 600; }}
            .status-open {{ background: rgba(56, 189, 248, 0.2); color: var(--accent); }}
            .status-waiting {{ background: rgba(245, 158, 11, 0.2); color: var(--warning); }}
            .status-resolved {{ background: rgba(16, 185, 129, 0.2); color: var(--success); }}
            
            .history-list {{ font-family: 'JetBrains Mono', monospace; font-size: 0.75rem; list-style: none; padding: 0; margin: 0; }}
            .history-item {{ padding: 8px 0; border-bottom: 1px dashed var(--border); }}
            .history-time {{ color: var(--sub); display: block; font-size: 0.65rem; }}
            
            /* Actions */
            .btn {{
                border: none; padding: 0.5rem 1rem; border-radius: 6px; font-size: 0.8rem; font-weight: 600; cursor: pointer;
                transition: transform 0.1s; display: flex; align-items: center; gap: 0.5rem;
            }}
            .btn:active {{ transform: scale(0.98); }}
            .btn-success {{ background: var(--success); color: white; width: 100%; justify-content: center; }}
            .btn-simulate {{ background: rgba(56, 189, 248, 0.1); color: var(--accent); border: 1px solid var(--accent); }}
            
            .conn-status {{ font-size: 0.75rem; display: flex; align-items: center; gap: 6px; }}
            .dot {{ width: 8px; height: 8px; border-radius: 50%; display: inline-block; }}
            .dot-green {{ background: var(--success); box-shadow: 0 0 8px var(--success); }}
            
            /* Markdown Styles */
            .markdown-body {{ font-size: 0.9rem; line-height: 1.6; color: #d1d5db; }}
            .markdown-body h1, .markdown-body h2 {{ color: var(--accent); border-bottom: 1px solid var(--border); padding-bottom: 0.3em; }}
            .markdown-body pre {{ background: #000; padding: 10px; border-radius: 4px; overflow-x: auto; }}
            .markdown-body code {{ font-family: 'JetBrains Mono', monospace; background: rgba(255,255,255,0.05); padding: 0.2em 0.4em; border-radius: 3px; }}
            .event-card.system-msg {{ cursor: default; border-style: dashed; opacity: 0.8; }}
            .event-card.system-msg:hover {{ border-color: var(--border); background: var(--card); }}
        </style>
    </head>
    <body>
        <header>
            <h1>Audit Aura <span style="font-weight: 300; color: var(--sub); font-size: 0.9rem;">SOC Console</span></h1>
            <div class="conn-status">
                <span class="dot dot-green"></span>
                <span id="conn-text">Live Connection Active</span>
                <button class="btn btn-simulate" style="margin-left: 1rem; padding: 0.3rem 0.8rem;" onclick="simulate()">Simulate</button>
            </div>
        </header>

        <main>
            <section id="feed-container">
                <div class="section-header">
                    <span class="section-title">Live Activity Feed</span>
                </div>
                <div id="feed">
                    <!-- Cards injected here -->
                </div>
            </section>

            <aside id="sidebar">
                <div id="empty-state" style="text-align: center; margin-top: 5rem; color: var(--sub);">
                    <p>Select an incident from the feed to view full Git Ticket details.</p>
                </div>
                
                <div id="ticket-view" style="display: none; height: 100%; flex-direction: column;">
                    <div class="tabs">
                        <div class="tab active" onclick="showTab('ticket')">TICKET DETAILS</div>
                        <div class="tab" onclick="showTab('evidence')">EVIDENCE PREVIEW</div>
                    </div>

                    <div id="tab-ticket" class="tab-content active">
                        <div class="ticket-header">
                            <div class="detail-label">Incident Identity</div>
                            <h2 id="side-id" style="margin: 0; color: var(--accent);">GIT-INC-XXXX</h2>
                            <div id="side-status-container" style="margin-top: 0.5rem;"></div>
                        </div>
                        
                        <div class="detail-section">
                            <div class="detail-label">Offending Entity</div>
                            <div class="detail-value" id="side-entity">unknown</div>
                        </div>
                        
                        <div class="detail-section" id="approval-box" style="display: none;">
                            <div class="detail-label" style="color: var(--warning);">Human Intervention Required</div>
                            <button class="btn btn-success" onclick="approveCurrent()">Approve Remediation</button>
                        </div>

                        <div class="detail-section" id="manual-box" style="display: none;">
                            <div class="detail-label" style="color: var(--warning);">Autonomous Remediation Exhausted</div>
                            <p style="font-size: 0.8rem; color: var(--sub); margin-bottom: 0.5rem;">Please apply manual fix and provide the Change Ticket Number below.</p>
                            <input type="text" id="manual-ticket" placeholder="e.g. GIT-CHG-9999" style="width: 100%; padding: 0.5rem; background: #000; border: 1px solid var(--border); color: white; border-radius: 4px; margin-bottom: 0.5rem;">
                            <button class="btn btn-success" onclick="submitManualFix()">Submit Manual Resolution</button>
                        </div>

                        <div class="detail-section">
                            <div class="detail-label">Execution Trace</div>
                            <div class="history-list" id="side-history"></div>
                        </div>
                    </div>

                    <div id="tab-evidence" class="tab-content">
                        <div id="markdown-container" class="markdown-body">
                            <p style="color: var(--sub)">Loading evidence artifact...</p>
                        </div>
                    </div>
                </div>
            </aside>
        </main>

        <script>
            const feed = document.getElementById('feed');
            const eventSource = new EventSource('/api/events{app_param}');
            let selectedId = null;
            let incidentCache = {{}};

            eventSource.onmessage = (event) => {{
                const data = JSON.parse(event.data);
                if (data.incident_id) {{
                    updateIncidentCache(data);
                    addOrUpdateCard(data);
                    if (selectedId === data.incident_id) renderSidebar(data.incident_id);
                }}
            }};

            function updateIncidentCache(data) {{
                const id = data.incident_id;
                if (!incidentCache[id]) incidentCache[id] = {{ history: [], status: 'Open' }};
                
                if (data.status) incidentCache[id].status = data.status;
                if (data.next) incidentCache[id].next = data.next;
                if (data.offending_entity) incidentCache[id].entity = data.offending_entity;
                if (data.update && data.update.execution_log) {{
                    incidentCache[id].history.push(...data.update.execution_log);
                }}
                if (data.update && data.update.remediation_action) incidentCache[id].remediation = data.update.remediation_action;
                if (data.update && data.update.severity) incidentCache[id].severity = data.update.severity;
            }}

            function addOrUpdateCard(data) {{
                const id = data.incident_id;
                let card = document.getElementById(`card-${{id}}`);
                const isSystem = id.startsWith('SYSTEM-');
                
                if (!card) {{
                    card = document.createElement('div');
                    card.id = `card-${{id}}`;
                    card.className = 'event-card' + (isSystem ? ' system-msg' : '');
                    if (!isSystem) card.onclick = () => selectIncident(id);
                    feed.prepend(card);
                }}

                const lastLog = (data.update && data.update.execution_log) ? data.update.execution_log[0].message : (data.message || 'Processing...');
                const statusClass = data.status === 'paused' ? 'status-waiting' : (data.status === 'finished' ? 'status-resolved' : 'status-open');
                const statusText = isSystem ? 'SYSTEM' : (data.status === 'paused' ? 'WAITING' : (data.status === 'finished' ? 'RESOLVED' : 'ACTIVE'));

                card.innerHTML = `
                    <div class="card-top">
                        <span class="incident-id" style="${{isSystem ? 'color: var(--sub)' : ''}}">${{id}}</span>
                        <span class="node-badge node-${{data.node || 'sensor'}}">${{data.node || 'sensor'}}</span>
                    </div>
                    <div class="card-msg">${{lastLog}}</div>
                    <div style="margin-top: 0.5rem; display: flex; justify-content: space-between; align-items: center;">
                        <span class="status-pill ${{isSystem ? '' : statusClass}}" style="${{isSystem ? 'background: rgba(255,255,255,0.05); color: var(--sub)' : ''}}">${{statusText}}</span>
                        <span class="timestamp">${{new Date().toLocaleTimeString()}}</span>
                    </div>
                `;
            }}

            function selectIncident(id) {{
                if (id.startsWith('SYSTEM-')) return;
                selectedId = id;
                document.querySelectorAll('.event-card').forEach(c => c.classList.remove('active'));
                const card = document.getElementById(`card-${{id}}`);
                if (card) card.classList.add('active');
                renderSidebar(id);
            }}

            function renderSidebar(id) {{
                const incident = incidentCache[id];
                document.getElementById('empty-state').style.display = 'none';
                document.getElementById('ticket-view').style.display = 'flex';
                
                document.getElementById('side-id').innerText = id;
                document.getElementById('side-entity').innerText = incident.entity || 'Calculating...';
                
                const statusText = incident.status === 'paused' ? 'WAITING' : (incident.status === 'finished' ? 'RESOLVED' : 'ACTIVE');
                const statusClass = incident.status === 'paused' ? 'status-waiting' : (incident.status === 'finished' ? 'status-resolved' : 'status-open');
                document.getElementById('side-status-container').innerHTML = `<span class="status-pill ${{statusClass}}">${{statusText}}</span>`;
                
                const historyEl = document.getElementById('side-history');
                historyEl.innerHTML = incident.history.map(h => `
                    <div class="history-item">
                        <span class="history-time">${{new Date(h.timestamp).toLocaleTimeString()}}</span>
                        ${{h.message}}
                    </div>
                `).join('');

                const isManual = incident.status === 'paused' && incident.next === 'manual_fix';
                const isApproval = incident.status === 'paused' && incident.next === 'approval';
                
                document.getElementById('approval-box').style.display = isApproval ? 'block' : 'none';
                document.getElementById('manual-box').style.display = isManual ? 'block' : 'none';
                
                // Fetch markdown if we are in evidence tab
                if (document.getElementById('tab-evidence').classList.contains('active')) {{
                    fetchEvidence(id);
                }}
            }}

            function showTab(tabName) {{
                document.querySelectorAll('.tab').forEach(t => t.classList.remove('active'));
                document.querySelectorAll('.tab-content').forEach(c => c.classList.remove('active'));
                
                document.querySelector(`.tab[onclick="showTab('${{tabName}}')"]`).classList.add('active');
                document.getElementById(`tab-${{tabName}}`).classList.add('active');
                
                if (tabName === 'evidence' && selectedId) {{
                    fetchEvidence(selectedId);
                }}
            }}

            async function fetchEvidence(id) {{
                const container = document.getElementById('markdown-container');
                try {{
                    const res = await fetch(`/api/evidence/${{id}}`);
                    if (res.ok) {{
                        const data = await res.json();
                        container.innerHTML = marked.parse(data.content);
                    }} else {{
                        container.innerHTML = '<p style="color: var(--error)">Evidence artifact not yet generated by Narrator agent.</p>';
                    }}
                }} catch (e) {{
                    container.innerHTML = '<p style="color: var(--error)">Error fetching evidence.</p>';
                }}
            }}

            async function approveCurrent() {{
                if (!selectedId) return;
                await fetch(`/api/resume/${{selectedId}}{app_param}`, {{
                    method: 'POST',
                    headers: {{ 'Content-Type': 'application/json' }},
                    body: JSON.stringify({{ approve: true }})
                }});
            }}

            async function submitManualFix() {{
                const ticket = document.getElementById('manual-ticket').value;
                if (!ticket) return alert("Please provide a Change Ticket number.");
                if (!selectedId) return;
                
                await fetch(`/api/resume/${{selectedId}}{app_param}`, {{
                    method: 'POST',
                    headers: {{ 'Content-Type': 'application/json' }},
                    body: JSON.stringify({{ approve: true, change_ticket: ticket }})
                }});
            }}

            async function simulate() {{
                await fetch('/api/simulate{app_param}');
            }}
        </script>
    </body>
    </html>
    """
    return HTMLResponse(content=html_content)
