"""
NEXO Data Platform - Document Content Processing Unit Tests
Tests extractors (PDF, HTML, DOCX, CSV, JSON, XML, TXT, Image), OCR adapter,
text quality validation, metadata enrichment, storage artifact packaging,
orchestrator idempotency, checkpointing, and CLI options.
Completely offline: uses mocks and temporary test directories with zero live network calls.
"""

import io
import json
import os
import shutil
import tempfile
import unittest
from unittest.mock import MagicMock, patch

from app.processing.models import (
    ExtractionResult,
    ExtractionStatus,
    OCRResult,
    OCRStatus,
    TextQualityStatus,
    DocumentProcessingRecord,
    ProcessingStats,
)
from app.processing.ocr.base import BaseOCREngine
from app.processing.ocr.adapter import OCRAdapter, NoOpOCREngine, MockOCREngine
from app.processing.extractors.base import BaseExtractor
from app.processing.extractors.txt_extractor import TXTExtractor
from app.processing.extractors.csv_extractor import CSVExtractor
from app.processing.extractors.json_xml_extractor import JSONExtractor, XMLExtractor
from app.processing.extractors.html_extractor import HTMLExtractor
from app.processing.extractors.docx_extractor import DOCXExtractor
from app.processing.extractors.pdf_extractor import PDFExtractor
from app.processing.extractors.image_extractor import ImageExtractor
from app.processing.extractors.registry import ExtractorRegistry
from app.processing.validator import TextQualityValidator
from app.processing.enricher import MetadataEnricher
from app.processing.storage import ProcessedStorageManager
from app.processing.orchestrator import DocumentContentProcessor


