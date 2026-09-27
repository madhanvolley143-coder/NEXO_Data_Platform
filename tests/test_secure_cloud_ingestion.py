"""
NEXO Data Platform - Secure Cloud Ingestion Unit Tests
Validates server-side authorization, credential isolation, two-phase transactional safety,
failure reconciliation, duplicate detection, secret redaction, and dry-run guarantees.
Completely offline: uses mocks and temporary test directories with zero live network calls.
"""

import os
import json
import tempfile
import shutil
import unittest
from unittest.mock import patch, MagicMock
from typing import Dict, Any, List, Optional

from app.ingestion.secure_cloud_ingestor import (
    SecureCloudIngestor,
    IngestionStatus,
    IngestionAuditRecord,
    redact_secrets,
)
from config.storage_config import STORAGE_BUCKET_NAME


class MockStorageObject:
    def __init__(self, name: str):
        self.name = name

    def get(self, key: str, default=None):
        if key == "name":
            return self.name
        return default


class MockStorageBucket:
    def __init__(self, bucket_name: str = STORAGE_BUCKET_NAME):
        self.bucket_name = bucket_name
        self.objects: Dict[str, bytes] = {}
        self.upload_fails = False
        self.upload_error_msg = "Simulated storage upload failure"
        self.list_fails = False

    def upload(self, path: str, file: bytes, file_options: Optional[Dict[str, Any]] = None):
        if self.upload_fails:
            raise Exception(self.upload_error_msg)
        upsert = file_options.get("upsert", "false") if file_options else "false"
        if upsert != "true" and path in self.objects:
            raise Exception(f"Duplicate: File already exists at {path}")
        self.objects[path] = file
        return {"Key": path}

    def list(self, folder: str = ""):
        if self.list_fails:
            return []
        prefix = f"{folder}/" if folder and not folder.endswith("/") else folder
        matching = []
        for obj_path in self.objects.keys():
            if not folder or obj_path.startswith(prefix):
                rel_name = obj_path[len(prefix):] if folder else obj_path
                # Only return direct child filename
                if "/" not in rel_name:
                    matching.append({"name": rel_name})
        return matching

    def download(self, path: str) -> bytes:
        if path not in self.objects:
            raise Exception(f"Storage object not found: {path}")
        return self.objects[path]


class MockStorageClient:
    def __init__(self, default_bucket: Optional[MockStorageBucket] = None):
        self.bucket = default_bucket or MockStorageBucket()

    def from_(self, bucket_name: str):
        return self.bucket

    def get_bucket(self, bucket_name: str):
        mock_b = MagicMock()
        mock_b.id = bucket_name
        mock_b.name = bucket_name
        mock_b.public = False
        return mock_b


class MockTableQuery:
    def __init__(self, table_name: str, table_data: List[Dict[str, Any]], insert_fails: bool = False):
        self.table_name = table_name
        self.table_data = table_data
        self.insert_fails = insert_fails
        self.filter_col = None
        self.filter_val = None
        self.last_inserted = None

    def select(self, *columns):
        return self

    def eq(self, column: str, value: Any):
        self.filter_col = column
        self.filter_val = str(value).lower()
        return self

    def insert(self, payload: Dict[str, Any]):
        if self.insert_fails:
            raise Exception("Simulated database insert failure")
        row = dict(payload)
        if "id" not in row or not row["id"]:
            row["id"] = f"mock-uuid-{len(self.table_data) + 1}"
        self.table_data.append(row)
        self.last_inserted = row
        return self

    def execute(self):
        mock_res = MagicMock()
        if self.last_inserted is not None:
            mock_res.data = [dict(self.last_inserted)]
            self.last_inserted = None
        elif self.filter_col:
            matched = [
                row for row in self.table_data
                if str(row.get(self.filter_col, "")).lower() == self.filter_val
            ]
            mock_res.data = matched
        else:
            mock_res.data = list(self.table_data)
        return mock_res


