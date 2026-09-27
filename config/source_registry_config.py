"""
NEXO Data Platform - Official Source Registry Configuration
Defines authority levels, verification workflows, domain categories, and institutional whitelist patterns.
"""

from enum import Enum
from typing import Set, Dict


class AuthorityLevel(str, Enum):
    """Hierarchical authority levels for official information providers."""
    CENTRAL_GOVERNMENT = "CENTRAL_GOVERNMENT"
    STATE_GOVERNMENT = "STATE_GOVERNMENT"
    DISTRICT_GOVERNMENT = "DISTRICT_GOVERNMENT"
    GOVERNMENT_INSTITUTION = "GOVERNMENT_INSTITUTION"
    STATUTORY_BODY = "STATUTORY_BODY"
    OTHER_OFFICIAL = "OTHER_OFFICIAL"


class VerificationStatus(str, Enum):
    """Lifecycle verification status of an official source in the registry."""
    PENDING = "PENDING"
    VERIFIED = "VERIFIED"
    REJECTED = "REJECTED"
    NEEDS_REVIEW = "NEEDS_REVIEW"


class DomainCategory(str, Enum):
    """Machine-readable domain slugs aligning with the 7 core NEXO domains."""
    GOVERNMENT_SCHEMES = "government_schemes"
    COOPERATIVE_GOVERNANCE = "cooperative_governance"
    AGRICULTURE_RURAL_SUSTAINABILITY = "agriculture_rural_sustainability"
    FOODTECH_COLDCHAIN = "foodtech_coldchain"
    RURAL_DEVELOPMENT_FINANCE = "rural_development_finance"
    LEGAL_ASSISTANCE = "legal_assistance"
    MULTILINGUAL = "multilingual"


# Human-friendly labels for domain slugs
DOMAIN_SLUG_TO_LABEL: Dict[str, str] = {
    DomainCategory.GOVERNMENT_SCHEMES.value: "Government Schemes",
    DomainCategory.COOPERATIVE_GOVERNANCE.value: "Cooperative Governance",
    DomainCategory.AGRICULTURE_RURAL_SUSTAINABILITY.value: "Agriculture and Rural Sustainability",
    DomainCategory.FOODTECH_COLDCHAIN.value: "FoodTech / Cold-chain / Rural Logistics",
    DomainCategory.RURAL_DEVELOPMENT_FINANCE.value: "Rural Development and Financial Assistance",
    DomainCategory.LEGAL_ASSISTANCE.value: "Legal Assistance / Grievance Redressal",
    DomainCategory.MULTILINGUAL.value: "Multilingual Government Information",
}

# Preferred second-level and top-level official government domains in India
PREFERRED_GOV_DOMAINS: Set[str] = {
    ".gov.in",
    ".nic.in",
}

# Recognized statutory bodies and apex government organizations
RECOGNIZED_INSTITUTIONAL_HOSTS: Set[str] = {
    "nabard.org",
    "rbi.org.in",
    "ncdc.in",
    "sfacindia.com",
    "fssai.gov.in",
    "nalsa.gov.in",
    "enam.gov.in",
    "digitalindia.gov.in",
    "india.gov.in",
}

# Default manifest paths
DEFAULT_SOURCES_MANIFEST_JSONL = "data/manifests/sources/sources_manifest.jsonl"
DEFAULT_SOURCES_MANIFEST_JSON = "data/manifests/sources/sources_manifest.json"
