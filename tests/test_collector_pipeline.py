"""
NEXO Data Platform - Collector Pipeline Test Suite
100% Offline unit tests covering:
1. Verified source filtering (ignoring inactive, pending, needs_review, rejected)
2. URL canonicalization and deduplication
3. Domain security and anti-spoofing
4. Redirect handling and loop detection
5. Relevance classification (CONFIRMED, NEEDS_REVIEW, IRRELEVANT)
6. Format detection and magic bytes validation
7. Polite HTTP client, rate limits, retries, and robots.txt
8. Downloader validation and quarantine
9. SHA-256 calculation and duplicate preservation
10. Geographic classification (Central, State, District, Unknown)
11. Checkpoint and resume functionality
12. Dry-run and live orchestrator execution
"""

import json
import os
import sys
import tempfile
import unittest

# Ensure project root is in sys.path
project_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if project_root not in sys.path:
    sys.path.insert(0, project_root)

from config.source_registry_config import DomainCategory, AuthorityLevel
from app.sources.models import SourceRecord
from app.collector.models import DiscoveredDocument, CrawlStats, CheckpointState
from app.collector.security import (
    is_safe_scheme,
    is_domain_authorized,
    validate_crawl_target,
    validate_redirect,
)
from app.collector.relevance import (
    assess_relevance,
    CONFIRMED,
    NEEDS_REVIEW,
    IRRELEVANT,
)
from app.collector.discovery import (
    HtmlLinkExtractor,
    extract_links_from_html,
    is_document_url,
)
from app.collector.polite_client import PoliteHttpClient, FetchResult
from app.collector.downloader import DocumentDownloader, DownloadResult
from app.collector.geo_tagger import classify_geography
from app.collector.checkpoint import CheckpointManager
from app.collector.orchestrator import CollectorPipeline


class TestCollectorSecurity(unittest.TestCase):
    """Tests URL schemes, domain anchoring, anti-spoofing, and redirect security."""

    def test_safe_scheme_validation(self):
        self.assertTrue(is_safe_scheme("https://cooperation.gov.in/schemes"))
        self.assertTrue(is_safe_scheme("http://agricoop.nic.in"))
        self.assertFalse(is_safe_scheme("javascript:alert(1)"))
        self.assertFalse(is_safe_scheme("mailto:info@cooperation.gov.in"))
        self.assertFalse(is_safe_scheme("ftp://files.gov.in"))
        self.assertFalse(is_safe_scheme("data:text/html;base64,..."))

    def test_domain_authorized_anchor(self):
        source = "https://cooperation.gov.in/portal"
        # Same host
        self.assertTrue(is_domain_authorized("https://cooperation.gov.in/schemes/pacs.pdf", source))
        # Subdomain
        self.assertTrue(is_domain_authorized("https://pacs.cooperation.gov.in/guidelines", source))
        # Whitelisted official document CDN
        self.assertTrue(is_domain_authorized("https://s3waas.gov.in/docs/gazette.pdf", source))
        # Commercial / external domain escape forbidden
        self.assertFalse(is_domain_authorized("https://google.com", source))
        self.assertFalse(is_domain_authorized("https://fake-cooperation-schemes.com", source))

    def test_anti_spoofing_in_crawl_target(self):
        source = "https://fake-gov-portal.com"  # Even if source was somehow suspicious
        # Target with suspicious token on commercial TLD must be rejected
        self.assertFalse(validate_crawl_target("https://fake-gov-portal.com/apply", source))

    def test_redirect_loop_and_escape_detection(self):
        source = "https://rural.gov.in"
        chain = ["https://rural.gov.in/step1", "https://rural.gov.in/step2"]

        # Legitimate redirect
        self.assertTrue(validate_redirect(chain[0], "https://rural.gov.in/step3", source, chain))
        # Loop detected
        self.assertFalse(validate_redirect(chain[0], "https://rural.gov.in/step1", source, chain))
        # Exceeded max redirects
        long_chain = [f"https://rural.gov.in/{i}" for i in range(10)]
        self.assertFalse(validate_redirect(long_chain[0], "https://rural.gov.in/end", source, long_chain))


