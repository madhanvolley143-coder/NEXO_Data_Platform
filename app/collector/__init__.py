"""
NEXO Data Platform - Document Discovery & Collector Package
Provides modular tools for discovering, vetting, and staging official government documents.
"""

from app.collector.models import DiscoveredDocument, CrawlStats, CheckpointState
from app.collector.security import (
    is_safe_scheme,
    is_domain_authorized,
    validate_crawl_target,
    validate_redirect,
)
from app.collector.relevance import (
    assess_relevance,
    RelevanceResult,
    CONFIRMED,
    NEEDS_REVIEW,
    IRRELEVANT,
)
from app.collector.polite_client import PoliteHttpClient, FetchResult
from app.collector.discovery import extract_links_from_html, is_document_url
from app.collector.downloader import DocumentDownloader, DownloadResult
from app.collector.geo_tagger import classify_geography, GeoClassificationResult
from app.collector.checkpoint import CheckpointManager
from app.collector.orchestrator import CollectorPipeline

__all__ = [
    "DiscoveredDocument",
    "CrawlStats",
    "CheckpointState",
    "is_safe_scheme",
    "is_domain_authorized",
    "validate_crawl_target",
    "validate_redirect",
    "assess_relevance",
    "RelevanceResult",
    "CONFIRMED",
    "NEEDS_REVIEW",
    "IRRELEVANT",
    "PoliteHttpClient",
    "FetchResult",
    "extract_links_from_html",
    "is_document_url",
    "DocumentDownloader",
    "DownloadResult",
    "classify_geography",
    "GeoClassificationResult",
    "CheckpointManager",
    "CollectorPipeline",
]
