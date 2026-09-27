"""
NEXO Data Platform - Source Registry Validators & URL Normalizer
Provides canonical URL normalization, domain classification checks, and auditable verification guardrails.
"""

from typing import Dict, Any, Optional, List
from urllib.parse import urlparse, urlunparse, parse_qsl, urlencode

from config.source_registry_config import (
    AuthorityLevel,
    VerificationStatus,
    DomainCategory,
)
from app.ingestion.exceptions import ValidationError
from app.sources.authority import assess_domain_authority, is_eligible_for_verification

VALID_DOMAINS = {d.value for d in DomainCategory}
VALID_AUTHORITY_LEVELS = {a.value for a in AuthorityLevel}
VALID_STATUSES = {s.value for s in VerificationStatus}


def normalize_url(url: str) -> str:
    """
    Deterministically normalizes a government URL for reliable deduplication:
    - Lowercases scheme and host
    - Removes default web ports (80, 443)
    - Strips fragment identifiers (#section)
    - Sorts query parameters deterministically
    - Trims trailing slash on paths
    """
    if not url or not isinstance(url, str):
        raise ValidationError("URL must be a non-empty string.")

    stripped = url.strip()
    parsed = urlparse(stripped)

    scheme = parsed.scheme.lower()
    if scheme not in ("http", "https"):
        raise ValidationError(
            f"Invalid URL scheme '{parsed.scheme}'. Only HTTP and HTTPS are permitted."
        )

    if not parsed.netloc:
        raise ValidationError(f"URL missing valid network domain/host: '{url}'")

    netloc = parsed.netloc.lower()
    # Strip default ports
    if netloc.endswith(":80") and scheme == "http":
        netloc = netloc[:-3]
    elif netloc.endswith(":443") and scheme == "https":
        netloc = netloc[:-4]

    # Normalize path: remove redundant slashes and trailing slash
    path = parsed.path or ""
    while "//" in path:
        path = path.replace("//", "/")
    if path.endswith("/"):
        path = path.rstrip("/")

    # Normalize and sort query params
    query_tuples = parse_qsl(parsed.query, keep_blank_values=True)
    sorted_query = urlencode(sorted(query_tuples))

    # Strip fragment completely
    normalized = urlunparse((scheme, netloc, path, parsed.params, sorted_query, ""))
    return normalized


def validate_source_url(url: str) -> str:
    """Validates URL and returns its canonical normalized representation."""
    return normalize_url(url)


def validate_domain_category(category: str) -> str:
    """
    Ensures domain_category is one of the 7 official NEXO machine-readable slugs.
    """
    if not category or not isinstance(category, str):
        raise ValidationError("domain_category must be a non-empty string.")

    cleaned = category.strip().lower()
    if cleaned not in VALID_DOMAINS:
        raise ValidationError(
            f"Invalid domain_category: '{category}'. Must be one of: {sorted(list(VALID_DOMAINS))}"
        )
    return cleaned


def validate_authority_level(level: str) -> str:
    """
    Ensures authority_level is one of the supported official tiers.
    """
    if not level or not isinstance(level, str):
        raise ValidationError("authority_level must be a non-empty string.")

    cleaned = level.strip().upper()
    if cleaned not in VALID_AUTHORITY_LEVELS:
        raise ValidationError(
            f"Invalid authority_level: '{level}'. Must be one of: {sorted(list(VALID_AUTHORITY_LEVELS))}"
        )
    return cleaned


def validate_verification_status(status: str) -> str:
    """
    Ensures verification_status is a valid lifecycle state.
    """
    if not status or not isinstance(status, str):
        raise ValidationError("verification_status must be a non-empty string.")

    cleaned = status.strip().upper()
    if cleaned not in VALID_STATUSES:
        raise ValidationError(
            f"Invalid verification_status: '{status}'. Must be one of: {sorted(list(VALID_STATUSES))}"
        )
    return cleaned


def validate_verification_guardrails(
    target_status: str,
    official_url: str,
    verification_method: Optional[str],
    verification_notes: Optional[str],
) -> None:
    """
    Enforces that a source CANNOT transition to VERIFIED without explicit,
    auditable verification metadata and anti-spoofing review.
    """
    status_clean = validate_verification_status(target_status)

    if status_clean == VerificationStatus.VERIFIED.value:
        if not verification_method or not verification_method.strip():
            raise ValidationError(
                "A source cannot be marked VERIFIED without specifying 'verification_method'."
            )
        if not verification_notes or not verification_notes.strip():
            raise ValidationError(
                "A source cannot be marked VERIFIED without specifying 'verification_notes'."
            )

        if not is_eligible_for_verification(
            official_url, verification_method, verification_notes
        ):
            raise ValidationError(
                f"Source URL '{official_url}' failed authority eligibility checks. "
                "Non-government or deceptive domains require explicit, detailed verification rationale."
            )
