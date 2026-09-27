"""
NEXO Data Platform - Schema and Configuration Validation Tests
Performs offline structural validation of the SQL migration files and client config.
Does NOT perform destructive database modifications.
"""

import os
import re
import sys
import unittest

# Ensure project root is in sys.path
project_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if project_root not in sys.path:
    sys.path.insert(0, project_root)

from config.settings import get_settings, Settings
from config.supabase_client import get_supabase_client, check_connection


class TestSQLMigrationSchema(unittest.TestCase):
    """Validates the PostgreSQL schema DDL syntax, constraints, and relationships."""

    @classmethod
    def setUpClass(cls):
        cls.migration_path = os.path.join(
            project_root, "scripts", "migrations", "001_initial_schema.sql"
        )
        cls.canonical_path = os.path.join(project_root, "scripts", "schema.sql")
        with open(cls.migration_path, "r", encoding="utf-8") as f:
            cls.sql_content = f.read()

    def test_migration_files_exist(self):
        self.assertTrue(os.path.exists(self.migration_path), "001_initial_schema.sql must exist")
        self.assertTrue(os.path.exists(self.canonical_path), "schema.sql must exist")

    def test_required_tables_present(self):
        expected_tables = [
            "sources",
            "schemes",
            "scheme_versions",
            "documents",
            "data_sync_logs",
        ]
        for table in expected_tables:
            pattern = rf"CREATE\s+TABLE\s+(IF\s+NOT\s+EXISTS\s+)?{table}\s*\("
            match = re.search(pattern, self.sql_content, re.IGNORECASE)
            self.assertIsNotNone(match, f"Table '{table}' definition missing in SQL migration")

    def test_uuid_primary_keys(self):
        expected_tables = [
            "sources",
            "schemes",
            "scheme_versions",
            "documents",
            "data_sync_logs",
        ]
        for table in expected_tables:
            # Check for id UUID PRIMARY KEY DEFAULT gen_random_uuid()
            pattern = rf"{table}\s*\([^;]*?id\s+UUID\s+PRIMARY\s+KEY\s+DEFAULT\s+gen_random_uuid\(\)"
            match = re.search(pattern, self.sql_content, re.IGNORECASE | re.DOTALL)
            self.assertIsNotNone(
                match, f"Table '{table}' must have 'id UUID PRIMARY KEY DEFAULT gen_random_uuid()'"
            )

    def test_foreign_key_relationships(self):
        relations = [
            ("schemes", r"source_id\s+UUID\s+REFERENCES\s+sources\s*\(\s*id\s*\)"),
            ("scheme_versions", r"scheme_id\s+UUID\s+NOT\s+NULL\s+REFERENCES\s+schemes\s*\(\s*id\s*\)"),
            ("documents", r"source_id\s+UUID\s+REFERENCES\s+sources\s*\(\s*id\s*\)"),
            ("documents", r"scheme_id\s+UUID\s+REFERENCES\s+schemes\s*\(\s*id\s*\)"),
            ("data_sync_logs", r"source_id\s+UUID\s+REFERENCES\s+sources\s*\(\s*id\s*\)"),
        ]
        for table, rel_pattern in relations:
            match = re.search(rel_pattern, self.sql_content, re.IGNORECASE)
            self.assertIsNotNone(match, f"Foreign key relationship for '{table}' ({rel_pattern}) missing")

    def test_unique_constraints(self):
        # sources.url UNIQUE
        self.assertRegex(self.sql_content, r"url\s+TEXT\s+NOT\s+NULL\s+UNIQUE", "sources.url should be UNIQUE")
        # documents.sha256 UNIQUE
        self.assertRegex(self.sql_content, r"sha256\s+TEXT\s+NOT\s+NULL\s+UNIQUE", "documents.sha256 should be UNIQUE")
        # scheme_versions (scheme_id, version_number) UNIQUE
        self.assertRegex(
            self.sql_content,
            r"UNIQUE\s*\(\s*scheme_id\s*,\s*version_number\s*\)",
            "scheme_versions should have UNIQUE(scheme_id, version_number)",
        )

    def test_jsonb_columns_in_scheme_versions(self):
        self.assertRegex(
            self.sql_content,
            r"changed_fields\s+JSONB",
            "scheme_versions.changed_fields must be JSONB",
        )
        self.assertRegex(
            self.sql_content,
            r"snapshot\s+JSONB\s+NOT\s+NULL",
            "scheme_versions.snapshot must be JSONB NOT NULL",
        )

    def test_updated_at_triggers(self):
        self.assertIn("update_updated_at_column", self.sql_content)
        self.assertIn("trg_sources_updated_at", self.sql_content)
        self.assertIn("trg_schemes_updated_at", self.sql_content)
        self.assertIn("trg_documents_updated_at", self.sql_content)

    def test_indexes_defined(self):
        expected_indexes = [
            "idx_sources_domain",
            "idx_sources_language",
            "idx_schemes_domain",
            "idx_schemes_source_id",
            "idx_scheme_versions_scheme_id",
            "idx_scheme_versions_is_current",
            "idx_documents_source_id",
            "idx_documents_sha256",
            "idx_data_sync_logs_source_id",
            "idx_data_sync_logs_status",
        ]
        for idx in expected_indexes:
            self.assertIn(idx, self.sql_content, f"Index '{idx}' should be defined")

    def test_row_level_security_enabled(self):
        tables = ["sources", "schemes", "scheme_versions", "documents", "data_sync_logs"]
        for table in tables:
            pattern = rf"ALTER\s+TABLE\s+{table}\s+ENABLE\s+ROW\s+LEVEL\s+SECURITY;"
            match = re.search(pattern, self.sql_content, re.IGNORECASE)
            self.assertIsNotNone(match, f"RLS must be enabled on table '{table}'")


