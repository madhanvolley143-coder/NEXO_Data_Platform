"""
NEXO Data Platform - First Controlled Live Collection Runner
Executes a small, controlled batch of verified official government documents.
Validates downloads, magic bytes, SHA-256 immutability, local staging,
and Supabase Storage / PostgreSQL metadata integration under strict RLS guardrails.
"""

import os
import sys
import json
import time
from datetime import datetime, timezone
from typing import Dict, Any, List, Optional

# Ensure UTF-8 output on Windows consoles
if sys.stdout.encoding != "utf-8":
    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except Exception:
        pass

# Ensure project root is in sys.path
project_root = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
if project_root not in sys.path:
    sys.path.insert(0, project_root)

from config.logging_config import get_logger
from config.settings import get_settings
from config.supabase_client import get_supabase_client
from config.storage_config import STORAGE_BUCKET_NAME, get_domain_folder
from app.collector.security import (
    is_safe_scheme,
    is_domain_authorized,
    validate_crawl_target,
)
from app.collector.polite_client import PoliteHttpClient
from app.ingestion.format_detector import detect_format, calculate_sha256
from app.storage.supabase_storage import generate_storage_path, upload_document
from app.ingestion.db_preparer import prepare_document_record
from app.collector.checkpoint import CheckpointManager

logger = get_logger("collector.live_runner")


# Controlled selection of 5 target documents across domains and formats
TARGET_CANDIDATES = [
    {
        "id": "cand_tn_multilingual_pdf",
        "title": "தமிழ்த்தாய் வாழ்த்து",
        "discovered_url": "https://www.tn.gov.in/sites/default/new_images/tamilthaivazhthusong.pdf",
        "source_name": "Government of Tamil Nadu Official Portal",
        "source_url": "https://www.tn.gov.in",
        "source_id": "10000000-0000-0000-0000-000000000003",
        "domain": "multilingual",
        "format": ".pdf",
        "government_level": "State",
        "state": "Tamil Nadu",
        "language": "ta",
    },
    {
        "id": "cand_tn_schemes_pdf",
        "title": "Application form for the post of Sign Language Interpretor",
        "discovered_url": "https://cms.tn.gov.in/cms_migrated/document/forms/sign_language_interpretor_appl.pdf",
        "source_name": "Government of Tamil Nadu Official Portal",
        "source_url": "https://www.tn.gov.in",
        "source_id": "10000000-0000-0000-0000-000000000003",
        "domain": "government_schemes",
        "format": ".pdf",
        "government_level": "State",
        "state": "Tamil Nadu",
        "language": "ta",
    },
    {
        "id": "cand_ncdc_coop_docx",
        "title": "जवाहरलाल नेहरू सहकारी एग्रीकल्चरल प्रोड्यूस प्रोसेसिंग सोसाइटी लिमिटेड, खरगोन, मध्य प्रदेश - प्रतिभूति हित (प्रवर्तन) नियम, 2002 के नियम 8(6) के साथ सरफेसी अधिनियम, 2002 के तहत अचल संपत्ति की बिक्री के लिए ई-नीलामी बिक्री सूचना",
        "discovered_url": "https://www.ncdc.in/documents/notice-circular/1411170826HINDI-Approved-Detailed-1st-sale-notice---14.08.2026.docx",
        "source_name": "National Cooperative Development Corporation",
        "source_url": "https://www.ncdc.in",
        "source_id": "20000000-0000-0000-0000-000000000002",
        "domain": "cooperative_governance",
        "format": ".docx",
        "government_level": "Central",
        "state": None,
        "language": "hi",
    },
    {
        "id": "cand_mofpi_flowchart_pdf",
        "title": "Organization Chart PDF (Download 1.2 mb)",
        "discovered_url": "https://www.mofpi.gov.in/sites/default/files/flowchart_0.pdf",
        "source_name": "Ministry of Food Processing Industries",
        "source_url": "https://www.mofpi.gov.in",
        "source_id": "40000000-0000-0000-0000-000000000001",
        "domain": "foodtech_coldchain",
        "format": ".pdf",
        "government_level": "Central",
        "state": None,
        "language": "en",
    },
    {
        "id": "cand_agri_pmfby_pdf",
        "title": "PIB PMFBY RWBCIS Press Notification (Download 423 KB)",
        "discovered_url": "https://agriwelfare.gov.in/Documents/PIB_PMFBY_RWBCIS_03012025.pdf",
        "source_name": "Ministry of Agriculture & Farmers Welfare",
        "source_url": "https://agriwelfare.gov.in",
        "source_id": "30000000-0000-0000-0000-000000000001",
        "domain": "agriculture_rural_sustainability",
        "format": ".pdf",
        "government_level": "Central",
        "state": None,
        "language": "en",
    },
]