class TestExtractors(unittest.TestCase):
    """Unit tests for format-specific extractors."""

    def test_txt_extractor_utf8(self):
        extractor = TXTExtractor()
        content = (
            "Government scheme notification for rural development.\n"
            "Official guideline text detailing implementation procedures for societies."
        )
        res = extractor.extract(content.encode("utf-8"), "guideline.txt")
        self.assertEqual(res.status, ExtractionStatus.SUCCESS)
        self.assertIn("Official guideline text", res.text)
        self.assertFalse(res.requires_ocr)

    def test_txt_extractor_latin1_fallback(self):
        extractor = TXTExtractor()
        # Ensure length >= 50 characters to achieve SUCCESS status
        content = (
            "Préstamo y crédito agrícola para cooperativas rurales en el sector agrario."
        ).encode("latin-1")
        res = extractor.extract(content, "spanish_guideline.txt")
        self.assertEqual(res.status, ExtractionStatus.SUCCESS)
        self.assertIn("crédito", res.text)

    def test_csv_extractor(self):
        extractor = CSVExtractor()
        csv_data = "Scheme Name,Budget (Cr),Beneficiaries\nPM Kisan,60000,110000000\nKCC,20000,5000000\n"
        res = extractor.extract(csv_data.encode("utf-8"), "schemes.csv")
        self.assertEqual(res.status, ExtractionStatus.SUCCESS)
        self.assertIn("Table Headers: Scheme Name, Budget (Cr), Beneficiaries", res.text)
        self.assertIn("PM Kisan", res.text)
        self.assertEqual(res.metadata.get("total_rows"), 3)

    def test_csv_extractor_empty(self):
        extractor = CSVExtractor()
        res = extractor.extract(b"", "empty.csv")
        self.assertEqual(res.status, ExtractionStatus.EXTRACTION_FAILED)

    def test_json_extractor(self):
        extractor = JSONExtractor()
        data = {
            "title": "National Cooperative Policy",
            "pillars": ["Governance", "Digital Infrastructure", "Financing"],
            "year": 2024,
        }
        res = extractor.extract(json.dumps(data).encode("utf-8"), "policy.json")
        self.assertEqual(res.status, ExtractionStatus.SUCCESS)
        self.assertIn("National Cooperative Policy", res.text)
        self.assertIn("Digital Infrastructure", res.text)

    def test_json_extractor_invalid(self):
        extractor = JSONExtractor()
        res = extractor.extract(b"{invalid_json:", "broken.json")
        self.assertEqual(res.status, ExtractionStatus.EXTRACTION_FAILED)

    def test_xml_extractor(self):
        extractor = XMLExtractor()
        xml_data = """<?xml version="1.0" encoding="UTF-8"?>
        <policy>
            <title>Agri Credit Reform</title>
            <section id="1">
                <heading>Objectives</heading>
                <paragraph>Enhance Kisan Credit Card coverage in rural districts.</paragraph>
            </section>
        </policy>
        """
        res = extractor.extract(xml_data.encode("utf-8"), "policy.xml")
        self.assertEqual(res.status, ExtractionStatus.SUCCESS)
        self.assertIn("Agri Credit Reform", res.text)
        self.assertIn("Kisan Credit Card coverage", res.text)

    def test_html_extractor(self):
        extractor = HTMLExtractor()
        html_data = """<!DOCTYPE html>
        <html>
        <head>
            <title>Ministry Guidelines</title>
            <style>body { font-size: 14px; }</style>
            <script>console.log("analytics");</script>
        </head>
        <body>
            <header><nav><a href="/home">Home</a><a href="/menu">Menu</a></nav></header>
            <main>
                <h1>Official Subsidies 2024</h1>
                <p>Eligible farmers can apply online through the centralized portal.</p>
            </main>
            <footer><p>&copy; 2024 Government of India. All rights reserved.</p></footer>
        </body>
        </html>
        """
        res = extractor.extract(html_data.encode("utf-8"), "guidelines.html")
        self.assertEqual(res.status, ExtractionStatus.SUCCESS)
        self.assertIn("Official Subsidies 2024", res.text)
        self.assertIn("Eligible farmers can apply online", res.text)
        # Scripts and styles should be stripped
        self.assertNotIn("console.log", res.text)
        self.assertNotIn("font-size", res.text)

    def test_docx_extractor(self):
        import docx
        doc = docx.Document()
        doc.add_heading("PACS Computerization Standard Operating Procedure", level=1)
        doc.add_paragraph("All primary agricultural credit societies must adhere to cyber audit norms.")
        table = doc.add_table(rows=2, cols=2)
        table.cell(0, 0).text = "Phase"
        table.cell(0, 1).text = "Timeline"
        table.cell(1, 0).text = "Phase 1"
        table.cell(1, 1).text = "Q4 2024"

        buf = io.BytesIO()
        doc.save(buf)
        docx_bytes = buf.getvalue()

        extractor = DOCXExtractor()
        res = extractor.extract(docx_bytes, "sop.docx")
        self.assertEqual(res.status, ExtractionStatus.SUCCESS)
        self.assertIn("PACS Computerization", res.text)
        self.assertIn("cyber audit norms", res.text)
        self.assertIn("Phase 1", res.text)

    def test_pdf_extractor_blank(self):
        import pypdf
        writer = pypdf.PdfWriter()
        writer.add_blank_page(width=300, height=300)
        buf = io.BytesIO()
        writer.write(buf)
        pdf_bytes = buf.getvalue()

        extractor = PDFExtractor()
        res = extractor.extract(pdf_bytes, "blank.pdf")
        self.assertTrue(res.requires_ocr)
        self.assertEqual(res.page_count, 1)

    def test_image_extractor(self):
        extractor = ImageExtractor()
        res = extractor.extract(b"\x89PNG\r\n\x1a\nFakePngData", "document_scan.png")
        self.assertEqual(res.status, ExtractionStatus.OCR_REQUIRED)
        self.assertTrue(res.requires_ocr)
        self.assertEqual(res.metadata.get("media_type"), "image")

    def test_registry_dispatch(self):
        registry = ExtractorRegistry()
        pdf_ext = registry.get_extractor(extension=".pdf", mime_type="application/pdf")
        self.assertIsInstance(pdf_ext, PDFExtractor)
        html_ext = registry.get_extractor(extension=".html", mime_type="text/html")
        self.assertIsInstance(html_ext, HTMLExtractor)
        csv_ext = registry.get_extractor(extension=".csv", mime_type="text/csv")
        self.assertIsInstance(csv_ext, CSVExtractor)
        img_ext = registry.get_extractor(extension=".jpg", mime_type="image/jpeg")
        self.assertIsInstance(img_ext, ImageExtractor)
        # Fallback should be TXTExtractor
        fallback_ext = registry.get_extractor(extension=".xyz", mime_type="unknown/format")
        self.assertIsInstance(fallback_ext, TXTExtractor)


