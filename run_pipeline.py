"""One-command end-to-end run: download -> ETL -> marts -> model -> dashboard -> tests."""
import subprocess
import sys
STEPS = ["src/download_data.py", "src/etl.py", "src/build_marts.py", "src/late_risk_model.py", "src/build_dashboard.py"]
for step in STEPS:
    print(f"\n=== {step} ===", flush=True)
    subprocess.run([sys.executable, step], check=True)
print("\n=== tests ===", flush=True)
sys.exit(subprocess.call([sys.executable, "-m", "pytest", "-q", "tests"]))
