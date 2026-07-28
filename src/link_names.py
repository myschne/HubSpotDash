from __future__ import annotations

import re
from urllib.parse import unquote, urlparse


ARTICLE_ID_PATTERN = re.compile(r"^article[_-][a-f0-9_-]{8,}$", re.IGNORECASE)


def article_or_site_name(url: str) -> str:
    parsed = urlparse(str(url))
    domain = parsed.netloc.lower().removeprefix("www.")
    path_parts = [part for part in parsed.path.split("/") if part]

    if domain.endswith("advancedmanufacturing.org") and path_parts:
        title_part = article_title_part(path_parts)
        return slug_to_title(title_part)

    if path_parts:
        return f"{slug_to_title(path_parts[-1])} ({domain})"
    return domain or url


def article_title_part(path_parts: list[str]) -> str:
    for part in reversed(path_parts):
        cleaned_part = re.sub(r"\.[a-z0-9]{2,5}$", "", part, flags=re.IGNORECASE)
        if ARTICLE_ID_PATTERN.match(cleaned_part):
            continue
        if cleaned_part.lower() in {"news-desk", "technologies", "industries", "multimedia"}:
            continue
        return cleaned_part
    return path_parts[-1]


def slug_to_title(value: str) -> str:
    text = unquote(value)
    text = re.sub(r"\.[a-z0-9]{2,5}$", "", text, flags=re.IGNORECASE)
    text = re.sub(r"[-_]+", " ", text)
    text = re.sub(r"\s+", " ", text).strip()
    if not text:
        return "Untitled Link"
    return headline_case(text)


def headline_case(text: str) -> str:
    small_words = {"a", "an", "and", "as", "at", "but", "by", "for", "in", "of", "on", "or", "the", "to", "vs"}
    contractions = {"didnt": "Didn't", "dont": "Don't", "cant": "Can't", "wont": "Won't", "isnt": "Isn't"}
    words = text.split()
    titled = []
    for index, word in enumerate(words):
        lower = word.lower()
        if lower in contractions:
            titled.append(contractions[lower])
        elif 0 < index < len(words) - 1 and lower in small_words:
            titled.append(lower)
        elif lower in {"us", "u.s", "u.s."}:
            titled.append("U.S.")
        else:
            titled.append(lower.capitalize())
    return " ".join(titled)
