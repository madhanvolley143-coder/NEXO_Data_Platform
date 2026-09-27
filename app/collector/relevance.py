"""
NEXO Data Platform - Document Relevance Classifier
Evaluates discovered links, titles, and document snippets against the 7 NEXO focus domains
with configurable taxonomies, multi-lingual token matching (English + Tamil),
and tri-state classification (CONFIRMED / NEEDS_REVIEW / IRRELEVANT).
"""

import re
from typing import Dict, Any, List, Optional, Tuple, Set
from dataclasses import dataclass
from config.source_registry_config import DomainCategory

CONFIRMED = "CONFIRMED"
NEEDS_REVIEW = "NEEDS_REVIEW"
IRRELEVANT = "IRRELEVANT"

# Domain-specific keyword taxonomies (English + Tamil romanized/transliterated + terms)
DOMAIN_KEYWORD_TAXONOMY: Dict[str, Dict[str, List[str]]] = {
    DomainCategory.GOVERNMENT_SCHEMES.value: {
        "primary": [
            "scheme", "yojana", "guidelines", "welfare", "subsidy", "beneficiary",
            "eligibility", "application form", "citizen charter", "direct benefit", "dbt",
            "grant", "entitlement", "assistance", "thittam", "pathakam", "welfare board",
        ],
        "secondary": [
            "notification", "circular", "announcement", "criteria", "faq", "operational",
            "implementation", "handbook", "brochure", "portal", "beneficiaries",
        ],
    },
    DomainCategory.COOPERATIVE_GOVERNANCE.value: {
        "primary": [
            "cooperative", "cooperation", "pacs", "paccs", "ncdc", "society",
            "bylaws", "by-laws", "kooturavu", "sangam", "federation", "credit society",
            "registrar", "cooperative bank", "multi-state", "cooperative act",
        ],
        "secondary": [
            "audit", "election", "management committee", "member", "shares", "deposit",
            "governance", "resolution", "cooperative federation", "union",
        ],
    },
    DomainCategory.AGRICULTURE_RURAL_SUSTAINABILITY.value: {
        "primary": [
            "agriculture", "farmer", "kisan", "crop", "soil health", "irrigation",
            "organic", "sustainability", "uzhavan", "agrisnet", "kharif", "rabi",
            "horticulture", "seed", "pmfby", "crop insurance", "nabard", "sfac", "fpo",
        ],
        "secondary": [
            "fertilizer", "pest", "monsoon", "advisory", "harvest", "agro",
            "yield", "water resources", "watershed", "renewable", "solar pump",
        ],
    },
    DomainCategory.FOODTECH_COLDCHAIN.value: {
        "primary": [
            "food processing", "cold chain", "cold storage", "post harvest", "apeda",
            "fssai", "packaging", "rural logistics", "mega food park", "pmfme",
            "perishable", "warehousing", "supply chain", "food preservation",
        ],
        "secondary": [
            "food safety", "hygiene", "standards", "compliance", "processing unit",
            "agro-processing", "refrigerated", "packhouse", "ripening chamber",
        ],
    },
    DomainCategory.RURAL_DEVELOPMENT_FINANCE.value: {
        "primary": [
            "rural development", "panchayat", "self-help group", "shg", "nrlm",
            "aajeevika", "mgnrega", "pmay", "pmay-g", "livelihood", "microfinance",
            "gramin", "financial assistance", "rural housing", "village council",
        ],
        "secondary": [
            "credit linkage", "revolving fund", "interest subvention", "skill development",
            "empowerment", "infrastructure", "sanitation", "rural roads", "pmgsy",
        ],
    },
    DomainCategory.LEGAL_ASSISTANCE.value: {
        "primary": [
            "legal aid", "lok adalat", "tele-law", "nalsa", "slsa", "dlsa",
            "grievance", "ombudsman", "dispute resolution", "legal services",
            "free legal", "mediation", "victim compensation", "legal awareness",
        ],
        "secondary": [
            "justice", "redressal", "petition", "panel lawyer", "paralegal",
            "human rights", "legal clinic", "court", "statutory rights",
        ],
    },
    DomainCategory.MULTILINGUAL.value: {
        "primary": [
            "translation", "bhashini", "multilingual", "local language", "regional language",
            "tamil", "hindi", "digital india", "vernacular", "speech recognition",
            "nlp", "machine translation", "language mission",
        ],
        "secondary": [
            "tamilvu", "font", "keyboard", "unicode", "accessibility", "dialect",
            "indic", "corpus", "voice interface", "digital inclusion",
        ],
    },
}

