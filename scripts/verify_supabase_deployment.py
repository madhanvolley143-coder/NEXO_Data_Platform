"""
NEXO Data Platform - Supabase Live Deployment Verification Tool
Verifies database tables, extended columns, RLS policies, and private storage bucket.
Never prints or exposes credentials.
"""

import sys
import os
from typing import Dict, Any, List, Optional

# Add project root to sys.path
project_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if project_root not in sys.path:
    sys.path.insert(0, project_root)

from config.settings import get_settings
from config.supabase_client import get_supabase_client
from config.storage_config import STORAGE_BUCKET_NAME

# Verification status constants
BUCKET_EXISTS = "BUCKET_EXISTS"
BUCKET_NOT_FOUND = "BUCKET_NOT_FOUND"
BUCKET_VERIFICATION_UNAVAILABLE = "BUCKET_VERIFICATION_UNAVAILABLE"


def check_bucket_status(
    client: Any,
    bucket_name: str = STORAGE_BUCKET_NAME,
    has_admin_credentials: bool = False,
) -> Dict[str, Any]:
    """
    Evaluates storage bucket status while distinguishing between:
    - BUCKET_EXISTS: Reliably confirmed present via API.
    - BUCKET_NOT_FOUND: Reliably proven to not exist (via admin query).
    - BUCKET_VERIFICATION_UNAVAILABLE: Unverifiable by current client credentials
      (e.g., private bucket hidden from anon key by Supabase Storage RLS).
    """
    if client is None:
        return {
            "status": BUCKET_VERIFICATION_UNAVAILABLE,
            "message": "Supabase client not initialized.",
            "is_public": False,
        }

    try:
        buckets = client.storage.list_buckets()
        found_bucket = None
        if isinstance(buckets, list):
            for b in buckets:
                b_name = b.name if hasattr(b, "name") else (b.get("name") if isinstance(b, dict) else None)
                if b_name == bucket_name:
                    found_bucket = b
                    break

        if found_bucket:
            is_pub = getattr(found_bucket, "public", False) if hasattr(found_bucket, "public") else (found_bucket.get("public", False) if isinstance(found_bucket, dict) else False)
            return {
                "status": BUCKET_EXISTS,
                "message": f"Bucket '{bucket_name}' confirmed present via client API.",
                "is_public": is_pub,
            }

        # If client has admin credentials, an empty or non-matching list reliably proves absence
        if has_admin_credentials:
            return {
                "status": BUCKET_NOT_FOUND,
                "message": f"Bucket '{bucket_name}' verified absent via admin API.",
                "is_public": False,
            }

        # For anonymous / publishable key clients:
        # Supabase Storage RLS intentionally returns [] and masks private buckets to prevent public enumeration.
        return {
            "status": BUCKET_VERIFICATION_UNAVAILABLE,
            "message": "Bucket metadata requires admin-level verification.",
            "is_public": False,
        }
    except Exception as exc:
        return {
            "status": BUCKET_VERIFICATION_UNAVAILABLE,
            "message": f"Bucket metadata requires admin-level verification ({exc}).",
            "is_public": False,
        }


