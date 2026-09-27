"""
NEXO Data Platform - Environment & Database Configuration
Loads and validates credentials from .env without exposing secrets.
"""

import os
from dataclasses import dataclass
from typing import Optional
from dotenv import load_dotenv

# Ensure environment variables are loaded
load_dotenv()


@dataclass(frozen=True)
class Settings:
    supabase_url: str
    supabase_publishable_key: str
    supabase_service_role_key: Optional[str] = None
    environment: str = "development"

    def __repr__(self) -> str:
        """Prevent accidental exposure of credentials in logs or interactive shells."""
        url_preview = self.supabase_url[:18] + "..." if len(self.supabase_url) > 18 else self.supabase_url
        key_masked = self.supabase_publishable_key[:6] + "..." if self.supabase_publishable_key else "NOT_SET"
        role_key_present = bool(self.supabase_service_role_key)
        return (
            f"Settings(supabase_url='{url_preview}', "
            f"supabase_publishable_key='{key_masked}', "
            f"service_role_key_set={role_key_present}, "
            f"environment='{self.environment}')"
        )


_settings_instance: Optional[Settings] = None


def get_settings() -> Settings:
    """
    Retrieve or initialize the cached application Settings.
    Raises ValueError if required connection credentials are missing.
    """
    global _settings_instance
    if _settings_instance is not None:
        return _settings_instance

    url = os.getenv("SUPABASE_URL")
    # Support both publishable key and anon key naming conventions
    publishable_key = (
        os.getenv("SUPABASE_PUBLISHABLE_KEY")
        or os.getenv("SUPABASE_ANON_KEY")
        or os.getenv("SUPABASE_KEY")
    )
    service_role_key = os.getenv("SUPABASE_SERVICE_ROLE_KEY")
    environment = os.getenv("ENVIRONMENT", "development")

    if not url:
        raise ValueError(
            "SUPABASE_URL environment variable is not set in .env. "
            "Please check your .env file."
        )

    if not publishable_key:
        raise ValueError(
            "SUPABASE_PUBLISHABLE_KEY (or SUPABASE_ANON_KEY) is not set in .env. "
            "Please check your .env file."
        )

    _settings_instance = Settings(
        supabase_url=url.strip(),
        supabase_publishable_key=publishable_key.strip(),
        supabase_service_role_key=service_role_key.strip() if service_role_key else None,
        environment=environment.strip(),
    )
    return _settings_instance
