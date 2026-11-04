#!/usr/bin/env python3
import subprocess
import sys

# The scripts must run in this exact order
scripts = ["convert_stage.py", "2_process_data.py", "3_generate_report.py"]

for script in scripts:
    print(f"🚀 Running {script}...")
    
    # Launch script using the current Python executable
    result = subprocess.run([sys.executable, script])
    
    # Strictly halt if an upstream script fails (returns non-zero exit code)
    if result.returncode != 0:
        print(f"❌ Pipeline aborted: {script} failed with exit code {result.returncode}.")
        sys.exit(result.returncode)

print("🎉 Pipeline completed successfully!")