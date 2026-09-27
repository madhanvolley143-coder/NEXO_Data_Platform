"""
NEXO Data Platform - Official Source Registry Engine
Provides offline, auditable management of authoritative government information providers.
"""

import json
import os
from datetime import datetime, timezone
from typing import Dict, Any, List, Optional, Union

from config.logging_config import get_logger
from config.source_registry_config import (
    AuthorityLevel,
    VerificationStatus,
    DomainCategory,
    DEFAULT_SOURCES_MANIFEST_JSONL,
)
from app.sources.models import SourceRecord
from app.sources.validator import normalize_url
from app.ingestion.exceptions import ValidationError

logger = get_logger("sources")


class SourceRegistry:
    """
    Offline registry managing the lifecycle of verified government and institutional sources.
    """

    def __init__(self, manifest_path: Optional[str] = None):
        if manifest_path is None:
            self.manifest_path = DEFAULT_SOURCES_MANIFEST_JSONL
        else:
            self.manifest_path = manifest_path
        self._sources_by_id: Dict[str, SourceRecord] = {}
        self._sources_by_normalized_url: Dict[str, str] = {}  # url -> id

        if self.manifest_path and os.path.exists(self.manifest_path):
            self.load_from_file(self.manifest_path)

    def add_source(
        self,
        source: Union[SourceRecord, Dict[str, Any]],
        persist: bool = True,
    ) -> SourceRecord:
        """
        Adds a new authoritative source to the registry.
        Rejects duplicate normalized URLs.
        """
        if isinstance(source, dict):
            record = SourceRecord(**source)
        elif isinstance(source, SourceRecord):
            record = source
        else:
            raise ValidationError("Source must be a SourceRecord instance or dictionary.")

        norm_url = record.normalized_url
        if norm_url in self._sources_by_normalized_url:
            existing_id = self._sources_by_normalized_url[norm_url]
            raise ValidationError(
                f"Source with normalized URL '{norm_url}' already exists in registry (id: {existing_id})."
            )

        if record.id in self._sources_by_id:
            raise ValidationError(f"Source with id '{record.id}' already exists in registry.")

        self._sources_by_id[record.id] = record
        self._sources_by_normalized_url[norm_url] = record.id

        logger.info(
            f"Added source: '{record.source_name}' ({record.domain_category}, "
            f"{record.authority_level}) -> {norm_url} [Status: {record.verification_status}]"
        )

        if persist and self.manifest_path:
            self._save_to_manifest()

        return record

    def get_source(self, id_or_url: str) -> Optional[SourceRecord]:
        """Looks up a source by UUID or official URL."""
        if not id_or_url:
            return None
        # Check by ID
        if id_or_url in self._sources_by_id:
            return self._sources_by_id[id_or_url]

        # Check by normalized URL
        try:
            norm_url = normalize_url(id_or_url)
            if norm_url in self._sources_by_normalized_url:
                source_id = self._sources_by_normalized_url[norm_url]
                return self._sources_by_id.get(source_id)
        except Exception:
            pass

        return None

    def find_by_url(self, url: str) -> Optional[SourceRecord]:
        """Finds a source by raw or normalized URL."""
        return self.get_source(url)

    def update_source(
        self,
        id_or_url: str,
        persist: bool = True,
        **updates: Any,
    ) -> SourceRecord:
        """
        Updates metadata on an existing source record with re-validation.
        """
        existing = self.get_source(id_or_url)
        if not existing:
            raise ValidationError(f"Source '{id_or_url}' not found in registry.")

        data = existing.model_dump()

        # Handle URL updates carefully
        if "official_url" in updates and updates["official_url"] != existing.official_url:
            new_norm = normalize_url(updates["official_url"])
            if (
                new_norm in self._sources_by_normalized_url
                and self._sources_by_normalized_url[new_norm] != existing.id
            ):
                raise ValidationError(f"Normalized URL '{new_norm}' already in use by another source.")
            # Remove old URL index
            self._sources_by_normalized_url.pop(existing.normalized_url, None)
            self._sources_by_normalized_url[new_norm] = existing.id

        data.update(updates)
        data["updated_at"] = datetime.now(timezone.utc).isoformat()

        # Re-validate completely via SourceRecord model
        updated_record = SourceRecord(**data)
        self._sources_by_id[existing.id] = updated_record

        if persist and self.manifest_path:
            self._save_to_manifest()

        return updated_record

    def verify_source(
        self,
        id_or_url: str,
        verification_method: str,
        verification_notes: str,
        persist: bool = True,
    ) -> SourceRecord:
        """
        Officially verifies a source with auditable verification method and notes.
        """
        if not verification_method or not verification_method.strip():
            raise ValidationError("Verification method is required to verify a source.")
        if not verification_notes or not verification_notes.strip():
            raise ValidationError("Verification notes are required to verify a source.")

        return self.update_source(
            id_or_url=id_or_url,
            verification_status=VerificationStatus.VERIFIED.value,
            verification_method=verification_method.strip(),
            verification_notes=verification_notes.strip(),
            last_verified_at=datetime.now(timezone.utc).isoformat(),
            persist=persist,
        )

    def reject_source(
        self,
        id_or_url: str,
        reason: str,
        persist: bool = True,
    ) -> SourceRecord:
        """Marks a source as REJECTED with an auditable reason."""
        if not reason or not reason.strip():
            raise ValidationError("A rejection reason must be supplied.")

        return self.update_source(
            id_or_url=id_or_url,
            verification_status=VerificationStatus.REJECTED.value,
            verification_notes=f"REJECTED: {reason.strip()}",
            is_active=False,
            persist=persist,
        )

    def deactivate_source(
        self,
        id_or_url: str,
        reason: Optional[str] = None,
        persist: bool = True,
    ) -> SourceRecord:
        """Deactivates a source from active scraping/collection."""
        existing = self.get_source(id_or_url)
        if not existing:
            raise ValidationError(f"Source '{id_or_url}' not found.")

        notes = existing.verification_notes or ""
        if reason:
            notes = f"{notes} | Deactivated: {reason}".strip(" |")

        return self.update_source(
            id_or_url=id_or_url,
            is_active=False,
            verification_notes=notes,
            persist=persist,
        )

    def find_by_domain(self, domain_category: str) -> List[SourceRecord]:
        """Finds all sources mapped to a specific domain category."""
        target = domain_category.strip().lower()
        return [s for s in self._sources_by_id.values() if s.domain_category == target]

    def find_by_authority(self, authority_level: str) -> List[SourceRecord]:
        """Finds all sources with a specific authority tier."""
        target = authority_level.strip().upper()
        return [s for s in self._sources_by_id.values() if s.authority_level == target]

    def find_by_status(self, status: str) -> List[SourceRecord]:
        """Finds all sources with a specific verification status."""
        target = status.strip().upper()
        return [s for s in self._sources_by_id.values() if s.verification_status == target]

    def list_all(self) -> List[SourceRecord]:
        """Returns all registered sources."""
        return list(self._sources_by_id.values())

    def export_json(self, destination_path: str) -> None:
        """Exports the entire registry to a formatted JSON file."""
        os.makedirs(os.path.dirname(os.path.abspath(destination_path)), exist_ok=True)
        data = [s.to_full_dict() for s in self._sources_by_id.values()]
        with open(destination_path, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2)

    def export_jsonl(self, destination_path: str) -> None:
        """Exports the registry to a line-delimited JSONL file."""
        os.makedirs(os.path.dirname(os.path.abspath(destination_path)), exist_ok=True)
        with open(destination_path, "w", encoding="utf-8") as f:
            for s in self._sources_by_id.values():
                f.write(json.dumps(s.to_full_dict()) + "\n")

    def load_from_file(self, source_path: str) -> int:
        """Loads records from a JSON or JSONL file into the registry."""
        if not os.path.exists(source_path):
            return 0

        count = 0
        is_jsonl = source_path.lower().endswith(".jsonl")

        if is_jsonl:
            with open(source_path, "r", encoding="utf-8") as f:
                for line in f:
                    line = line.strip()
                    if line:
                        record = SourceRecord(**json.loads(line))
                        self._sources_by_id[record.id] = record
                        self._sources_by_normalized_url[record.normalized_url] = record.id
                        count += 1
        else:
            with open(source_path, "r", encoding="utf-8") as f:
                try:
                    data = json.load(f)
                    if isinstance(data, list):
                        for item in data:
                            record = SourceRecord(**item)
                            self._sources_by_id[record.id] = record
                            self._sources_by_normalized_url[record.normalized_url] = record.id
                            count += 1
                except json.JSONDecodeError:
                    return 0

        return count

    def _save_to_manifest(self) -> None:
        """Persists current state to the configured manifest path."""
        if not self.manifest_path:
            return
        if self.manifest_path.lower().endswith(".jsonl"):
            self.export_jsonl(self.manifest_path)
        else:
            self.export_json(self.manifest_path)
