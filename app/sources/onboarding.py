"""
NEXO Data Platform - Verified Official Source Onboarding Workflow
Manages the complete lifecycle of candidate sources from submission, URL normalization,
anti-spoofing authority assessment, explicit auditable verification, to Supabase adapter formatting
and collector handoff.
"""

import json
import os
import uuid
from datetime import datetime, timezone
from enum import Enum
from typing import Dict, Any, List, Optional, Union
from pydantic import BaseModel, Field, field_validator, model_validator

from config.logging_config import get_logger
from config.source_registry_config import (
    AuthorityLevel,
    VerificationStatus,
    DomainCategory,
)
from app.sources.models import SourceRecord
from app.sources.registry import SourceRegistry
from app.sources.validator import (
    normalize_url,
    validate_source_url,
    validate_domain_category,
    validate_authority_level,
    validate_verification_status,
    validate_verification_guardrails,
)
from app.sources.authority import assess_domain_authority, is_eligible_for_verification
from app.ingestion.exceptions import ValidationError

logger = get_logger("sources.onboarding")


class VerificationEvidenceType(str, Enum):
    """Auditable evidence categories supporting official source verification."""
    OFFICIAL_DOMAIN_AUTHORITY = "OFFICIAL_DOMAIN_AUTHORITY"
    GOVERNMENT_ORGANIZATION_ID = "GOVERNMENT_ORGANIZATION_ID"
    DEPARTMENT_MINISTRY_ASSOCIATION = "DEPARTMENT_MINISTRY_ASSOCIATION"
    AUTHORITATIVE_PORTAL_RELATION = "AUTHORITATIVE_PORTAL_RELATION"
    CROSS_REFERENCE_GOV_SOURCE = "CROSS_REFERENCE_GOV_SOURCE"
    GAZETTE_NOTIFICATION = "GAZETTE_NOTIFICATION"
    MANUAL_EXPLICIT_AUDIT = "MANUAL_EXPLICIT_AUDIT"


class CandidateSource(BaseModel):
    """
    Representation of an unverified candidate government or institutional source.
    Defaults to PENDING. Must never become VERIFIED without explicit verification evidence.
    """
    candidate_id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    source_name: str
    organization_name: str
    official_url: str
    normalized_url: str = ""
    domain_category: str
    authority_level: str
    language: str = "en"
    country: str = "IN"
    state: Optional[str] = None
    verification_status: str = VerificationStatus.PENDING.value
    verification_method: Optional[str] = None
    verification_notes: Optional[str] = None
    rejection_reason: Optional[str] = None
    authority_assessment: Optional[Dict[str, Any]] = None
    audit_trail: List[Dict[str, Any]] = Field(default_factory=list)
    submitted_at: str = Field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    updated_at: str = Field(default_factory=lambda: datetime.now(timezone.utc).isoformat())

    @field_validator("source_name", "organization_name")
    def validate_names(cls, v: str) -> str:
        if not v or not v.strip():
            raise ValidationError("Name field cannot be empty.")
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
    def enforce_invariants(self) -> "CandidateSource":
        # Compute normalized URL deterministically
        if not self.normalized_url or self.normalized_url != normalize_url(self.official_url):
            self.normalized_url = normalize_url(self.official_url)

        # Enforce verification guardrails: cannot be instantiated as VERIFIED without evidence
        if self.verification_status == VerificationStatus.VERIFIED.value:
            validate_verification_guardrails(
                target_status=self.verification_status,
                official_url=self.normalized_url,
                verification_method=self.verification_method,
                verification_notes=self.verification_notes,
            )

        return self

    def add_audit_event(
        self,
        action: str,
        reviewer: str = "system",
        notes: Optional[str] = None,
        method: Optional[str] = None,
        reason: Optional[str] = None,
    ) -> None:
        """Appends an immutable audit entry to the candidate record."""
        event = {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "action": action,
            "status": self.verification_status,
            "reviewer": reviewer,
            "method": method or self.verification_method,
            "notes": notes or self.verification_notes,
            "reason": reason or self.rejection_reason,
        }
        self.audit_trail.append(event)
        self.updated_at = event["timestamp"]


