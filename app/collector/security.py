"""
NEXO Data Platform - Collector URL Security & Source Validator
Enforces domain anchoring, canonicalization, anti-spoofing, and redirect security.
Prevents the crawler from escaping to untrusted external domains.
"""

from typing import Optional, Set, List
from urllib.parse import urlparse
from app.sources.validator import normalize_url
from app.sources.authority import assess_domain_authority, extract_host
from app.ingestion.exceptions import ValidationError

# Allowed official cross-domain document CDNs commonly used by Indian Government portals
OFFICIAL_DOCUMENT_CDNS: Set[str] = {
    "s3waas.gov.in",
    "egazette.gov.in",
    "egazette.nic.in",
    "digitalindia.gov.in",
    "india.gov.in",
}

SAFE_SCHEMES: Set[str] = {"http", "https"}


def is_safe_scheme(url: str) -> bool:
    """Verifies that URL uses HTTP or HTTPS and not javascript, mailto, data, etc."""
    if not url or not isinstance(url, str):
        return False
    stripped = url.strip()
    parsed = urlparse(stripped)
    return parsed.scheme.lower() in SAFE_SCHEMES


def is_domain_authorized(
    url: str,
    source_url: str,
    allowed_extra_domains: Optional[Set[str]] = None,
) -> bool:
    """
    Trust Anchor Verification:
    Ensures the target URL belongs to the verified source host, its subdomains,
    or a designated official document repository.
    """
    if not is_safe_scheme(url) or not is_safe_scheme(source_url):
        return False

    target_host = extract_host(url)
    source_host = extract_host(source_url)

    if not target_host or not source_host:
        return False

    # 1. Exact host match
    if target_host == source_host:
        return True

    # 2. Subdomain of the verified source host
    # e.g., 'pacs.cooperation.gov.in' is authorized under 'cooperation.gov.in'
    if target_host.endswith(f".{source_host}"):
        return True

    # 3. If source is a sub-organization under a state/central portal, check reverse if applicable
    # e.g., 'coop.tn.gov.in' and 'tn.gov.in'
    if source_host.endswith(".gov.in") and target_host.endswith(".gov.in"):
        source_parts = source_host.split(".")
        target_parts = target_host.split(".")
        # If both are under the same state SLD, e.g. '*.tn.gov.in'
        if len(source_parts) >= 3 and len(target_parts) >= 3:
            if source_parts[-3:] == target_parts[-3:]:
                return True

    # 4. Official government document CDNs
    extra_allowed = OFFICIAL_DOCUMENT_CDNS.union(allowed_extra_domains or set())
    if any(target_host == cdn or target_host.endswith(f".{cdn}") for cdn in extra_allowed):
        return True

    return False


def validate_crawl_target(
    url: str,
    source_url: str,
    allowed_extra_domains: Optional[Set[str]] = None,
) -> bool:
    """
    Combined security check:
    1. Safe protocol
    2. Authorized domain anchor
    3. Anti-spoofing check
    """
    if not is_safe_scheme(url):
        return False

    if not is_domain_authorized(url, source_url, allowed_extra_domains):
        return False

    # Anti-spoofing check: ensure target host does not exhibit spoofing patterns
    assessment = assess_domain_authority(url)
    if assessment.get("has_suspicious_gov_pattern"):
        return False

    return True


def validate_redirect(
    original_url: str,
    target_url: str,
    source_url: str,
    redirect_chain: List[str],
    max_redirects: int = 5,
) -> bool:
    """
    Validates redirect security:
    - Protects against infinite redirect loops.
    - Ensures redirected URL does not escape to an unauthorized external domain.
    """
    if len(redirect_chain) > max_redirects:
        return False

    if target_url in redirect_chain:
        # Loop detected
        return False

    return validate_crawl_target(target_url, source_url)