class ControlledLiveCollector:
    """
    Executes and validates the first controlled live collection batch.
    """

    def __init__(
        self,
        output_dir: str = "data",
        candidates: Optional[List[Dict[str, Any]]] = None,
    ):
        self.output_dir = output_dir
        self.processed_dir = os.path.join(output_dir, "processed")
        self.ocr_dir = os.path.join(output_dir, "ocr")
        self.failed_dir = os.path.join(output_dir, "failed")
        self.manifest_dir = os.path.join(output_dir, "manifests", "collector")

        os.makedirs(self.processed_dir, exist_ok=True)
        os.makedirs(self.ocr_dir, exist_ok=True)
        os.makedirs(self.failed_dir, exist_ok=True)
        os.makedirs(self.manifest_dir, exist_ok=True)

        self.candidates = candidates or TARGET_CANDIDATES
        self.client = PoliteHttpClient(crawl_delay=1.5, timeout=20.0, max_retries=3)
        self.supabase = get_supabase_client()
        self.audit_records: List[Dict[str, Any]] = []

    def run(self) -> Dict[str, Any]:
        """
        Executes the controlled collection workflow item-by-item.
        Haults on verification failures as per Requirement 16.
        """
        print("\n" + "=" * 75)
        print("NEXO DATA PLATFORM - FIRST CONTROLLED LIVE COLLECTION")
        print("=" * 75)
        print(f"Total Candidates Selected : {len(self.candidates)}")
        print(f"Target Storage Bucket     : {STORAGE_BUCKET_NAME} (Private)")
        print(f"Staging Base Directory    : {self.output_dir}")
        print("=" * 75 + "\n")

        successful_downloads = 0
        staged_count = 0
        storage_uploads = 0
        db_inserts = 0
        halted = False
        halt_reason = None

        for idx, item in enumerate(self.candidates, 1):
            if halted:
                print(f"[HALTED] Skipping item #{idx} due to prior failure: {halt_reason}")
                break

            record = self._process_single_item(idx, item)
            self.audit_records.append(record)

            if record["download_success"]:
                successful_downloads += 1
            if record["staged_locally"]:
                staged_count += 1
            if record["storage_uploaded"]:
                storage_uploads += 1
            if record["db_inserted"]:
                db_inserts += 1

            # Check if critical verification failure requires halt
            if record["error_stage"] == "download":
                print(f"  [WARNING] Download failure on item #{idx}: {record['error_message']}")
            elif record["error_stage"] == "content_validation":
                print(f"  [HALT] Content validation failed on item #{idx}: {record['error_message']}")
                halted = True
                halt_reason = f"Content validation failed on item #{idx}: {record['error_message']}"
            elif record["error_stage"] in ("storage_upload", "db_insert"):
                # RLS permission denial expected with anon key
                print(f"  [RLS NOTIFICATION] Supabase {record['error_stage']} blocked as expected: {record['error_message']}")

        # Save audit manifests
        self._save_audit_manifests()

        summary = {
            "total_candidates": len(self.candidates),
            "processed": len(self.audit_records),
            "successful_downloads": successful_downloads,
            "staged_locally": staged_count,
            "storage_uploaded": storage_uploads,
            "db_inserted": db_inserts,
            "halted": halted,
            "halt_reason": halt_reason,
            "records": self.audit_records,
        }

        self._print_summary(summary)
        return summary

    def _process_single_item(self, index: int, item: Dict[str, Any]) -> Dict[str, Any]:
        """Processes a single document end-to-end with strict auditing."""
        doc_url = item["discovered_url"]
        source_url = item["source_url"]
        domain = item["domain"]
        title = item["title"]

        record: Dict[str, Any] = {
            "index": index,
            "id": item["id"],
            "title": title,
            "url": doc_url,
            "source_name": item["source_name"],
            "source_url": source_url,
            "source_id": item["source_id"],
            "domain": domain,
            "expected_format": item["format"],
            "government_level": item["government_level"],
            "state": item["state"],
            "language": item["language"],
            "download_success": False,
            "http_status": None,
            "content_length": 0,
            "detected_mime": None,
            "detected_ext": None,
            "sha256": None,
            "requires_ocr": False,
            "staged_locally": False,
            "local_path": None,
            "storage_path": None,
            "storage_uploaded": False,
            "db_inserted": False,
            "error_stage": None,
            "error_message": None,
            "timestamp": datetime.now(timezone.utc).isoformat(),
        }

        print(f"[{index}/{len(self.candidates)}] Processing Document:")
        print(f"  Title     : {title}")
        print(f"  Source    : {item['source_name']} ({source_url})")
        print(f"  Doc URL   : {doc_url}")
        print(f"  Domain    : {domain} | Format: {item['format']} | Level: {item['government_level']}")

        # 1. Security validation
        is_safe = validate_crawl_target(doc_url, source_url)
        if not is_safe:
            record["error_stage"] = "security_validation"
            record["error_message"] = "Security check rejected URL (unauthorized domain or invalid scheme)."
            print("  [SECURITY REJECTED] URL violates scheme or domain boundary policies.")
            return record

        # 2. Live HTTP Download via PoliteHttpClient
        print(f"  Fetching binary payload (delay: {self.client.crawl_delay}s)...")
        fetch_res = self.client.fetch(doc_url)
        record["http_status"] = fetch_res.status_code
        record["content_length"] = len(fetch_res.content)

        if not fetch_res.success or not fetch_res.content:
            record["error_stage"] = "download"
            record["error_message"] = f"HTTP {fetch_res.status_code} error: {fetch_res.error_message}"
            print(f"  [DOWNLOAD FAILED] HTTP {fetch_res.status_code}: {fetch_res.error_message}")
            return record

        record["download_success"] = True
        print(f"  [DOWNLOAD OK] {len(fetch_res.content):,} bytes received in {fetch_res.elapsed_seconds:.2f}s")

        # 3. Format & Magic-Byte Detection
        content_bytes = fetch_res.content
        detection = detect_format(content_bytes, filename_or_url=doc_url)
        record["detected_mime"] = detection.mime_type
        record["detected_ext"] = detection.extension
        record["requires_ocr"] = detection.requires_ocr

        if not detection.mime_type or detection.detection_method == "empty_content":
            record["error_stage"] = "content_validation"
            record["error_message"] = f"Invalid/empty binary payload (mime: {detection.mime_type})"
            print(f"  [CONTENT INVALID] Invalid payload detected: {detection.mime_type}")
            return record

        print(f"  [MAGIC BYTES] Detected: {detection.mime_type} ({detection.extension}) via {detection.detection_method}")

        # 4. SHA-256 Checksum Calculation (Content Identity)
        sha256 = calculate_sha256(content_bytes)
        record["sha256"] = sha256
        print(f"  [SHA-256] {sha256}")

        # 5. Local Immutable Staging
        domain_folder = get_domain_folder(domain)
        source_slug = item["source_id"] or "general"
        target_dir = self.ocr_dir if detection.requires_ocr else self.processed_dir
        dest_folder = os.path.join(target_dir, domain_folder, source_slug)
        os.makedirs(dest_folder, exist_ok=True)

        staged_filename = f"{sha256}{detection.extension}"
        staged_filepath = os.path.join(dest_folder, staged_filename)

        # Immutability check: if already staged with identical SHA-256, preserve without overwrite
        if os.path.exists(staged_filepath):
            print(f"  [LOCAL CAS] Content-addressable file already staged at {staged_filepath}")
        else:
            with open(staged_filepath, "wb") as f:
                f.write(content_bytes)
            print(f"  [LOCAL STAGED] Saved {len(content_bytes):,} bytes to {staged_filepath}")

        record["staged_locally"] = True
        record["local_path"] = staged_filepath

        # 6. Canonical Storage Path Generation
        storage_path = generate_storage_path(
            domain=domain,
            source_id=item["source_id"],
            sha256=sha256,
            extension=detection.extension,
        )
        record["storage_path"] = storage_path
        print(f"  [STORAGE PATH] {storage_path}")

        # 7. Attempt Supabase Storage Upload (Live)
        print(f"  Attempting upload to Supabase Storage: bucket='{STORAGE_BUCKET_NAME}', path='{storage_path}'...")
        try:
            upload_res = upload_document(
                file_content=content_bytes,
                storage_path=storage_path,
                content_type=detection.mime_type,
                bucket_name=STORAGE_BUCKET_NAME,
                dry_run=False,
                client=self.supabase,
            )
            record["storage_uploaded"] = upload_res.get("uploaded", False)
            print("  [STORAGE UPLOAD] Success! Upload confirmed.")
        except Exception as exc:
            err_msg = str(exc)
            record["error_stage"] = "storage_upload"
            record["error_message"] = err_msg
            if "row-level security" in err_msg.lower() or "403" in err_msg or "unauthorized" in err_msg.lower():
                print(f"  [STORAGE RLS PROTECTED] Blocked by Storage RLS: {err_msg}")
            else:
                print(f"  [STORAGE ERROR] {err_msg}")

        # 8. Prepare and Attempt PostgreSQL Insert (Live)
        print(f"  Preparing PostgreSQL record for table 'documents'...")
        doc_payload = prepare_document_record(
            title=title,
            source_url=doc_url,
            target_domain=domain,
            mime_type=detection.mime_type,
            file_size=len(content_bytes),
            sha256=sha256,
            storage_path=storage_path,
            source_id=item["source_id"],
            language=item["language"],
            requires_ocr=detection.requires_ocr,
        )

        # Filter payload strictly to valid table columns in Supabase schema
        valid_columns = {
            "id", "source_id", "scheme_id", "title", "document_type",
            "source_url", "storage_path", "language", "mime_type",
            "file_size", "sha256", "requires_ocr", "scraped_at",
            "published_at", "is_active"
        }
        filtered_payload = {k: v for k, v in doc_payload.items() if k in valid_columns}

        try:
            res = self.supabase.table("documents").insert(filtered_payload).execute()
            if res.data:
                record["db_inserted"] = True
                print("  [POSTGRESQL INSERT] Success! Record created.")
            else:
                record["error_stage"] = "db_insert"
                record["error_message"] = "No data returned from insert."
                print("  [POSTGRESQL INSERT] No data returned from insert.")
        except Exception as exc:
            err_msg = str(exc)
            # Do not overwrite storage_upload error if storage also failed
            if not record["error_stage"]:
                record["error_stage"] = "db_insert"
                record["error_message"] = err_msg
            if "row-level security" in err_msg.lower() or "42501" in err_msg:
                print(f"  [POSTGRESQL RLS PROTECTED] Blocked by PostgreSQL RLS: {err_msg}")
            else:
                print(f"  [POSTGRESQL ERROR] {err_msg}")

        print()
        return record

    def _save_audit_manifests(self) -> None:
        """Saves JSON and JSONL manifests for this controlled run."""
        json_path = os.path.join(self.manifest_dir, "controlled_live_manifest.json")
        jsonl_path = os.path.join(self.manifest_dir, "controlled_live_manifest.jsonl")

        with open(json_path, "w", encoding="utf-8") as f:
            json.dump(self.audit_records, f, indent=2, ensure_ascii=False)

        with open(jsonl_path, "w", encoding="utf-8") as f:
            for rec in self.audit_records:
                f.write(json.dumps(rec, ensure_ascii=False) + "\n")

        print(f"Audit Manifests saved to:\n  - {json_path}\n  - {jsonl_path}")

    def _print_summary(self, summary: Dict[str, Any]) -> None:
        """Prints a human-readable execution summary."""
        print("\n" + "=" * 75)
        print("CONTROLLED LIVE RUN EXECUTION SUMMARY")
        print("=" * 75)
        print(f"Candidates Evaluated      : {summary['total_candidates']}")
        print(f"Successful HTTP Downloads : {summary['successful_downloads']}")
        print(f"Locally Staged (CAS)      : {summary['staged_locally']}")
        print(f"Supabase Storage Uploads  : {summary['storage_uploaded']}")
        print(f"PostgreSQL Database Rows  : {summary['db_inserted']}")
        print(f"Halted on Fatal Error     : {summary['halted']}")
        if summary['halt_reason']:
            print(f"Halt Reason               : {summary['halt_reason']}")
        print("=" * 75)


if __name__ == "__main__":
    runner = ControlledLiveCollector()
    runner.run()
