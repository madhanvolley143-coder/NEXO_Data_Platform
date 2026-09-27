"""
NEXO Data Platform - Official Source Registry Package
"""

from app.sources.models import SourceRecord
from app.sources.registry import SourceRegistry
from app.sources.validator import normalize_url, validate_source_url
from app.sources.authority import assess_domain_authority, is_eligible_for_verification
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
from config.source_registry_config import (
    AuthorityLevel,
    VerificationStatus,
    DomainCategory,
)

__all__ = [
    "SourceRecord",
    "SourceRegistry",
    "CandidateSource",
    "VerificationEvidenceType",
    "AuthorityLevel",
    "VerificationStatus",
    "DomainCategory",
    "normalize_url",
    "validate_source_url",
    "assess_domain_authority",
    "is_eligible_for_verification",
    "submit_candidate_source",
    "assess_candidate_source",
    "verify_candidate_source",
    "reject_candidate_source",
    "flag_needs_review",
    "prepare_supabase_record",
    "get_verified_sources",
    "export_onboarding_manifest",
]

