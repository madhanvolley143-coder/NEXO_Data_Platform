"""
NEXO Data Platform - Supabase Storage Configuration
Defines bucket names, domain directory mappings, and supported file formats.
"""

from typing import Dict, Set

# Supabase Storage bucket for all verified official government documents
STORAGE_BUCKET_NAME = "nexo-government-documents"

# Official NEXO domain names mapped to their canonical storage folder slugs
DOMAIN_TO_FOLDER_MAP: Dict[str, str] = {
    "Government Schemes": "government_schemes",
    "Cooperative Governance": "cooperative_governance",
    "Agriculture and Rural Sustainability": "agriculture_rural_sustainability",
    "FoodTech / Cold-chain / Rural Logistics": "foodtech_coldchain",
    "Rural Development and Financial Assistance": "rural_development_finance",
    "Legal Assistance / Grievance Redressal": "legal_assistance",
    "Multilingual government information": "multilingual",
}

# Lookup for normalized / lowercase domain names
_NORMALIZED_DOMAIN_MAP: Dict[str, str] = {
    k.lower().strip(): v for k, v in DOMAIN_TO_FOLDER_MAP.items()
}
# Also support direct slug inputs
for v in DOMAIN_TO_FOLDER_MAP.values():
    _NORMALIZED_DOMAIN_MAP[v.lower()] = v

# Supported MIME types and primary extensions
MIME_TO_EXTENSION_MAP: Dict[str, str] = {
    "application/pdf": ".pdf",
    "text/html": ".html",
    "application/vnd.openxmlformats-officedocument.wordprocessingml.document": ".docx",
    "text/csv": ".csv",
    "application/json": ".json",
    "application/xml": ".xml",
    "text/xml": ".xml",
    "text/plain": ".txt",
    "image/jpeg": ".jpg",
    "image/png": ".png",
    "image/tiff": ".tiff",
    "image/webp": ".webp",
}

# Formats that intrinsically require Optical Character Recognition (OCR)
OCR_MIME_TYPES: Set[str] = {
    "image/jpeg",
    "image/png",
    "image/tiff",
    "image/webp",
}

SUPPORTED_EXTENSIONS: Set[str] = {
    ".pdf",
    ".html",
    ".htm",
    ".docx",
    ".csv",
    ".json",
    ".xml",
    ".txt",
    ".jpg",
    ".jpeg",
    ".png",
    ".tiff",
    ".tif",
    ".webp",
}


def get_domain_folder(domain: str) -> str:
    """
    Retrieve the canonical storage folder slug for a given NEXO domain.
    Raises ValueError if domain is invalid.
    """
    cleaned = domain.strip().lower()
    if cleaned in _NORMALIZED_DOMAIN_MAP:
        return _NORMALIZED_DOMAIN_MAP[cleaned]
    # Check partial / keyword match
    for key, folder in _NORMALIZED_DOMAIN_MAP.items():
        if key in cleaned or cleaned in key:
            return folder

    valid_domains = list(DOMAIN_TO_FOLDER_MAP.keys())
    raise ValueError(
        f"Unknown domain: '{domain}'. Must be one of: {valid_domains}"
    )


def is_supported_mime(mime_type: str) -> bool:
    """Check if the MIME type is supported by NEXO ingestion."""
    if not mime_type:
        return False
    base_mime = mime_type.split(";")[0].strip().lower()
    return base_mime in MIME_TO_EXTENSION_MAP


def is_ocr_mime(mime_type: str) -> bool:
    """Check if the MIME type requires OCR."""
    if not mime_type:
        return False
    base_mime = mime_type.split(";")[0].strip().lower()
    return base_mime in OCR_MIME_TYPES
