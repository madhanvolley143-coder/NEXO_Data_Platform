"""
NEXO Data Platform - Official Source Curation & Manifest Generator
Populates verified_sources.json, verified_sources.jsonl, candidate_sources.json,
and supabase_source_seed_preview.json using the official SourceRecord model and validators.
Runs 100% offline.
"""

import json
import os
import sys
from datetime import datetime, timezone
from typing import List, Dict, Any

# Ensure project root is in sys.path
project_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if project_root not in sys.path:
    sys.path.insert(0, project_root)

from config.source_registry_config import (
    AuthorityLevel,
    VerificationStatus,
    DomainCategory,
)
from app.sources.models import SourceRecord
from app.sources.onboarding import (
    CandidateSource,
    VerificationEvidenceType,
    prepare_supabase_record,
)

CURATION_TIMESTAMP = "2026-09-14T18:50:00Z"

VERIFIED_SOURCES_RAW = [
    # Domain 1: government_schemes
    {
        "id": "10000000-0000-0000-0000-000000000001",
        "source_name": "myScheme National Portal",
        "organization_name": "National e-Governance Division (NeGD) & Ministry of Electronics and IT",
        "official_url": "https://www.myscheme.gov.in",
        "domain_category": DomainCategory.GOVERNMENT_SCHEMES.value,
        "authority_level": AuthorityLevel.CENTRAL_GOVERNMENT.value,
        "country": "IN",
        "state": None,
        "language": "en",
        "verification_status": VerificationStatus.VERIFIED.value,
        "verification_method": VerificationEvidenceType.AUTHORITATIVE_PORTAL_RELATION.value,
        "verification_notes": (
            "National public services portal developed by NeGD and MeitY under the Digital India initiative, "
            "providing unified single-window discovery of Union and State government welfare schemes."
        ),
        "is_active": True,
        "last_verified_at": CURATION_TIMESTAMP,
        "created_at": CURATION_TIMESTAMP,
        "updated_at": CURATION_TIMESTAMP,
    },
    {
        "id": "10000000-0000-0000-0000-000000000002",
        "source_name": "National Portal of India",
        "organization_name": "National Informatics Centre (NIC), Ministry of Electronics and IT",
        "official_url": "https://www.india.gov.in",
        "domain_category": DomainCategory.GOVERNMENT_SCHEMES.value,
        "authority_level": AuthorityLevel.CENTRAL_GOVERNMENT.value,
        "country": "IN",
        "state": None,
        "language": "en",
        "verification_status": VerificationStatus.VERIFIED.value,
        "verification_method": VerificationEvidenceType.OFFICIAL_DOMAIN_AUTHORITY.value,
        "verification_notes": (
            "Apex official web portal of the Government of India designed, developed and hosted by "
            "National Informatics Centre (NIC) providing single-point access to citizen services, gazettes, and schemes."
        ),
        "is_active": True,
        "last_verified_at": CURATION_TIMESTAMP,
        "created_at": CURATION_TIMESTAMP,
        "updated_at": CURATION_TIMESTAMP,
    },
    {
        "id": "10000000-0000-0000-0000-000000000003",
        "source_name": "Government of Tamil Nadu Official Portal",
        "organization_name": "Department of Information Technology and Digital Services, Government of Tamil Nadu",
        "official_url": "https://www.tn.gov.in",
        "domain_category": DomainCategory.GOVERNMENT_SCHEMES.value,
        "authority_level": AuthorityLevel.STATE_GOVERNMENT.value,
        "country": "IN",
        "state": "Tamil Nadu",
        "language": "ta",
        "verification_status": VerificationStatus.VERIFIED.value,
        "verification_method": VerificationEvidenceType.OFFICIAL_DOMAIN_AUTHORITY.value,
        "verification_notes": (
            "Apex official state government portal of Tamil Nadu, hosting official government orders (GOs), "
            "citizen welfare schemes, and departmental directories."
        ),
        "is_active": True,
        "last_verified_at": CURATION_TIMESTAMP,
        "created_at": CURATION_TIMESTAMP,
        "updated_at": CURATION_TIMESTAMP,
    },

    # Domain 2: cooperative_governance
    {
        "id": "20000000-0000-0000-0000-000000000001",
        "source_name": "Ministry of Cooperation Portal",
        "organization_name": "Ministry of Cooperation, Government of India",
        "official_url": "https://www.cooperation.gov.in",
        "domain_category": DomainCategory.COOPERATIVE_GOVERNANCE.value,
        "authority_level": AuthorityLevel.CENTRAL_GOVERNMENT.value,
        "country": "IN",
        "state": None,
        "language": "en",
        "verification_status": VerificationStatus.VERIFIED.value,
        "verification_method": VerificationEvidenceType.DEPARTMENT_MINISTRY_ASSOCIATION.value,
        "verification_notes": (
            "Apex Union Ministry established on July 6, 2021 by the Government of India to strengthen the "
            "cooperative movement, PACS computerization, and Model Bye-laws."
        ),
        "is_active": True,
        "last_verified_at": CURATION_TIMESTAMP,
        "created_at": CURATION_TIMESTAMP,
        "updated_at": CURATION_TIMESTAMP,
    },
    {
        "id": "20000000-0000-0000-0000-000000000002",
        "source_name": "National Cooperative Development Corporation",
        "organization_name": "National Cooperative Development Corporation (NCDC)",
        "official_url": "https://www.ncdc.in",
        "domain_category": DomainCategory.COOPERATIVE_GOVERNANCE.value,
        "authority_level": AuthorityLevel.STATUTORY_BODY.value,
        "country": "IN",
        "state": None,
        "language": "en",
        "verification_status": VerificationStatus.VERIFIED.value,
        "verification_method": VerificationEvidenceType.CROSS_REFERENCE_GOV_SOURCE.value,
        "verification_notes": (
            "Statutory development finance corporation established by an Act of Parliament (NCDC Act, 1962) "
            "under the Ministry of Cooperation, promoting economic programs through cooperatives."
        ),
        "is_active": True,
        "last_verified_at": CURATION_TIMESTAMP,
        "created_at": CURATION_TIMESTAMP,
        "updated_at": CURATION_TIMESTAMP,
    },
    {
        "id": "20000000-0000-0000-0000-000000000003",
        "source_name": "Tamil Nadu Registrar of Cooperative Societies Portal",
        "organization_name": "Department of Cooperation, Food and Consumer Protection, Government of Tamil Nadu",
        "official_url": "https://kooturavu.tn.gov.in",
        "domain_category": DomainCategory.COOPERATIVE_GOVERNANCE.value,
        "authority_level": AuthorityLevel.STATE_GOVERNMENT.value,
        "country": "IN",
        "state": "Tamil Nadu",
        "language": "ta",
        "verification_status": VerificationStatus.VERIFIED.value,
        "verification_method": VerificationEvidenceType.OFFICIAL_DOMAIN_AUTHORITY.value,
        "verification_notes": (
            "Official portal of the Registrar of Cooperative Societies, Government of Tamil Nadu, "
            "administering Primary Agricultural Cooperative Credit Societies (PACCS) and cooperative governance in Tamil Nadu."
        ),
        "is_active": True,
        "last_verified_at": CURATION_TIMESTAMP,
        "created_at": CURATION_TIMESTAMP,
        "updated_at": CURATION_TIMESTAMP,
    },

    # Domain 3: agriculture_rural_sustainability
    {
        "id": "30000000-0000-0000-0000-000000000001",
        "source_name": "Ministry of Agriculture & Farmers Welfare",
        "organization_name": "Department of Agriculture & Farmers Welfare, Ministry of Agriculture & Farmers Welfare, GoI",
        "official_url": "https://agriwelfare.gov.in",
        "domain_category": DomainCategory.AGRICULTURE_RURAL_SUSTAINABILITY.value,
        "authority_level": AuthorityLevel.CENTRAL_GOVERNMENT.value,
        "country": "IN",
        "state": None,
        "language": "en",
        "verification_status": VerificationStatus.VERIFIED.value,
        "verification_method": VerificationEvidenceType.DEPARTMENT_MINISTRY_ASSOCIATION.value,
        "verification_notes": (
            "Central Ministry of Agriculture and Farmers Welfare responsible for national agriculture policy, "
            "PM-KISAN, PMFBY crop insurance, and sustainable agricultural missions."
        ),
        "is_active": True,
        "last_verified_at": CURATION_TIMESTAMP,
        "created_at": CURATION_TIMESTAMP,
        "updated_at": CURATION_TIMESTAMP,
    },
    {
        "id": "30000000-0000-0000-0000-000000000002",
        "source_name": "National Bank for Agriculture and Rural Development",
        "organization_name": "National Bank for Agriculture and Rural Development (NABARD)",
        "official_url": "https://www.nabard.org",
        "domain_category": DomainCategory.AGRICULTURE_RURAL_SUSTAINABILITY.value,
        "authority_level": AuthorityLevel.STATUTORY_BODY.value,
        "country": "IN",
        "state": None,
        "language": "en",
        "verification_status": VerificationStatus.VERIFIED.value,
        "verification_method": VerificationEvidenceType.CROSS_REFERENCE_GOV_SOURCE.value,
        "verification_notes": (
            "Apex development financial institution established under the National Bank for Agriculture and "
            "Rural Development Act 1981, providing refinance and rural infrastructure development support."
        ),
        "is_active": True,
        "last_verified_at": CURATION_TIMESTAMP,
        "created_at": CURATION_TIMESTAMP,
        "updated_at": CURATION_TIMESTAMP,
    },
    {
        "id": "30000000-0000-0000-0000-000000000003",
        "source_name": "Small Farmers' Agribusiness Consortium",
        "organization_name": "Small Farmers' Agribusiness Consortium (SFAC), Ministry of Agriculture & Farmers Welfare",
        "official_url": "https://sfacindia.com",
        "domain_category": DomainCategory.AGRICULTURE_RURAL_SUSTAINABILITY.value,
        "authority_level": AuthorityLevel.GOVERNMENT_INSTITUTION.value,
        "country": "IN",
        "state": None,
        "language": "en",
        "verification_status": VerificationStatus.VERIFIED.value,
        "verification_method": VerificationEvidenceType.DEPARTMENT_MINISTRY_ASSOCIATION.value,
        "verification_notes": (
            "Specialized institution promoted by Dept of Agriculture & Farmers Welfare, GoI, "
            "implementing e-NAM (National Agriculture Market) and Farmer Producer Organization (FPO) development."
        ),
        "is_active": True,
        "last_verified_at": CURATION_TIMESTAMP,
        "created_at": CURATION_TIMESTAMP,
        "updated_at": CURATION_TIMESTAMP,
    },
    {
        "id": "30000000-0000-0000-0000-000000000004",
        "source_name": "Tamil Nadu AGRISNET Portal",
        "organization_name": "Department of Agriculture and Farmers Welfare, Government of Tamil Nadu",
        "official_url": "https://www.tnagrisnet.tn.gov.in",
        "domain_category": DomainCategory.AGRICULTURE_RURAL_SUSTAINABILITY.value,
        "authority_level": AuthorityLevel.STATE_GOVERNMENT.value,
        "country": "IN",
        "state": "Tamil Nadu",
        "language": "ta",
        "verification_status": VerificationStatus.VERIFIED.value,
        "verification_method": VerificationEvidenceType.OFFICIAL_DOMAIN_AUTHORITY.value,
        "verification_notes": (
            "Official portal of the Agriculture Department of Tamil Nadu providing agricultural input schemes, "
            "subsidies, crop advisories, and farmer welfare services."
        ),
        "is_active": True,
        "last_verified_at": CURATION_TIMESTAMP,
        "created_at": CURATION_TIMESTAMP,
        "updated_at": CURATION_TIMESTAMP,
    },

    # Domain 4: foodtech_coldchain
    {
        "id": "40000000-0000-0000-0000-000000000001",
        "source_name": "Ministry of Food Processing Industries",
        "organization_name": "Ministry of Food Processing Industries, Government of India",
        "official_url": "https://www.mofpi.gov.in",
        "domain_category": DomainCategory.FOODTECH_COLDCHAIN.value,
        "authority_level": AuthorityLevel.CENTRAL_GOVERNMENT.value,
        "country": "IN",
        "state": None,
        "language": "en",
        "verification_status": VerificationStatus.VERIFIED.value,
        "verification_method": VerificationEvidenceType.DEPARTMENT_MINISTRY_ASSOCIATION.value,
        "verification_notes": (
            "Central government ministry administering PM Formalisation of Micro food processing Enterprises (PMFME) "
            "scheme and Pradhan Mantri Kisan SAMPADA Yojana for mega food parks and cold chain infrastructure."
        ),
        "is_active": True,
        "last_verified_at": CURATION_TIMESTAMP,
        "created_at": CURATION_TIMESTAMP,
        "updated_at": CURATION_TIMESTAMP,
    },
    {
        "id": "40000000-0000-0000-0000-000000000002",
        "source_name": "Food Safety and Standards Authority of India",
        "organization_name": "Food Safety and Standards Authority of India (FSSAI)",
        "official_url": "https://www.fssai.gov.in",
        "domain_category": DomainCategory.FOODTECH_COLDCHAIN.value,
        "authority_level": AuthorityLevel.STATUTORY_BODY.value,
        "country": "IN",
        "state": None,
        "language": "en",
        "verification_status": VerificationStatus.VERIFIED.value,
        "verification_method": VerificationEvidenceType.CROSS_REFERENCE_GOV_SOURCE.value,
        "verification_notes": (
            "Statutory body established under the Food Safety and Standards Act, 2006 under the Ministry of Health "
            "and Family Welfare, regulating food manufacturing, cold chain hygiene standards, and safety compliances."
        ),
        "is_active": True,
        "last_verified_at": CURATION_TIMESTAMP,
        "created_at": CURATION_TIMESTAMP,
        "updated_at": CURATION_TIMESTAMP,
    },
    {
        "id": "40000000-0000-0000-0000-000000000003",
        "source_name": "Agricultural and Processed Food Products Export Development Authority",
        "organization_name": "Agricultural and Processed Food Products Export Development Authority (APEDA)",
        "official_url": "https://apeda.gov.in",
        "domain_category": DomainCategory.FOODTECH_COLDCHAIN.value,
        "authority_level": AuthorityLevel.STATUTORY_BODY.value,
        "country": "IN",
        "state": None,
        "language": "en",
        "verification_status": VerificationStatus.VERIFIED.value,
        "verification_method": VerificationEvidenceType.CROSS_REFERENCE_GOV_SOURCE.value,
        "verification_notes": (
            "Statutory authority established by the APEDA Act 1985 under the Ministry of Commerce & Industry, "
            "managing cold chain logistics, packhouse infrastructure, and agro-export standards."
        ),
        "is_active": True,
        "last_verified_at": CURATION_TIMESTAMP,
        "created_at": CURATION_TIMESTAMP,
        "updated_at": CURATION_TIMESTAMP,
    },

    # Domain 5: rural_development_finance
    {
        "id": "50000000-0000-0000-0000-000000000001",
        "source_name": "Ministry of Rural Development",
        "organization_name": "Ministry of Rural Development, Government of India",
        "official_url": "https://rural.gov.in",
        "domain_category": DomainCategory.RURAL_DEVELOPMENT_FINANCE.value,
        "authority_level": AuthorityLevel.CENTRAL_GOVERNMENT.value,
        "country": "IN",
        "state": None,
        "language": "en",
        "verification_status": VerificationStatus.VERIFIED.value,
        "verification_method": VerificationEvidenceType.DEPARTMENT_MINISTRY_ASSOCIATION.value,
        "verification_notes": (
            "Apex Union Ministry implementing socio-economic development programs in rural India, "
            "including MGNREGA, PMGSY, and social assistance pensions."
        ),
        "is_active": True,
        "last_verified_at": CURATION_TIMESTAMP,
        "created_at": CURATION_TIMESTAMP,
        "updated_at": CURATION_TIMESTAMP,
    },
    {
        "id": "50000000-0000-0000-0000-000000000002",
        "source_name": "DAY-NRLM Aajeevika Portal",
        "organization_name": "Rural Livelihoods Division, Ministry of Rural Development, Government of India",
        "official_url": "https://aajeevika.gov.in",
        "domain_category": DomainCategory.RURAL_DEVELOPMENT_FINANCE.value,
        "authority_level": AuthorityLevel.CENTRAL_GOVERNMENT.value,
        "country": "IN",
        "state": None,
        "language": "en",
        "verification_status": VerificationStatus.VERIFIED.value,
        "verification_method": VerificationEvidenceType.AUTHORITATIVE_PORTAL_RELATION.value,
        "verification_notes": (
            "Official national portal for DAY-NRLM (Aajeevika), governing financial inclusion, "
            "revolving funds, and interest subvention for rural Self-Help Groups (SHGs)."
        ),
        "is_active": True,
        "last_verified_at": CURATION_TIMESTAMP,
        "created_at": CURATION_TIMESTAMP,
        "updated_at": CURATION_TIMESTAMP,
    },
    {
        "id": "50000000-0000-0000-0000-000000000003",
        "source_name": "Tamil Nadu Rural Development and Panchayat Raj Department",
        "organization_name": "Rural Development and Panchayat Raj Department, Government of Tamil Nadu",
        "official_url": "https://tnrd.tn.gov.in",
        "domain_category": DomainCategory.RURAL_DEVELOPMENT_FINANCE.value,
        "authority_level": AuthorityLevel.STATE_GOVERNMENT.value,
        "country": "IN",
        "state": "Tamil Nadu",
        "language": "ta",
        "verification_status": VerificationStatus.VERIFIED.value,
        "verification_method": VerificationEvidenceType.OFFICIAL_DOMAIN_AUTHORITY.value,
        "verification_notes": (
            "Official department website of Rural Development and Panchayat Raj, Government of Tamil Nadu, "
            "administering state rural development schemes, village panchayat administration, and local infrastructure grants."
        ),
        "is_active": True,
        "last_verified_at": CURATION_TIMESTAMP,
        "created_at": CURATION_TIMESTAMP,
        "updated_at": CURATION_TIMESTAMP,
    },

    # Domain 6: legal_assistance
    {
        "id": "60000000-0000-0000-0000-000000000001",
        "source_name": "National Legal Services Authority",
        "organization_name": "National Legal Services Authority (NALSA)",
        "official_url": "https://nalsa.gov.in",
        "domain_category": DomainCategory.LEGAL_ASSISTANCE.value,
        "authority_level": AuthorityLevel.STATUTORY_BODY.value,
        "country": "IN",
        "state": None,
        "language": "en",
        "verification_status": VerificationStatus.VERIFIED.value,
        "verification_method": VerificationEvidenceType.CROSS_REFERENCE_GOV_SOURCE.value,
        "verification_notes": (
            "Apex statutory authority constituted under the Legal Services Authorities Act, 1987, "
            "headed by the Chief Justice of India, providing free and competent legal services to marginalized citizens."
        ),
        "is_active": True,
        "last_verified_at": CURATION_TIMESTAMP,
        "created_at": CURATION_TIMESTAMP,
        "updated_at": CURATION_TIMESTAMP,
    },
    {
        "id": "60000000-0000-0000-0000-000000000002",
        "source_name": "Department of Justice - Tele-Law Portal",
        "organization_name": "Department of Justice, Ministry of Law and Justice, Government of India",
        "official_url": "https://www.tele-law.in",
        "domain_category": DomainCategory.LEGAL_ASSISTANCE.value,
        "authority_level": AuthorityLevel.CENTRAL_GOVERNMENT.value,
        "country": "IN",
        "state": None,
        "language": "en",
        "verification_status": VerificationStatus.VERIFIED.value,
        "verification_method": VerificationEvidenceType.AUTHORITATIVE_PORTAL_RELATION.value,
        "verification_notes": (
            "Official digital legal aid initiative of the Department of Justice, Ministry of Law and Justice, "
            "connecting citizens in rural areas to panel lawyers via Common Service Centres (CSCs)."
        ),
        "is_active": True,
        "last_verified_at": CURATION_TIMESTAMP,
        "created_at": CURATION_TIMESTAMP,
        "updated_at": CURATION_TIMESTAMP,
    },
    {
        "id": "60000000-0000-0000-0000-000000000003",
        "source_name": "Tamil Nadu State Legal Services Authority",
        "organization_name": "Tamil Nadu State Legal Services Authority (TNSLSA), High Court of Madras",
        "official_url": "https://www.tnlegalservices.tn.gov.in",
        "domain_category": DomainCategory.LEGAL_ASSISTANCE.value,
        "authority_level": AuthorityLevel.STATE_GOVERNMENT.value,
        "country": "IN",
        "state": "Tamil Nadu",
        "language": "ta",
        "verification_status": VerificationStatus.VERIFIED.value,
        "verification_method": VerificationEvidenceType.OFFICIAL_DOMAIN_AUTHORITY.value,
        "verification_notes": (
            "Statutory state authority constituted under Section 6 of the Legal Services Authorities Act 1987, "
            "delivering legal aid, Lok Adalats, and grievance mediation across Tamil Nadu districts."
        ),
        "is_active": True,
        "last_verified_at": CURATION_TIMESTAMP,
        "created_at": CURATION_TIMESTAMP,
        "updated_at": CURATION_TIMESTAMP,
    },

    # Domain 7: multilingual
    {
        "id": "70000000-0000-0000-0000-000000000001",
        "source_name": "BHASHINI National Language Translation Mission",
        "organization_name": "Digital India BHASHINI Division (DIBD), Digital India Corporation, MeitY",
        "official_url": "https://bhashini.gov.in",
        "domain_category": DomainCategory.MULTILINGUAL.value,
        "authority_level": AuthorityLevel.GOVERNMENT_INSTITUTION.value,
        "country": "IN",
        "state": None,
        "language": "en",
        "verification_status": VerificationStatus.VERIFIED.value,
        "verification_method": VerificationEvidenceType.DEPARTMENT_MINISTRY_ASSOCIATION.value,
        "verification_notes": (
            "Official language technology mission under Ministry of Electronics and IT (MeitY), "
            "building open-source multilingual AI models, datasets, and translation infrastructure across 22 scheduled Indian languages."
        ),
        "is_active": True,
        "last_verified_at": CURATION_TIMESTAMP,
        "created_at": CURATION_TIMESTAMP,
        "updated_at": CURATION_TIMESTAMP,
    },
    {
        "id": "70000000-0000-0000-0000-000000000002",
        "source_name": "Digital India Official Portal",
        "organization_name": "Digital India Corporation, Ministry of Electronics and Information Technology",
        "official_url": "https://www.digitalindia.gov.in",
        "domain_category": DomainCategory.MULTILINGUAL.value,
        "authority_level": AuthorityLevel.CENTRAL_GOVERNMENT.value,
        "country": "IN",
        "state": None,
        "language": "en",
        "verification_status": VerificationStatus.VERIFIED.value,
        "verification_method": VerificationEvidenceType.OFFICIAL_DOMAIN_AUTHORITY.value,
        "verification_notes": (
            "Apex mission portal of the Government of India for citizen-centric digital services, "
            "multilingual public interfaces, and public digital infrastructure."
        ),
        "is_active": True,
        "last_verified_at": CURATION_TIMESTAMP,
        "created_at": CURATION_TIMESTAMP,
        "updated_at": CURATION_TIMESTAMP,
    },
    {
        "id": "70000000-0000-0000-0000-000000000003",
        "source_name": "Tamil Virtual Academy",
        "organization_name": "Information Technology and Digital Services Department, Government of Tamil Nadu",
        "official_url": "https://www.tamilvu.org",
        "domain_category": DomainCategory.MULTILINGUAL.value,
        "authority_level": AuthorityLevel.STATE_GOVERNMENT.value,
        "country": "IN",
        "state": "Tamil Nadu",
        "language": "ta",
        "verification_status": VerificationStatus.VERIFIED.value,
        "verification_method": VerificationEvidenceType.GOVERNMENT_ORGANIZATION_ID.value,
        "verification_notes": (
            "Statutory autonomous board under the IT&DS Department, Government of Tamil Nadu, "
            "established to digitize Tamil literature, provide computing tools, standardized fonts, and multilingual resources."
        ),
        "is_active": True,
        "last_verified_at": CURATION_TIMESTAMP,
        "created_at": CURATION_TIMESTAMP,
        "updated_at": CURATION_TIMESTAMP,
    },
    {
        "id": "70000000-0000-0000-0000-000000000004",
        "source_name": "Tamil Nadu e-Governance Agency",
        "organization_name": "Department of Information Technology and Digital Services, Government of Tamil Nadu",
        "official_url": "https://tnega.tn.gov.in",
        "domain_category": DomainCategory.MULTILINGUAL.value,
        "authority_level": AuthorityLevel.STATE_GOVERNMENT.value,
        "country": "IN",
        "state": "Tamil Nadu",
        "language": "ta",
        "verification_status": VerificationStatus.VERIFIED.value,
        "verification_method": VerificationEvidenceType.OFFICIAL_DOMAIN_AUTHORITY.value,
        "verification_notes": (
            "Nodal agency of the Government of Tamil Nadu for e-governance implementation, state portals, "
            "citizen services (e-Sevai), and multilingual digital delivery."
        ),
        "is_active": True,
        "last_verified_at": CURATION_TIMESTAMP,
        "created_at": CURATION_TIMESTAMP,
        "updated_at": CURATION_TIMESTAMP,
    },
]

