from __future__ import annotations

import re
from typing import Any


EMAIL_TYPES = ["Newsletter", "Advertising", "Digital Deployment", "Unclassified"]
NEWSLETTER_PATTERN = re.compile(r"\bMW\s+\d{1,2}/\d{1,2}/\d{2}\b", re.IGNORECASE)
CUSTOM_EMAIL_PATTERN = re.compile(r"\bcustom\s+email\b", re.IGNORECASE)


def email_name(email: dict[str, Any]) -> str:
    return str(email.get("name") or email.get("emailName") or email.get("title") or "")


def classify_email(email: dict[str, Any]) -> str:
    name = email_name(email)
    normalized = name.lower()

    if NEWSLETTER_PATTERN.search(name):
        return "Newsletter"
    if CUSTOM_EMAIL_PATTERN.search(name):
        return "Advertising"
    if "digital deployment" in normalized or "deployment" in normalized:
        return "Digital Deployment"
    return "Unclassified"