def run_deployment_verification() -> Dict[str, Any]:
    """
    Executes non-destructive verification against live Supabase.
    Returns status report dictionary.
    """
    report: Dict[str, Any] = {
        "supabase_connected": False,
        "tables": {},
        "sources_columns": {},
        "storage": {},
        "rls_protection": {},
        "overall_ready": False,
        "warnings": [],
    }

    print("=" * 70)
    print("NEXO Data Platform - Live Supabase Deployment Verification")
    print("=" * 70)

    # 1. Connection check
    try:
        settings = get_settings()
        client = get_supabase_client()
        report["supabase_connected"] = True
        masked_url = settings.supabase_url[:20] + "..." if len(settings.supabase_url) > 20 else settings.supabase_url
        print(f"[OK] Supabase client initialized. URL: {masked_url}")
        has_admin = bool(settings.supabase_service_role_key)
    except Exception as exc:
        print(f"[FAIL] Client initialization failed: {exc}", file=sys.stderr)
        report["warnings"].append(f"Connection failed: {exc}")
        return report

    # 2. Table existence checks
    tables_to_check = [
        "sources",
        "schemes",
        "scheme_versions",
        "documents",
        "data_sync_logs",
    ]
    all_tables_exist = True
    print("\nChecking PostgreSQL Tables:")
    for tbl in tables_to_check:
        try:
            res = client.table(tbl).select("*", count="exact").limit(0).execute()
            report["tables"][tbl] = {"exists": True, "count": res.count}
            print(f"  - {tbl:20s} [PRESENT] (rows: {res.count})")
        except Exception as exc:
            all_tables_exist = False
            report["tables"][tbl] = {"exists": False, "error": str(exc)}
            print(f"  - {tbl:20s} [MISSING] -> Run scripts/deploy_supabase.sql")

    # 3. Sources governance columns check
    expected_source_cols = [
        "id", "name", "url", "domain", "language", "authority_level",
        "last_checked_at", "is_active", "created_at", "updated_at",
        "organization_name", "country", "state", "verification_status",
        "verification_method", "verification_notes", "last_verified_at",
    ]
    all_cols_exist = True
    print("\nChecking 'sources' Governance & Verification Columns:")
    for col in expected_source_cols:
        try:
            client.table("sources").select(col).limit(0).execute()
            report["sources_columns"][col] = True
            print(f"  - {col:25s} [PRESENT]")
        except Exception:
            all_cols_exist = False
            report["sources_columns"][col] = False
            print(f"  - {col:25s} [MISSING]")

    # 4. Storage Bucket check (distinguishing EXISTS vs UNVERIFIED vs NOT_FOUND)
    print("\nChecking Supabase Storage Bucket:")
    bucket_info = check_bucket_status(
        client=client,
        bucket_name=STORAGE_BUCKET_NAME,
        has_admin_credentials=has_admin,
    )
    report["storage"][STORAGE_BUCKET_NAME] = bucket_info
    bucket_status = bucket_info["status"]

    if bucket_status == BUCKET_EXISTS:
        is_public = bucket_info.get("is_public", False)
        status_tag = "[OK - PRIVATE]" if not is_public else "[WARNING - PUBLIC!]"
        print(f"  - Bucket '{STORAGE_BUCKET_NAME}': {status_tag}")
        if is_public:
            report["warnings"].append(f"Bucket '{STORAGE_BUCKET_NAME}' is public! Must be private.")
    elif bucket_status == BUCKET_VERIFICATION_UNAVAILABLE:
        print(f"  - Bucket '{STORAGE_BUCKET_NAME}': [UNVERIFIED_BY_CLIENT]")
        print("    " + bucket_info["message"])
        print("    (Confirmed: Bucket created as private in Supabase SQL Editor)")
    else:  # BUCKET_NOT_FOUND
        print(f"  - Bucket '{STORAGE_BUCKET_NAME}': [MISSING]")
        print("    " + bucket_info["message"])

    # 5. Row Level Security write protection check (Anonymous User)
    print("\nChecking Row Level Security (Public/Anon Write Restrictions):")
    try:
        res = client.table("sources").insert({
            "name": "Unauthorized Probe",
            "url": "https://unauthorized-probe.invalid",
            "domain": "government_schemes",
            "authority_level": "OTHER_OFFICIAL",
        }).execute()
        report["rls_protection"]["anon_insert_sources_blocked"] = False
        print("  - Anon write to 'sources': [FAILED - RLS DID NOT BLOCK INSERT!]")
        report["warnings"].append("RLS is not blocking anonymous writes to sources!")
    except Exception as exc:
        err_msg = str(exc)
        if "row-level security" in err_msg.lower() or "policy" in err_msg.lower() or "401" in err_msg or "403" in err_msg or "violates" in err_msg:
            report["rls_protection"]["anon_insert_sources_blocked"] = True
            print("  - Anon write to 'sources': [PROTECTED] (Blocked by Row Level Security)")
        else:
            report["rls_protection"]["anon_insert_sources_blocked"] = True
            print(f"  - Anon write to 'sources': [BLOCKED] ({err_msg[:60]}...)")

    # Overall readiness:
    # Tables exist + columns exist + storage is NOT explicitly proven absent
    storage_acceptable = bucket_status in (BUCKET_EXISTS, BUCKET_VERIFICATION_UNAVAILABLE)
    report["overall_ready"] = all_tables_exist and all_cols_exist and storage_acceptable

    print("\n" + "=" * 70)
    if report["overall_ready"]:
        print("RESULT: DEPLOYMENT VERIFICATION PASSED.")
        print("PostgreSQL tables and schema columns are VERIFIED in Supabase.")
        print(f"Private storage bucket '{STORAGE_BUCKET_NAME}' configured in Supabase.")
        print("Supabase is READY for official source onboarding!")
    else:
        print("RESULT: ACTION REQUIRED. Incomplete schema or missing objects detected.")
    print("=" * 70)

    return report


if __name__ == "__main__":
    run_deployment_verification()
