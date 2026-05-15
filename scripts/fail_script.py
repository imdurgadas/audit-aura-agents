import sys
print("Simulating a failed remediation...")
sys.stderr.write("Error: Could not connect to resource API.\n")
sys.exit(1)
