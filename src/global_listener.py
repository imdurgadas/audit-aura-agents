import requests
import json

STREAM_URL = "http://127.0.0.1:8000/api/events"

def listen_globally():
    print("🌍 Listening to GLOBAL Audit Aura Events...")
    try:
        with requests.get(STREAM_URL, stream=True) as r:
            for line in r.iter_lines():
                if line:
                    decoded_line = line.decode('utf-8')
                    if decoded_line.startswith("data: "):
                        event_data = json.loads(decoded_line[6:])
                        incident_id = event_data.get("incident_id", "Unknown")
                        node = event_data.get("node", "SYSTEM")
                        status = event_data.get("status")
                        
                        if status == "completed":
                            msg = event_data.get("update", {}).get("execution_log", [{}])[-1].get("message", "Step finished.")
                            print(f"[{incident_id}] 🤖 Agent {node.upper()}: {msg}")
                        else:
                            print(f"[{incident_id}] ℹ️  Status: {status} - {event_data.get('message', '')}")
    except Exception as e:
        print(f"❌ Listener error: {e}")

if __name__ == "__main__":
    listen_globally()