def submit_candidate_source(
    data: Union[Dict[str, Any], CandidateSource],
    registry: Optional[SourceRegistry] = None,
    auto_assess: bool = True,
    submitted_by: str = "system",
) -> CandidateSource:
    """
    Submits a candidate source for official onboarding.
    - Normalizes official URL
    - Rejects duplicate URLs against the registry
    - Performs anti-spoofing and domain authority assessment
    - Enforces PENDING default status
    - Preserves audit metadata
    """
    if isinstance(data, dict):
        # Enforce default PENDING if not provided
        cand_dict = dict(data)
        if "verification_status" not in cand_dict:
            cand_dict["verification_status"] = VerificationStatus.PENDING.value
        candidate = CandidateSource(**cand_dict)
    elif isinstance(data, CandidateSource):
        candidate = data
    else:
        raise ValidationError("Candidate data must be a dictionary or CandidateSource instance.")

    # Deduplication check against active or registered sources
    if registry:
        existing = registry.find_by_url(candidate.normalized_url)
        if existing:
            raise ValidationError(
                f"Candidate URL '{candidate.normalized_url}' already exists in registry "
                f"as '{existing.source_name}' (ID: {existing.id}, Status: {existing.verification_status})."
            )

    # Initial audit log
    candidate.add_audit_event(
        action="SUBMITTED",
        reviewer=submitted_by,
        notes=f"Candidate source submitted for domain '{candidate.domain_category}'.",
    )

    # Auto authority assessment if requested
    if auto_assess:
        assess_candidate_source(candidate)

    logger.info(
        f"Submitted candidate source: '{candidate.source_name}' ({candidate.normalized_url}) "
        f"[Status: {candidate.verification_status}]"
    )
    return candidate


def assess_candidate_source(candidate: CandidateSource) -> Dict[str, Any]:
    """
    Assesses candidate domain authority and anti-spoofing indicators.
    If suspicious patterns are detected (e.g. 'gov'/'scheme' tokens on commercial TLDs),
    sets status to NEEDS_REVIEW.
    """
    assessment = assess_domain_authority(candidate.normalized_url)
    candidate.authority_assessment = assessment

    # If domain has suspicious spoofing pattern, flag for human review
    if assessment.get("has_suspicious_gov_pattern"):
        candidate.verification_status = VerificationStatus.NEEDS_REVIEW.value
        candidate.verification_notes = assessment.get("assessment")
        candidate.add_audit_event(
            action="FLAGGED_SUSPICIOUS_DOMAIN",
            reviewer="authority_evaluator",
            notes=assessment.get("assessment"),
        )
    elif assessment.get("is_preferred_gov") or assessment.get("is_recognized_institution"):
        # Official TLD/institution, but still strictly PENDING or NEEDS_REVIEW until explicit evidence provided
        candidate.add_audit_event(
            action="ASSESSED_OFFICIAL_PATTERN",
            reviewer="authority_evaluator",
            notes=assessment.get("assessment"),
        )
    else:
        candidate.add_audit_event(
            action="ASSESSED_GENERAL_DOMAIN",
            reviewer="authority_evaluator",
            notes=assessment.get("assessment"),
        )

    return assessment