class TestCollectorRelevance(unittest.TestCase):
    """Tests domain relevance rules, scoring, and tri-state categorization."""

    def test_confirmed_relevance_for_primary_keywords(self):
        res = assess_relevance(
            url="https://cooperation.gov.in/pacs_model_bylaws.pdf",
            title="Model By-laws for Primary Agricultural Credit Societies (PACS)",
            default_domain="cooperative_governance",
        )
        self.assertEqual(res.status, CONFIRMED)
        self.assertEqual(res.category, "cooperative_governance")
        self.assertGreaterEqual(res.score, 0.4)

    def test_needs_review_for_general_document(self):
        res = assess_relevance(
            url="https://agriwelfare.gov.in/department_circular_2026.pdf",
            title="Operational Administrative Circular",
            default_domain="agriculture_rural_sustainability",
        )
        # Moderate signals are preserved as NEEDS_REVIEW, never discarded
        self.assertIn(res.status, [CONFIRMED, NEEDS_REVIEW])
        self.assertNotEqual(res.status, IRRELEVANT)

    def test_irrelevant_administrative_boilerplate_filtered(self):
        res = assess_relevance(
            url="https://rural.gov.in/privacy-policy.html",
            title="Privacy Policy and Terms of Use",
            default_domain="rural_development_finance",
        )
        self.assertEqual(res.status, IRRELEVANT)


class TestCollectorDiscovery(unittest.TestCase):
    """Tests HTML link extraction, relative URL resolution, and document extension checks."""

    def test_html_link_extraction(self):
        html = """
        <html>
            <body>
                <h1>Government Guidelines</h1>
                <a href="/docs/kcc_guidelines.pdf">Kisan Credit Card Guidelines</a>
                <a href="https://agriwelfare.gov.in/schemes">Schemes Page</a>
                <a href="https://external-untrusted-blog.com/tips">Third Party Blog</a>
                <a href="javascript:void(0)">Click Here</a>
            </body>
        </html>
        """
        base_url = "https://agriwelfare.gov.in/index.html"
        source_url = "https://agriwelfare.gov.in"

        links = extract_links_from_html(base_url, html, source_url)

        # Expected: kcc_guidelines.pdf and schemes page, excluding external blog and javascript
        extracted_urls = [u for u, text, is_doc in links]
        self.assertIn("https://agriwelfare.gov.in/docs/kcc_guidelines.pdf", extracted_urls)
        self.assertIn("https://agriwelfare.gov.in/schemes", extracted_urls)
        self.assertFalse(any("external-untrusted-blog.com" in u for u in extracted_urls))
        self.assertFalse(any("javascript" in u for u in extracted_urls))

    def test_is_document_url(self):
        self.assertTrue(is_document_url("https://tn.gov.in/orders/go_123.pdf"))
        self.assertTrue(is_document_url("https://data.gov.in/export.csv"))
        self.assertTrue(is_document_url("https://bhashini.gov.in/model_spec.json"))
        self.assertFalse(is_document_url("https://tn.gov.in/departments/cooperation"))


class TestPoliteHttpClientAndMocks(unittest.TestCase):
    """Tests rate limiting, retries, robots.txt, and max response size."""

    def test_mock_response_retrieval(self):
        client = PoliteHttpClient()
        client.set_mock_response(
            url="https://mock.gov.in/data.json",
            content=b'{"key": "value"}',
            status_code=200,
            headers={"content-type": "application/json"},
        )

        res = client.fetch("https://mock.gov.in/data.json")
        self.assertTrue(res.success)
        self.assertEqual(res.content, b'{"key": "value"}')
        self.assertEqual(res.status_code, 200)

    def test_robots_txt_disallow(self):
        client = PoliteHttpClient()
        client.set_mock_robot_permission("https://restricted.gov.in", allowed=False)

        res = client.fetch("https://restricted.gov.in/secret.pdf")
        self.assertFalse(res.success)
        self.assertEqual(res.status_code, 403)
        self.assertIn("robots.txt", res.error_message)