class TestDatabaseConfiguration(unittest.TestCase):
    """Tests the Python configuration and client connection helper."""

    def test_settings_masking(self):
        test_settings = Settings(
            supabase_url="https://xyzcompany.supabase.co",
            supabase_publishable_key="sb_publishable_secret_key_12345",
            supabase_service_role_key="sb_service_role_secret_key_67890",
            environment="test",
        )
        repr_output = repr(test_settings)
        # Verify secret keys are masked in string representation
        self.assertNotIn("secret_key", repr_output)
        self.assertIn("...", repr_output)

    def test_client_initialization_and_health_check(self):
        health = check_connection()
        self.assertEqual(health.get("status"), "connected")
        self.assertTrue(health.get("auth_available"))
        self.assertTrue(health.get("storage_available"))
        self.assertTrue(health.get("postgrest_available"))


class TestMigration002AndDeploy(unittest.TestCase):
    """Validates migration 002 and the consolidated deploy_supabase.sql script."""

    @classmethod
    def setUpClass(cls):
        cls.mig002_path = os.path.join(
            project_root, "scripts", "migrations", "002_add_source_verification_fields.sql"
        )
        cls.deploy_path = os.path.join(project_root, "scripts", "deploy_supabase.sql")
        with open(cls.mig002_path, "r", encoding="utf-8") as f:
            cls.mig002_content = f.read()
        with open(cls.deploy_path, "r", encoding="utf-8") as f:
            cls.deploy_content = f.read()

    def test_migration_002_exists_and_valid(self):
        self.assertTrue(os.path.exists(self.mig002_path))
        expected_cols = [
            "organization_name", "country", "state",
            "verification_status", "verification_method",
            "verification_notes", "last_verified_at"
        ]
        for col in expected_cols:
            self.assertIn(col, self.mig002_content)
        self.assertIn("chk_sources_verification_status", self.mig002_content)
        self.assertIn("nexo-government-documents", self.mig002_content)
        self.assertIn("storage.objects", self.mig002_content)

    def test_deploy_supabase_script_comprehensive(self):
        self.assertTrue(os.path.exists(self.deploy_path))
        for tbl in ["sources", "schemes", "scheme_versions", "documents", "data_sync_logs"]:
            self.assertIn(tbl, self.deploy_content)
        self.assertIn("nexo-government-documents", self.deploy_content)
        self.assertIn("ENABLE ROW LEVEL SECURITY", self.deploy_content)


if __name__ == "__main__":
    unittest.main()
