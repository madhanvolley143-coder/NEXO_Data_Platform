"""
NEXO Data Platform - Database Schema & Source Registry Reconciliation Unit Tests
Tests database schema compatibility, source manifest to DB mapping, deterministic source IDs,
source seeding idempotency, document versioning fields, source registration bugfix,
and orphan storage reconciliation. Completely offline with zero live network calls.
"""

import os
import json
import uuid
import tempfile
import shutil
import unittest
from unittest.mock import MagicMock, patch

from app.sources.onboarding import prepare_supabase_record
from app.sources.models import SourceRecord
from app.ingestion.db_preparer import prepare_document_record
from app.ingestion.secure_cloud_ingestor import (
    SecureCloudIngestor,
    IngestionStatus,
    redact_secrets,
)
from scripts.seed_verified_sources import (
    load_verified_sources_manifest,
    seed_verified_sources,
)


class MockTableQuery:
    def __init__(self, table_name: str, table_data: list, insert_fails: bool = False):
        self.table_name = table_name
        self.table_data = table_data
        self.insert_fails = insert_fails
        self.filter_col = None
        self.filter_val = None
        self.last_inserted = None

    def select(self, *columns):
        return self

    def eq(self, column: str, value: any):
        self.filter_col = column
        self.filter_val = str(value).lower()
        return self

    def insert(self, payload: dict):
        if self.insert_fails:
            raise Exception("Simulated database insert failure")
        row = dict(payload)
        if "id" not in row or not row["id"]:
            row["id"] = f"mock-uuid-{len(self.table_data) + 1}"
        self.table_data.append(row)
        self.last_inserted = row
        return self

    def upsert(self, payloads: list, on_conflict: str = "id"):
        if not isinstance(payloads, list):
            payloads = [payloads]
        for p in payloads:
            existing = next((r for r in self.table_data if r.get(on_conflict) == p.get(on_conflict)), None)
            if existing:
                existing.update(p)
            else:
                self.table_data.append(dict(p))
        mock_res = MagicMock()
        mock_res.data = list(self.table_data)
        return mock_res

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


class MockStorageBucket:
    def __init__(self, bucket_name: str = "nexo-government-documents"):
        self.bucket_name = bucket_name
        self.objects = {}
        self.upload_fails = False

    def upload(self, path: str, file: bytes, file_options: dict = None):
        if self.upload_fails:
            raise Exception("Simulated storage upload failure")
        self.objects[path] = file
        return {"Key": path}

    def list(self, folder: str = ""):
        prefix = f"{folder}/" if folder and not folder.endswith("/") else folder
        matching = []
        for obj_path in self.objects.keys():
            if not folder or obj_path.startswith(prefix):
                rel_name = obj_path[len(prefix):] if folder else obj_path
                if "/" not in rel_name:
                    matching.append({"name": rel_name})
        return matching

    def download(self, path: str) -> bytes:
        if path not in self.objects:
            raise Exception(f"Storage object not found: {path}")
        return self.objects[path]


class MockStorageClient:
    def __init__(self, bucket: MockStorageBucket):
        self.bucket = bucket

    def from_(self, bucket_name: str):
        return self.bucket

    def get_bucket(self, bucket_name: str):
        mock_b = MagicMock()
        mock_b.id = bucket_name
        mock_b.name = bucket_name
        mock_b.public = False
        return mock_b


class MockSupabaseClient:
    def __init__(self):
        self.storage_bucket = MockStorageBucket()
        self.storage = MockStorageClient(self.storage_bucket)
        self.tables = {
            "sources": [],
            "documents": [],
            "schemes": [],
            "scheme_versions": [],
        }

    def table(self, table_name: str) -> MockTableQuery:
        self.tables.setdefault(table_name, [])
        return MockTableQuery(table_name, self.tables[table_name])


