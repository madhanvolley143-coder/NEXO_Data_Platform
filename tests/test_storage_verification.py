"""
NEXO Data Platform - Storage Verification Tri-State Unit Tests
Tests that the deployment verifier correctly distinguishes:
1. BUCKET_EXISTS
2. BUCKET_NOT_FOUND
3. BUCKET_VERIFICATION_UNAVAILABLE
Runs 100% offline using mock storage clients.
"""

import os
import sys
import unittest
from unittest.mock import MagicMock

# Ensure project root is in sys.path
project_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if project_root not in sys.path:
    sys.path.insert(0, project_root)

from scripts.verify_supabase_deployment import (
    check_bucket_status,
    BUCKET_EXISTS,
    BUCKET_NOT_FOUND,
    BUCKET_VERIFICATION_UNAVAILABLE,
)


class MockBucket:
    """Mock Supabase Storage Bucket object."""
    def __init__(self, name: str, public: bool = False):
        self.name = name
        self.public = public


class TestStorageBucketVerification(unittest.TestCase):
    """Verifies that storage checks distinguish permissions from actual missing status."""

    def test_bucket_exists_when_returned_by_api(self):
        """Case 1: BUCKET_EXISTS when client can see the bucket."""
        mock_client = MagicMock()
        mock_client.storage.list_buckets.return_value = [
            MockBucket("nexo-government-documents", public=False)
        ]

        result = check_bucket_status(
            client=mock_client,
            bucket_name="nexo-government-documents",
            has_admin_credentials=False,
        )
        self.assertEqual(result["status"], BUCKET_EXISTS)
        self.assertFalse(result["is_public"])
        self.assertIn("confirmed present", result["message"].lower())

    def test_bucket_not_found_when_admin_queries_and_missing(self):
        """Case 2: BUCKET_NOT_FOUND when admin credentials query and bucket is absent."""
        mock_client = MagicMock()
        mock_client.storage.list_buckets.return_value = [
            MockBucket("other-bucket", public=False)
        ]

        result = check_bucket_status(
            client=mock_client,
            bucket_name="nexo-government-documents",
            has_admin_credentials=True,
        )
        self.assertEqual(result["status"], BUCKET_NOT_FOUND)
        self.assertIn("verified absent", result["message"].lower())

    def test_bucket_verification_unavailable_for_anon_client_with_empty_list(self):
        """Case 3: BUCKET_VERIFICATION_UNAVAILABLE when anonymous client receives empty list."""
        mock_client = MagicMock()
        # Supabase returns [] to anon users when buckets are private
        mock_client.storage.list_buckets.return_value = []

        result = check_bucket_status(
            client=mock_client,
            bucket_name="nexo-government-documents",
            has_admin_credentials=False,
        )
        self.assertEqual(result["status"], BUCKET_VERIFICATION_UNAVAILABLE)
        self.assertIn("requires admin-level verification", result["message"])

    def test_bucket_verification_unavailable_on_permission_error(self):
        """Case 4: BUCKET_VERIFICATION_UNAVAILABLE when storage raises unauthorized or 403."""
        mock_client = MagicMock()
        mock_client.storage.list_buckets.side_effect = Exception(
            "403 Client Error: row-level security policy violation"
        )

        result = check_bucket_status(
            client=mock_client,
            bucket_name="nexo-government-documents",
            has_admin_credentials=False,
        )
        self.assertEqual(result["status"], BUCKET_VERIFICATION_UNAVAILABLE)
        self.assertIn("admin-level verification", result["message"])

    def test_client_none_returns_unavailable(self):
        result = check_bucket_status(client=None, bucket_name="nexo-government-documents")
        self.assertEqual(result["status"], BUCKET_VERIFICATION_UNAVAILABLE)


if __name__ == "__main__":
    unittest.main()