def verify_candidate_source(
    candidate: CandidateSource,
    verification_method: str,
    verification_notes: str,
    reviewed_by: str = "official_auditor",
    registry: Optional[SourceRegistry] = None,
) -> SourceRecord:
    """
    Promotes a candidate source to VERIFIED when explicit, auditable evidence is supplied.
    - Validates verification method and notes
    - Checks anti-spoofing eligibility
    - Updates audit trail
    - Generates and registers an active SourceRecord
    """
    if not verification_method or not verification_method.strip():
        raise ValidationError("Verification method is required to verify a source.")
    if not verification_notes or not verification_notes.strip():
        raise ValidationError("Verification notes are required to verify a source.")

    # Guardrail evaluation
    validate_verification_guardrails(
        target_status=VerificationStatus.VERIFIED.value,
        official_url=candidate.normalized_url,
        verification_method=verification_method,
        verification_notes=verification_notes,
    )

    prev_status = candidate.verification_status
    candidate.verification_status = VerificationStatus.VERIFIED.value
    candidate.verification_method = verification_method.strip()
    candidate.verification_notes = verification_notes.strip()

    candidate.add_audit_event(
        action="VERIFIED",
        reviewer=reviewed_by,
        method=candidate.verification_method,
        notes=candidate.verification_notes,
    )

    now_iso = datetime.now(timezone.utc).isoformat()
    record = SourceRecord(
        id=candidate.candidate_id,
        source_name=candidate.source_name,
        organization_name=candidate.organization_name,
        official_url=candidate.normalized_url,
        normalized_url=candidate.normalized_url,
        domain_category=candidate.domain_category,
        authority_level=candidate.authority_level,
        language=candidate.language,
        country=candidate.country,
        state=candidate.state,
        verification_status=VerificationStatus.VERIFIED.value,
        verification_method=candidate.verification_method,
        verification_notes=candidate.verification_notes,
        is_active=True,
        last_verified_at=now_iso,
        created_at=candidate.submitted_at,
        updated_at=now_iso,
    )

    if registry:
        registry.add_source(record)

    logger.info(
        f"Verified candidate source '{candidate.source_name}' -> registered as active official source."
    )
    return record


def reject_candidate_source(
    candidate: CandidateSource,
    reason: str,
    reviewed_by: str = "official_auditor",
    registry: Optional[SourceRegistry] = None,
) -> CandidateSource:
    """
    Rejects a candidate source with an auditable reason.
    Sets verification_status to REJECTED.
    """
    if not reason or not reason.strip():
        raise ValidationError("Rejection reason must be specified.")

    clean_reason = reason.strip()
    candidate.verification_status = VerificationStatus.REJECTED.value
    candidate.rejection_reason = clean_reason
    candidate.verification_notes = f"REJECTED: {clean_reason}"

    candidate.add_audit_event(
        action="REJECTED",
        reviewer=reviewed_by,
        reason=clean_reason,
        notes=candidate.verification_notes,
    )

    if registry and registry.get_source(candidate.normalized_url):
        registry.reject_source(candidate.normalized_url, reason=clean_reason)

    logger.info(f"Rejected candidate source '{candidate.source_name}': {clean_reason}")
    return candidate


def flag_needs_review(
    candidate: CandidateSource,
    reason: str,
    reviewed_by: str = "reviewer",
) -> CandidateSource:
    """Transitions a candidate to NEEDS_REVIEW with an auditable explanation."""
    if not reason or not reason.strip():
        raise ValidationError("Review reason must be specified.")

    candidate.verification_status = VerificationStatus.NEEDS_REVIEW.value
    candidate.verification_notes = f"NEEDS_REVIEW: {reason.strip()}"

    candidate.add_audit_event(
        action="FLAG_NEEDS_REVIEW",
        reviewer=reviewed_by,
        notes=candidate.verification_notes,
    )
    return candidate


