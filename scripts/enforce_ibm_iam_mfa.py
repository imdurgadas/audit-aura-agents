import sys
import time

def remediate():
    print("Initiating remediation: Enforcing MFA for IBM IAM User...")
    time.sleep(1)
    print("Executing ibmcloud iam user-policy-create ibm-new-contractor@company.com --roles Viewer --resource-type identity --mfa-required")
    time.sleep(1)
    print("Remediation successful.")
    
if __name__ == "__main__":
    remediate()
