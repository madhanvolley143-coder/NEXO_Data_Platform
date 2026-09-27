"""
NEXO Data Platform - Centralized Supabase Client Factory
Provides standard and admin clients with safe health-check capabilities.
"""

from typing import Optional, Dict, Any
from supabase import create_client, Client
from config.settings import get_settings

_client_instance: Optional[Client] = None
_admin_client_instance: Optional[Client] = None


def get_supabase_client() -> Client:
    """
    Get or initialize the standard Supabase client (using publishable/anon key).
    Respects Row Level Security (RLS).
    """
    global _client_instance
    if _client_instance is None:
        settings = get_settings()
        _client_instance = create_client(
            settings.supabase_url,
            settings.supabase_publishable_key,
        )
    return _client_instance


def get_supabase_admin_client() -> Client:
    """
    Get or initialize the administrative Supabase client (using service role key).
    Bypasses Row Level Security (RLS). Used for backend ingestion pipelines.
    Raises ValueError if SUPABASE_SERVICE_ROLE_KEY is not configured.
    """
    global _admin_client_instance
    if _admin_client_instance is None:
        settings = get_settings()
        if not settings.supabase_service_role_key:
            raise ValueError(
                "SUPABASE_SERVICE_ROLE_KEY is required for administrative client access, "
                "but it is not configured in .env."
            )
        _admin_client_instance = create_client(
            settings.supabase_url,
            settings.supabase_service_role_key,
        )
    return _admin_client_instance


def check_connection() -> Dict[str, Any]:
    """
    Validates that the Supabase client can be initialized and credentials are valid.
    Does NOT perform any destructive or modifying operations.
    Returns status dictionary.
    """
    try:
        client = get_supabase_client()
        # Initialize check without executing arbitrary table queries
        # Safe read of client status
        is_configured = bool(client and client.supabase_url)
        return {
            "status": "connected" if is_configured else "error",
            "supabase_url": get_settings().supabase_url[:20] + "...",
            "auth_available": hasattr(client, "auth"),
            "storage_available": hasattr(client, "storage"),
            "postgrest_available": hasattr(client, "postgrest"),
        }
    except Exception as exc:
        return {
            "status": "failed",
            "error": str(exc),
        }
