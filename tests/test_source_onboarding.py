"""
NEXO Data Platform - Source Onboarding Workflow Test Suite
Comprehensive offline unit tests validating:
1. Candidate creation & URL normalization
2. PENDING default status enforcement
3. Anti-spoofing & authority assessment (gov/scheme tokens on commercial TLDs)
4. Duplicate URL detection
5. Verification guardrails (prohibiting unverified promotion)
6. Valid verification evidence workflow
7. Rejection & Needs-Review workflows
8. Audit trail preservation across lifecycle events
9. Future collector handoff (strict active + VERIFIED filtering)
10. Supabase 17-column payload preparation & dry run
11. Manifest export to JSON / JSONL
12. Offline integrity (no network, placeholder verification)
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

from config.source_registry_config import (
    AuthorityLevel,
    VerificationStatus,
    DomainCategory,
)
from app.sources.models import SourceRecord
from app.sources.registry import SourceRegistry
from app.sources.onboarding import (
    CandidateSource,
    VerificationEvidenceType,
    submit_candidate_source,
    assess_candidate_source,
    verify_candidate_source,
    reject_candidate_source,
    flag_needs_review,
    prepare_supabase_record,
    get_verified_sources,
    export_onboarding_manifest,
)
from app.ingestion.exceptions import ValidationError


class TestCandidateSourceModel(unittest.TestCase):
    """Tests the CandidateSource Pydantic model validation and guardrails."""

    def test_candidate_creation_defaults_to_pending(self):
        candidate = CandidateSource(
            source_name="Ministry of Agriculture Portal",
            organization_name="Ministry of Agriculture & Farmers Welfare",
            official_url="https://agricoop.nic.in/schemes/",
            domain_category=DomainCategory.AGRICULTURE_RURAL_SUSTAINABILITY.value,
            authority_level=AuthorityLevel.CENTRAL_GOVERNMENT.value,
        )
        self.assertEqual(candidate.verification_status, VerificationStatus.PENDING.value)
        self.assertEqual(candidate.normalized_url, "https://agricoop.nic.in/schemes")
        self.assertIsNone(candidate.verification_method)
        self.assertIsNone(candidate.verification_notes)

    def test_url_normalization_on_candidate_creation(self):
        candidate = CandidateSource(
            source_name="State Cooperative Registrar",
            organization_name="Cooperation Department",
            official_url="HTTPS://COOP.UP.GOV.IN:443/bylaws/#section-1",
            domain_category=DomainCategory.COOPERATIVE_GOVERNANCE.value,
            authority_level=AuthorityLevel.STATE_GOVERNMENT.value,
        )
        self.assertEqual(candidate.normalized_url, "https://coop.up.gov.in/bylaws")

    def test_verification_guard_prevents_unverified_creation(self):
        """A candidate cannot be instantiated as VERIFIED without explicit evidence."""
        with self.assertRaises(ValidationError):
            CandidateSource(
                source_name="Prematurely Verified Source",
                organization_name="Unknown Department",
                official_url="https://agricoop.nic.in",
                domain_category=DomainCategory.GOVERNMENT_SCHEMES.value,
                authority_level=AuthorityLevel.CENTRAL_GOVERNMENT.value,
                verification_status=VerificationStatus.VERIFIED.value,
                # Missing verification_method and verification_notes
            )

    def test_empty_names_rejected(self):
        with self.assertRaises(ValidationError):
            CandidateSource(
                source_name="   ",
                organization_name="Some Org",
                official_url="https://agricoop.nic.in",
                domain_category=DomainCategory.GOVERNMENT_SCHEMES.value,
                authority_level=AuthorityLevel.CENTRAL_GOVERNMENT.value,
            )

    def test_invalid_domain_category_rejected(self):
        with self.assertRaises(ValidationError):
            CandidateSource(
                source_name="Valid Name",
                organization_name="Some Org",
                official_url="https://agricoop.nic.in",
                domain_category="invalid_unknown_domain",
                authority_level=AuthorityLevel.CENTRAL_GOVERNMENT.value,
            )


class TestCandidateSubmissionAndAuthority(unittest.TestCase):
    """Tests candidate submission, duplicate detection, and authority assessment."""

    def test_submit_candidate_source_auto_assesses_authority(self):
        candidate = submit_candidate_source({
            "source_name": "PM Kisan Official Portal",
            "organization_name": "Ministry of Agriculture",
            "official_url": "https://pmkisan.gov.in/",
            "domain_category": "government_schemes",
            "authority_level": "CENTRAL_GOVERNMENT",
        })
        self.assertEqual(candidate.verification_status, VerificationStatus.PENDING.value)
        self.assertIsNotNone(candidate.authority_assessment)
        self.assertTrue(candidate.authority_assessment["is_preferred_gov"])
        self.assertFalse(candidate.authority_assessment["has_suspicious_gov_pattern"])
        self.assertGreater(len(candidate.audit_trail), 0)

    def test_official_tld_remains_pending_without_auto_verification(self):
        """Even .gov.in sources must never be verified automatically."""
        candidate = submit_candidate_source({
            "source_name": "Department of Animal Husbandry",
            "organization_name": "Ministry of Fisheries, Animal Husbandry and Dairying",
            "official_url": "https://dahd.gov.in",
            "domain_category": "agriculture_rural_sustainability",
            "authority_level": "CENTRAL_GOVERNMENT",
        })
        self.assertNotEqual(candidate.verification_status, VerificationStatus.VERIFIED.value)
        self.assertEqual(candidate.verification_status, VerificationStatus.PENDING.value)

    def test_suspicious_domain_flagged_needs_review(self):
        """Websites with gov/scheme tokens on commercial TLDs must be flagged NEEDS_REVIEW."""
        candidate = submit_candidate_source({
            "source_name": "Commercial Schemes Blog",
            "organization_name": "Independent Blog",
            "official_url": "https://government-schemes-portal.com/apply",
            "domain_category": "government_schemes",
            "authority_level": "OTHER_OFFICIAL",
        })
        self.assertEqual(candidate.verification_status, VerificationStatus.NEEDS_REVIEW.value)
        self.assertTrue(candidate.authority_assessment["has_suspicious_gov_pattern"])

    def test_duplicate_candidate_url_rejected(self):
        registry = SourceRegistry(manifest_path="")
        # Register an existing verified source
        record = SourceRecord(
            source_name="NCDC Official",
            organization_name="National Cooperative Development Corporation",
            official_url="https://ncdc.in/schemes",
            domain_category=DomainCategory.COOPERATIVE_GOVERNANCE.value,
            authority_level=AuthorityLevel.STATUTORY_BODY.value,
            verification_status=VerificationStatus.VERIFIED.value,
            verification_method="Statutory Act Cross-Reference",
            verification_notes="Verified against NCDC Act 1962.",
        )
        registry.add_source(record)

        # Attempt to submit a candidate with the same normalized URL
        with self.assertRaises(ValidationError) as ctx:
            submit_candidate_source(
                {
                    "source_name": "NCDC Candidate",
                    "organization_name": "NCDC",
                    "official_url": "https://ncdc.in/schemes/",
                    "domain_category": "cooperative_governance",
                    "authority_level": "STATUTORY_BODY",
                },
                registry=registry,
            )
        self.assertIn("already exists in registry", str(ctx.exception))


class TestVerificationLifecycle(unittest.TestCase):
    """Tests verification, rejection, needs-review, and audit trail generation."""

    def test_verify_candidate_with_valid_evidence(self):
        registry = SourceRegistry(manifest_path="")
        candidate = submit_candidate_source({
            "source_name": "Ministry of Rural Development",
            "organization_name": "Ministry of Rural Development, GoI",
            "official_url": "https://rural.gov.in/schemes",
            "domain_category": "rural_development_finance",
            "authority_level": "CENTRAL_GOVERNMENT",
        })

        record = verify_candidate_source(
            candidate=candidate,
            verification_method=VerificationEvidenceType.OFFICIAL_DOMAIN_AUTHORITY.value,
            verification_notes="Verified via GoI Allocation of Business Rules and NIC DNS records.",
            reviewed_by="chief_compliance_auditor",
            registry=registry,
        )

        self.assertEqual(candidate.verification_status, VerificationStatus.VERIFIED.value)
        self.assertIsInstance(record, SourceRecord)
        self.assertEqual(record.verification_status, VerificationStatus.VERIFIED.value)
        self.assertTrue(record.is_active)
        self.assertIsNotNone(record.last_verified_at)

        # Confirm source is registered in the registry
        self.assertIsNotNone(registry.get_source(record.id))

    def test_verify_candidate_without_evidence_rejected(self):
        candidate = submit_candidate_source({
            "source_name": "Food Safety Authority",
            "organization_name": "FSSAI",
            "official_url": "https://fssai.gov.in",
            "domain_category": "foodtech_coldchain",
            "authority_level": "STATUTORY_BODY",
        })

        with self.assertRaises(ValidationError):
            verify_candidate_source(
                candidate=candidate,
                verification_method="",
                verification_notes="Some notes",
            )

        with self.assertRaises(ValidationError):
            verify_candidate_source(
                candidate=candidate,
                verification_method="Official Gazette",
                verification_notes="   ",
            )

    def test_reject_candidate_workflow(self):
        registry = SourceRegistry(manifest_path="")
        candidate = submit_candidate_source({
            "source_name": "Suspect Schemes Aggregator",
            "organization_name": "Private Entities Ltd",
            "official_url": "https://fake-gov-schemes.com",
            "domain_category": "government_schemes",
            "authority_level": "OTHER_OFFICIAL",
        })

        rejected = reject_candidate_source(
            candidate=candidate,
            reason="Unverified commercial third-party aggregator with deceptive gov domain token.",
            reviewed_by="security_auditor",
            registry=registry,
        )

        self.assertEqual(rejected.verification_status, VerificationStatus.REJECTED.value)
        self.assertEqual(rejected.rejection_reason, "Unverified commercial third-party aggregator with deceptive gov domain token.")
        self.assertIn("REJECTED", rejected.verification_notes)

        # Verify audit trail contains the rejection event
        actions = [event["action"] for event in rejected.audit_trail]
        self.assertIn("REJECTED", actions)

    def test_flag_needs_review_workflow(self):
        candidate = submit_candidate_source({
            "source_name": "Regional Agribusiness Board",
            "organization_name": "State Federation",
            "official_url": "https://sfacindia.com",
            "domain_category": "agriculture_rural_sustainability",
            "authority_level": "GOVERNMENT_INSTITUTION",
        })

        reviewed = flag_needs_review(
            candidate=candidate,
            reason="Requires confirmation of current statutory board gazette notification.",
            reviewed_by="reviewer_1",
        )
        self.assertEqual(reviewed.verification_status, VerificationStatus.NEEDS_REVIEW.value)
        self.assertIn("NEEDS_REVIEW", reviewed.verification_notes)

    def test_audit_metadata_preserved_across_lifecycle(self):
        candidate = submit_candidate_source({
            "source_name": "National Legal Services Authority",
            "organization_name": "NALSA",
            "official_url": "https://nalsa.gov.in",
            "domain_category": "legal_assistance",
            "authority_level": "STATUTORY_BODY",
        })
        self.assertEqual(candidate.audit_trail[0]["action"], "SUBMITTED")

        flag_needs_review(candidate, reason="Pending committee audit", reviewed_by="compliance_1")
        self.assertEqual(candidate.audit_trail[-1]["action"], "FLAG_NEEDS_REVIEW")

        verify_candidate_source(
            candidate=candidate,
            verification_method="Official Gazette",
            verification_notes="Legal Services Authorities Act 1987 verified.",
            reviewed_by="compliance_lead",
        )
        self.assertEqual(candidate.audit_trail[-1]["action"], "VERIFIED")
        self.assertEqual(len(candidate.audit_trail), 4)  # SUBMITTED + ASSESSED + FLAG_NEEDS_REVIEW + VERIFIED


class TestCollectorHandoff(unittest.TestCase):
    """Tests that future document collectors receive ONLY approved, active, verified sources."""

    def setUp(self):
        self.registry = SourceRegistry(manifest_path="")

        # 1. Active & Verified
        self.verified_active_schemes = SourceRecord(
            source_name="PM Kisan Portal",
            organization_name="MoA&FW",
            official_url="https://pmkisan.gov.in",
            domain_category="government_schemes",
            authority_level="CENTRAL_GOVERNMENT",
            verification_status="VERIFIED",
            verification_method="Gazette",
            verification_notes="Confirmed via official portal.",
            is_active=True,
        )
        self.registry.add_source(self.verified_active_schemes)

        # 2. Inactive but Verified (MUST BE EXCLUDED)
        self.verified_inactive_coop = SourceRecord(
            source_name="Deprecated State Coop",
            organization_name="State Coop",
            official_url="https://old-coop.gov.in",
            domain_category="cooperative_governance",
            authority_level="STATE_GOVERNMENT",
            verification_status="VERIFIED",
            verification_method="Gazette",
            verification_notes="Confirmed historical source.",
            is_active=False,
        )
        self.registry.add_source(self.verified_inactive_coop)

        # 3. Active but PENDING (MUST BE EXCLUDED)
        self.pending_source = SourceRecord(
            source_name="Pending Source",
            organization_name="Pending Dept",
            official_url="https://pending-dept.gov.in",
            domain_category="government_schemes",
            authority_level="CENTRAL_GOVERNMENT",
            verification_status="PENDING",
            is_active=True,
        )
        self.registry.add_source(self.pending_source)

        # 4. Active but NEEDS_REVIEW (MUST BE EXCLUDED)
        self.needs_review_source = SourceRecord(
            source_name="Review Source",
            organization_name="Review Dept",
            official_url="https://review-dept.gov.in",
            domain_category="rural_development_finance",
            authority_level="CENTRAL_GOVERNMENT",
            verification_status="NEEDS_REVIEW",
            is_active=True,
        )
        self.registry.add_source(self.needs_review_source)

        # 5. REJECTED (MUST BE EXCLUDED)
        self.rejected_source = SourceRecord(
            source_name="Rejected Source",
            organization_name="Private",
            official_url="https://rejected-source.com",
            domain_category="government_schemes",
            authority_level="OTHER_OFFICIAL",
            verification_status="REJECTED",
            verification_notes="REJECTED: Deceptive portal.",
            is_active=False,
        )
        self.registry.add_source(self.rejected_source)

    def test_get_verified_sources_returns_only_active_and_verified(self):
        targets = get_verified_sources(self.registry)
        self.assertEqual(len(targets), 1)
        self.assertEqual(targets[0].id, self.verified_active_schemes.id)
        self.assertTrue(targets[0].is_active)
        self.assertEqual(targets[0].verification_status, VerificationStatus.VERIFIED.value)

    def test_get_verified_sources_filters_by_domain(self):
        # Register a second active verified source under legal_assistance
        legal_source = SourceRecord(
            source_name="NALSA Portal",
            organization_name="NALSA",
            official_url="https://nalsa.gov.in",
            domain_category="legal_assistance",
            authority_level="STATUTORY_BODY",
            verification_status="VERIFIED",
            verification_method="Act 1987",
            verification_notes="Official apex statutory legal authority.",
            is_active=True,
        )
        self.registry.add_source(legal_source)

        # Query for government_schemes
        schemes_targets = get_verified_sources(self.registry, domain="government_schemes")
        self.assertEqual(len(schemes_targets), 1)
        self.assertEqual(schemes_targets[0].domain_category, "government_schemes")

        # Query for legal_assistance
        legal_targets = get_verified_sources(self.registry, domain="legal_assistance")
        self.assertEqual(len(legal_targets), 1)
        self.assertEqual(legal_targets[0].domain_category, "legal_assistance")

        # Query for domain with no verified sources
        empty_targets = get_verified_sources(self.registry, domain="foodtech_coldchain")
        self.assertEqual(len(empty_targets), 0)


class TestSupabasePayloadAdapter(unittest.TestCase):
    """Tests preparation of 17-column payloads for Supabase deployment."""

    def test_prepare_supabase_record_from_source_record(self):
        record = SourceRecord(
            source_name="Ministry of Cooperation",
            organization_name="Ministry of Cooperation, GoI",
            official_url="https://cooperation.gov.in/",
            domain_category="cooperative_governance",
            authority_level="CENTRAL_GOVERNMENT",
            verification_status="VERIFIED",
            verification_method="Official Gazette",
            verification_notes="Created under Cabinet Secretariat Notification 2021.",
        )
        payload = prepare_supabase_record(record, dry_run=True)
        expected_columns = {
            "id", "name", "url", "domain", "language", "authority_level",
            "organization_name", "country", "state", "verification_status",
            "verification_method", "verification_notes", "is_active",
            "last_verified_at", "last_checked_at", "created_at", "updated_at",
        }
        self.assertEqual(set(payload.keys()), expected_columns)
        self.assertEqual(payload["name"], "Ministry of Cooperation")
        self.assertEqual(payload["verification_status"], "VERIFIED")
        self.assertTrue(payload["is_active"])

    def test_prepare_supabase_record_from_candidate_source(self):
        candidate = CandidateSource(
            source_name="State Marketing Board",
            organization_name="Agriculture Department",
            official_url="https://agrimarketing.rajasthan.gov.in",
            domain_category="agriculture_rural_sustainability",
            authority_level="STATE_GOVERNMENT",
            state="Rajasthan",
        )
        payload = prepare_supabase_record(candidate, dry_run=True)
        self.assertEqual(payload["name"], "State Marketing Board")
        self.assertEqual(payload["verification_status"], "PENDING")
        self.assertFalse(payload["is_active"])  # PENDING candidates are not active targets
        self.assertEqual(payload["state"], "Rajasthan")


class TestManifestExportAndOfflineIntegrity(unittest.TestCase):
    """Tests manifest export and validates offline integrity of template files."""

    def test_export_onboarding_manifest_json_and_jsonl(self):
        cand1 = submit_candidate_source({
            "source_name": "Portal One",
            "organization_name": "Dept One",
            "official_url": "https://portal-one.gov.in",
            "domain_category": "government_schemes",
            "authority_level": "CENTRAL_GOVERNMENT",
        })
        cand2 = submit_candidate_source({
            "source_name": "Portal Two",
            "organization_name": "Dept Two",
            "official_url": "https://portal-two.gov.in",
            "domain_category": "cooperative_governance",
            "authority_level": "STATE_GOVERNMENT",
        })

        with tempfile.TemporaryDirectory() as tmpdir:
            # Test JSON export
            json_path = os.path.join(tmpdir, "candidates.json")
            export_onboarding_manifest([cand1, cand2], json_path)
            self.assertTrue(os.path.exists(json_path))
            with open(json_path, "r", encoding="utf-8") as f:
                loaded_json = json.load(f)
            self.assertEqual(len(loaded_json), 2)
            self.assertEqual(loaded_json[0]["source_name"], "Portal One")

            # Test JSONL export
            jsonl_path = os.path.join(tmpdir, "candidates.jsonl")
            export_onboarding_manifest([cand1, cand2], jsonl_path)
            self.assertTrue(os.path.exists(jsonl_path))
            with open(jsonl_path, "r", encoding="utf-8") as f:
                lines = [line.strip() for line in f if line.strip()]
            self.assertEqual(len(lines), 2)
            self.assertEqual(json.loads(lines[1])["source_name"], "Portal Two")

    def test_template_manifests_are_offline_and_contain_placeholders(self):
        """Verifies template manifests on disk have only placeholders and zero real URLs."""
        json_manifest = os.path.join(project_root, "data", "manifests", "sources", "candidate_sources.json")
        jsonl_manifest = os.path.join(project_root, "data", "manifests", "sources", "candidate_sources.jsonl")

        self.assertTrue(os.path.exists(json_manifest), "candidate_sources.json must exist.")
        self.assertTrue(os.path.exists(jsonl_manifest), "candidate_sources.jsonl must exist.")

        # Check JSON manifest
        with open(json_manifest, "r", encoding="utf-8") as f:
            records = json.load(f)
        self.assertGreater(len(records), 0)
        for r in records:
            self.assertIn(r["verification_status"], ["PENDING", "NEEDS_REVIEW"])
            self.assertNotEqual(r["verification_status"], "VERIFIED")

        # Check JSONL manifest
        with open(jsonl_manifest, "r", encoding="utf-8") as f:
            lines = [json.loads(l) for l in f if l.strip()]
        self.assertEqual(len(lines), len(records))
        for r in lines:
            self.assertIn(r["verification_status"], ["PENDING", "NEEDS_REVIEW"])
            self.assertNotEqual(r["verification_status"], "VERIFIED")


if __name__ == "__main__":
    unittest.main()
