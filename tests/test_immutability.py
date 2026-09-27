"""
NEXO Data Platform - Document Immutability & Versioning Test Suite
Validates zero-overwrite guarantees, content-addressable storage, duplicate preservation,
and version lineage tracking 100% offline.
"""

import os
import sys
import tempfile
import unittest

# Ensure project root is in sys.path
project_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if project_root not in sys.path:
    sys.path.insert(0, project_root)

from app.ingestion.document_ingestion import DocumentIngestor, IngestionResult
from app.ingestion.manifest import ManifestManager, ManifestRecord
from app.ingestion.exceptions import ImmutableDocumentViolationError
from app.storage.supabase_storage import upload_document, generate_storage_path


class TestDocumentImmutability(unittest.TestCase):
    """Proves that existing documents cannot be overwritten or mutated."""

    def setUp(self):
        self.temp_dir = tempfile.mkdtemp()
        self.manifest_path = os.path.join(self.temp_dir, "manifest.jsonl")
        self.manifest = ManifestManager(self.manifest_path)
        self.ingestor = DocumentIngestor(
            manifest_manager=self.manifest,
            local_staging_dir=os.path.join(self.temp_dir, "processed"),
        )

    def tearDown(self):
        import shutil
        shutil.rmtree(self.temp_dir, ignore_errors=True)

    def test_existing_storage_path_cannot_be_overwritten(self):
        """Rule 1 & 2: Overwrite attempts must raise ImmutableDocumentViolationError."""
        mock_registry = set()
        storage_path = "agriculture_rural_sustainability/agricoop/sample_hash.pdf"

        # Initial upload succeeds
        res = upload_document(
            file_content=b"original government circular content v1",
            storage_path=storage_path,
            content_type="application/pdf",
            dry_run=True,
            mock_registry=mock_registry,
        )
        self.assertEqual(res["status"], "staged_dry_run")
        self.assertIn(storage_path, mock_registry)

        # Attempting to upload again to the identical storage path MUST raise ImmutableDocumentViolationError
        with self.assertRaises(ImmutableDocumentViolationError):
            upload_document(
                file_content=b"malicious or accidental overwrite attempt",
                storage_path=storage_path,
                content_type="application/pdf",
                dry_run=True,
                mock_registry=mock_registry,
            )

    def test_identical_sha256_detected_as_duplicate_without_duplicate_files(self):
        """Rule 4: Identical SHA-256 is audited as duplicate, preserving the original."""
        source_url = "https://agricoop.nic.in/guidelines/pacs.pdf"
        content_v1 = b"%PDF-1.4\nOfficial PACS Model Bylaws 2024..."

        # First ingestion
        result1 = self.ingestor.ingest_bytes(
            content=content_v1,
            source_url=source_url,
            target_domain="Cooperative Governance",
            title="PACS Model Bylaws 2024",
            source_id="mocoop",
            stage_locally=True,
        )
        self.assertEqual(result1.version, 1)
        self.assertFalse(result1.is_duplicate)
        self.assertEqual(result1.processing_status, "staged")
        initial_storage_path = result1.storage_path
        initial_sha256 = result1.sha256

        # Second ingestion with identical content
        result2 = self.ingestor.ingest_bytes(
            content=content_v1,
            source_url=source_url,
            target_domain="Cooperative Governance",
            title="PACS Model Bylaws 2024 Re-scrape",
            source_id="mocoop",
            stage_locally=True,
        )

        # Must be flagged as duplicate
        self.assertTrue(result2.is_duplicate)
        self.assertEqual(result2.processing_status, "duplicate_preserved")
        self.assertEqual(result2.sha256, initial_sha256)
        self.assertEqual(result2.storage_path, initial_storage_path)
        self.assertIsNone(result2.staged_local_path)  # Did not write a duplicate file

        # Check that duplicate audit count was incremented in manifest
        records = self.manifest.load_records()
        self.assertEqual(len(records), 1)  # No redundant manifest entry created
        self.assertEqual(records[0].duplicate_check_count, 1)
        self.assertIsNotNone(records[0].last_verified_at)

    def test_updated_content_creates_new_version_preserving_old(self):
        """Rule 5: Official update preserves old document, assigns new version & new SHA-256."""
        source_url = "https://rural.nic.in/schemes/pmay-g.pdf"
        content_v1 = b"%PDF-1.4\nPMAY-G Guidelines 2023 Original..."
        content_v2 = b"%PDF-1.4\nPMAY-G Guidelines 2024 Revised Amendment with new subsidy amounts..."

        # 1. Ingest Version 1
        res_v1 = self.ingestor.ingest_bytes(
            content=content_v1,
            source_url=source_url,
            target_domain="Rural Development and Financial Assistance",
            title="PMAY-G Operational Guidelines",
            source_id="mord",
            stage_locally=True,
        )
        self.assertEqual(res_v1.version, 1)
        sha_v1 = res_v1.sha256
        path_v1 = res_v1.storage_path

        # 2. Ingest Version 2 (Updated content published at the same source URL)
        res_v2 = self.ingestor.ingest_bytes(
            content=content_v2,
            source_url=source_url,
            target_domain="Rural Development and Financial Assistance",
            title="PMAY-G Operational Guidelines (Revised)",
            source_id="mord",
            stage_locally=True,
        )

        # Version 2 assertions
        self.assertEqual(res_v2.version, 2)
        self.assertFalse(res_v2.is_duplicate)
        self.assertNotEqual(res_v2.sha256, sha_v1)
        self.assertNotEqual(res_v2.storage_path, path_v1)
        self.assertTrue(res_v2.storage_path.endswith(f"{res_v2.sha256}.pdf"))

        # Database record must link back to previous_sha256
        db_rec_v2 = res_v2.document_db_record
        self.assertEqual(db_rec_v2["version"], 2)
        self.assertEqual(db_rec_v2["previous_sha256"], sha_v1)
        self.assertTrue(db_rec_v2["is_current"])

        # 3. Verify Complete Audit Trail Lineage in Manifest
        lineage = self.manifest.get_lineage_by_url(source_url)
        self.assertEqual(len(lineage), 2)

        # Version 1 state in lineage
        record_v1 = lineage[0]
        self.assertEqual(record_v1.version, 1)
        self.assertEqual(record_v1.sha256, sha_v1)
        self.assertEqual(record_v1.storage_path, path_v1)
        self.assertFalse(record_v1.is_current)  # Deprecated in favor of v2

        # Version 2 state in lineage
        record_v2 = lineage[1]
        self.assertEqual(record_v2.version, 2)
        self.assertEqual(record_v2.sha256, res_v2.sha256)
        self.assertEqual(record_v2.previous_sha256, sha_v1)
        self.assertEqual(record_v2.previous_storage_path, path_v1)
        self.assertTrue(record_v2.is_current)

    def test_old_version_remains_preserved_and_accessible(self):
        """Verifies old physical files on disk remain untouched when new versions arrive."""
        source_url = "https://agricoop.nic.in/schemes/kcc.pdf"
        v1_bytes = b"%PDF-1.4\nKisan Credit Card 2023..."
        v2_bytes = b"%PDF-1.4\nKisan Credit Card 2024 Revised..."

        res1 = self.ingestor.ingest_bytes(
            content=v1_bytes,
            source_url=source_url,
            target_domain="Agriculture and Rural Sustainability",
            title="KCC Guidelines",
            stage_locally=True,
        )
        v1_file_path = res1.staged_local_path
        self.assertTrue(os.path.exists(v1_file_path))

        res2 = self.ingestor.ingest_bytes(
            content=v2_bytes,
            source_url=source_url,
            target_domain="Agriculture and Rural Sustainability",
            title="KCC Guidelines 2024",
            stage_locally=True,
        )
        v2_file_path = res2.staged_local_path
        self.assertTrue(os.path.exists(v2_file_path))

        # Both physical files must exist and be distinct
        self.assertNotEqual(v1_file_path, v2_file_path)
        self.assertTrue(os.path.exists(v1_file_path))
        self.assertTrue(os.path.exists(v2_file_path))

        # Content of v1 must be strictly intact
        with open(v1_file_path, "rb") as f:
            self.assertEqual(f.read(), v1_bytes)
        with open(v2_file_path, "rb") as f:
            self.assertEqual(f.read(), v2_bytes)


if __name__ == "__main__":
    unittest.main()
