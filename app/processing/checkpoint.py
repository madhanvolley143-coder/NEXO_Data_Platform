"""
NEXO Data Platform - Checkpoint & Idempotency Manager
Ensures idempotent execution:
- Same raw SHA-256 + same processor version does not create duplicate processing records.
- If already processed successfully: return SKIPPED_ALREADY_PROCESSED.
- If processor version changes: allow a new processing result while keeping raw files untouched.
- Provides atomic persistence of processing checkpoint.
"""

import os
import json
from typing import Dict, Any, Optional, Tuple
from datetime import datetime, timezone
from config.logging_config import get_logger

logger = get_logger("processing.checkpoint")

DEFAULT_CHECKPOINT_DIR = os.path.join("data", "manifests", "processing")
DEFAULT_CHECKPOINT_FILE = os.path.join(DEFAULT_CHECKPOINT_DIR, "processing_checkpoint.json")


class ProcessingCheckpoint:
    """Manages processing checkpoint state and enforces pipeline idempotency."""

    def __init__(self, checkpoint_path: Optional[str] = None):
        self.checkpoint_path = checkpoint_path or DEFAULT_CHECKPOINT_FILE
        self.data: Dict[str, Any] = {"last_updated": None, "processed_documents": {}}
        self.load()

    def load(self) -> None:
        """Loads checkpoint from disk if present."""
        if os.path.isfile(self.checkpoint_path):
            try:
                with open(self.checkpoint_path, "r", encoding="utf-8") as f:
                    self.data = json.load(f)
            except Exception as exc:
                logger.warning(f"Could not load checkpoint from {self.checkpoint_path}: {exc}")
                self.data = {"last_updated": None, "processed_documents": {}}

    def save(self) -> None:
        """Persists checkpoint atomically to disk."""
        self.data["last_updated"] = datetime.now(timezone.utc).isoformat()
        checkpoint_dir = os.path.dirname(self.checkpoint_path)
        if checkpoint_dir:
            os.makedirs(checkpoint_dir, exist_ok=True)

        temp_path = self.checkpoint_path + ".tmp"
        try:
            with open(temp_path, "w", encoding="utf-8") as f:
                json.dump(self.data, f, indent=2, ensure_ascii=False)
            os.replace(temp_path, self.checkpoint_path)
        except Exception as exc:
            logger.error(f"Failed to persist checkpoint to {self.checkpoint_path}: {exc}")

    def is_already_processed(
        self,
        raw_sha256: str,
        current_processor_version: str,
        force_reprocess: bool = False,
    ) -> Tuple[bool, Optional[Dict[str, Any]]]:
        """
        Determines whether document with raw_sha256 has already been processed
        under current_processor_version.
        Returns: (is_processed, previous_record)
        """
        if force_reprocess:
            return False, None

        clean_sha = (raw_sha256 or "").lower().strip()
        proc_history = self.data.setdefault("processed_documents", {})

        if clean_sha in proc_history:
            prev = proc_history[clean_sha]
            # If processor version matches and status was processed
            if prev.get("processor_version") == current_processor_version:
                return True, prev

        return False, None

    def record(
        self,
        raw_sha256: str,
        record_info: Dict[str, Any],
    ) -> None:
        """Records document processing state in checkpoint."""
        clean_sha = (raw_sha256 or "").lower().strip()
        self.data.setdefault("processed_documents", {})[clean_sha] = record_info
        self.save()


# Backward-compatible alias
CheckpointManager = ProcessingCheckpoint
