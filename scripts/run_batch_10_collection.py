"""
NEXO Data Platform - Controlled Live Collection Batch 10 Runner
Collects exactly 10 new official documents across NEXO domains from verified active sources,
stages them locally, ingests into Supabase Storage & PostgreSQL via SecureCloudIngestor,
and runs the full 12-point post-ingestion verification for every document.
"""

import os
import sys
import json
import time
from datetime import datetime, timezone
from typing import Dict, Any, List

# Ensure project root is in sys.path
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

from config.logging_config import get_logger
from config.storage_config import STORAGE_BUCKET_NAME, get_domain_folder
from app.collector.polite_client import PoliteHttpClient
from app.collector.security import validate_crawl_target
from app.ingestion.format_detector import detect_format, calculate_sha256
from app.storage.supabase_storage import generate_storage_path
from app.ingestion.secure_cloud_ingestor import SecureCloudIngestor, IngestionStatus

logger = get_logger("collector.batch10")

# Exactly 10 new candidate documents across NEXO domains from verified active sources
BATCH_10_CANDIDATES = [
    {
        "id": "cand_1_gov_schemes_mail",
        "title": "Download Mail Subscription Form",
        "discovered_url": "https://cms.tn.gov.in/cms_migrated/document/forms/Email-Application-Form-V1.1.pdf",
        "source_name": "Government of Tamil Nadu Official Portal",
        "source_url": "https://www.tn.gov.in",
        "source_id": "10000000-0000-0000-0000-000000000003",
        "domain": "government_schemes",
        "format": ".pdf",
        "government_level": "State",
        "state": "Tamil Nadu",
        "language": "en",
        "document_type": "application_form",
    },
    {
        "id": "cand_2_gov_schemes_dns_ssl",
        "title": "Download D N S Request / SSL Application Form",
        "discovered_url": "https://cms.tn.gov.in/cms_migrated/document/forms/DNS_request_SSL_Application_Form-V1.pdf",
        "source_name": "Government of Tamil Nadu Official Portal",
        "source_url": "https://www.tn.gov.in",
        "source_id": "10000000-0000-0000-0000-000000000003",
        "domain": "government_schemes",
        "format": ".pdf",
        "government_level": "State",
        "state": "Tamil Nadu",
        "language": "en",
        "document_type": "application_form",
    },
    {
        "id": "cand_3_coop_citizen_charter",
        "title": "Citizen Charter (नागरिक चार्टर)",
        "discovered_url": "https://www.ncdc.in/documents/other/CitizenCharter.pdf",
        "source_name": "National Cooperative Development Corporation",
        "source_url": "https://www.ncdc.in",
        "source_id": "20000000-0000-0000-0000-000000000002",
        "domain": "cooperative_governance",
        "format": ".pdf",
        "government_level": "Central",
        "state": None,
        "language": "hi",
        "document_type": "guideline",
    },
    {
        "id": "cand_4_coop_crm_guide",
        "title": "NCDC CRM Portal User Guide (सीआरएम)",
        "discovered_url": "https://www.ncdc.in/documents/CRM_Hindi.pdf",
        "source_name": "National Cooperative Development Corporation",
        "source_url": "https://www.ncdc.in",
        "source_id": "20000000-0000-0000-0000-000000000002",
        "domain": "cooperative_governance",
        "format": ".pdf",
        "government_level": "Central",
        "state": None,
        "language": "hi",
        "document_type": "manual",
    },
    {
        "id": "cand_5_agri_rabi_campaign",
        "title": "Rabi Campaign 2024 Strategy & Guidelines",
        "discovered_url": "https://agriwelfare.gov.in/Documents/PIB_RabiCampaign2024_21102024.pdf",
        "source_name": "Ministry of Agriculture & Farmers Welfare",
        "source_url": "https://agriwelfare.gov.in",
        "source_id": "30000000-0000-0000-0000-000000000001",
        "domain": "agriculture_rural_sustainability",
        "format": ".pdf",
        "government_level": "Central",
        "state": None,
        "language": "en",
        "document_type": "guideline",
    },
    {
        "id": "cand_6_agri_digital_mission",
        "title": "Cabinet Approves Digital Agriculture Mission",
        "discovered_url": "https://agriwelfare.gov.in/Documents/pib_ DigitalAgricultureMission.pdf",
        "source_name": "Ministry of Agriculture & Farmers Welfare",
        "source_url": "https://agriwelfare.gov.in",
        "source_id": "30000000-0000-0000-0000-000000000001",
        "domain": "agriculture_rural_sustainability",
        "format": ".pdf",
        "government_level": "Central",
        "state": None,
        "language": "en",
        "document_type": "press_release",
    },
    {
        "id": "cand_7_foodtech_invest_desk",
        "title": "Investment Facilitation Desk in MoFPI Guidelines",
        "discovered_url": "http://mofpi.gov.in/sites/default/files/setting_up_an_investment_facilitation_desk_in_mofpi.pdf",
        "source_name": "Ministry of Food Processing Industries",
        "source_url": "https://www.mofpi.gov.in",
        "source_id": "40000000-0000-0000-0000-000000000001",
        "domain": "foodtech_coldchain",
        "format": ".pdf",
        "government_level": "Central",
        "state": None,
        "language": "en",
        "document_type": "guideline",
    },
    {
        "id": "cand_8_rural_dev_contractors_go",
        "title": "Tamil Nadu Rural Development Contractors Registration G.O. Ms. No. 115",
        "discovered_url": "https://tnrd.tn.gov.in/pdf/G.O.Ms.No.115-Contractors Registration.pdf",
        "source_name": "Tamil Nadu Rural Development and Panchayat Raj Department",
        "source_url": "https://tnrd.tn.gov.in",
        "source_id": "50000000-0000-0000-0000-000000000003",
        "domain": "rural_development_finance",
        "format": ".pdf",
        "government_level": "State",
        "state": "Tamil Nadu",
        "language": "en",
        "document_type": "circular",
    },
    {
        "id": "cand_9_multilingual_waqf_nomination",
        "title": "Tamil Nadu Waqf Board Election Nomination Form (தமிழ் / English)",
        "discovered_url": "https://cms.tn.gov.in/cms_migrated/document/forms/TN_Waqf_Board_Election_Nomination_Form.pdf",
        "source_name": "Government of Tamil Nadu Official Portal",
        "source_url": "https://www.tn.gov.in",
        "source_id": "10000000-0000-0000-0000-000000000003",
        "domain": "multilingual",
        "format": ".pdf",
        "government_level": "State",
        "state": "Tamil Nadu",
        "language": "ta",
        "document_type": "application_form",
    },
    {
        "id": "cand_10_multilingual_fin_go",
        "title": "Government Order of Finance Department - Tamil Version (அரசாணை)",
        "discovered_url": "https://cms.tn.gov.in/cms_migrated/document/GO/fin_t_15120106_2026.pdf",
        "source_name": "Government of Tamil Nadu Official Portal",
        "source_url": "https://www.tn.gov.in",
        "source_id": "10000000-0000-0000-0000-000000000003",
        "domain": "multilingual",
        "format": ".pdf",
        "government_level": "State",
        "state": "Tamil Nadu",
        "language": "ta",
        "document_type": "circular",
    },
]


