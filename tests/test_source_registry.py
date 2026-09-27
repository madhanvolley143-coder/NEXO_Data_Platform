"""
NEXO Data Platform - Official Source Registry Test Suite
Validates source creation, URL normalization, authority checks, verification workflows,
manifest exports, and database payload formatting 100% offline.
"""

import os
import sys
import tempfile
import unittest

# Ensure project root is in sys.path
project_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if project_root not in sys.path:
    sys.path.insert(0, project_root)

from config.source_registry_config import (
    AuthorityLevel,
    VerificationStatus,
    DomainCategory,
)
from app.sources.models import SourceRecord
from app.sources.registry import SourceRegistry
from app.sources.validator import normalize_url, validate_source_url
from app.sources.authority import assess_domain_authority, is_eligible_for_verification
from app.ingestion.exceptions import ValidationError


class TestURLNormalization(unittest.TestCase):
    """Verifies that URLs are normalized deterministically for deduplication."""

    def test_trailing_slash_normalization(self):
        url1 = "https://agricoop.nic.in/schemes/"
        url2 = "https://agricoop.nic.in/schemes"
        self.assertEqual(normalize_url(url1), normalize_url(url2))
        self.assertEqual(normalize_url(url1), "https://agricoop.nic.in/schemes")

    def test_case_insensitivity_in_scheme_and_host(self):
        url1 = "HTTPS://AGRICOOP.NIC.IN/Schemes/PM-KISAN"
        url2 = "https://agricoop.nic.in/Schemes/PM-KISAN"
        self.assertEqual(normalize_url(url1), normalize_url(url2))

    def test_default_ports_stripped(self):
        url_https = "https://cooperation.gov.in:443/bylaws"
        url_http = "http://cooperation.gov.in:80/bylaws"
        self.assertEqual(normalize_url(url_https), "https://cooperation.gov.in/bylaws")
        self.assertEqual(normalize_url(url_http), "http://cooperation.gov.in/bylaws")

    def test_fragments_stripped(self):
        url = "https://rural.nic.in/guidelines#eligibility-section"
        self.assertEqual(normalize_url(url), "https://rural.nic.in/guidelines")

    def test_query_params_sorted(self):
        url1 = "https://ncdc.in/schemes?type=coop&year=2024"
        url2 = "https://ncdc.in/schemes?year=2024&type=coop"
        self.assertEqual(normalize_url(url1), normalize_url(url2))

    def test_invalid_urls_rejected(self):
        with self.assertRaises(ValidationError):
            normalize_url("ftp://agricoop.nic.in")
        with self.assertRaises(ValidationError):
            normalize_url("just-a-plain-string")
        with self.assertRaises(ValidationError):
            normalize_url("")


class TestAuthorityAssessment(unittest.TestCase):
    """Verifies authority heuristics and anti-spoofing checks."""

    def test_official_nic_and_gov_recognized(self):
        res1 = assess_domain_authority("https://agricoop.nic.in")
        self.assertTrue(res1["is_preferred_gov"])
        self.assertFalse(res1["has_suspicious_gov_pattern"])

        res2 = assess_domain_authority("https://pmkisan.gov.in")
        self.assertTrue(res2["is_preferred_gov"])

    def test_recognized_apex_institutions(self):
        res_nabard = assess_domain_authority("https://nabard.org/schemes")
        self.assertTrue(res_nabard["is_recognized_institution"])

        res_rbi = assess_domain_authority("https://rbi.org.in")
        self.assertTrue(res_rbi["is_recognized_institution"])

    def test_deceptive_gov_token_flagged(self):
        """Websites with 'gov' in commercial TLDs must be flagged as suspicious."""
        res = assess_domain_authority("https://fake-gov-schemes.com/apply")
        self.assertFalse(res["is_preferred_gov"])
        self.assertTrue(res["has_suspicious_gov_pattern"])
        self.assertEqual(res["initial_status"], VerificationStatus.NEEDS_REVIEW.value)