CANDIDATES_REVIEW_RAW = [
    {
        "candidate_id": "90000000-0000-0000-0000-000000000001",
        "source_name": "Bhashini AI Private Commercial Entity",
        "organization_name": "Bhashini.ai (Private Company)",
        "official_url": "https://bhashini.ai",
        "domain_category": DomainCategory.MULTILINGUAL.value,
        "authority_level": AuthorityLevel.OTHER_OFFICIAL.value,
        "language": "en",
        "country": "IN",
        "state": None,
        "verification_status": VerificationStatus.NEEDS_REVIEW.value,
        "verification_method": None,
        "verification_notes": (
            "NEEDS_REVIEW: Name collision with official MeitY BHASHINI mission (bhashini.gov.in). "
            "Independent private commercial company without confirmed government authority; requires formal review."
        ),
        "rejection_reason": None,
        "audit_trail": [
            {
                "timestamp": CURATION_TIMESTAMP,
                "action": "FLAG_NEEDS_REVIEW",
                "status": "NEEDS_REVIEW",
                "reviewer": "chief_compliance_auditor",
                "notes": "Flagged for scrutiny due to commercial domain and name collision with MeitY mission.",
                "reason": None,
            }
        ],
        "submitted_at": CURATION_TIMESTAMP,
        "updated_at": CURATION_TIMESTAMP,
    },
    {
        "candidate_id": "90000000-0000-0000-0000-000000000002",
        "source_name": "Tamil Nadu Cooperative Housing Federation Portal",
        "organization_name": "TN Cooperative Housing Federation",
        "official_url": "https://www.rcshousing.com",
        "domain_category": DomainCategory.COOPERATIVE_GOVERNANCE.value,
        "authority_level": AuthorityLevel.OTHER_OFFICIAL.value,
        "language": "ta",
        "country": "IN",
        "state": "Tamil Nadu",
        "verification_status": VerificationStatus.NEEDS_REVIEW.value,
        "verification_method": None,
        "verification_notes": (
            "NEEDS_REVIEW: Uses commercial .com TLD for cooperative housing. "
            "Requires confirmation of statutory mandate from Registrar of Cooperative Societies before verification."
        ),
        "rejection_reason": None,
        "audit_trail": [
            {
                "timestamp": CURATION_TIMESTAMP,
                "action": "FLAG_NEEDS_REVIEW",
                "status": "NEEDS_REVIEW",
                "reviewer": "chief_compliance_auditor",
                "notes": "Commercial TLD requires formal government verification.",
                "reason": None,
            }
        ],
        "submitted_at": CURATION_TIMESTAMP,
        "updated_at": CURATION_TIMESTAMP,
    },
]


