from __future__ import annotations

import os
from dataclasses import dataclass

import streamlit as st


@dataclass(frozen=True)
class HubSpotSettings:
    primary_token: str
    secondary_token: str
    base_url: str = "https://api.hubapi.com"

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


def load_settings() -> HubSpotSettings:
    return HubSpotSettings(
        primary_token=_secret_or_env("HUBSPOT_PRIVATE_APP_TOKEN"),
        secondary_token=_secret_or_env("HUBSPOT_SECONDARY_PRIVATE_APP_TOKEN"),
        base_url=_secret_or_env("HUBSPOT_BASE_URL", "https://api.hubapi.com").rstrip("/"),
    )
