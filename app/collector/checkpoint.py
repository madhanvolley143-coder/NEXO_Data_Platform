"""
NEXO Data Platform - Collector Checkpoint & Resume Manager
Preserves crawl state across sessions to prevent redundant HTTP requests and enable
safe resumption of interrupted crawls.
"""

import json
import os
from datetime import datetime, timezone
from typing import Set, Dict, Any, Optional

from config.logging_config import get_logger

logger = get_logger("collector.checkpoint")

DEFAULT_CHECKPOINT_FILE = os.path.join("data", "manifests", "collector", "checkpoint.json")


class CheckpointManager:
    """Manages crawl checkpoints and URL deduplication across sessions."""

    def __init__(self, checkpoint_path: Optional[str] = None):
        self.checkpoint_path = checkpoint_path or DEFAULT_CHECKPOINT_FILE
        self.visited_urls: Set[str] = set()
        self.processed_hashes: Set[str] = set()
        self.completed_sources: Set[str] = set()
        self.load()

    def is_visited(self, url: str) -> bool:
        """Checks if a URL has already been processed."""
        return url.strip() in self.visited_urls

    def mark_visited(self, url: str) -> None:
        """Marks a URL as visited."""
        self.visited_urls.add(url.strip())

    def mark_hash_processed(self, sha256: str) -> None:
        """Marks a content hash as processed."""
        self.processed_hashes.add(sha256.lower().strip())

    def is_hash_processed(self, sha256: str) -> bool:
        """Checks if this exact content hash has already been stored."""
        return sha256.lower().strip() in self.processed_hashes

    def mark_source_completed(self, source_id: str) -> None:
        """Marks a source as completed."""
        self.completed_sources.add(source_id.strip())

    def is_source_completed(self, source_id: str) -> bool:
        """Checks if a source was completed in a previous session."""
        return source_id.strip() in self.completed_sources

    def save(self) -> None:
        """Persists current state to JSON."""
        os.makedirs(os.path.dirname(os.path.abspath(self.checkpoint_path)), exist_ok=True)
        data = {
            "visited_urls": sorted(list(self.visited_urls)),
            "processed_hashes": sorted(list(self.processed_hashes)),
            "completed_sources": sorted(list(self.completed_sources)),
            "last_updated_at": datetime.now(timezone.utc).isoformat(),
        }
        temp_file = f"{self.checkpoint_path}.tmp"
        try:
            with open(temp_file, "w", encoding="utf-8") as f:
                json.dump(data, f, indent=2)
            os.replace(temp_file, self.checkpoint_path)
            logger.debug(f"Saved checkpoint with {len(self.visited_urls)} visited URLs.")
        except Exception as exc:
            logger.warning(f"Could not save checkpoint: {exc}")

    def load(self) -> None:
        """Loads state from checkpoint JSON if it exists."""
        if not os.path.exists(self.checkpoint_path):
            return
        try:
            with open(self.checkpoint_path, "r", encoding="utf-8") as f:
                data = json.load(f)
            self.visited_urls = set(data.get("visited_urls", []))
            self.processed_hashes = set(data.get("processed_hashes", []))
            self.completed_sources = set(data.get("completed_sources", []))
            logger.info(f"Loaded checkpoint with {len(self.visited_urls)} visited URLs.")
        except Exception as exc:
            logger.warning(f"Could not load checkpoint: {exc}")