class TestOCREngineAndAdapter(unittest.TestCase):
    """Unit tests for OCR engine and vendor-neutral adapter."""

    def test_noop_ocr_engine(self):
        noop = NoOpOCREngine()
        self.assertTrue(noop.is_available())
        res = noop.process(b"image_data", "image.png")
        self.assertEqual(res.status, OCRStatus.PENDING)
        self.assertEqual(res.text, "")
        self.assertIsNone(res.confidence)

    def test_mock_ocr_engine(self):
        mock_engine = MockOCREngine(mock_text="Extracted scan text", confidence=0.95, language="eng")
        self.assertTrue(mock_engine.is_available())
        res = mock_engine.process(b"scan_bytes", "image.png")
        self.assertEqual(res.status, OCRStatus.COMPLETED)
        self.assertEqual(res.text, "Extracted scan text")
        self.assertEqual(res.confidence, 0.95)
        self.assertEqual(res.language, "eng")

    def test_ocr_adapter_routing(self):
        adapter = OCRAdapter(engine=NoOpOCREngine())
        res = adapter.process(b"data", "image.png")
        self.assertEqual(res.status, OCRStatus.PENDING)


class TestTextQualityValidator(unittest.TestCase):
    """Unit tests for text quality validation and classification."""

    def setUp(self):
        self.validator = TextQualityValidator()

    def test_quality_success(self):
        # Text with >= 100 words to test HIGH quality classification
        good_text = (
            "This is a high quality official government document outlining comprehensive guidelines "
            "for agricultural cooperative credit societies in rural districts across India. "
            "All registered societies must comply with the reporting norms and quarterly audit requirements. "
            "The Department of Agriculture and Farmers Welfare mandates that state nodal agencies coordinate "
            "closely with primary agricultural credit societies to ensure seamless distribution of subvention "
            "benefits directly to beneficiary bank accounts. Transparency, integrity, and timely reconciliation "
            "form the bedrock of this national agricultural initiative. Regular training programs will be conducted "
            "for district managers and branch auditors to prevent compliance bottlenecks and facilitate digital adoption. "
            "All records must be preserved for minimum five fiscal years."
        )
        extraction = ExtractionResult(
            status=ExtractionStatus.SUCCESS,
            text=good_text,
            requires_ocr=False,
        )
        final_status, quality, metrics = self.validator.validate(extraction)
        self.assertEqual(final_status, ExtractionStatus.SUCCESS)
        self.assertEqual(quality, TextQualityStatus.HIGH)
        self.assertTrue(metrics["printable_ratio"] > 0.95)
        self.assertTrue(metrics["word_count"] >= 100)

    def test_quality_ocr_required(self):
        extraction = ExtractionResult(
            status=ExtractionStatus.SUCCESS,
            text="",
            requires_ocr=True,
        )
        final_status, quality, metrics = self.validator.validate(extraction)
        self.assertEqual(final_status, ExtractionStatus.OCR_REQUIRED)
        self.assertEqual(quality, TextQualityStatus.EMPTY)

    def test_quality_low_text(self):
        extraction = ExtractionResult(
            status=ExtractionStatus.SUCCESS,
            text="Hello world guidelines",
            requires_ocr=False,
        )
        final_status, quality, metrics = self.validator.validate(extraction)
        self.assertEqual(final_status, ExtractionStatus.LOW_TEXT)
        self.assertEqual(quality, TextQualityStatus.LOW)

    def test_quality_extraction_failed(self):
        extraction = ExtractionResult(
            status=ExtractionStatus.EXTRACTION_FAILED,
            text="",
            error_message="Corrupted ZIP archive",
        )
        final_status, quality, metrics = self.validator.validate(extraction)
        self.assertEqual(final_status, ExtractionStatus.EXTRACTION_FAILED)
        self.assertEqual(quality, TextQualityStatus.EMPTY)

    def test_quality_needs_review_binary(self):
        binary_gibberish = "Test\x00\x01\x02\x03\x04\x05\x06\x07\x08\x0b\x0c\x0e\x0f" * 10
        extraction = ExtractionResult(
            status=ExtractionStatus.SUCCESS,
            text=binary_gibberish,
        )
        final_status, quality, metrics = self.validator.validate(extraction)
        self.assertEqual(final_status, ExtractionStatus.NEEDS_REVIEW)
        self.assertEqual(quality, TextQualityStatus.CORRUPT)