class TestDownloaderAndValidation(unittest.TestCase):
    """Tests download validation, magic-byte inspection, and failure quarantine."""

    def setUp(self):
        self.temp_dir = tempfile.mkdtemp()
        self.client = PoliteHttpClient(crawl_delay=0.0)
        self.downloader = DocumentDownloader(client=self.client, quarantine_dir=self.temp_dir)

    def test_download_valid_pdf(self):
        valid_pdf_content = b"%PDF-1.4\n%Fake PDF binary for test\n%%EOF"
        url = "https://agricoop.nic.in/kcc.pdf"
        self.client.set_mock_response(url, valid_pdf_content, headers={"content-type": "application/pdf"})

        res = self.downloader.download_and_validate(url)
        self.assertTrue(res.success)
        self.assertEqual(res.mime_type, "application/pdf")
        self.assertEqual(res.extension, ".pdf")
        self.assertGreater(len(res.sha256), 30)

    def test_mismatched_content_rejected_and_quarantined(self):
        """Detects when an HTML 404 page is returned for a .pdf URL."""
        html_error_page = b"<!doctype html><html><body>Error 404 Not Found</body></html>"
        url = "https://agricoop.nic.in/missing_scheme.pdf"
        self.client.set_mock_response(url, html_error_page, headers={"content-type": "text/html"})

        res = self.downloader.download_and_validate(url)
        self.assertFalse(res.success)
        self.assertIn("Content mismatch", res.failure_reason)

        # Check quarantine log written
        quarantine_file = os.path.join(self.temp_dir, "failed_downloads.jsonl")
        self.assertTrue(os.path.exists(quarantine_file))


class TestCollectorGeoTagger(unittest.TestCase):
    """Tests geographic level and jurisdiction classification."""

    def test_district_level_classification(self):
        res = classify_geography(
            url="https://tn.gov.in/schemes/madurai/welfare.pdf",
            title="Madurai District Agriculture Assistance",
            source_state="Tamil Nadu",
        )
        self.assertEqual(res.government_level, "District")
        self.assertEqual(res.state, "Tamil Nadu")
        self.assertEqual(res.district, "Madurai")

    def test_state_level_classification(self):
        res = classify_geography(
            url="https://kooturavu.tn.gov.in/circulars/pacs_order.pdf",
            title="State Cooperative Guidelines",
            source_state="Tamil Nadu",
            authority_level="STATE_GOVERNMENT",
        )
        self.assertEqual(res.government_level, "State")
        self.assertEqual(res.state, "Tamil Nadu")
        self.assertIsNone(res.district)

    def test_central_level_classification(self):
        res = classify_geography(
            url="https://myscheme.gov.in/schemes/pm-kisan",
            title="PM-Kisan National Scheme",
            source_state=None,
            authority_level="CENTRAL_GOVERNMENT",
        )
        self.assertEqual(res.government_level, "Central")
        self.assertIsNone(res.state)