def prepare_supabase_record(
    source: Union[SourceRecord, CandidateSource, Dict[str, Any]],
    dry_run: bool = True,
) -> Dict[str, Any]:
    """
    Database Adapter: Formats a SourceRecord or CandidateSource to match all 17 columns
    of the deployed Supabase PostgreSQL 'sources' table schema.
    
    Compatible with:
    - scripts/migrations/001_initial_schema.sql
    - scripts/migrations/002_add_source_verification_fields.sql
    - scripts/deploy_supabase.sql
    """
    if isinstance(source, SourceRecord):
        rec_id = source.id
        name = source.source_name
        url = source.normalized_url
        domain = source.domain_category
        lang = source.language
        auth = source.authority_level
        org = source.organization_name
        country = source.country
        state = source.state
        status = source.verification_status
        method = source.verification_method
        notes = source.verification_notes
        is_active = source.is_active
        last_verified = source.last_verified_at
        last_checked = source.last_checked_at
        created = source.created_at
        updated = source.updated_at
    elif isinstance(source, CandidateSource):
        rec_id = source.candidate_id
        name = source.source_name
        url = source.normalized_url
        domain = source.domain_category
        lang = source.language
        auth = source.authority_level
        org = source.organization_name
        country = source.country
        state = source.state
        status = source.verification_status
        method = source.verification_method
        notes = source.verification_notes
        is_active = (status == VerificationStatus.VERIFIED.value)
        last_verified = source.updated_at if status == VerificationStatus.VERIFIED.value else None
        now_iso = datetime.now(timezone.utc).isoformat()
        last_checked = getattr(source, "last_checked_at", None) or now_iso
        created = source.submitted_at
        updated = source.updated_at
    elif isinstance(source, dict):
        rec_id = source.get("id") or source.get("candidate_id") or str(uuid.uuid4())
        name = source.get("source_name") or source.get("name", "")
        url = normalize_url(source.get("official_url") or source.get("url", ""))
        domain = source.get("domain_category") or source.get("domain", "")
        lang = source.get("language", "en")
        auth = source.get("authority_level", "")
        org = source.get("organization_name", "")
        country = source.get("country", "IN")
        state = source.get("state")
        status = source.get("verification_status", VerificationStatus.PENDING.value)
        method = source.get("verification_method")
        notes = source.get("verification_notes")
        is_active = source.get("is_active", status == VerificationStatus.VERIFIED.value)
        last_verified = source.get("last_verified_at")
        now_iso = datetime.now(timezone.utc).isoformat()
        last_checked = source.get("last_checked_at") or source.get("last_verified_at") or now_iso
        created = source.get("created_at") or source.get("submitted_at") or now_iso
        updated = source.get("updated_at") or now_iso
    else:
        raise ValidationError("Invalid source type for Supabase payload preparation.")

    payload = {
        "id": str(rec_id),
        "name": name,
        "url": url,
        "domain": domain,
        "language": lang,
        "authority_level": auth,
        "organization_name": org,
        "country": country,
        "state": state,
        "verification_status": status,
        "verification_method": method,
        "verification_notes": notes,
        "is_active": is_active,
        "last_verified_at": last_verified,
        "last_checked_at": last_checked,
        "created_at": created,
        "updated_at": updated,
    }

    if dry_run:
        logger.info(
            f"[DRY RUN - SUPABASE PAYLOAD] Prepared record for '{name}' "
            f"(status: {status}, domain: {domain}, active: {is_active})"
        )

    return payload


def get_verified_sources(
    registry: Optional[SourceRegistry] = None,
    domain: Optional[str] = None,
) -> List[SourceRecord]:
    """
    Collector Handoff Interface:
    Returns strictly approved, active, and verified official sources for scraping/ingestion.
    
    Filters:
    - is_active == True
    - verification_status == VERIFIED
    - domain_category == domain (if provided)
    
    NEEDS_REVIEW, PENDING, REJECTED, or inactive sources are NEVER returned.
    """
    active_registry = registry or SourceRegistry()
    candidates = active_registry.list_all()

    target_domain = domain.strip().lower() if domain else None

    verified_sources: List[SourceRecord] = []
    for src in candidates:
        # Strict dual-check: must be both active and officially verified
        if not src.is_active:
            continue
        if src.verification_status != VerificationStatus.VERIFIED.value:
            continue
        if target_domain and src.domain_category != target_domain:
            continue
        verified_sources.append(src)

    return verified_sources


def export_onboarding_manifest(
    candidates: List[CandidateSource],
    destination_path: str,
) -> None:
    """Exports candidate sources with their audit trail to JSON or JSONL."""
    os.makedirs(os.path.dirname(os.path.abspath(destination_path)), exist_ok=True)
    is_jsonl = destination_path.lower().endswith(".jsonl")

    if is_jsonl:
        with open(destination_path, "w", encoding="utf-8") as f:
            for c in candidates:
                f.write(json.dumps(c.model_dump()) + "\n")
    else:
        with open(destination_path, "w", encoding="utf-8") as f:
            json.dump([c.model_dump() for c in candidates], f, indent=2)