def run_batch_10_live() -> Dict[str, Any]:
    print("=" * 80)
    print("NEXO DATA PLATFORM - CONTROLLED LIVE COLLECTION BATCH 10")
    print(f"Target Count       : EXACTLY {len(BATCH_10_CANDIDATES)} NEW DOCUMENTS")
    print(f"Target Storage     : {STORAGE_BUCKET_NAME} (Private, upsert=false)")
    print(f"Target Database    : Supabase PostgreSQL 'documents' table")
    print("=" * 80 + "\n")

    # 1. Initialize client & ingestor
    http_client = PoliteHttpClient(crawl_delay=1.0, timeout=15)
    ingestor = SecureCloudIngestor(dry_run=False)

    # 2. Check existing documents in DB to strictly prevent duplicate collection
    db_res = ingestor.client.table("documents").select("id, sha256, storage_path").execute()
    existing_db_docs = db_res.data or []
    existing_db_shas = {d["sha256"].lower() for d in existing_db_docs}
    print(f"Current existing documents in PostgreSQL: {len(existing_db_docs)}")
    print(f"Existing document hashes: {[s[:12] for s in existing_db_shas]}\n")

    processed_dir = os.path.join("data", "processed")
    ocr_dir = os.path.join("data", "ocr")

    results: List[Dict[str, Any]] = []
    success_count = 0
    failure_count = 0

    for idx, cand in enumerate(BATCH_10_CANDIDATES, 1):
        title = cand["title"]
        doc_url = cand["discovered_url"]
        source_url = cand["source_url"]
        domain = cand["domain"]
        source_id = cand["source_id"]
        doc_type = cand.get("document_type", "guideline")
        lang = cand.get("language", "en")

        print("-" * 80)
        print(f"[{idx}/{len(BATCH_10_CANDIDATES)}] Processing New Document:")
        print(f"  Title     : {title}")
        print(f"  Source    : {cand['source_name']} ({source_id})")
        print(f"  Domain    : {domain} | Type: {doc_type} | Lang: {lang}")
        print(f"  Doc URL   : {doc_url}")

        audit_entry: Dict[str, Any] = {
            "index": idx,
            "id": cand["id"],
            "title": title,
            "url": doc_url,
            "source_id": source_id,
            "source_name": cand["source_name"],
            "source_url": source_url,
            "domain": domain,
            "document_type": doc_type,
            "language": lang,
            "government_level": cand.get("government_level"),
            "state": cand.get("state"),
            "http_status": None,
            "file_size": 0,
            "mime_type": None,
            "sha256": None,
            "requires_ocr": False,
            "local_staged_path": None,
            "storage_path": None,
            "version": 1,
            "is_current": True,
            "ingestion_status": None,
            "validation_passed": False,
            "error_message": None,
            "timestamp": datetime.now(timezone.utc).isoformat(),
        }

        # Step 1: Security Validation
        if not validate_crawl_target(doc_url, source_url):
            err = "Security check rejected URL (unauthorized domain or invalid scheme)."
            print(f"  [ERROR] {err}")
            audit_entry["error_message"] = err
            audit_entry["ingestion_status"] = "SECURITY_REJECTED"
            failure_count += 1
            results.append(audit_entry)
            continue

        # Step 2: Polite Live HTTP Download
        print(f"  Fetching document (crawl delay: {http_client.crawl_delay}s)...")
        fetch_res = http_client.fetch(doc_url)
        audit_entry["http_status"] = fetch_res.status_code

        if not fetch_res.success or not fetch_res.content:
            err = f"HTTP download failed: status {fetch_res.status_code} ({fetch_res.error_message})"
            print(f"  [ERROR] {err}")
            audit_entry["error_message"] = err
            audit_entry["ingestion_status"] = "DOWNLOAD_FAILED"
            failure_count += 1
            results.append(audit_entry)
            continue

        content_bytes = fetch_res.content
        file_size = len(content_bytes)
        audit_entry["file_size"] = file_size

        # Step 3: Magic Byte & MIME Validation
        detection = detect_format(content_bytes, doc_url)
        sha256 = calculate_sha256(content_bytes)
        audit_entry["detected_mime"] = detection.mime_type
        audit_entry["mime_type"] = detection.mime_type
        audit_entry["detected_ext"] = detection.extension
        audit_entry["sha256"] = sha256
        audit_entry["requires_ocr"] = detection.requires_ocr

        print(f"  [OK] Fetched {file_size:,} bytes | MIME: {detection.mime_type} ({detection.extension})")
        print(f"  [SHA-256] {sha256}")

        # Ensure not in existing 5 documents
        if sha256.lower() in existing_db_shas:
            err = f"SHA-256 {sha256} already exists in database! Skipping to prevent duplication."
            print(f"  [ALREADY INGESTED] {err}")
            audit_entry["error_message"] = err
            audit_entry["ingestion_status"] = "DUPLICATE_EXISTING"
            results.append(audit_entry)
            continue

        # Step 4: Local Content-Addressed Staging
        domain_folder = get_domain_folder(domain)
        target_dir = ocr_dir if detection.requires_ocr else processed_dir
        dest_folder = os.path.join(target_dir, domain_folder, source_id)
        os.makedirs(dest_folder, exist_ok=True)

        staged_filename = f"{sha256}{detection.extension}"
        staged_filepath = os.path.join(dest_folder, staged_filename)

        with open(staged_filepath, "wb") as f:
            f.write(content_bytes)

        audit_entry["local_staged_path"] = staged_filepath
        print(f"  [LOCAL CAS] Staged to {staged_filepath}")

        # Step 5: Secure Cloud Ingestion (Storage + PostgreSQL)
        print("  Executing Secure Cloud Ingestion (Storage + DB)...")
        audit_rec = ingestor.ingest_document_file(
            local_file_path=staged_filepath,
            source_url=source_url,
            target_domain=domain,
            title=title,
            source_id=source_id,
            document_url=doc_url,
            source_name=cand["source_name"],
            language=lang,
            document_type=doc_type,
        )

        audit_entry["storage_path"] = audit_rec.storage_path
        audit_entry["storage_result"] = audit_rec.storage_result
        audit_entry["database_result"] = audit_rec.database_result
        audit_entry["ingestion_status"] = audit_rec.final_status
        audit_entry["error_message"] = audit_rec.error_message
        audit_entry["verification_result"] = audit_rec.verification_result

        v_res = audit_rec.verification_result or {}
        v_passed = v_res.get("all_passed", False)
        audit_entry["validation_passed"] = v_passed

        print(f"  Ingestion Status : {audit_rec.final_status}")
        print(f"  Storage Upload   : {audit_rec.storage_result.get('status')} -> {audit_rec.storage_path}")
        print(f"  Database Insert  : {audit_rec.database_result.get('status')} (ID: {audit_rec.database_result.get('id')})")
        print(f"  12-Pt Validation : {'PASSED (12/12)' if v_passed else 'FAILED/INCOMPLETE'}")

        if audit_rec.final_status == IngestionStatus.INGESTION_CONFIRMED.value and v_passed:
            success_count += 1
            existing_db_shas.add(sha256.lower())
        else:
            failure_count += 1

    # Persist Batch 10 Manifests
    manifest_dir = os.path.join("data", "manifests", "collector")
    os.makedirs(manifest_dir, exist_ok=True)
    batch10_json_path = os.path.join(manifest_dir, "batch10_live_manifest.json")
    batch10_jsonl_path = os.path.join(manifest_dir, "batch10_live_manifest.jsonl")

    with open(batch10_json_path, "w", encoding="utf-8") as f:
        json.dump(results, f, indent=2, ensure_ascii=False)

    with open(batch10_jsonl_path, "w", encoding="utf-8") as f:
        for r in results:
            f.write(json.dumps(r, ensure_ascii=False) + "\n")

    print("\n" + "=" * 80)
    print("CONTROLLED BATCH 10 EXECUTION SUMMARY")
    print(f"Candidates Attempted    : {len(BATCH_10_CANDIDATES)}")
    print(f"Successfully Ingested   : {success_count} / {len(BATCH_10_CANDIDATES)}")
    print(f"Failures                : {failure_count}")
    print(f"Batch Manifest (JSON)   : {batch10_json_path}")
    print(f"Batch Manifest (JSONL)  : {batch10_jsonl_path}")
    print("=" * 80 + "\n")

    return {
        "success": success_count == len(BATCH_10_CANDIDATES),
        "total_attempted": len(BATCH_10_CANDIDATES),
        "successfully_ingested": success_count,
        "failures": failure_count,
        "results": results,
    }


if __name__ == "__main__":
    run_batch_10_live()
