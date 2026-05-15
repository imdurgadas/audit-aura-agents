# Audit Aura: Continuous Compliance Observer

**Audit Aura** is an agentic AI framework designed to transition organizations from point-in-time manual audits to **continuous, automated compliance auditing**. Using LangGraph and LLM-powered agents, it monitors raw cloud logs (AWS, K8s, IBM), identifies violations against specific compliance controls, and automates remediation.

---

## 📽️ Demo & Presentation
- **Demo Video**: [Include Link to Demo Video in Repository]
- **Presentation**: [Include Link to Presentation File in Repository]

---

## 🎯 Project Overview

### Target User
*   **SOC Analysts**: Who need real-time visibility into infrastructure drift and compliance violations.
*   **Compliance Officers**: Who require verifiable, persistent forensic evidence of detection and remediation for audit reporting.

### Problem Statement
Traditional audits are static, reactive, and resource-intensive. Security teams often discover misconfigurations (like public S3 buckets or disabled MFA) weeks after they occur, leaving a massive window of vulnerability.

### Value Hypothesis
By leveraging **Agentic AI** to reason over raw, unnormalized platform logs, Audit Aura reduces the detection-to-remediation lifecycle from days to seconds. It provides:
1.  **Continuous Visibility**: Real-time auditing against SOC2/ISO27001 controls.
2.  **Autonomous Remediation**: Auto-fixes for low/medium risk drifts.
3.  **Verifiable Evidence**: Automatically generated forensic reports with full log dumps.

---

## 🛠️ Technical Architecture

### Core Workflow
1.  **Sensor Agent**: Ingests raw platform logs (CloudTrail, K8s Audit, etc.).
2.  **Auditor Agent**: Performs bulk reasoning to map logs to specific Compliance Controls in ChromaDB.
3.  **Ticketer Agent**: Splits violations into individual **GIT-INC** threads and generates initial evidence.
4.  **Remediator Agent**: Executes targeted Python scripts to fix the detected drift.
5.  **Narrator Agent**: Persists a full Markdown forensic report as physical evidence.

### Technology Stack
*   **Orchestration**: LangGraph (Stateful Multi-Agent Workflow)
*   **Intelligence**: Google Gemma-4-e4b (via LM Studio)
*   **Database**: MySQL (RDS) for deployment, SQLite for local development.
*   **Vector Store**: ChromaDB (Control Mapping)
*   **API**: FastAPI with SSE (Server-Sent Events) for real-time dashboard streaming.

---

## 🚀 Getting Started

### Local Setup
1. **Environment**:
   ```bash
   python -m venv .venv
   source .venv/bin/activate
   pip install -r requirements.txt
   ```
2. **Database Initialization**:
   ```bash
   python -m src.setup_data
   ```
3. **Run API**:
   ```bash
   uvicorn src.api:app --host 0.0.0.0 --port 8000
   ```

### Docker Deployment (Semicolons Portal)
The application is fully containerized and configured for the Semicolons shared DNS model.
*   **Port**: 8000
*   **App Parameter**: Automatically preserved across all API/SSE endpoints.
*   **Database**: Automatically connects to centrally provided RDS via environment variables.

```bash
docker build -t audit-aura .
docker run -p 8000:8000 audit-aura
```

---

## 📊 Interactive Dashboard
Audit Aura includes a built-in, real-time web dashboard for easy demonstration.

1.  **Open Dashboard**: Navigate to the root URL (e.g., `http://localhost:8000/`) in your browser.
2.  **Live Feed**: The dashboard automatically connects to the SSE stream and displays "Agent Thinking" cards as the workflow processes logs.
3.  **One-Click Simulation**: Use the **🚀 Simulate Violation** button on the dashboard to trigger a pre-configured violation workflow without needing CLI tools.

### Key API Endpoints
*   **Web Dashboard**: `/` (Browser-friendly)
*   **Trigger Simulation**: `/api/simulate` (GET)
*   **Real-time Global Stream**: `/api/events` (SSE)
*   **Incident Registry**: `/api/incidents`
*   **System Metrics**: `/api/stats`

---
*Developed for the Semicolons Hackathon*
