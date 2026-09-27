"""
NEXO Data Platform - Document Discovery & Collector CLI Entry Point
Usage:
    python -m app.collector --dry-run
    python -m app.collector --dry-run --domain government_schemes
    python -m app.collector --dry-run --limit 3
    python -m app.collector --resume
"""

import argparse
import sys
import os

# Ensure project root is in sys.path
project_root = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
if project_root not in sys.path:
    sys.path.insert(0, project_root)

from app.collector.orchestrator import CollectorPipeline


def main():
    parser = argparse.ArgumentParser(
        description="NEXO Data Platform - Official Document Discovery & Collector Pipeline"
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        default=True,
        help="Simulate discovery and manifest generation without downloading binaries (default: True).",
    )
    parser.add_argument(
        "--live",
        dest="dry_run",
        action="store_false",
        help="Execute live downloading, content validation, and local staging.",
    )
    parser.add_argument(
        "--domain",
        type=str,
        default=None,
        help="Filter crawling to a specific NEXO domain category.",
    )
    parser.add_argument(
        "--source-id",
        type=str,
        default=None,
        help="Crawl only the specified verified source ID.",
    )
    parser.add_argument(
        "--max-depth",
        type=int,
        default=1,
        help="Maximum link exploration depth (default: 1).",
    )
    parser.add_argument(
        "--limit",
        type=int,
        default=10,
        help="Maximum pages to visit per source (default: 10).",
    )
    parser.add_argument(
        "--resume",
        action="store_true",
        default=False,
        help="Resume crawling from checkpoint state.",
    )

    args = parser.parse_args()

    print("=" * 70)
    print("NEXO Data Platform - Document Discovery & Collector Pipeline")
    print("=" * 70)
    mode_text = "DRY RUN (Simulated Discovery & Manifest Staging)" if args.dry_run else "LIVE COLLECTION"
    print(f"Mode       : {mode_text}")
    print(f"Domain     : {args.domain or 'All 7 NEXO Focus Domains'}")
    print(f"Max Depth  : {args.max_depth}")
    print(f"Page Limit : {args.limit} per source")
    print(f"Resume     : {args.resume}")
    print("=" * 70)

    pipeline = CollectorPipeline(
        dry_run=args.dry_run,
        max_depth=args.max_depth,
        max_pages_per_source=args.limit,
        allowed_domain=args.domain,
        target_source_id=args.source_id,
        resume=args.resume,
    )

    stats = pipeline.run()

    print("\n" + "=" * 70)
    print("COLLECTOR PIPELINE EXECUTION SUMMARY")
    print("=" * 70)
    print(f"Total Sources Considered : {stats.total_sources}")
    print(f"URLs Discovered          : {stats.urls_discovered}")
    print(f"Documents Identified     : {stats.documents_identified}")
    print(f"Documents Staged         : {stats.documents_staged}")
    print(f"Duplicates Preserved     : {stats.duplicates_preserved}")
    print(f"Documents Failed         : {stats.documents_failed}")
    print("=" * 70)


if __name__ == "__main__":
    main()