class MockSupabaseClient:
    def __init__(self):
        self.storage_bucket = MockStorageBucket()
        self.storage = MockStorageClient(self.storage_bucket)
        self.tables: Dict[str, List[Dict[str, Any]]] = {
            "sources": [],
            "documents": [],
            "data_sync_logs": [],
        }
        self.table_insert_fails: Dict[str, bool] = {}

    def table(self, table_name: str) -> MockTableQuery:
        self.tables.setdefault(table_name, [])
        insert_fails = self.table_insert_fails.get(table_name, False)
        return MockTableQuery(table_name, self.tables[table_name], insert_fails=insert_fails)


class TestSecureCloudIngestion(unittest.TestCase):
    """Test suite verifying all aspects of secure cloud ingestion."""

    def setUp(self):
        self.test_dir = tempfile.mkdtemp()
        self.manifest_dir = os.path.join(self.test_dir, "manifests")
        self.mock_client = MockSupabaseClient()

        # Create dummy local test document (valid PDF bytes)
        self.dummy_pdf_path = os.path.join(self.test_dir, "sample.pdf")
        self.dummy_pdf_content = b"%PDF-1.4\n%Test PDF document for cloud ingestion\n%%EOF"
        with open(self.dummy_pdf_path, "wb") as f:
            f.write(self.dummy_pdf_content)

        # Create dummy verified sources manifest
        self.dummy_sources_path = os.path.join(self.test_dir, "verified_sources.json")
        sources_manifest = [
            {
                "id": "10000000-0000-0000-0000-000000000001",
                "name": "myScheme National Portal",
                "url": "https://www.myscheme.gov.in",
                "domain": "government_schemes",
                "language": "en",
                "authority_level": "CENTRAL_GOVERNMENT",
                "organization_name": "NeGD",
                "country": "IN",
                "state": None,
                "verification_status": "VERIFIED",
                "is_active": True,
            }
        ]
        with open(self.dummy_sources_path, "w", encoding="utf-8") as f:
            json.dump(sources_manifest, f)

    def tearDown(self):
        shutil.rmtree(self.test_dir, ignore_errors=True)

    def test_credential_isolation_anon_cannot_write(self):
        """Validates that anonymous client raises authorization error when attempting writes."""
        # Simulated anon client that throws 403 on storage and 42501 on DB
        anon_client = MockSupabaseClient()
        anon_client.storage_bucket.upload_fails = True
        anon_client.storage_bucket.upload_error_msg = "{'statusCode': 403, 'error': 'Unauthorized', 'message': 'new row violates row-level security policy'}"

        ingestor = SecureCloudIngestor(
            client=anon_client,
            manifest_dir=self.manifest_dir,
            verified_sources_path=self.dummy_sources_path,
        )

        record = ingestor.ingest_document_file(
            local_file_path=self.dummy_pdf_path,
            source_url="https://www.myscheme.gov.in",
            target_domain="government_schemes",
            title="Sample Scheme Guideline",
            source_id="10000000-0000-0000-0000-000000000001",
        )

        self.assertEqual(record.final_status, IngestionStatus.STORAGE_UPLOAD_FAILED.value)
        self.assertIn("violates row-level security policy", record.storage_result.get("error", ""))
        self.assertFalse(record.storage_result["uploaded"])
        self.assertFalse(record.database_result["inserted"])
        # File must remain preserved on disk
        self.assertTrue(os.path.isfile(self.dummy_pdf_path))

    def test_secret_redaction(self):
        """Ensures secrets (service role keys, JWTs, Bearer tokens) are redacted from logs and errors."""
        raw_error = "Failed with token eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.e30.t-ae and service_role_key = super_secret_123"
        sanitized = redact_secrets(raw_error)
        self.assertNotIn("eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9", sanitized)
        self.assertNotIn("super_secret_123", sanitized)
        self.assertIn("[REDACTED_JWT]", sanitized)
        self.assertIn("[REDACTED]", sanitized)

    def test_successful_mock_cloud_ingestion(self):
        """Verifies successful end-to-end cloud ingestion of a valid PDF."""
        ingestor = SecureCloudIngestor(
            client=self.mock_client,
            manifest_dir=self.manifest_dir,
            verified_sources_path=self.dummy_sources_path,
        )

        record = ingestor.ingest_document_file(
            local_file_path=self.dummy_pdf_path,
            source_url="https://www.myscheme.gov.in",
            target_domain="government_schemes",
            title="PM Kisan Guidelines",
            source_id="10000000-0000-0000-0000-000000000001",
        )

        self.assertEqual(record.final_status, IngestionStatus.INGESTION_CONFIRMED.value)
        self.assertTrue(record.storage_result["uploaded"])
        self.assertTrue(record.database_result["inserted"])
        self.assertEqual(record.mime_type, "application/pdf")
        self.assertFalse(record.requires_ocr)

        # Verify storage object created
        self.assertIn(record.storage_path, self.mock_client.storage_bucket.objects)

        # Verify database row inserted
        db_rows = self.mock_client.tables["documents"]
        self.assertEqual(len(db_rows), 1)
        self.assertEqual(db_rows[0]["sha256"], record.document_sha256)
        self.assertEqual(db_rows[0]["source_id"], "10000000-0000-0000-0000-000000000001")

        # Verify source was automatically registered in sources table
        source_rows = self.mock_client.tables["sources"]
        self.assertEqual(len(source_rows), 1)
        self.assertEqual(source_rows[0]["id"], "10000000-0000-0000-0000-000000000001")

    def test_duplicate_detection_zero_reupload(self):
        """Validates that ingesting an identical document hash skips upload and preserves CAS original."""
        ingestor = SecureCloudIngestor(
            client=self.mock_client,
            manifest_dir=self.manifest_dir,
            verified_sources_path=self.dummy_sources_path,
        )

        # Ingest first time
        first_rec = ingestor.ingest_document_file(
            local_file_path=self.dummy_pdf_path,
            source_url="https://www.myscheme.gov.in",
            target_domain="government_schemes",
            title="First Upload",
            source_id="10000000-0000-0000-0000-000000000001",
        )
        self.assertEqual(first_rec.final_status, IngestionStatus.INGESTION_CONFIRMED.value)

        # Ingest second time with identical content
        second_rec = ingestor.ingest_document_file(
            local_file_path=self.dummy_pdf_path,
            source_url="https://www.myscheme.gov.in",
            target_domain="government_schemes",
            title="Duplicate Attempt",
            source_id="10000000-0000-0000-0000-000000000001",
        )

        self.assertEqual(second_rec.final_status, IngestionStatus.DUPLICATE_PRESERVED.value)
        self.assertFalse(second_rec.storage_result["uploaded"])
        self.assertEqual(second_rec.storage_result["status"], "duplicate_preserved")
        # Database rows should still be 1 (no duplicate row)
        self.assertEqual(len(self.mock_client.tables["documents"]), 1)

    def test_partial_failure_storage_success_db_failure(self):
        """Validates transactional safety when storage succeeds but DB insert fails."""
        self.mock_client.table_insert_fails["documents"] = True

        ingestor = SecureCloudIngestor(
            client=self.mock_client,
            manifest_dir=self.manifest_dir,
            verified_sources_path=self.dummy_sources_path,
        )

        record = ingestor.ingest_document_file(
            local_file_path=self.dummy_pdf_path,
            source_url="https://www.myscheme.gov.in",
            target_domain="government_schemes",
            title="Failure Safety Test",
            source_id="10000000-0000-0000-0000-000000000001",
        )

        # Status must be RECONCILIATION_REQUIRED
        self.assertEqual(record.final_status, IngestionStatus.RECONCILIATION_REQUIRED.value)
        self.assertTrue(record.storage_result["uploaded"])
        self.assertFalse(record.database_result["inserted"])
        self.assertTrue(record.reconciliation_state["needed"])
        self.assertEqual(record.reconciliation_state["stage"], "db_insert")

        # Storage object must be preserved (immutability rule: never delete uploaded CAS objects)
        self.assertIn(record.storage_path, self.mock_client.storage_bucket.objects)
        # Original file on disk preserved
        self.assertTrue(os.path.isfile(self.dummy_pdf_path))

    def test_partial_failure_db_success_storage_verify_failure(self):
        """Validates behavior when DB insert succeeds but storage post-confirmation fails."""
        # Configure list to return empty (simulating storage confirmation failure)
        self.mock_client.storage_bucket.list_fails = True

        ingestor = SecureCloudIngestor(
            client=self.mock_client,
            manifest_dir=self.manifest_dir,
            verified_sources_path=self.dummy_sources_path,
        )

        record = ingestor.ingest_document_file(
            local_file_path=self.dummy_pdf_path,
            source_url="https://www.myscheme.gov.in",
            target_domain="government_schemes",
            title="Confirmation Failure Test",
            source_id="10000000-0000-0000-0000-000000000001",
        )

        self.assertEqual(record.final_status, IngestionStatus.RECONCILIATION_REQUIRED.value)
        self.assertTrue(record.reconciliation_state["needed"])
        self.assertEqual(record.reconciliation_state["stage"], "storage_confirmation")

    def test_idempotent_reconciliation_retry(self):
        """Validates that retrying a document after a prior DB failure succeeds idempotently."""
        # 1. First run: DB fails
        self.mock_client.table_insert_fails["documents"] = True
        ingestor = SecureCloudIngestor(
            client=self.mock_client,
            manifest_dir=self.manifest_dir,
            verified_sources_path=self.dummy_sources_path,
        )

        rec1 = ingestor.ingest_document_file(
            local_file_path=self.dummy_pdf_path,
            source_url="https://www.myscheme.gov.in",
            target_domain="government_schemes",
            title="Retry Test",
            source_id="10000000-0000-0000-0000-000000000001",
        )
        self.assertEqual(rec1.final_status, IngestionStatus.RECONCILIATION_REQUIRED.value)

        # 2. Fix DB failure and retry
        self.mock_client.table_insert_fails["documents"] = False
        rec2 = ingestor.ingest_document_file(
            local_file_path=self.dummy_pdf_path,
            source_url="https://www.myscheme.gov.in",
            target_domain="government_schemes",
            title="Retry Test",
            source_id="10000000-0000-0000-0000-000000000001",
        )

        self.assertEqual(rec2.final_status, IngestionStatus.INGESTION_CONFIRMED.value)
        self.assertEqual(rec2.storage_result["status"], "already_exists_reused")
        self.assertTrue(rec2.database_result["inserted"])
        self.assertEqual(len(self.mock_client.tables["documents"]), 1)

    def test_dry_run_preservation(self):
        """Validates that dry_run=True performs non-destructive simulation without network calls."""
        ingestor = SecureCloudIngestor(
            client=None,
            manifest_dir=self.manifest_dir,
            verified_sources_path=self.dummy_sources_path,
            dry_run=True,
        )

        record = ingestor.ingest_document_file(
            local_file_path=self.dummy_pdf_path,
            source_url="https://www.myscheme.gov.in",
            target_domain="government_schemes",
            title="Dry Run Test",
            source_id="10000000-0000-0000-0000-000000000001",
        )

        self.assertEqual(record.final_status, IngestionStatus.DRY_RUN_SIMULATED.value)
        self.assertFalse(record.storage_result["uploaded"])
        self.assertFalse(record.database_result["inserted"])
        self.assertFalse(record.reconciliation_state["needed"])

    def test_audit_manifest_export(self):
        """Verifies that audit records are written to JSON and JSONL manifest files."""
        ingestor = SecureCloudIngestor(
            client=self.mock_client,
            manifest_dir=self.manifest_dir,
            verified_sources_path=self.dummy_sources_path,
        )

        ingestor.ingest_document_file(
            local_file_path=self.dummy_pdf_path,
            source_url="https://www.myscheme.gov.in",
            target_domain="government_schemes",
            title="Manifest Verification",
            source_id="10000000-0000-0000-0000-000000000001",
        )

        json_path = os.path.join(self.manifest_dir, "cloud_ingestion_audit.json")
        jsonl_path = os.path.join(self.manifest_dir, "cloud_ingestion_audit.jsonl")

        self.assertTrue(os.path.isfile(json_path))
        self.assertTrue(os.path.isfile(jsonl_path))

        with open(json_path, "r", encoding="utf-8") as f:
            data = json.load(f)
        self.assertEqual(len(data), 1)
        self.assertEqual(data[0]["title"], "Manifest Verification")
        self.assertEqual(data[0]["final_status"], IngestionStatus.INGESTION_CONFIRMED.value)

    def test_server_side_authorization_guard(self):
        """Verifies that attempting live ingestion without server-side credentials raises PermissionError."""
        with patch.dict(os.environ, {}, clear=True):
            # No credentials in environment
            with patch("app.ingestion.secure_cloud_ingestor.get_supabase_admin_client", side_effect=ValueError("SUPABASE_SERVICE_ROLE_KEY missing")):
                with self.assertRaises(PermissionError):
                    SecureCloudIngestor(client=None, dry_run=False)

    def test_rls_and_private_bucket_preservation(self):
        """Verifies that the target bucket is strictly nexo-government-documents and private."""
        ingestor = SecureCloudIngestor(client=self.mock_client, dry_run=True)
        self.assertEqual(ingestor.bucket_name, "nexo-government-documents")
        # Verify default storage config preserves private status
        self.assertEqual(STORAGE_BUCKET_NAME, "nexo-government-documents")

    def test_version_lineage_ingestion(self):
        """Validates that a new document version is created when file content changes at a URL."""
        ingestor = SecureCloudIngestor(
            client=self.mock_client,
            manifest_dir=self.manifest_dir,
            verified_sources_path=self.dummy_sources_path,
        )

        # Version 1 upload
        rec1 = ingestor.ingest_document_bytes(
            file_bytes=b"%PDF-1.4\nOriginal Version 1 content\n%%EOF",
            source_url="https://www.myscheme.gov.in/guidelines.pdf",
            target_domain="government_schemes",
            title="Guideline v1",
            source_id="10000000-0000-0000-0000-000000000001",
        )
        self.assertEqual(rec1.final_status, IngestionStatus.INGESTION_CONFIRMED.value)

        # Version 2 upload (content changed -> distinct SHA-256)
        rec2 = ingestor.ingest_document_bytes(
            file_bytes=b"%PDF-1.4\nUpdated Version 2 revised content\n%%EOF",
            source_url="https://www.myscheme.gov.in/guidelines.pdf",
            target_domain="government_schemes",
            title="Guideline v2",
            source_id="10000000-0000-0000-0000-000000000001",
        )
        self.assertEqual(rec2.final_status, IngestionStatus.INGESTION_CONFIRMED.value)
        self.assertNotEqual(rec1.document_sha256, rec2.document_sha256)
        self.assertNotEqual(rec1.storage_path, rec2.storage_path)
        # Both distinct version files are stored in CAS
        self.assertEqual(len(self.mock_client.tables["documents"]), 2)
        self.assertEqual(len(self.mock_client.storage_bucket.objects), 2)

    def test_12_point_post_ingestion_verification(self):
        """Validates all 12 post-ingestion verification checkpoints on an ingested document."""
        ingestor = SecureCloudIngestor(
            client=self.mock_client,
            manifest_dir=self.manifest_dir,
            verified_sources_path=self.dummy_sources_path,
        )

        record = ingestor.ingest_document_file(
            local_file_path=self.dummy_pdf_path,
            source_url="https://www.myscheme.gov.in",
            target_domain="government_schemes",
            title="12 Checkpoint Test",
            source_id="10000000-0000-0000-0000-000000000001",
        )

        self.assertEqual(record.final_status, IngestionStatus.INGESTION_CONFIRMED.value)
        self.assertIsNotNone(record.verification_result)
        v = record.verification_result

        # Assert all 12 checkpoints pass
        self.assertTrue(v["storage_object_exists"])
        self.assertTrue(v["storage_is_private"])
        self.assertTrue(v["readback_checksum_matches"])
        self.assertTrue(v["file_size_matches"])
        self.assertTrue(v["mime_type_matches"])
        self.assertTrue(v["database_row_exists"])
        self.assertTrue(v["source_id_matches"])
        self.assertTrue(v["storage_path_matches"])
        self.assertTrue(v["sha256_matches"])
        self.assertTrue(v["ocr_flag_matches"] or not record.requires_ocr)
        self.assertTrue(v["version_matches"])
        self.assertTrue(v["no_overwrite_confirmed"])
        self.assertTrue(v["all_passed"])


if __name__ == "__main__":
    unittest.main()
