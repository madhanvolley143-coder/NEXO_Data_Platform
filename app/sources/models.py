"""
NEXO Data Platform - Official Source Record Model
Defines the SourceRecord schema with strict validation, immutability,
and a database payload adapter for Supabase.
"""

import uuid
from datetime import datetime, timezone
from typing import Optional, Dict, Any
from pydantic import BaseModel, Field, field_validator, model_validator

from config.source_registry_config import (
    AuthorityLevel,
    VerificationStatus,
    DomainCategory,
)
from app.sources.validator import (
    normalize_url,
    validate_source_url,
    validate_domain_category,
    validate_authority_level,
    validate_verification_status,
    validate_verification_guardrails,
)


class SourceRecord(BaseModel):
    """
    Structured, auditable record representing an official government or institutional source.
    """
    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    source_name: str
    organization_name: str
    official_url: str
    normalized_url: str = ""
    domain_category: str
    authority_level: str
    country: str = "IN"
    state: Optional[str] = None
    language: str = "en"
    verification_status: str = VerificationStatus.PENDING.value
    verification_method: Optional[str] = None
    verification_notes: Optional[str] = None
    is_active: bool = True
    last_verified_at: Optional[str] = None
    last_checked_at: Optional[str] = None
    created_at: str = Field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    updated_at: str = Field(default_factory=lambda: datetime.now(timezone.utc).isoformat())

    @field_validator("source_name", "organization_name")
    def validate_names(cls, v: str) -> str:
        if not v or not v.strip():
            raise ValueError("Name field cannot be empty.")
        return v.strip()

    @field_validator("official_url")
    def check_url(cls, v: str) -> str:
        return validate_source_url(v)

    @field_validator("domain_category")
    def check_domain(cls, v: str) -> str:
        return validate_domain_category(v)

    @field_validator("authority_level")
    def check_authority(cls, v: str) -> str:
        return validate_authority_level(v)

    @field_validator("verification_status")
    def check_status(cls, v: str) -> str:
        return validate_verification_status(v)

    @model_validator(mode="after")
    def enforce_invariants(self) -> "SourceRecord":
        # Compute normalized URL
        if not self.normalized_url or self.normalized_url != normalize_url(self.official_url):
            self.normalized_url = normalize_url(self.official_url)

        # Enforce verification guardrails: cannot be VERIFIED without method & notes
        validate_verification_guardrails(
            target_status=self.verification_status,
            official_url=self.normalized_url,
            verification_method=self.verification_method,
            verification_notes=self.verification_notes,
        )

        if self.verification_status == VerificationStatus.VERIFIED.value and not self.last_verified_at:
            self.last_verified_at = datetime.now(timezone.utc).isoformat()

        return self

    def to_supabase_dict(self) -> Dict[str, Any]:
        """
        Database Adapter: Maps the rich SourceRecord to the existing 'sources'
        PostgreSQL table schema defined in scripts/migrations/001_initial_schema.sql.
        
        Preserves compatibility without requiring immediate DDL alteration.
        """
        return {
            "id": self.id,
            "name": self.source_name,
            "url": self.normalized_url,
            "domain": self.domain_category,
            "language": self.language,
            "authority_level": self.authority_level,
            "last_checked_at": self.last_checked_at,
            "is_active": self.is_active,
            "created_at": self.created_at,
            "updated_at": self.updated_at,
        }

    def to_full_dict(self) -> Dict[str, Any]:
        """Full dictionary representation containing complete verification and governance metadata."""
        return self.model_dump()