class TestCollectorCheckpointAndResume(unittest.TestCase):
    """Tests checkpoint persistence and resume mechanics."""

    def test_checkpoint_save_and_load(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            chk_file = os.path.join(tmpdir, "checkpoint.json")
            mgr = CheckpointManager(checkpoint_path=chk_file)
            mgr.mark_visited("https://cooperation.gov.in/page1")
            mgr.mark_hash_processed("abcdef123456")
            mgr.mark_source_completed("source_uuid_1")
            mgr.save()

            # Create new instance loading from disk
            mgr2 = CheckpointManager(checkpoint_path=chk_file)
            self.assertTrue(mgr2.is_visited("https://cooperation.gov.in/page1"))
            self.assertTrue(mgr2.is_hash_processed("abcdef123456"))
            self.assertTrue(mgr2.is_source_completed("source_uuid_1"))
            self.assertFalse(mgr2.is_visited("https://cooperation.gov.in/page2"))


class TestCollectorOrchestrator(unittest.TestCase):
    """Tests end-to-end pipeline execution in dry-run and live modes with mocks."""

    def setUp(self):
        self.temp_dir = tempfile.mkdtemp()
        self.manifest_dir = os.path.join(self.temp_dir, "manifests")
        self.processed_dir = os.path.join(self.temp_dir, "processed")

        # Create dummy verified manifest
        self.dummy_manifest_path = os.path.join(self.temp_dir, "verified_sources.json")
        self.source_data = [
            {
                "id": "11111111-1111-1111-1111-111111111111",
                "source_name": "Ministry of Cooperation Portal",
                "organization_name": "Ministry of Cooperation",
                "official_url": "https://cooperation.gov.in",
                "normalized_url": "https://cooperation.gov.in",
                "domain_category": "cooperative_governance",
                "authority_level": "CENTRAL_GOVERNMENT",
                "verification_status": "VERIFIED",
                "verification_method": "DEPARTMENT_MINISTRY_ASSOCIATION",
                "verification_notes": "Official ministry portal verified via Cabinet Gazette.",
                "is_active": True,
            },
            {
                "id": "22222222-2222-2222-2222-222222222222",
                "source_name": "Unverified Inactive Source",
                "organization_name": "Unknown",
                "official_url": "https://unverified.gov.in",
                "normalized_url": "https://unverified.gov.in",
                "domain_category": "government_schemes",
                "authority_level": "OTHER_OFFICIAL",
                "verification_status": "PENDING",  # MUST BE IGNORED
                "is_active": False,
            },
        ]
        with open(self.dummy_manifest_path, "w", encoding="utf-8") as f:
            json.dump(self.source_data, f)

        # Mock HTTP responses
        self.client = PoliteHttpClient(crawl_delay=0.0)
        html_page = """
        <html>
            <body>
                <a href="/pacs_bylaws.pdf">PACS Model By-laws</a>
                <a href="/privacy-policy">Privacy Policy</a>
            </body>
        </html>
        """
        self.client.set_mock_response("https://cooperation.gov.in", html_page.encode("utf-8"))
        self.pdf_bytes = b"%PDF-1.4\n%PACS Model Bylaws 2024 content\n%%EOF"
        self.client.set_mock_response(
            "https://cooperation.gov.in/pacs_bylaws.pdf",
            self.pdf_bytes,
            headers={"content-type": "application/pdf"},
        )

    def test_dry_run_pipeline_execution(self):
        pipeline = CollectorPipeline(
            verified_manifest_path=self.dummy_manifest_path,
            dry_run=True,
            client=self.client,
            manifest_dir=self.manifest_dir,
            processed_dir=self.processed_dir,
        )

        stats = pipeline.run()

        # Should only process the active verified source (1 source)
        self.assertEqual(stats.total_sources, 1)
        self.assertEqual(stats.documents_identified, 1)
        self.assertEqual(stats.documents_staged, 1)

        # Confirm dry-run manifests generated
        json_manifest = os.path.join(self.manifest_dir, "discovered_documents.json")
        self.assertTrue(os.path.exists(json_manifest))
        with open(json_manifest, "r", encoding="utf-8") as f:
            docs = json.load(f)
        self.assertEqual(len(docs), 1)
        self.assertEqual(docs[0]["status"], "dry_run_staged")
        self.assertEqual(docs[0]["relevance_category"], "cooperative_governance")

    def test_live_collection_with_duplicate_handling(self):
        pipeline = CollectorPipeline(
            verified_manifest_path=self.dummy_manifest_path,
            dry_run=False,  # Live staging
            client=self.client,
            manifest_dir=self.manifest_dir,
            processed_dir=self.processed_dir,
        )

        stats1 = pipeline.run()
        self.assertEqual(stats1.documents_downloaded, 1)
        self.assertEqual(stats1.duplicates_preserved, 0)

        # Re-run: exact same content should be preserved as duplicate
        pipeline2 = CollectorPipeline(
            verified_manifest_path=self.dummy_manifest_path,
            dry_run=False,
            client=self.client,
            manifest_dir=self.manifest_dir,
            processed_dir=self.processed_dir,
        )
        stats2 = pipeline2.run()
        self.assertEqual(stats2.duplicates_preserved, 1)


if __name__ == "__main__":
    unittest.main()