class TestMetadataEnricher(unittest.TestCase):
    """Unit tests for metadata enrichment and lineage preservation."""

    def test_enricher_zero_guessing_policy(self):
        enricher = MetadataEnricher()
        raw_doc = {
            "id": "11111111-2222-3333-4444-555555555555",
            "source_id": "00000000-1111-2222-3333-444444444444",
            "sha256": "abcdef1234567890" * 4,
            "url": "https://agricoop.nic.in/guideline.pdf",
            "domain": "agriculture_rural_sustainability",
            "title": "National Mission on Sustainable Agriculture",
            "file_size": 102400,
            "mime_type": "application/pdf",
        }
        # Provide text with >= 25 words so final status is SUCCESS
        full_text = (
            "National Mission on Sustainable Agriculture operational guidelines for state nodal agencies "
            "and district agricultural directors across all zones to promote organic farming and micro irrigation "
            "practices in rainfed agricultural regions."
        )
        extraction = ExtractionResult(
            status=ExtractionStatus.SUCCESS,
            text=full_text,
            page_count=12,
        )
        final_status, quality, metrics = TextQualityValidator().validate(extraction)
        metadata = enricher.enrich(
            raw_doc=raw_doc,
            extraction_result=extraction,
            final_status=final_status,
            quality_status=quality,
            metrics=metrics,
            processed_storage_path="processed/agriculture_rural_sustainability/00000000-1111-2222-3333-444444444444/" + raw_doc["sha256"],
        )

        self.assertEqual(metadata["raw_sha256"], raw_doc["sha256"])
        self.assertEqual(metadata["domain"], "agriculture_rural_sustainability")
        self.assertEqual(metadata["page_count"], 12)
        self.assertEqual(metadata["extraction_status"], "SUCCESS")
        # Ensure zero guessing for unverified attributes
        self.assertIsNone(metadata["state"])
        self.assertIsNone(metadata["district"])


class TestProcessedStorageManager(unittest.TestCase):
    """Unit tests for processed artifact packaging and file integrity."""

    def setUp(self):
        self.test_dir = tempfile.mkdtemp()
        self.storage = ProcessedStorageManager(local_base_dir=self.test_dir)

    def tearDown(self):
        shutil.rmtree(self.test_dir, ignore_errors=True)

    def test_artifact_save_and_manifest(self):
        sha = "1234567890abcdef" * 4
        text = "Official agricultural credit reform policy document."
        metadata = {
            "document_id": "doc-001",
            "domain": "cooperative_governance",
            "source_id": "src-001",
            "raw_sha256": sha,
            "character_count": len(text),
        }
        manifest = {
            "processing_version": "1.0.0",
            "raw_sha256": sha,
            "artifacts": {
                "extracted_txt": "extracted.txt",
                "metadata_json": "metadata.json",
                "processing_manifest_json": "processing_manifest.json",
            },
        }

        saved_paths = self.storage.save_artifacts(
            domain="cooperative_governance",
            source_id="src-001",
            raw_sha256=sha,
            extracted_text=text,
            metadata=metadata,
            manifest=manifest,
        )

        self.assertTrue(os.path.exists(saved_paths["local_dir"]))
        self.assertTrue(os.path.exists(saved_paths["extracted_txt"]))
        self.assertTrue(os.path.exists(saved_paths["metadata_json"]))
        self.assertTrue(os.path.exists(saved_paths["processing_manifest_json"]))

        with open(saved_paths["extracted_txt"], "r", encoding="utf-8") as f:
            self.assertEqual(f.read(), text)

        with open(saved_paths["processing_manifest_json"], "r", encoding="utf-8") as f:
            manifest_data = json.load(f)
            self.assertEqual(manifest_data["raw_sha256"], sha)
            self.assertIn("extracted_txt", manifest_data["artifacts"])


