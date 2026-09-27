"""
NEXO Data Platform - Ingestion Foundation Test Suite
Runs 100% offline with zero live network or Supabase dependencies.
"""

import io
import json
import logging
import os
import sys
import tempfile
import unittest

# Ensure project root is in sys.path
project_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if project_root not in sys.path:
    sys.path.insert(0, project_root)

from config.storage_config import (
    STORAGE_BUCKET_NAME,
    DOMAIN_TO_FOLDER_MAP,
    get_domain_folder,
    is_supported_mime,
    is_ocr_mime,
)
from config.logging_config import setup_logging, CredentialSanitizingFilter
from app.ingestion.format_detector import (
    calculate_sha256,
    detect_format,
    _heuristic_pdf_requires_ocr,
)
from app.ingestion.validation import (
    validate_sha256,
    validate_source_url,
    validate_target_domain,
    validate_file_size,
    validate_mime_type,
    validate_metadata,
    check_duplicate_sha256,
)
from app.ingestion.manifest import ManifestRecord, ManifestManager
from app.ingestion.document_ingestion import DocumentIngestor, IngestionResult
from app.ingestion.exceptions import (
    ValidationError,
    DuplicateDocumentError,
    UnsupportedFormatError,
    CorruptedFileError,
    StorageUploadError,
)
from app.ingestion.db_preparer import (
    prepare_document_record,
    prepare_source_record,
    prepare_scheme_record,
    prepare_scheme_version_record,
    prepare_sync_log_record,
)
from app.storage.supabase_storage import (
    generate_storage_path,
    upload_document,
    document_exists,
)


class TestStorageConfiguration(unittest.TestCase):
    """Verifies storage bucket names and folder slug mappings for all 7 domains."""

    def test_bucket_name(self):
        self.assertEqual(STORAGE_BUCKET_NAME, "nexo-government-documents")

    def test_all_seven_domains_mapped(self):
        expected_domains = [
            "Government Schemes",
            "Cooperative Governance",
            "Agriculture and Rural Sustainability",
            "FoodTech / Cold-chain / Rural Logistics",
            "Rural Development and Financial Assistance",
            "Legal Assistance / Grievance Redressal",
            "Multilingual government information",
        ]
        for domain in expected_domains:
            self.assertIn(domain, DOMAIN_TO_FOLDER_MAP)
            slug = get_domain_folder(domain)
            self.assertTrue(len(slug) > 0)
            self.assertFalse(" " in slug)  # Slugs must not contain spaces

    def test_invalid_domain_raises(self):
        with self.assertRaises(ValueError):
            get_domain_folder("Nonexistent Space Domain")


