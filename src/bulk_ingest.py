import requests
import time
import uuid
import json
import random

API_URL = "http://127.0.0.1:8000/api/logs"

# Raw Platform Log Templates
RAW_LOG_TEMPLATES = [
    {
        "platform": "AWS CloudTrail",
        "description": "Public S3 Bucket Policy (Violation - Critical)",
        "log": {
            "eventVersion": "1.08",
            "userIdentity": {"arn": "arn:aws:iam::123456789012:user/dev-user-01"},
            "eventTime": "2026-05-15T08:00:00Z",
            "eventSource": "s3.amazonaws.com",
            "eventName": "PutBucketPolicy",
            "awsRegion": "us-east-1",
            "requestParameters": {
                "bucketName": "finance-records-prod",
                "policy": "{\"Statement\":[{\"Effect\":\"Allow\",\"Principal\":\"*\",\"Action\":\"s3:GetObject\"}]}"
            }
        }
    },
    {
        "platform": "AWS CloudTrail",
        "description": "SSH Port Open (Violation - Low)",
        "log": {
            "eventVersion": "1.08",
            "userIdentity": {"arn": "arn:aws:iam::123456789012:user/dev-admin"},
            "eventTime": "2026-05-15T08:02:00Z",
            "eventSource": "ec2.amazonaws.com",
            "eventName": "AuthorizeSecurityGroupIngress",
            "awsRegion": "us-east-1",
            "requestParameters": {
                "groupId": "sg-0123456789",
                "ipPermissions": {
                    "items": [{"ipProtocol": "tcp", "fromPort": 22, "toPort": 22, "ipRanges": {"items": [{"cidrIp": "0.0.0.0/0"}]}}]
                }
            }
        }
    },
    {
        "platform": "IBM Activity Tracker",
        "description": "IAM MFA Disabled (Violation - Critical)",
        "log": {
            "eventTime": "2026-05-15T08:10:00Z",
            "initiator": {"id": "IBMid-55000888", "name": "contractor@partner.com"},
            "target": {"id": "crn:v1:bluemix:public:iam::::user:contractor@partner.com"},
            "action": "iam-identity.user-mfa.update",
            "outcome": "success",
            "requestData": {"mfa": "NONE"}
        }
    },
    {
        "platform": "AWS CloudTrail",
        "description": "Normal Console Login (Success)",
        "log": {
            "eventVersion": "1.08",
            "userIdentity": {"arn": "arn:aws:iam::123456789012:user/admin"},
            "eventTime": "2026-05-15T08:15:00Z",
            "eventSource": "signin.amazonaws.com",
            "eventName": "ConsoleLogin",
            "awsRegion": "us-east-1",
            "responseElements": {"ConsoleLogin": "Success"}
        }
    }
]

def run_simulation():
    print("🚀 Starting Audit Aura Bulk Simulation (Individual Incident Split)...")
    
    logs_to_send = [t["log"] for t in RAW_LOG_TEMPLATES]
    payload = {"logs": logs_to_send}
    
    print(f"📦 Sending {len(logs_to_send)} raw platform logs for bulk auditing...")
    
    try:
        resp = requests.post(API_URL, json=payload)
        resp.raise_for_status()
        data = resp.json()
        
        incident_ids = data.get('incident_ids', [])
        if not incident_ids:
            print(f"✅ Response: {data['message']}")
            return

        print(f"✅ Bulk Audit Complete. Detected {len(incident_ids)} violations.")
        print(f"🧵 Spawned {len(incident_ids)} individual analysis threads: {', '.join(incident_ids)}")
        
        # 2. Listen to Global Stream to see all incidents
        print("\n📡 Listening to GLOBAL Agent Events (SSE)...")
        global_stream_url = "http://127.0.0.1:8000/api/events"
        
        with requests.get(global_stream_url, stream=True) as r:
            for line in r.iter_lines():
                if line:
                    decoded_line = line.decode('utf-8')
                    if decoded_line.startswith("data: "):
                        event_data = json.loads(decoded_line[6:])
                        iid = event_data.get("incident_id", "Unknown")
                        node = event_data.get("node", "SYSTEM")
                        status = event_data.get("status")
                        
                        if status == "paused":
                            print(f"\n⏸️  [{iid}] [PAUSED] {event_data.get('message')} at node: {event_data.get('next')}")
                        elif status == "finished":
                            print(f"\n🏁 [{iid}] [FINISHED] {event_data.get('message')}")
                        elif status == "completed":
                            update = event_data.get("update", {})
                            msg = update.get("execution_log", [{}])[-1].get("message", "Processing...")
                            print(f"[{iid}] 🤖 Agent [{node.upper()}]: {msg}")
                            
                            # If it's a narrative report, print a highlight
                            if "narrative" in update:
                                print(f"📄 [{iid}] EVIDENCE REPORT GENERATED: {update['narrative'][:100]}...")

    except Exception as e:
        print(f"❌ Simulation Failed: {e}")

    except Exception as e:
        print(f"❌ Simulation Failed: {e}")

if __name__ == "__main__":
    run_simulation()