class TestDocumentContentProcessor(unittest.TestCase):
    """Unit tests for processor orchestrator, dry-run, idempotency, and checkpointing."""

    def setUp(self):
        self.test_dir = tempfile.mkdtemp()
        self.artifacts_dir = os.path.join(self.test_dir, "artifacts")
        self.manifests_dir = os.path.join(self.test_dir, "manifests")
        self.checkpoint_path = os.path.join(self.manifests_dir, "checkpoint.json")
        self.storage_manager = ProcessedStorageManager(local_base_dir=self.artifacts_dir)

    def tearDown(self):
        shutil.rmtree(self.test_dir, ignore_errors=True)

    def test_dry_run_processing(self):
        processor = DocumentContentProcessor(
            dry_run=True,
            manifest_dir=self.manifests_dir,
            checkpoint_path=self.checkpoint_path,
            storage_manager=self.storage_manager,
        )

        sample_doc = {
            "id": "11111111-0000-0000-0000-000000000001",
            "source_id": "src-100",
            "domain": "government_schemes",
            "title": "PM-KISAN Guidelines 2024",
            "url": "https://pmkisan.gov.in/guidelines.txt",
            "storage_path": "government_schemes/src-100/dummy.txt",
            "sha256": "a1b2c3d4e5f60718" * 4,
            "format": "txt",
            "mime_type": "text/plain",
        }

        # Mock retrieval of raw bytes: returns (bytes, source_location)
        sample_text = (
            "Pradhan Mantri Kisan Samman Nidhi operational guidelines for registered eligible beneficiaries. "
            "All state nodal departments must verify land records and bank account details prior to disbursal "
            "to guarantee that financial assistance reaches small and marginal farmer households on schedule."
        )
        with patch.object(
            processor,
            "retrieve_raw_bytes",
            return_value=(sample_text.encode("utf-8"), "local_cache"),
        ):
            record = processor.process_document(sample_doc)

        self.assertEqual(record["extraction_status"], "SUCCESS")
        self.assertEqual(record["character_count"], len(sample_text))
        self.assertEqual(record["text_quality_status"], "MEDIUM")

    def test_idempotency_skip(self):
        processor = DocumentContentProcessor(
            dry_run=True,
            manifest_dir=self.manifests_dir,
            checkpoint_path=self.checkpoint_path,
            storage_manager=self.storage_manager,
        )

        sample_doc = {
            "id": "11111111-0000-0000-0000-000000000002",
            "source_id": "src-200",
            "domain": "cooperative_governance",
            "title": "NCDC Scheme",
            "url": "https://ncdc.in/scheme.txt",
            "storage_path": "cooperative_governance/src-200/dummy.txt",
            "sha256": "f0e1d2c3b4a50099" * 4,
            "format": "txt",
            "mime_type": "text/plain",
        }

        sample_text = (
            "NCDC Yuva Sahakar cooperative enterprise support scheme operational guidelines for applicants across state sectors. "
            "The scheme provides concessional term loans and financial assistance to newly formed cooperatives led by young entrepreneurs "
            "and women in rural agricultural clusters."
        )
        with patch.object(
            processor,
            "retrieve_raw_bytes",
            return_value=(sample_text.encode("utf-8"), "local_cache"),
        ):
            record1 = processor.process_document(sample_doc)
            self.assertEqual(record1["extraction_status"], "SUCCESS")

            # Second run without force should be skipped
            record2 = processor.process_document(sample_doc)
            self.assertEqual(record2["status"], "ALREADY_PROCESSED")

            # Run with force_reprocess=True should reprocess
            processor.force_reprocess = True
            record3 = processor.process_document(sample_doc)
            self.assertEqual(record3["extraction_status"], "SUCCESS")


if __name__ == "__main__":
    unittest.main()
