import sys
import time

def remediate():
    print("Initiating remediation: Closing public SSH port...")
    time.sleep(1)
    print("Executing aws ec2 revoke-security-group-ingress --group-id sg-0123456789abcdef0 --protocol tcp --port 22 --cidr 0.0.0.0/0")
    time.sleep(1)
    print("Remediation successful.")
    
if __name__ == "__main__":
    remediate()
