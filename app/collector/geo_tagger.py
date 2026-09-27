"""
NEXO Data Platform - Geographic Classifier & Metadata Tagger
Classifies discovered documents into Central, State, and District levels
using reliable token matching from source metadata, URLs, and document titles.
"""

from typing import Optional, Dict, Tuple
from dataclasses import dataclass

INDIAN_STATES_UTS: Dict[str, str] = {
    "tamil nadu": "Tamil Nadu",
    "tamilnadu": "Tamil Nadu",
    "kerala": "Kerala",
    "karnataka": "Karnataka",
    "andhra pradesh": "Andhra Pradesh",
    "telangana": "Telangana",
    "maharashtra": "Maharashtra",
    "gujarat": "Gujarat",
    "rajasthan": "Rajasthan",
    "madhya pradesh": "Madhya Pradesh",
    "uttar pradesh": "Uttar Pradesh",
    "bihar": "Bihar",
    "west bengal": "West Bengal",
    "punjab": "Punjab",
    "haryana": "Haryana",
    "odisha": "Odisha",
    "assam": "Assam",
    "jharkhand": "Jharkhand",
    "chhattisgarh": "Chhattisgarh",
    "himachal pradesh": "Himachal Pradesh",
    "uttarakhand": "Uttarakhand",
    "delhi": "Delhi",
}

# Key districts in Tamil Nadu and major focus states
TAMIL_NADU_DISTRICTS = {
    "chennai", "coimbatore", "madurai", "tiruchirappalli", "trichy", "salem",
    "tirunelveli", "tiruppur", "erode", "vellore", "thanjavur", "dindigul",
    "kanchipuram", "tiruvallur", "cuddalore", "nagapattinam", "dharmapuri",
    "krishnagiri", "viluppuram", "ramanathapuram", "virudhunagar", "sivaganga",
    "theni", "karur", "ariyalur", "perambalur", "pudukkottai", "namakkal",
    "nilgiris", "kanyakumari", "thiruvarur", "tenkasi", "tirupathur", "ranipet",
    "chengalpattu", "kallakurichi", "mayiladuthurai",
}


@dataclass
class GeoClassificationResult:
    """Outcome of geographic level and jurisdiction classification."""
    government_level: str  # Central, State, District, Unknown
    state: Optional[str]
    district: Optional[str]
    confidence: float
    evidence: str


def classify_geography(
    url: str,
    title: str = "",
    source_state: Optional[str] = None,
    authority_level: Optional[str] = None,
) -> GeoClassificationResult:
    """
    Deterministically determines geographic level (Central, State, District)
    and location attributes. Does not guess.
    """
    text_corpus = f"{url.lower()} {title.lower()}"

    # 1. District check (highest granularity)
    # Check if a district token appears as a word boundary
    found_district: Optional[str] = None
    target_state = source_state

    for dist in TAMIL_NADU_DISTRICTS:
        if f"/{dist}/" in text_corpus or f"-{dist}-" in text_corpus or f" {dist} " in f" {text_corpus} ":
            found_district = dist.capitalize()
            target_state = target_state or "Tamil Nadu"
            break

    if found_district:
        return GeoClassificationResult(
            government_level="District",
            state=target_state,
            district=found_district,
            confidence=0.9,
            evidence=f"District '{found_district}' detected in document path/title.",
        )

    # 2. State check
    found_state: Optional[str] = source_state
    if not found_state:
        for state_key, canonical_state in INDIAN_STATES_UTS.items():
            if state_key in text_corpus or f".{state_key.replace(' ', '')}." in text_corpus:
                found_state = canonical_state
                break

    if found_state:
        return GeoClassificationResult(
            government_level="State",
            state=found_state,
            district=None,
            confidence=0.85,
            evidence=f"State '{found_state}' identified from source profile or URL path.",
        )

    # 3. Central check
    if authority_level in ("CENTRAL_GOVERNMENT", "STATUTORY_BODY", "GOVERNMENT_INSTITUTION"):
        return GeoClassificationResult(
            government_level="Central",
            state=None,
            district=None,
            confidence=0.95,
            evidence=f"Classified as Central from authority level: {authority_level}",
        )

    # 4. Unknown / Needs Review
    return GeoClassificationResult(
        government_level="Unknown",
        state=None,
        district=None,
        confidence=0.2,
        evidence="Geographic level not determinable without ambiguity.",
    )