def build_manifests():
    print("=" * 70)
    print("NEXO Data Platform - Curation & Manifest Generator")
    print("=" * 70)

    # 1. Validate all verified sources with SourceRecord
    verified_records: List[SourceRecord] = []
    seen_urls = set()

    for item in VERIFIED_SOURCES_RAW:
        record = SourceRecord(**item)
        if record.normalized_url in seen_urls:
            raise ValueError(f"Duplicate normalized URL detected: {record.normalized_url}")
        seen_urls.add(record.normalized_url)
        verified_records.append(record)

    print(f"[OK] Validated {len(verified_records)} official sources with SourceRecord.")

    # 2. Output verified_sources.json and verified_sources.jsonl
    manifests_dir = os.path.join(project_root, "data", "manifests", "sources")
    os.makedirs(manifests_dir, exist_ok=True)

    verified_json_path = os.path.join(manifests_dir, "verified_sources.json")
    verified_jsonl_path = os.path.join(manifests_dir, "verified_sources.jsonl")

    verified_data = [r.to_full_dict() for r in verified_records]

    with open(verified_json_path, "w", encoding="utf-8") as f:
        json.dump(verified_data, f, indent=2, ensure_ascii=False)
    print(f"[SAVED] {verified_json_path} ({len(verified_data)} records)")

    with open(verified_jsonl_path, "w", encoding="utf-8") as f:
        for item in verified_data:
            f.write(json.dumps(item, ensure_ascii=False) + "\n")
    print(f"[SAVED] {verified_jsonl_path} ({len(verified_data)} records)")

    # 3. Generate candidate_sources.json and candidate_sources.jsonl
    candidates_json_path = os.path.join(manifests_dir, "candidate_sources.json")
    candidates_jsonl_path = os.path.join(manifests_dir, "candidate_sources.jsonl")

    candidate_objs = [CandidateSource(**c) for c in CANDIDATES_REVIEW_RAW]
    candidate_data = [c.model_dump() for c in candidate_objs]

    with open(candidates_json_path, "w", encoding="utf-8") as f:
        json.dump(candidate_data, f, indent=2, ensure_ascii=False)
    print(f"[SAVED] {candidates_json_path} ({len(candidate_data)} review/rejected candidates)")

    with open(candidates_jsonl_path, "w", encoding="utf-8") as f:
        for item in candidate_data:
            f.write(json.dumps(item, ensure_ascii=False) + "\n")
    print(f"[SAVED] {candidates_jsonl_path} ({len(candidate_data)} review/rejected candidates)")

    # 4. Generate supabase_source_seed_preview.json (all 17 columns formatted by prepare_supabase_record)
    seed_preview_path = os.path.join(manifests_dir, "supabase_source_seed_preview.json")
    seed_payloads = [prepare_supabase_record(r, dry_run=False) for r in verified_records]

    with open(seed_preview_path, "w", encoding="utf-8") as f:
        json.dump(seed_payloads, f, indent=2, ensure_ascii=False)
    print(f"[SAVED] {seed_preview_path} ({len(seed_payloads)} 17-column seed payloads)")

    # 5. Print domain breakdown
    print("\nCurated Sources Breakdown by Domain:")
    by_domain: Dict[str, int] = {}
    for r in verified_records:
        by_domain[r.domain_category] = by_domain.get(r.domain_category, 0) + 1

    for domain, count in sorted(by_domain.items()):
        print(f"  - {domain:35s}: {count} sources")

    print(f"\nTotal Verified Sources: {len(verified_records)}")
    print("=" * 70)


if __name__ == "__main__":
    build_manifests()
