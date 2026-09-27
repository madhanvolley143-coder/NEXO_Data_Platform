"""
NEXO Data Platform - Processed Artifact Storage & Manifest Manager
Manages persistence of processed document artifacts in the separate processed storage structure:
  processed/{domain}/{source_id}/{raw_sha256}/
      extracted.txt
      metadata.json
      processing_manifest.json

Safely isolates processed artifacts from raw storage.
"""

import os
import json
from typing import Dict, Any, Optional, List
from config.logging_config import get_logger

logger = get_logger("processing.manifest")

DEFAULT_LOCAL_PROCESSED_DIR = os.path.join("data", "processed_artifacts")
DEFAULT_MANIFEST_DIR = os.path.join("data", "manifests", "processing")


class ProcessedStorageManager:
    """Manages the generation, local staging, and storage paths of processed artifacts."""

    def __init__(self, local_base_dir: Optional[str] = None):
        self.local_base_dir = local_base_dir or DEFAULT_LOCAL_PROCESSED_DIR
        os.makedirs(self.local_base_dir, exist_ok=True)

    def get_relative_storage_prefix(self, domain: str, source_id: str, raw_sha256: str) -> str:
        """Returns the canonical cloud storage path prefix for processed artifacts."""
        clean_domain = (domain or "general").strip().lower().replace(" ", "_")
        clean_source = (source_id or "unknown_source").strip()
        clean_sha = (raw_sha256 or "unknown_sha").strip().lower()
        return f"processed/{clean_domain}/{clean_source}/{clean_sha}"

    def get_local_directory(self, domain: str, source_id: str, raw_sha256: str) -> str:
        """Returns the local filesystem path for staging artifacts."""
        clean_domain = (domain or "general").strip().lower().replace(" ", "_")
        clean_source = (source_id or "unknown_source").strip()
        clean_sha = (raw_sha256 or "unknown_sha").strip().lower()
        return os.path.join(self.local_base_dir, clean_domain, clean_source, clean_sha)

    def save_artifacts(
        self,
        domain: str,
        source_id: str,
        raw_sha256: str,
        extracted_text: str,
        metadata: Dict[str, Any],
        manifest: Dict[str, Any],
    ) -> Dict[str, str]:
        """
        Saves extracted.txt, metadata.json, and processing_manifest.json locally.
        Returns a dict of paths to the saved files.
        """
        dir_path = self.get_local_directory(domain, source_id, raw_sha256)
        os.makedirs(dir_path, exist_ok=True)

        txt_path = os.path.join(dir_path, "extracted.txt")
        meta_path = os.path.join(dir_path, "metadata.json")
        man_path = os.path.join(dir_path, "processing_manifest.json")

        # 1. extracted.txt
        with open(txt_path + ".tmp", "w", encoding="utf-8") as f:
            f.write(extracted_text or "")
        os.replace(txt_path + ".tmp", txt_path)

        # 2. metadata.json
        with open(meta_path + ".tmp", "w", encoding="utf-8") as f:
            json.dump(metadata, f, indent=2, ensure_ascii=False)
        os.replace(meta_path + ".tmp", meta_path)

        # 3. processing_manifest.json
        with open(man_path + ".tmp", "w", encoding="utf-8") as f:
            json.dump(manifest, f, indent=2, ensure_ascii=False)
        os.replace(man_path + ".tmp", man_path)

        return {
            "local_dir": dir_path,
            "extracted_txt": txt_path,
            "metadata_json": meta_path,
            "processing_manifest_json": man_path,
            "storage_prefix": self.get_relative_storage_prefix(domain, source_id, raw_sha256),
        }

    def write_overall_manifests(
        self,
        manifest_dir: str,
        entries: List[Dict[str, Any]],
        stats_dict: Dict[str, Any],
    ) -> Dict[str, str]:
        """Writes summary and audit manifests for an entire processing run."""
        os.makedirs(manifest_dir, exist_ok=True)
        json_path = os.path.join(manifest_dir, "content_processing_manifest.json")
        jsonl_path = os.path.join(manifest_dir, "content_processing_manifest.jsonl")
        summary_path = os.path.join(manifest_dir, "content_processing_summary.json")

        with open(json_path, "w", encoding="utf-8") as f:
            json.dump(entries, f, indent=2, ensure_ascii=False)

        with open(jsonl_path, "w", encoding="utf-8") as f:
            for item in entries:
                f.write(json.dumps(item, ensure_ascii=False) + "\n")

        with open(summary_path, "w", encoding="utf-8") as f:
            json.dump(stats_dict, f, indent=2, ensure_ascii=False)

        return {
            "manifest_json": json_path,
            "manifest_jsonl": jsonl_path,
            "summary_json": summary_path,
        }


# Backward-compatible alias
ManifestManager = ProcessedStorageManager