class TestSourceRecordModel(unittest.TestCase):
    """Verifies SourceRecord schema validation, guardrails, and adapters."""

    def test_valid_source_creation(self):
        record = SourceRecord(
            source_name="Ministry of Agriculture Portal",
            organization_name="Ministry of Agriculture & Farmers Welfare",
            official_url="https://agricoop.nic.in/",
            domain_category=DomainCategory.AGRICULTURE_RURAL_SUSTAINABILITY.value,
            authority_level=AuthorityLevel.CENTRAL_GOVERNMENT.value,
        )
        self.assertEqual(record.verification_status, VerificationStatus.PENDING.value)
        self.assertEqual(record.normalized_url, "https://agricoop.nic.in")
        self.assertTrue(record.is_active)

    def test_invalid_domain_slug_rejected(self):
        with self.assertRaises(Exception):
            SourceRecord(
                source_name="Invalid Domain Portal",
                organization_name="Some Org",
                official_url="https://example.gov.in",
                domain_category="invalid_domain_category",
                authority_level=AuthorityLevel.CENTRAL_GOVERNMENT.value,
            )

    def test_invalid_authority_level_rejected(self):
        with self.assertRaises(Exception):
            SourceRecord(
                source_name="Invalid Authority Portal",
                organization_name="Some Org",
                official_url="https://example.gov.in",
                domain_category=DomainCategory.GOVERNMENT_SCHEMES.value,
                authority_level="UNAUTHORIZED_TIER",
            )

    def test_cannot_create_verified_without_metadata(self):
        """A source cannot be initialized as VERIFIED without method and notes."""
        with self.assertRaises(ValidationError):
            SourceRecord(
                source_name="Prematurely Verified Portal",
                organization_name="Some Org",
                official_url="https://agricoop.nic.in",
                domain_category=DomainCategory.AGRICULTURE_RURAL_SUSTAINABILITY.value,
                authority_level=AuthorityLevel.CENTRAL_GOVERNMENT.value,
                verification_status=VerificationStatus.VERIFIED.value,
                # Missing verification_method and verification_notes
            )

    def test_valid_verified_source_creation(self):
        record = SourceRecord(
            source_name="PM Kisan Official Portal",
            organization_name="Ministry of Agriculture",
            official_url="https://pmkisan.gov.in",
            domain_category=DomainCategory.GOVERNMENT_SCHEMES.value,
            authority_level=AuthorityLevel.CENTRAL_GOVERNMENT.value,
            verification_status=VerificationStatus.VERIFIED.value,
            verification_method="Official Gazette Cross-Reference",
            verification_notes="Verified against Union Cabinet Resolution notification.",
        )
        self.assertEqual(record.verification_status, VerificationStatus.VERIFIED.value)
        self.assertIsNotNone(record.last_verified_at)

    def test_supabase_adapter_mapping(self):
        record = SourceRecord(
            source_name="Ministry of Cooperation",
            organization_name="Ministry of Cooperation, GoI",
            official_url="https://cooperation.gov.in/",
            domain_category=DomainCategory.COOPERATIVE_GOVERNANCE.value,
            authority_level=AuthorityLevel.CENTRAL_GOVERNMENT.value,
        )
        supabase_dict = record.to_supabase_dict()
        self.assertEqual(supabase_dict["name"], "Ministry of Cooperation")
        self.assertEqual(supabase_dict["url"], "https://cooperation.gov.in")
        self.assertEqual(supabase_dict["domain"], "cooperative_governance")
        self.assertEqual(supabase_dict["authority_level"], "CENTRAL_GOVERNMENT")
        self.assertTrue(supabase_dict["is_active"])
        # Verify schema conformity
        expected_keys = {
            "id", "name", "url", "domain", "language", "authority_level",
            "last_checked_at", "is_active", "created_at", "updated_at"
        }
        self.assertEqual(set(supabase_dict.keys()), expected_keys)


