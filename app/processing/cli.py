"""
NEXO Data Platform - Content Processing Pipeline CLI
Command line interface for document content extraction and processing.
"""

import argparse
import sys
import os

# Ensure project root is in sys.path
project_root = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
if project_root not in sys.path:
    sys.path.insert(0, project_root)

# Reconfigure stdout for Windows console UTF-8 support
try:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    if hasattr(sys.stderr, "reconfigure"):
        sys.stderr.reconfigure(encoding="utf-8", errors="replace")
except Exception:
    pass

from app.processing.orchestrator import DocumentContentProcessor


def main():
    parser = argparse.ArgumentParser(
        description="NEXO Data Platform - Production Document Content Processing Pipeline",
        formatter_class=argparse.ArgumentDefaultsHelpFormatter,
    )

    parser.add_argument(
        "--dry-run",
        action="store_true",
        default=True,
        help="Execute in simulation mode without writing to database or uploading artifacts.",
    )
    parser.add_argument(
        "--live",
        action="store_true",
        default=False,
        help="Execute in LIVE mode writing processing records to PostgreSQL.",
    )
    parser.add_argument(
        "--limit",
        type=int,
        default=None,
        help="Maximum number of documents to evaluate.",
    )
    parser.add_argument(
        "--document-id",
        type=str,
        default=None,
        help="Process a single specific document by its PostgreSQL UUID.",
    )
    parser.add_argument(
        "--force-reprocess",
        action="store_true",
        default=False,
        help="Force reprocessing even if document was already processed under the current version.",
    )
    parser.add_argument(
        "--manifest-dir",
        type=str,
        default=None,
        help="Custom directory for saving processing manifests and checkpoints.",
    )

    args = parser.parse_args()

    # If --live is explicitly given, dry_run is False
    is_dry_run = not args.live

    processor = DocumentContentProcessor(
        dry_run=is_dry_run,
        manifest_dir=args.manifest_dir,
        force_reprocess=args.force_reprocess,
    )

    processor.run(
        limit=args.limit,
        document_id=args.document_id,
    )


if __name__ == "__main__":
    main()