class TestSchemaReconciliation(unittest.TestCase):
    """Unit tests validating full database and application schema reconciliation."""

    def setUp(self):
        self.test_dir = tempfile.mkdtemp()
        self.manifest_dir = os.path.join(self.test_dir, "manifests")
        os.makedirs(self.manifest_dir, exist_ok=True)
        self.mock_client = MockSupabaseClient()

        # Dummy document
        self.dummy_pdf_path = os.path.join(self.test_dir, "test.pdf")
        self.dummy_pdf_content = b"%PDF-1.4\n%NEXO Test Reconciled Content\n%%EOF"
        with open(self.dummy_pdf_path, "wb") as f:
            f.write(self.dummy_pdf_content)

        # Verified sources path
        self.verified_sources_path = os.path.join("data", "manifests", "sources", "verified_sources.json")

    def tearDown(self):
        shutil.rmtree(self.test_dir, ignore_errors=True)

    def test_source_manifest_to_db_mapping(self):
        """Validates that all 23 verified sources map to all 17 database columns without errors."""
        sources = load_verified_sources_manifest(self.verified_sources_path)
        self.assertEqual(len(sources), 23)

        expected_cols = {
            "id", "name", "url", "domain", "language", "authority_level",
            "organization_name", "country", "state", "verification_status",
            "verification_method", "verification_notes", "is_active",
            "last_verified_at", "last_checked_at", "created_at", "updated_at"
        }

        for source_raw in sources:
            db_payload = prepare_supabase_record(source_raw)
            # Check all 17 keys are present
            self.assertEqual(set(db_payload.keys()), expected_cols)
            # Check mandatory values are non-empty
            self.assertTrue(db_payload["id"])
            self.assertTrue(db_payload["name"])
            self.assertTrue(db_payload["url"])
            self.assertTrue(db_payload["domain"])
            self.assertEqual(db_payload["verification_status"], "VERIFIED")
            self.assertTrue(db_payload["is_active"])

    def test_deterministic_source_ids_preserved(self):
        """Ensures that deterministic source IDs are valid UUIDs and preserve domain prefix."""
        sources = load_verified_sources_manifest(self.verified_sources_path)
        for s in sources:
            sid = s["id"]
            # Validate valid UUID format
            parsed = uuid.UUID(sid)
            self.assertEqual(str(parsed), sid)
            # Verify deterministic format e.g. 10000000-0000-...
            self.assertTrue(sid.endswith("-0000-0000-0000-000000000001") or
                            sid.endswith("-0000-0000-0000-000000000002") or
                            sid.endswith("-0000-0000-0000-000000000003") or
                            sid.endswith("-0000-0000-0000-000000000004"))

    def test_source_seeding_idempotency(self):
        """Verifies that seeding sources is completely idempotent."""
        # First seed
        res1 = seed_verified_sources(
            manifest_path=self.verified_sources_path,
            dry_run=False,
            client=self.mock_client,
        )
        self.assertTrue(res1["success"])
        self.assertEqual(len(self.mock_client.tables["sources"]), 23)

        # Second seed (upsert)
        res2 = seed_verified_sources(
            manifest_path=self.verified_sources_path,
            dry_run=False,
            client=self.mock_client,
        )
        self.assertTrue(res2["success"])
        # Still exactly 23 rows (no duplicates)
        self.assertEqual(len(self.mock_client.tables["sources"]), 23)

    def test_documents_version_compatibility(self):
        """Ensures document records include versioning fields expected by PostgreSQL and application."""
        doc_record = prepare_document_record(
            title="Test Doc",
            source_url="https://tn.gov.in/test.pdf",
            target_domain="government_schemes",
            mime_type="application/pdf",
            file_size=1234,
            sha256="abc123hash",
            storage_path="path/to/doc.pdf",
            version=2,
            previous_sha256="prevhash123",
            is_current=True,
        )

        self.assertEqual(doc_record["version"], 2)
        self.assertEqual(doc_record["previous_sha256"], "prevhash123")
        self.assertTrue(doc_record["is_current"])

        # Check VALID_DOCUMENTS_COLUMNS in SecureCloudIngestor
        self.assertIn("version", SecureCloudIngestor.VALID_DOCUMENTS_COLUMNS)
        self.assertIn("previous_sha256", SecureCloudIngestor.VALID_DOCUMENTS_COLUMNS)
        self.assertIn("is_current", SecureCloudIngestor.VALID_DOCUMENTS_COLUMNS)

    def test_source_registration_bug_fixed(self):
        """Regression test ensuring _ensure_source_registered handles verified manifest schemas."""
        ingestor = SecureCloudIngestor(
            client=self.mock_client,
            manifest_dir=self.manifest_dir,
            verified_sources_path=self.verified_sources_path,
        )

        # Ensure Tamil Nadu source (10000000-0000-0000-0000-000000000003) registers without 'name' KeyError
        ingestor._ensure_source_registered("10000000-0000-0000-0000-000000000003")

        source_rows = self.mock_client.tables["sources"]
        self.assertEqual(len(source_rows), 1)
        self.assertEqual(source_rows[0]["id"], "10000000-0000-0000-0000-000000000003")
        self.assertEqual(source_rows[0]["name"], "Government of Tamil Nadu Official Portal")
        self.assertEqual(source_rows[0]["domain"], "government_schemes")
        self.assertEqual(source_rows[0]["url"], "https://www.tn.gov.in")

    def test_orphan_storage_reconciliation(self):
        """Validates that existing Storage objects are detected, not overwritten, and reconciled into DB."""
        ingestor = SecureCloudIngestor(
            client=self.mock_client,
            manifest_dir=self.manifest_dir,
            verified_sources_path=self.verified_sources_path,
        )

        # Pre-seed storage object (simulate orphaned binary from prior run)
        import hashlib
        file_sha256 = hashlib.sha256(self.dummy_pdf_content).hexdigest()
        storage_path = f"government_schemes/10000000-0000-0000-0000-000000000001/{file_sha256}.pdf"
        self.mock_client.storage_bucket.objects[storage_path] = self.dummy_pdf_content

        # Execute ingestion for this file
        record = ingestor.ingest_document_file(
            local_file_path=self.dummy_pdf_path,
            source_url="https://www.myscheme.gov.in/test.pdf",
            target_domain="government_schemes",
            title="Orphan Storage Reconciliation Test",
            source_id="10000000-0000-0000-0000-000000000001",
        )

        # Ingestion must be confirmed
        self.assertEqual(record.final_status, IngestionStatus.INGESTION_CONFIRMED.value)
        # Storage must be marked as already_exists_reused (NOT re-uploaded, NOT overwritten)
        self.assertEqual(record.storage_result["status"], "already_exists_reused")
        # Database row must be created and reconciled
        self.assertTrue(record.database_result["inserted"])
        self.assertEqual(len(self.mock_client.tables["documents"]), 1)
        self.assertEqual(self.mock_client.tables["documents"][0]["sha256"], file_sha256)


if __name__ == "__main__":
    unittest.main()