class TestFormatAndMimeDetection(unittest.TestCase):
    """Validates magic-byte inspection and OCR detection across supported formats."""

    def test_pdf_detection(self):
        pdf_bytes = b"%PDF-1.4 Mock document text streams..."
        result = detect_format(pdf_bytes, "test.pdf")
        self.assertEqual(result.mime_type, "application/pdf")
        self.assertEqual(result.extension, ".pdf")
        self.assertFalse(result.requires_ocr)

    def test_scanned_pdf_ocr_heuristic(self):
        scanned_pdf = b"%PDF-1.4\n1 0 obj\n<< /Type /XObject /Subtype /Image >>\nendobj\n"
        result = detect_format(scanned_pdf, "scanned.pdf")
        self.assertEqual(result.mime_type, "application/pdf")
        self.assertTrue(result.requires_ocr)

    def test_image_formats_require_ocr(self):
        # PNG
        png_bytes = b"\x89PNG\r\n\x1a\n\x00\x00\x00\rIHDR"
        res_png = detect_format(png_bytes, "scan.png")
        self.assertEqual(res_png.mime_type, "image/png")
        self.assertTrue(res_png.requires_ocr)

        # JPEG
        jpeg_bytes = b"\xff\xd8\xff\xe0\x00\x10JFIF"
        res_jpeg = detect_format(jpeg_bytes, "circular.jpg")
        self.assertEqual(res_jpeg.mime_type, "image/jpeg")
        self.assertTrue(res_jpeg.requires_ocr)

        # TIFF
        tiff_bytes = b"II*\x00\x08\x00\x00\x00"
        res_tiff = detect_format(tiff_bytes, "gazette.tiff")
        self.assertEqual(res_tiff.mime_type, "image/tiff")
        self.assertTrue(res_tiff.requires_ocr)

        # WebP
        webp_bytes = b"RIFF\x18\x00\x00\x00WEBPVP8 "
        res_webp = detect_format(webp_bytes, "photo.webp")
        self.assertEqual(res_webp.mime_type, "image/webp")
        self.assertTrue(res_webp.requires_ocr)

    def test_docx_detection(self):
        docx_bytes = b"PK\x03\x04\x14\x00\x06\x00word/document.xml[Content_Types].xml"
        result = detect_format(docx_bytes, "guidelines.docx")
        self.assertEqual(
            result.mime_type,
            "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
        )
        self.assertEqual(result.extension, ".docx")
        self.assertFalse(result.requires_ocr)

    def test_json_detection(self):
        json_bytes = b'{"scheme_id": "PM-KISAN", "active": true}'
        result = detect_format(json_bytes, "data.json")
        self.assertEqual(result.mime_type, "application/json")
        self.assertEqual(result.extension, ".json")
        self.assertFalse(result.requires_ocr)

    def test_xml_detection(self):
        xml_bytes = b'<?xml version="1.0"?><scheme><name>PACS</name></scheme>'
        result = detect_format(xml_bytes, "feed.xml")
        self.assertEqual(result.mime_type, "application/xml")
        self.assertEqual(result.extension, ".xml")

    def test_html_detection(self):
        html_bytes = b'<!DOCTYPE html><html><body>Govt Portal</body></html>'
        result = detect_format(html_bytes, "index.html")
        self.assertEqual(result.mime_type, "text/html")
        self.assertEqual(result.extension, ".html")

    def test_csv_detection(self):
        csv_bytes = b"id,name,amount\n1,Sub-Mission,50000\n2,Credit Guarantee,20000\n"
        result = detect_format(csv_bytes, "table.csv")
        self.assertEqual(result.mime_type, "text/csv")
        self.assertEqual(result.extension, ".csv")

    def test_txt_detection(self):
        txt_bytes = b"Official Circular: Notice of revised agricultural subsidies 2024."
        result = detect_format(txt_bytes, "notice.txt")
        self.assertEqual(result.mime_type, "text/plain")
        self.assertEqual(result.extension, ".txt")


class TestValidationFunctions(unittest.TestCase):
    """Verifies metadata validation, URL validation, and SHA-256 checks."""

    def test_valid_sha256(self):
        valid_hash = "a" * 64
        self.assertTrue(validate_sha256(valid_hash))

    def test_invalid_sha256_raises(self):
        with self.assertRaises(ValidationError):
            validate_sha256("short_hash")
        with self.assertRaises(ValidationError):
            validate_sha256("g" * 64)  # Invalid non-hex char

    def test_valid_urls(self):
        self.assertTrue(validate_source_url("https://agricoop.nic.in/en/guidelines.pdf"))
        self.assertTrue(validate_source_url("http://ncdc.gov.in/schemes"))

    def test_invalid_urls_raise(self):
        with self.assertRaises(ValidationError):
            validate_source_url("ftp://server/file.pdf")
        with self.assertRaises(ValidationError):
            validate_source_url("just_a_string")
        with self.assertRaises(ValidationError):
            validate_source_url("")

    def test_file_size_validation(self):
        self.assertTrue(validate_file_size(1024))
        with self.assertRaises(CorruptedFileError):
            validate_file_size(0)
        with self.assertRaises(CorruptedFileError):
            validate_file_size(-50)
        with self.assertRaises(ValidationError):
            validate_file_size(200 * 1024 * 1024)  # Exceeds max limit

    def test_duplicate_sha256_detection(self):
        existing = {"1111" + "a" * 60, "2222" + "b" * 60}
        new_hash = "3333" + "c" * 60
        self.assertFalse(check_duplicate_sha256(new_hash, existing))

        with self.assertRaises(DuplicateDocumentError):
            check_duplicate_sha256("1111" + "a" * 60, existing)


