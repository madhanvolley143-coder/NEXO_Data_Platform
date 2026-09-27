"""
NEXO Data Platform - Supabase Connection Test Script
Tests client initialization safely without exposing secrets or crashing on Windows cp1252.
"""

import sys
import os

# Add project root to sys.path to allow running from any working directory
project_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if project_root not in sys.path:
    sys.path.insert(0, project_root)

from dotenv import load_dotenv
from config.supabase_client import get_supabase_client, check_connection
from config.settings import get_settings

load_dotenv()


def main():
    print("[NEXO] Initializing Supabase client test...")
    try:
        settings = get_settings()
        # Test client initialization
        client = get_supabase_client()
        health = check_connection()

        # Use ASCII arrow -> instead of unicode \u2192 to avoid Windows cp1252 charmap errors
        print(f"[NEXO] -> Supabase connection initialized successfully!")
        print(f"[NEXO] -> Target URL: {health.get('supabase_url')}")
        print(f"[NEXO] -> Client status: {health.get('status')}")
        print(f"[NEXO] -> Environment: {settings.environment}")
    except Exception as exc:
        print(f"[NEXO] Connection test failed: {exc}", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()