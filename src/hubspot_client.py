from __future__ import annotations

from datetime import date, datetime
from typing import Any

import pandas as pd
import requests


class HubSpotClientError(RuntimeError):
    """Raised when HubSpot configuration or API access fails."""


class HubSpotClientAuthError(HubSpotClientError):
    """Raised when HubSpot rejects a token for a specific endpoint."""


class HubSpotClient:
    MARKETING_EMAILS_PATH = "/marketing/emails/2026-03"
    EMAIL_EVENTS_PATH = "/email/public/v1/events"

    def __init__(
        self,
        access_token: str,
        base_url: str = "https://api.hubapi.com",
        use_legacy_events: bool = False,
    ) -> None:
        self.access_token = access_token.strip()
        self.base_url = base_url.rstrip("/")
        self.use_legacy_events = use_legacy_events
        self.event_warnings: list[str] = []
        self.detail_warnings: list[str] = []
        if not self.access_token:
            raise HubSpotClientError("HubSpot access token is missing.")

    def marketing_emails(self, created_after: date | None = None) -> list[dict[str, Any]]:
        params: dict[str, Any] = {"limit": 100}
        if created_after:
            params["createdAfter"] = f"{created_after.isoformat()}T00:00:00Z"

        emails: list[dict[str, Any]] = []
        after = ""
        while True:
            if after:
                params["after"] = after
            payload = self._get_json(self.MARKETING_EMAILS_PATH, params=params)
            results = payload.get("results") if isinstance(payload, dict) else None
            if not isinstance(results, list):
                results = payload if isinstance(payload, list) else []
            emails.extend(result for result in results if isinstance(result, dict))

            paging = payload.get("paging", {}) if isinstance(payload, dict) else {}
            after = str(paging.get("next", {}).get("after", "") or "")
            if not after:
                return emails

    def email_detail(self, email_id: str) -> dict[str, Any]:
        if not email_id:
            return {}
        try:
            return self._get_json(
                f"{self.MARKETING_EMAILS_PATH}/{email_id}",
                params={"includeStats": "true"},
            )
        except HubSpotClientError as error:
            self.detail_warnings.append(
                f"Detail lookup skipped for email ID {self.safe_id(email_id)}: {error}"
            )
            return {}

    def email_event_totals(self, email: dict[str, Any]) -> dict[str, int]:
        totals = {"opens": 0, "clicks": 0}
        if not self.use_legacy_events:
            return totals

        for campaign_id in self.email_campaign_ids(email):
            if not campaign_id.isdigit():
                self.event_warnings.append(
                    f"Skipped non-numeric campaign ID {self.safe_id(campaign_id)} for legacy events endpoint."
                )
                continue
            try:
                totals["opens"] += self._count_total_events(campaign_id, "OPEN")
                totals["clicks"] += self._count_total_events(campaign_id, "CLICK")
            except HubSpotClientAuthError as error:
                self.event_warnings.append(str(error))
                return totals
            except HubSpotClientError as error:
                self.event_warnings.append(
                    f"Legacy email events lookup skipped for campaign ID {self.safe_id(campaign_id)}: {error}"
                )
                return totals
        return totals

    def _count_total_events(self, campaign_id: str, event_type: str) -> int:
        params: dict[str, Any] = {
            "limit": 1000,
            "campaignId": campaign_id,
            "eventType": event_type,
        }
        total = 0

        while True:
            payload = self._get_json(self.EMAIL_EVENTS_PATH, params=params)
            for event in payload.get("events", []):
                if event.get("filteredEvent") is False:
                    total += 1

            if not payload.get("hasMore"):
                return total
            params["offset"] = payload.get("offset")

    def _get_json(self, path: str, params: dict[str, Any] | None = None) -> dict[str, Any]:
        response = requests.get(
            f"{self.base_url}{path}",
            headers={
                "Authorization": f"Bearer {self.access_token}",
                "Accept": "application/json",
            },
            params=params,
            timeout=30,
        )
        if response.status_code in {401, 403}:
            raise HubSpotClientAuthError(
                f"HubSpot rejected the private app token for {path} "
                f"with HTTP {response.status_code}. Check token value and scopes."
            )
        try:
            response.raise_for_status()
        except requests.HTTPError as exc:
            raise HubSpotClientError(
                f"HubSpot API request failed: {response.status_code} {response.text[:300]}"
            ) from exc
        return response.json()

    @staticmethod
    def email_campaign_ids(email: dict[str, Any]) -> list[str]:
        campaign_ids = []
        for key in [
            "primaryEmailCampaignId",
            "emailCampaignId",
            "campaignId",
            "campaign_id",
        ]:
            value = email.get(key)
            if isinstance(value, dict):
                value = value.get("id") or value.get("campaignId")
            if value and str(value).isdigit():
                campaign_ids.append(str(value))
        for key in ["allEmailCampaignIds", "emailCampaignIds", "campaignIds"]:
            value = email.get(key)
            if isinstance(value, list):
                campaign_ids.extend(str(item) for item in value if item and str(item).isdigit())
        return list(dict.fromkeys(campaign_ids))

    @staticmethod
    def safe_id(value: str) -> str:
        if len(value) <= 8:
            return value
        return f"{value[:4]}...{value[-4:]}"

    @staticmethod
    def email_name(email: dict[str, Any]) -> str:
        return str(email.get("name") or email.get("emailName") or email.get("title") or "")

    @classmethod
    def email_date(cls, email: dict[str, Any]) -> date | None:
        return cls.coerce_date(
            cls.first_value(
                email,
                [
                    "publishedAt",
                    "publishDate",
                    "sentAt",
                    "sendDate",
                    "lastSendTime",
                    "lastSentAt",
                    "lastPublishedAt",
                    "createdAt",
                ],
            )
        )

    @classmethod
    def metric_value(cls, payload: dict[str, Any], keys: list[str]) -> int:
        stats = payload.get("stats", {}) if isinstance(payload.get("stats"), dict) else payload
        counter_value = cls.counter_value(stats, keys)
        if counter_value is not None:
            return counter_value
        found = cls.first_value(stats, keys)
        try:
            return int(float(found or 0))
        except (TypeError, ValueError):
            return 0

    @classmethod
    def counter_value(cls, value: Any, keys: list[str]) -> int | None:
        if not isinstance(value, dict):
            return None

        for counter_container in [
            value.get("counters"),
            value.get("counter"),
            value.get("aggregations", {}).get("counters")
            if isinstance(value.get("aggregations"), dict)
            else None,
        ]:
            if not isinstance(counter_container, dict):
                continue
            found = cls.first_value(counter_container, keys)
            try:
                return int(float(found))
            except (TypeError, ValueError):
                continue
        return None

    @classmethod
    def first_value(cls, value: Any, keys: list[str]) -> Any:
        if isinstance(value, dict):
            for key in keys:
                if key in value and value[key] not in (None, ""):
                    return value[key]
            for nested in value.values():
                found = cls.first_value(nested, keys)
                if found not in (None, ""):
                    return found
        if isinstance(value, list):
            for item in value:
                found = cls.first_value(item, keys)
                if found not in (None, ""):
                    return found
        return None

    @staticmethod
    def coerce_date(value: Any) -> date | None:
        if isinstance(value, date) and not isinstance(value, datetime):
            return value
        text = str(value or "").strip()
        if not text:
            return None
        parsed = pd.to_datetime(text, errors="coerce")
        if pd.isna(parsed):
            return None
        return parsed.date()
