"""
NEXO Data Platform - Source Authority & Anti-Spoofing Evaluator
Inspects domains, TLDs, and institutional patterns to prevent unverified
or deceptive websites from receiving official government trust.
"""

from typing import Dict, Any, Optional
from urllib.parse import urlparse
from config.source_registry_config import (
    PREFERRED_GOV_DOMAINS,
    RECOGNIZED_INSTITUTIONAL_HOSTS,
    VerificationStatus,
)


def extract_host(url: str) -> str:
    """Extracts and cleans the hostname from a URL string."""
    parsed = urlparse(url.strip())
    host = parsed.netloc.split(":")[0].strip().lower()
    return host


def assess_domain_authority(url_or_host: str) -> Dict[str, Any]:
    """
    Evaluates the authority of a domain host against official government patterns.
    Flags spoofed or deceptive domains (e.g. 'fake-gov-schemes.com').
    """
    host = extract_host(url_or_host) if "://" in url_or_host else url_or_host.strip().lower()

    is_preferred_gov = any(host.endswith(tld) for tld in PREFERRED_GOV_DOMAINS)
    is_recognized_institution = any(
        host == inst or host.endswith(f".{inst}")
        for inst in RECOGNIZED_INSTITUTIONAL_HOSTS
    )

    # Check for deceptive / spoof patterns: contains "gov", "government", "nic", "yojana", or "scheme"
    # but does not belong to an official government TLD (.gov.in or .nic.in) or recognized institution
    has_suspicious_gov_pattern = False
    if not is_preferred_gov and not is_recognized_institution:
        suspicious_tokens = ("gov", "government", "nic", "yojana", "scheme")
        if any(token in host for token in suspicious_tokens):
            has_suspicious_gov_pattern = True

    if is_preferred_gov or is_recognized_institution:
        initial_status = VerificationStatus.NEEDS_REVIEW.value
        assessment = (
            "Recognized official government or statutory institution domain. "
            "Requires explicit verification metadata before being marked VERIFIED."
        )
    elif has_suspicious_gov_pattern:
        initial_status = VerificationStatus.NEEDS_REVIEW.value
        assessment = (
            "Caution: Host contains official-sounding tokens ('gov', 'government', 'nic', 'yojana', 'scheme') "
            "but does NOT belong to an official government TLD (.gov.in / .nic.in). Requires strict scrutiny."
        )
    else:
        initial_status = VerificationStatus.PENDING.value
        assessment = (
            "General web domain. Must be explicitly reviewed and validated as an authorized "
            "statutory or public institution before any verification."
        )

    return {
        "host": host,
        "is_preferred_gov": is_preferred_gov,
        "is_recognized_institution": is_recognized_institution,
        "has_suspicious_gov_pattern": has_suspicious_gov_pattern,
        "initial_status": initial_status,
        "assessment": assessment,
    }


def is_eligible_for_verification(
    url: str,
    verification_method: Optional[str],
    verification_notes: Optional[str],
) -> bool:
    """
    Enforces that NO source can transition to VERIFIED without explicit
    auditable verification method and notes.
    """
    if not verification_method or not verification_method.strip():
        return False
    if not verification_notes or not verification_notes.strip():
        return False

    # Assess domain
    assessment = assess_domain_authority(url)
    # If suspicious deceptive domain, prevent automatic verification
    if assessment["has_suspicious_gov_pattern"]:
        # Must have detailed notes explicitly addressing the domain check
        if len(verification_notes.strip()) < 20:
            return False

    return True
