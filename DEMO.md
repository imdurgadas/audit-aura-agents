# Audit Aura Agents - Demo Guide

This guide provides step-by-step instructions to demonstrate the Continuous Compliance Observer features, including raw log ingestion, LLM-powered auditing, and real-time SSE streaming.

## Prerequisites
1. Ensure **LM Studio** is running at `http://127.0.0.1:1234/v1` with the `google/gemma-4-e4b` model loaded.
2. Activate the virtual environment:
   ```bash
   source .venv/bin/activate
   ```
3. Install dependencies:
   ```bash
   pip install -r requirements.txt
   ```
4. **Reset Environment (Optional but recommended for fresh demo)**:
   ```bash
   python -m src.setup_data
   ```

## Step 1: Start the API Server
In a new terminal window, start the FastAPI server. This initializes the LangGraph workflow and the database connections.
```bash
uvicorn src.api:app --reload --port 8000
```

## Step 2: Start the Global Event Listener
In another terminal, start the global listener. This will show you events from **all** incidents as they happen across the system.
```bash
python -m src.global_listener
```

## Step 3: Trigger Bulk Log Ingestion
Run the bulk simulator to send a mix of raw logs (AWS, K8s, IBM) to the API.
```bash
python -m src.bulk_ingest
```
**What to watch for:**
- The **Sensor** agent will report ingestion of raw streams.
- The **Auditor** agent will perform "step-by-step" reasoning to map logs to controls (visible in the global listener and API logs).
- **Violations** will be detected, and the workflow will pause for **Critical** severity (Human-in-the-Loop).

## Step 4: Explore the Dashboard APIs
You can verify the system state using the following endpoints:

*   **Registry Status**: [http://127.0.0.1:8000/api/incidents](http://127.0.0.1:8000/api/incidents) - View all processed logs and their reasoning history.
*   **System Stats**: [http://127.0.0.1:8000/api/stats](http://127.0.0.1:8000/api/stats) - View metrics like total violations and resolved incidents.
*   **Pending Approvals**: [http://127.0.0.1:8000/api/approvals](http://127.0.0.1:8000/api/approvals) - See which incidents are waiting for your review.

## Step 5: Resume a Paused Workflow (HITL)
If an incident is in `Waiting for Approval` status, you can resume it via the API:
```bash
curl -X POST http://127.0.0.1:8000/api/resume/<incident_id> \
     -H "Content-Type: application/json" \
     -d '{"approve": true}'
```
The workflow will then proceed to **Remediation**, **Validation**, and **Resolution**.