class TestManifestSystem(unittest.TestCase):
    """Validates manifest recording in both JSON and JSONL formats."""

    def setUp(self):
        self.temp_dir = tempfile.mkdtemp()

    def tearDown(self):
        import shutil
        shutil.rmtree(self.temp_dir, ignore_errors=True)

    def test_manifest_jsonl_lifecycle(self):
        manifest_path = os.path.join(self.temp_dir, "test_manifest.jsonl")
        manager = ManifestManager(manifest_path)

        record1 = ManifestRecord(
            source_url="https://agricoop.nic.in/pmkisan.pdf",
            title="PM-KISAN Guidelines",
            target_domain="Agriculture and Rural Sustainability",
            mime_type="application/pdf",
            file_size=54321,
            sha256="a" * 64,
            storage_path="agriculture_rural_sustainability/general/" + "a" * 64 + ".pdf",
        )
        manager.append_record(record1)

        self.assertTrue(manager.has_sha256("a" * 64))
        self.assertFalse(manager.has_sha256("b" * 64))

        records = manager.load_records()
        self.assertEqual(len(records), 1)
        self.assertEqual(records[0].title, "PM-KISAN Guidelines")

        # Update status
        updated = manager.update_status("a" * 64, "uploaded")
        self.assertTrue(updated)
        reloaded = manager.load_records()
        self.assertEqual(reloaded[0].processing_status, "uploaded")

    def test_manifest_json_lifecycle(self):
        manifest_path = os.path.join(self.temp_dir, "test_manifest.json")
        manager = ManifestManager(manifest_path)

        record = ManifestRecord(
            source_url="https://cooperation.gov.in/bylaws.docx",
            title="PACS Model Bylaws",
            target_domain="Cooperative Governance",
            mime_type="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
            file_size=12345,
            sha256="c" * 64,
            storage_path="cooperative_governance/general/" + "c" * 64 + ".docx",
        )
        manager.append_record(record)
        self.assertTrue(manager.has_sha256("c" * 64))

        records = manager.load_records()
        self.assertEqual(len(records), 1)
        self.assertEqual(records[0].title, "PACS Model Bylaws")


class TestDocumentIngestor(unittest.TestCase):
    """Tests the full DocumentIngestor processor workflow offline."""

    def setUp(self):
        self.temp_dir = tempfile.mkdtemp()
        self.manifest_path = os.path.join(self.temp_dir, "manifest.jsonl")
        self.manifest_manager = ManifestManager(self.manifest_path)
        self.ingestor = DocumentIngestor(
            manifest_manager=self.manifest_manager,
            local_staging_dir=os.path.join(self.temp_dir, "processed"),
        )

    def tearDown(self):
        import shutil
        shutil.rmtree(self.temp_dir, ignore_errors=True)

    def test_ingest_bytes_workflow(self):
        pdf_content = b"%PDF-1.4\nGovernment Welfare Scheme Guidelines Content..."
        result = self.ingestor.ingest_bytes(
            content=pdf_content,
            source_url="https://rural.nic.in/schemes/guidelines.pdf",
            target_domain="Rural Development and Financial Assistance",
            title="National Rural Livelihood Mission Guidelines",
            source_id="mord_portal",
            stage_locally=True,
        )

        self.assertIsInstance(result, IngestionResult)
        self.assertEqual(result.mime_type, "application/pdf")
        self.assertFalse(result.requires_ocr)
        self.assertTrue(result.storage_path.startswith("rural_development_finance/mord_portal/"))
        self.assertTrue(result.storage_path.endswith(".pdf"))
        self.assertTrue(self.manifest_manager.has_sha256(result.sha256))

        # Check database record payload structure
        db_rec = result.document_db_record
        self.assertEqual(db_rec["title"], "National Rural Livelihood Mission Guidelines")
        self.assertEqual(db_rec["sha256"], result.sha256)
        self.assertEqual(db_rec["source_id"], "mord_portal")
        self.assertTrue(db_rec["is_active"])

    def test_duplicate_prevention(self):
        content = b"<!DOCTYPE html><html><body>Government Notification</body></html>"
        self.ingestor.ingest_bytes(
            content=content,
            source_url="https://lawmin.gov.in/notice.html",
            target_domain="Legal Assistance / Grievance Redressal",
            title="Lok Adalat Notification",
        )

        # Under the same URL: handled via immutable duplicate preservation (Rule 4)
        res_same = self.ingestor.ingest_bytes(
            content=content,
            source_url="https://lawmin.gov.in/notice.html",
            target_domain="Legal Assistance / Grievance Redressal",
            title="Lok Adalat Notification Rescrape",
        )
        self.assertTrue(res_same.is_duplicate)
        self.assertEqual(res_same.processing_status, "duplicate_preserved")

        # Under a different URL: raises DuplicateDocumentError to prevent identical files under disparate URLs
        with self.assertRaises(DuplicateDocumentError):
            self.ingestor.ingest_bytes(
                content=content,
                source_url="https://lawmin.gov.in/another_page.html",
                target_domain="Legal Assistance / Grievance Redressal",
                title="Cross-URL Duplicate",
                allow_duplicates=False,
            )


