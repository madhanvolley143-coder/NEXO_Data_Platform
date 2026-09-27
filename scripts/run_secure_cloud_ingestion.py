"""
NEXO Data Platform - Secure Cloud Ingestion CLI Script
Command line interface to trigger secure cloud ingestion for controlled batches.
Usage:
    python scripts/run_secure_cloud_ingestion.py --dry-run
    python scripts/run_secure_cloud_ingestion.py --live
"""

import sys
import os

project_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if project_root not in sys.path:
    sys.path.insert(0, project_root)

# Ensure UTF-8 output on Windows consoles
try:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    if hasattr(sys.stderr, "reconfigure"):
        sys.stderr.reconfigure(encoding="utf-8", errors="replace")
except Exception:
    pass

from app.ingestion.secure_cloud_ingestor import run_controlled_batch_ingestion

if __name__ == "__main__":
    is_live = "--live" in sys.argv
    run_controlled_batch_ingestion(dry_run=not is_live)
