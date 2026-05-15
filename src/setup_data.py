import os
import shutil
import sqlite3
import chromadb
from src.registry import init_registry

DATA_DIR = "data"

def reset_db():
    print("🧹 Cleaning up databases and stale records...")
    if os.path.exists(DATA_DIR):
        shutil.rmtree(DATA_DIR)
    os.makedirs(DATA_DIR)
    
    # Re-initialize registry
    init_registry()
    print("✅ Databases reset.")

def seed_controls():
    print("🌱 Seeding compliance controls into ChromaDB...")
    client = chromadb.PersistentClient(path=os.path.join(DATA_DIR, "chroma_db"))
    collection = client.get_or_create_collection(name="compliance_controls")
    
    controls = [
        # SOC2
        ("SOC2-CC6.1", "The entity implements logical access security software, infrastructure, and architectures over protected information assets to protect them from security events.", "Access Control"),
        ("SOC2-CC7.1", "The entity uses detection and monitoring procedures to identify and respond to security events, including those identified by monitoring entities and sources outside its boundaries.", "Monitoring"),
        ("SOC2-CC6.6", "The entity implements logical access security measures to protect against threats from sources outside its boundaries (e.g., through network-level restrictions).", "Network"),
        ("SOC2-CC6.3", "The entity authorizes, modifies, and removes access to data, software, and other information assets based on their classification and individual roles.", "Identity"),
        # PCI-DSS
        ("PCI-DSS-1.1.1", "Formal process for approving and testing all network connections and changes to firewall and router configurations.", "Firewall"),
        ("PCI-DSS-7.1.2", "Restrict access to privileged user IDs to least privileges necessary to perform job responsibilities.", "Least Privilege"),
        ("PCI-DSS-8.3.1", "Incorporate multi-factor authentication for all non-console administrative access into the CDE.", "MFA"),
        ("PCI-DSS-10.2.1", "Implement automated audit trails for all individual user accesses to cardholder data.", "Logging"),
        # HIPAA
        ("HIPAA-164.308.a.1", "Implement policies and procedures to prevent, detect, contain, and correct security violations.", "Administrative"),
        ("HIPAA-164.312.a.1", "Implement technical policies and procedures for electronic information systems that maintain ePHI to allow access only to those persons or software programs that have been granted access.", "Technical"),
        # ISO27001
        ("ISO27001-A.9.1", "The objective is to limit access to information and information processing facilities based on business and security requirements.", "Access Control"),
        ("ISO27001-A.12.4.1", "Event logs recording user activities, exceptions, faults and information security events shall be produced, kept and regularly reviewed.", "Logging")
    ]
    
    for cid, text, focus in controls:
        collection.add(
            ids=[cid],
            documents=[text],
            metadatas=[{'type': 'Compliance', 'focus': focus}]
        )
    print(f"✅ Ingested {len(controls)} controls.")

if __name__ == "__main__":
    reset_db()
    seed_controls()
    print("✨ Environment is clean and ready for demo.")