class TestStorageInterface(unittest.TestCase):
    """Verifies storage path generation and dry-run safety."""

    def test_generate_storage_path(self):
        path = generate_storage_path(
            domain="FoodTech / Cold-chain / Rural Logistics",
            source_id="mofpi_gov",
            sha256="d" * 64,
            extension=".pdf",
        )
        self.assertEqual(
            path,
            f"foodtech_coldchain/mofpi_gov/{'d' * 64}.pdf",
        )

    def test_dry_run_upload_safety(self):
        # Must return staged_dry_run without calling any remote API
        res = upload_document(
            file_content=b"sample document data",
            storage_path="government_schemes/general/mock.pdf",
            content_type="application/pdf",
            dry_run=True,
        )
        self.assertEqual(res["status"], "staged_dry_run")
        self.assertFalse(res["uploaded"])
        self.assertEqual(res["file_size"], 20)

    def test_empty_content_upload_raises(self):
        with self.assertRaises(StorageUploadError):
            upload_document(
                file_content=b"",
                storage_path="test/empty.txt",
                content_type="text/plain",
                dry_run=True,
            )


class TestDatabasePreparer(unittest.TestCase):
    """Verifies payload generation for all 5 core tables."""

    def test_prepare_document_record(self):
        rec = prepare_document_record(
            title="Cold Storage Scheme Circular",
            source_url="https://mofpi.gov.in/circular.pdf",
            target_domain="FoodTech / Cold-chain / Rural Logistics",
            mime_type="application/pdf",
            file_size=4096,
            sha256="e" * 64,
            storage_path="foodtech_coldchain/general/" + "e" * 64 + ".pdf",
        )
        self.assertEqual(rec["title"], "Cold Storage Scheme Circular")
        self.assertEqual(rec["file_size"], 4096)
        self.assertTrue(rec["is_active"])

    def test_prepare_source_record(self):
        rec = prepare_source_record(
            name="Ministry of Agriculture",
            url="https://agricoop.nic.in",
            domain="Agriculture and Rural Sustainability",
            authority_level="central",
        )
        self.assertEqual(rec["authority_level"], "central")
        self.assertEqual(rec["domain"], "Agriculture and Rural Sustainability")

    def test_prepare_scheme_record(self):
        rec = prepare_scheme_record(
            name="PM Kisan Samman Nidhi",
            domain="Agriculture and Rural Sustainability",
            government_level="central",
            official_url="https://pmkisan.gov.in",
        )
        self.assertEqual(rec["name"], "PM Kisan Samman Nidhi")
        self.assertEqual(rec["government_level"], "central")

    def test_prepare_scheme_version_record(self):
        rec = prepare_scheme_version_record(
            scheme_id="scheme-uuid-1234",
            version_number=1,
            content_hash="f" * 64,
            snapshot={"name": "PM Kisan", "benefit": "6000 INR"},
        )
        self.assertEqual(rec["version_number"], 1)
        self.assertTrue(rec["is_current"])
        self.assertEqual(rec["snapshot"]["benefit"], "6000 INR")

    def test_prepare_sync_log_record(self):
        rec = prepare_sync_log_record(
            status="completed",
            documents_found=15,
            documents_added=12,
            documents_updated=3,
        )
        self.assertEqual(rec["status"], "completed")
        self.assertEqual(rec["documents_found"], 15)
        self.assertEqual(rec["documents_added"], 12)


class TestCredentialSanitization(unittest.TestCase):
    """Verifies that sensitive credentials are never logged."""

    def test_credential_sanitizer_filter(self):
        sanitizer = CredentialSanitizingFilter()
        log_record = logging.LogRecord(
            name="nexo.test",
            level=logging.INFO,
            pathname="",
            lineno=0,
            msg="Connecting using token eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.dummy and key sbp_secret12345",
            args=(),
            exc_info=None,
        )
        sanitizer.filter(log_record)
        self.assertNotIn("sbp_secret12345", log_record.msg)
        self.assertNotIn("eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9", log_record.msg)
        self.assertIn("[REDACTED_KEY]", log_record.msg)


if __name__ == "__main__":
    unittest.main()
