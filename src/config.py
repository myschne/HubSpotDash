from __future__ import annotations

import os
from dataclasses import dataclass
from typing import Any

import streamlit as st


@dataclass(frozen=True)
class GoogleSheetsCacheSettings:
    enabled: bool
    spreadsheet_id: str
    emails_worksheet: str
    links_worksheet: str
    service_account_file: str
    service_account_json: Any


@dataclass(frozen=True)
class HubSpotSettings:
    primary_token: str
    secondary_token: str
    base_url: str = "https://api.hubapi.com"
    google_cache: GoogleSheetsCacheSettings | None = None

    def token_options(self) -> list[tuple[str, str]]:
        options = []
        if self.primary_token:
            options.append(("primary", self.primary_token))
        if self.secondary_token and self.secondary_token != self.primary_token:
            options.append(("secondary", self.secondary_token))
        return options


def _secret_or_env(name: str, default: str = "") -> str:
    try:
        value = st.secrets.get(name, "")
    except Exception:
        value = ""
    return str(value or os.getenv(name, default)).strip()


def _secret_or_env_raw(name: str, default: Any = "") -> Any:
    try:
        value = st.secrets.get(name, None)
    except Exception:
        value = None
    if value not in (None, ""):
        return value
    return os.getenv(name, default)


def _secret_or_env_bool(name: str, default: bool = False) -> bool:
    value = _secret_or_env(name, str(default))
    return value.lower() in {"1", "true", "yes", "on"}


def load_settings() -> HubSpotSettings:
    google_cache = GoogleSheetsCacheSettings(
        enabled=_secret_or_env_bool("GOOGLE_SHEETS_CACHE_ENABLED", False),
        spreadsheet_id=_secret_or_env("GOOGLE_SHEETS_SPREADSHEET_ID"),
        emails_worksheet=_secret_or_env("GOOGLE_SHEETS_EMAILS_WORKSHEET", "hubspot_emails"),
        links_worksheet=_secret_or_env("GOOGLE_SHEETS_LINKS_WORKSHEET", "hubspot_link_clicks"),
        service_account_file=_secret_or_env(
            "GOOGLE_SERVICE_ACCOUNT_FILE",
            "stable-hologram-497015-i9-45282bfa717e.json",
        ),
        service_account_json=_secret_or_env_raw("GOOGLE_SERVICE_ACCOUNT_JSON"),
    )
    return HubSpotSettings(
        primary_token=_secret_or_env("HUBSPOT_PRIVATE_APP_TOKEN"),
        secondary_token=_secret_or_env("HUBSPOT_SECONDARY_PRIVATE_APP_TOKEN"),
        base_url=_secret_or_env("HUBSPOT_BASE_URL", "https://api.hubapi.com").rstrip("/"),
        google_cache=google_cache,
    )
