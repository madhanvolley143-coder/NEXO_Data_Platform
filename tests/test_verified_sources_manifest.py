"""
NEXO Data Platform - Verified Sources Manifest Test Suite
Validates the curated official government source manifest:
1. File existence and JSON/JSONL format
2. Full schema validation via SourceRecord
3. Domain coverage across all 7 NEXO focus domains
4. Strict VERIFIED status and is_active flag enforcement
5. Normalized URL uniqueness (zero duplicates)
6. Non-vague, concrete verification evidence
7. Supabase 17-column seed preview conformity
8. Candidate review/rejection manifest integrity
Runs 100% offline.
"""

import json
import os
import sys
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
from app.sources.onboarding import VerificationEvidenceType


class TestVerifiedSourcesManifest(unittest.TestCase):
    """Verifies the integrity of curated official sources."""

    @classmethod
    def setUpClass(cls):
        cls.manifests_dir = os.path.join(project_root, "data", "manifests", "sources")
        cls.json_path = os.path.join(cls.manifests_dir, "verified_sources.json")
        cls.jsonl_path = os.path.join(cls.manifests_dir, "verified_sources.jsonl")
        cls.seed_path = os.path.join(cls.manifests_dir, "supabase_source_seed_preview.json")
        cls.candidates_path = os.path.join(cls.manifests_dir, "candidate_sources.json")

    def test_verified_sources_json_structure_and_count(self):
        self.assertTrue(os.path.exists(self.json_path), "verified_sources.json must exist.")
        with open(self.json_path, "r", encoding="utf-8") as f:
            data = json.load(f)

        self.assertIsInstance(data, list)
        self.assertEqual(len(data), 23, "Expected 23 curated official sources.")

        for item in data:
            record = SourceRecord(**item)
            self.assertEqual(record.verification_status, VerificationStatus.VERIFIED.value)
            self.assertTrue(record.is_active)
            self.assertIsNotNone(record.last_verified_at)

    def test_verified_sources_jsonl_matches_json(self):
        self.assertTrue(os.path.exists(self.jsonl_path), "verified_sources.jsonl must exist.")
        with open(self.jsonl_path, "r", encoding="utf-8") as f:
            lines = [line.strip() for line in f if line.strip()]

        self.assertEqual(len(lines), 23)

        with open(self.json_path, "r", encoding="utf-8") as f:
            json_data = json.load(f)

        for line, json_item in zip(lines, json_data):
            parsed = json.loads(line)
            self.assertEqual(parsed["normalized_url"], json_item["normalized_url"])
            self.assertEqual(parsed["domain_category"], json_item["domain_category"])

    def test_domain_coverage_across_all_seven_domains(self):
        with open(self.json_path, "r", encoding="utf-8") as f:
            data = json.load(f)

        domains_found = set()
        domain_counts = {}

        for item in data:
            d = item["domain_category"]
            domains_found.add(d)
            domain_counts[d] = domain_counts.get(d, 0) + 1

        all_expected_domains = {d.value for d in DomainCategory}
        self.assertEqual(
            domains_found,
            all_expected_domains,
            "All 7 NEXO domains must have curated sources.",
        )

        for d, count in domain_counts.items():
            self.assertGreaterEqual(
                count,
                2,
                f"Domain '{d}' must have at least 2 verified sources (has {count}).",
            )

    def test_strict_verified_status_and_active_flag(self):
        with open(self.json_path, "r", encoding="utf-8") as f:
            data = json.load(f)

        for item in data:
            self.assertEqual(item["verification_status"], "VERIFIED")
            self.assertTrue(item["is_active"])
            self.assertFalse(item.get("has_suspicious_gov_pattern", False))

    def test_normalized_url_uniqueness(self):
        with open(self.json_path, "r", encoding="utf-8") as f:
            data = json.load(f)

        urls = [item["normalized_url"] for item in data]
        unique_urls = set(urls)
        self.assertEqual(
            len(urls),
            len(unique_urls),
            "All verified sources must have unique normalized URLs.",
        )

    def test_verification_evidence_validity(self):
        valid_evidence_types = {e.value for e in VerificationEvidenceType}
        with open(self.json_path, "r", encoding="utf-8") as f:
            data = json.load(f)

        for item in data:
            method = item.get("verification_method")
            notes = item.get("verification_notes")

            self.assertIn(
                method,
                valid_evidence_types,
                f"Source '{item['source_name']}' has invalid verification method '{method}'",
            )
            self.assertIsNotNone(notes)
            self.assertGreater(
                len(notes.strip()),
                20,
                f"Source '{item['source_name']}' has insufficiently detailed verification notes.",
            )

    def test_supabase_seed_preview_schema_alignment(self):
        self.assertTrue(os.path.exists(self.seed_path), "supabase_source_seed_preview.json must exist.")
        with open(self.seed_path, "r", encoding="utf-8") as f:
            payloads = json.load(f)

        self.assertEqual(len(payloads), 23)

        expected_columns = {
            "id", "name", "url", "domain", "language", "authority_level",
            "organization_name", "country", "state", "verification_status",
            "verification_method", "verification_notes", "is_active",
            "last_verified_at", "last_checked_at", "created_at", "updated_at",
        }

        for p in payloads:
            self.assertEqual(
                set(p.keys()),
                expected_columns,
                f"Payload for '{p.get('name')}' does not match the 17-column Supabase schema.",
            )
            self.assertEqual(p["verification_status"], "VERIFIED")
            self.assertTrue(p["is_active"])

    def test_candidate_sources_review_status(self):
        self.assertTrue(os.path.exists(self.candidates_path), "candidate_sources.json must exist.")
        with open(self.candidates_path, "r", encoding="utf-8") as f:
            candidates = json.load(f)

        self.assertGreater(len(candidates), 0)
        for c in candidates:
            # None of the candidate review records should be marked VERIFIED
            self.assertNotEqual(
                c["verification_status"],
                "VERIFIED",
                f"Candidate '{c.get('source_name')}' must not be VERIFIED.",
            )
            self.assertIn(
                c["verification_status"],
                ["PENDING", "NEEDS_REVIEW", "REJECTED"],
            )


if __name__ == "__main__":
    unittest.main()