class TestSourceRegistryOperations(unittest.TestCase):
    """Verifies registry lifecycle operations, filtering, deduplication, and file exports."""

    def setUp(self):
        self.temp_dir = tempfile.mkdtemp()
        self.manifest_path = os.path.join(self.temp_dir, "sources.jsonl")
        self.registry = SourceRegistry(manifest_path=self.manifest_path)

    def tearDown(self):
        import shutil
        shutil.rmtree(self.temp_dir, ignore_errors=True)

    def test_add_and_get_source(self):
        record = self.registry.add_source({
            "source_name": "NCDC Cooperative Portal",
            "organization_name": "National Cooperative Development Corporation",
            "official_url": "https://ncdc.in/schemes/",
            "domain_category": DomainCategory.COOPERATIVE_GOVERNANCE.value,
            "authority_level": AuthorityLevel.GOVERNMENT_INSTITUTION.value,
        })
        self.assertEqual(record.source_name, "NCDC Cooperative Portal")

        # Lookup by ID
        found_by_id = self.registry.get_source(record.id)
        self.assertIsNotNone(found_by_id)
        self.assertEqual(found_by_id.official_url, "https://ncdc.in/schemes")

        # Lookup by URL
        found_by_url = self.registry.find_by_url("https://ncdc.in/schemes/")
        self.assertIsNotNone(found_by_url)
        self.assertEqual(found_by_url.id, record.id)

    def test_duplicate_url_detection(self):
        self.registry.add_source({
            "source_name": "PM Kisan Portal",
            "organization_name": "Govt of India",
            "official_url": "https://pmkisan.gov.in/",
            "domain_category": DomainCategory.GOVERNMENT_SCHEMES.value,
            "authority_level": AuthorityLevel.CENTRAL_GOVERNMENT.value,
        })

        # Same URL with slight formatting difference must be detected as duplicate
        with self.assertRaises(ValidationError):
            self.registry.add_source({
                "source_name": "PM Kisan Duplicate",
                "organization_name": "Govt of India",
                "official_url": "https://pmkisan.gov.in",
                "domain_category": DomainCategory.GOVERNMENT_SCHEMES.value,
                "authority_level": AuthorityLevel.CENTRAL_GOVERNMENT.value,
            })

    def test_verification_workflow(self):
        source = self.registry.add_source({
            "source_name": "SFAC Agribusiness Portal",
            "organization_name": "Small Farmers Agribusiness Consortium",
            "official_url": "https://sfacindia.com",
            "domain_category": DomainCategory.AGRICULTURE_RURAL_SUSTAINABILITY.value,
            "authority_level": AuthorityLevel.GOVERNMENT_INSTITUTION.value,
        })
        self.assertEqual(source.verification_status, VerificationStatus.PENDING.value)

        # Attempt verification without notes must fail
        with self.assertRaises(ValidationError):
            self.registry.verify_source(
                id_or_url=source.id,
                verification_method="NIC Directory Check",
                verification_notes="",  # Empty notes
            )

        # Successful verification
        verified = self.registry.verify_source(
            id_or_url=source.id,
            verification_method="NIC Official Directory",
            verification_notes="Verified via official NIC Central Autonomous Body register.",
        )
        self.assertEqual(verified.verification_status, VerificationStatus.VERIFIED.value)
        self.assertIsNotNone(verified.last_verified_at)

    def test_rejection_workflow(self):
        source = self.registry.add_source({
            "source_name": "Third-Party Subsidies Blog",
            "organization_name": "Commercial Blog Network",
            "official_url": "https://commercial-schemes-blog.net",
            "domain_category": DomainCategory.GOVERNMENT_SCHEMES.value,
            "authority_level": AuthorityLevel.OTHER_OFFICIAL.value,
        })

        rejected = self.registry.reject_source(
            id_or_url=source.id,
            reason="Commercial aggregator portal with no statutory mandate.",
        )
        self.assertEqual(rejected.verification_status, VerificationStatus.REJECTED.value)
        self.assertFalse(rejected.is_active)
        self.assertIn("Commercial aggregator", rejected.verification_notes)

    def test_deactivation_workflow(self):
        source = self.registry.add_source({
            "source_name": "Deprecated State Portal",
            "organization_name": "State Govt",
            "official_url": "https://old-state-portal.gov.in",
            "domain_category": DomainCategory.GOVERNMENT_SCHEMES.value,
            "authority_level": AuthorityLevel.STATE_GOVERNMENT.value,
        })
        self.assertTrue(source.is_active)

        deactivated = self.registry.deactivate_source(
            id_or_url=source.id,
            reason="Portal superseded by unified national portal.",
        )
        self.assertFalse(deactivated.is_active)
        self.assertIn("superseded", deactivated.verification_notes)

    def test_search_and_filtering(self):
        self.registry.add_source({
            "source_name": "Central Schemes Portal",
            "organization_name": "MeitY",
            "official_url": "https://schemes.gov.in",
            "domain_category": DomainCategory.GOVERNMENT_SCHEMES.value,
            "authority_level": AuthorityLevel.CENTRAL_GOVERNMENT.value,
        })
        self.registry.add_source({
            "source_name": "State Cooperative Registrar",
            "organization_name": "Dept of Cooperation UP",
            "official_url": "https://cooperativeregistrar.up.gov.in",
            "domain_category": DomainCategory.COOPERATIVE_GOVERNANCE.value,
            "authority_level": AuthorityLevel.STATE_GOVERNMENT.value,
        })

        # By domain
        coop_sources = self.registry.find_by_domain(DomainCategory.COOPERATIVE_GOVERNANCE.value)
        self.assertEqual(len(coop_sources), 1)
        self.assertEqual(coop_sources[0].source_name, "State Cooperative Registrar")

        # By authority
        central_sources = self.registry.find_by_authority(AuthorityLevel.CENTRAL_GOVERNMENT.value)
        self.assertEqual(len(central_sources), 1)
        self.assertEqual(central_sources[0].source_name, "Central Schemes Portal")

        # By status
        pending_sources = self.registry.find_by_status(VerificationStatus.PENDING.value)
        self.assertEqual(len(pending_sources), 2)

    def test_export_and_reload_manifest(self):
        self.registry.add_source({
            "source_name": "FSSAI Portal",
            "organization_name": "Food Safety and Standards Authority of India",
            "official_url": "https://fssai.gov.in",
            "domain_category": DomainCategory.FOODTECH_COLDCHAIN.value,
            "authority_level": AuthorityLevel.STATUTORY_BODY.value,
        })

        # Export to JSON
        json_path = os.path.join(self.temp_dir, "export.json")
        self.registry.export_json(json_path)
        self.assertTrue(os.path.exists(json_path))

        # Reload in new registry instance
        new_registry = SourceRegistry(manifest_path=json_path)
        self.assertEqual(len(new_registry.list_all()), 1)
        self.assertEqual(new_registry.list_all()[0].source_name, "FSSAI Portal")


if __name__ == "__main__":
    unittest.main()
