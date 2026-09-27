"""
NEXO Data Platform - Official Verified Source Seeding & Sync Script
Idempotently seeds and synchronizes the 23 verified official sources from
data/manifests/sources/verified_sources.json into the Supabase PostgreSQL 'sources' table.

Usage:
    python scripts/seed_verified_sources.py --dry-run
    python scripts/seed_verified_sources.py --live
"""

import os
import sys
import json
from typing import List, Dict, Any, Optional

project_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if project_root not in sys.path:
    sys.path.insert(0, project_root)

# Ensure UTF-8 output on Windows consoles
if sys.stdout.encoding != "utf-8":
    try:
        sys.stdout.reconfigure(encoding="utf-8")
        sys.stderr.reconfigure(encoding="utf-8")
    except Exception:
        pass

from config.logging_config import get_logger
from config.supabase_client import get_supabase_admin_client
from app.sources.onboarding import prepare_supabase_record

logger = get_logger("sources.seeding")

DEFAULT_VERIFIED_SOURCES_PATH = os.path.join(
    project_root, "data", "manifests", "sources", "verified_sources.json"
)


def load_verified_sources_manifest(path: str = DEFAULT_VERIFIED_SOURCES_PATH) -> List[Dict[str, Any]]:
    """Loads and validates the verified sources manifest from disk."""
    if not os.path.isfile(path):
        raise FileNotFoundError(f"Verified sources manifest not found at: {path}")

    with open(path, "r", encoding="utf-8") as f:
        data = json.load(f)

    if not isinstance(data, list):
        raise ValueError(f"Expected list of sources in {path}, got {type(data)}")

    # Strictly filter for active, officially VERIFIED sources
    verified = [
        s for s in data
        if s.get("verification_status") == "VERIFIED" and s.get("is_active", True)
    ]
    return verified


def seed_verified_sources(
    manifest_path: str = DEFAULT_VERIFIED_SOURCES_PATH,
    dry_run: bool = True,
    client: Optional[Any] = None,
) -> Dict[str, Any]:
    """
    Synchronizes the verified sources into PostgreSQL 'sources' table.
    Guarantees idempotency via ON CONFLICT (id) DO UPDATE.
    """
    sources_raw = load_verified_sources_manifest(manifest_path)
    total_count = len(sources_raw)

    print("\n" + "=" * 80)
    print("NEXO DATA PLATFORM - VERIFIED OFFICIAL SOURCE SEEDING")
    print("=" * 80)
    print(f"Mode             : {'DRY RUN (Simulation)' if dry_run else 'LIVE DATABASE SEEDING'}")
    print(f"Manifest Source  : {manifest_path}")
    print(f"Verified Records : {total_count}")
    print("=" * 80 + "\n")

    prepared_payloads: List[Dict[str, Any]] = []
    for idx, raw in enumerate(sources_raw, 1):
        payload = prepare_supabase_record(raw)
        prepared_payloads.append(payload)
        print(f"[{idx:02d}/{total_count:02d}] {payload['id']} | {payload['domain'][:28]:<28} | {payload['name'][:35]}")

    print()
    if dry_run:
        print(f"[DRY RUN COMPLETE] {len(prepared_payloads)} verified source records prepared.")
        print("No live database writes executed. Pass --live to write to Supabase.\n")
        return {
            "success": True,
            "dry_run": True,
            "count": len(prepared_payloads),
            "records": prepared_payloads,
        }

    # Live execution
    if client is None:
        client = get_supabase_admin_client()

    print(f"Connecting to Supabase and upserting {len(prepared_payloads)} records into 'sources'...")
    try:
        # Batch upsert with on_conflict='id'
        res = client.table("sources").upsert(prepared_payloads, on_conflict="id").execute()
        seeded_count = len(res.data) if res.data else len(prepared_payloads)
        print(f"[SUCCESS] Upserted {seeded_count} verified official sources into 'sources' table.\n")
        logger.info(f"Successfully seeded {seeded_count} verified sources into database.")
        return {
            "success": True,
            "dry_run": False,
            "count": seeded_count,
            "records": res.data if res.data else prepared_payloads,
        }
    except Exception as exc:
        print(f"[ERROR] Database upsert failed: {exc}\n")
        logger.error(f"Failed to seed verified sources: {exc}")
        return {
            "success": False,
            "dry_run": False,
            "error": str(exc),
        }


if __name__ == "__main__":
    is_live = "--live" in sys.argv
    res = seed_verified_sources(dry_run=not is_live)
    if not res.get("success"):
        sys.exit(1)