# Non-informative noise keywords (administrative boilerplate)
NOISE_KEYWORDS: Set[str] = {
    "privacy policy", "terms of service", "terms and conditions", "disclaimer",
    "cookie policy", "sitemap", "copyright", "feedback", "login", "register",
    "admin login", "portal login", "sign in", "contact webmaster", "screen reader",
}


@dataclass
class RelevanceResult:
    """Outcome of domain relevance analysis."""
    category: str
    score: float
    status: str  # CONFIRMED, NEEDS_REVIEW, IRRELEVANT
    reason: str
    matched_keywords: List[str]


def assess_relevance(
    url: str,
    title: str = "",
    text_content: str = "",
    default_domain: Optional[str] = None,
) -> RelevanceResult:
    """
    Evaluates relevance of a discovered document URL/text across the 7 NEXO domains.
    Prioritizes the source's designated domain while supporting cross-domain relevance.
    """
    clean_url = url.lower()
    clean_title = title.lower()
    clean_text = text_content[:5000].lower() if text_content else ""
    search_corpus = f"{clean_url} {clean_title} {clean_text}"

    # 1. Check for administrative noise
    for noise in NOISE_KEYWORDS:
        if noise in clean_title or (noise in clean_url and not any(ext in clean_url for ext in [".pdf", ".docx", ".csv"])):
            return RelevanceResult(
                category=default_domain or "general",
                score=0.0,
                status=IRRELEVANT,
                reason=f"Matches administrative boilerplate: '{noise}'",
                matched_keywords=[noise],
            )

    best_category = default_domain or DomainCategory.GOVERNMENT_SCHEMES.value
    best_score = 0.0
    best_matches: List[str] = []
    category_scores: Dict[str, Tuple[float, List[str]]] = {}

    for domain_slug, keywords in DOMAIN_KEYWORD_TAXONOMY.items():
        score = 0.0
        matches = []

        # Check primary keywords (weight 0.4 per match, max 0.8)
        for kw in keywords["primary"]:
            if kw in search_corpus:
                score += 0.4
                matches.append(kw)

        # Check secondary keywords (weight 0.15 per match, max 0.4)
        for kw in keywords["secondary"]:
            if kw in search_corpus:
                score += 0.15
                matches.append(kw)

        # Boost score if this matches the source's default domain
        if default_domain and domain_slug == default_domain and score > 0:
            score += 0.25

        score = min(score, 1.0)
        category_scores[domain_slug] = (score, matches)

        if score > best_score:
            best_score = score
            best_category = domain_slug
            best_matches = matches

    # 2. File extension heuristic: Official documents (.pdf, .docx, .csv) with domain anchor
    has_doc_extension = any(clean_url.endswith(ext) or f"{ext}?" in clean_url for ext in [".pdf", ".docx", ".csv", ".json"])
    if has_doc_extension and best_score == 0.0 and default_domain:
        # Document on an authorized official domain but without matching keywords
        best_category = default_domain
        best_score = 0.25
        best_matches = ["official_document_extension"]

    # 3. Categorization thresholds
    if best_score >= 0.4:
        status = CONFIRMED
        reason = f"High confidence domain relevance for '{best_category}' (score: {best_score:.2f})"
    elif best_score >= 0.15:
        status = NEEDS_REVIEW
        reason = f"Moderate/potential relevance for '{best_category}'. Preserved for human audit."
    else:
        status = IRRELEVANT
        reason = "Insufficient domain relevance signals detected."

    return RelevanceResult(
        category=best_category,
        score=round(best_score, 2),
        status=status,
        reason=reason,
        matched_keywords=best_matches,
    )
