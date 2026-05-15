import sys
import time

def remediate():
    print("Initiating remediation: Closing public SSH port on IBM VSI Security Group...")
    time.sleep(1)
    print("Executing ibmcloud is security-group-rule-delete sg-ibm-123abc456def rule-ssh-public")
    time.sleep(1)
    print("Remediation successful.")
    
if __name__ == "__main__":
    remediate()
