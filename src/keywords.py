from __future__ import annotations

import re
from urllib.parse import unquote, urlparse

import pandas as pd


STOPWORDS = {
    "about",
    "after",
    "again",
    "also",
    "amid",
    "and",
    "are",
    "brief",
    "but",
    "can",
    "for",
    "from",
    "has",
    "have",
    "how",
    "into",
    "its",
    "manufacturing",
    "nan",
    "new",
    "not",
    "now",
    "of",
    "on",
    "or",
    "over",
    "the",
    "their",
    "this",
    "through",
    "to",
    "under",
    "using",
    "what",
    "when",
    "where",
    "while",
    "with",
    "would",
    "your",
}


def is_advanced_manufacturing_link(url: str) -> bool:
    domain = urlparse(str(url)).netloc.lower().removeprefix("www.")
    return domain.endswith("advancedmanufacturing.org")


def keyword_clicks(link_frame: pd.DataFrame, max_keywords: int = 25) -> pd.DataFrame:
    if link_frame.empty:
        return pd.DataFrame(columns=["keyword", "clicks", "links"])

    rows = []
    for row in link_frame.to_dict(orient="records"):
        if not is_advanced_manufacturing_link(str(row.get("link", ""))):
            continue
        text = " ".join(
            clean_text_part(row.get(column, ""))
            for column in ["title", "blurb", "article_or_site"]
        )
        clicks = int(float(row.get("clicks", 0) or 0))
        for keyword in extract_keywords(text):
            rows.append(
                {
                    "keyword": keyword,
                    "clicks": clicks,
                    "link": row.get("link", ""),
                    "article_key": article_key(row.get("link", "")),
                }
            )

    if not rows:
        return pd.DataFrame(columns=["keyword", "clicks", "links"])

    frame = (
        pd.DataFrame(rows)
        .groupby(["keyword", "article_key"], dropna=False)
        .agg(clicks=("clicks", "sum"), link=("link", "first"))
        .reset_index()
    )
    summary = (
        frame.groupby("keyword")
        .agg(
            clicks=("clicks", "sum"),
            average_clicks=("clicks", "mean"),
            median_clicks=("clicks", "median"),
            links=("article_key", "nunique"),
        )
        .reset_index()
        .sort_values(["clicks", "links"], ascending=False)
        .head(max_keywords)
    )
    return summary


def keyword_article_distribution(link_frame: pd.DataFrame, keyword: str) -> pd.DataFrame:
    if link_frame.empty or not keyword:
        return pd.DataFrame(columns=["article_or_site", "link", "clicks"])

    keyword = keyword.lower().strip()
    rows = []
    for row in link_frame.to_dict(orient="records"):
        if not is_advanced_manufacturing_link(str(row.get("link", ""))):
            continue
        text = " ".join(
            clean_text_part(row.get(column, ""))
            for column in ["title", "blurb", "article_or_site"]
        )
        if keyword not in extract_keywords(text):
            continue
        rows.append(
            {
                "article_key": article_key(row.get("link", "")),
                "article_or_site": clean_text_part(row.get("article_or_site", "")),
                "title": clean_text_part(row.get("title", "")),
                "link": row.get("link", ""),
                "clicks": int(float(row.get("clicks", 0) or 0)),
            }
        )

    if not rows:
        return pd.DataFrame(columns=["article_or_site", "title", "link", "clicks"])

    return (
        pd.DataFrame(rows)
        .groupby("article_key", dropna=False)
        .agg(
            article_or_site=("article_or_site", "first"),
            title=("title", "first"),
            link=("link", "first"),
            clicks=("clicks", "sum"),
        )
        .reset_index()
        .sort_values("clicks", ascending=False)
        .drop(columns=["article_key"])
    )


def click_distribution_histogram(distribution: pd.DataFrame) -> pd.DataFrame:
    if distribution.empty:
        return pd.DataFrame(columns=["Click Range", "Articles", "Sort"])

    clicks = pd.to_numeric(distribution["clicks"], errors="coerce").dropna().astype(int)
    if clicks.empty:
        return pd.DataFrame(columns=["Click Range", "Articles", "Sort"])

    buckets = [
        ("0", 0, 0),
        ("1-5", 1, 5),
        ("6-10", 6, 10),
        ("11-20", 11, 20),
        ("21-50", 21, 50),
        ("50-100", 51, 100),
        ("100-150", 101, 150),
        ("151-200", 151, 200),
        ("200+", 201, None),
    ]
    rows = []
    for index, (label, lower, upper) in enumerate(buckets):
        if upper is None:
            count = int((clicks >= lower).sum())
        else:
            count = int(((clicks >= lower) & (clicks <= upper)).sum())
        rows.append(
            {
                "Click Range": label,
                "Articles": count,
                "Sort": index,
            }
        )
    return pd.DataFrame(rows)


def preview_keyword_open_rates(email_frame: pd.DataFrame, max_keywords: int = 25) -> pd.DataFrame:
    if email_frame.empty:
        return pd.DataFrame(columns=["keyword", "open_rate", "emails", "delivered", "opens"])

    rows = []
    for row in email_frame.to_dict(orient="records"):
        preview_text = clean_text_part(row.get("preview_text", ""))
        if not preview_text:
            preview_text = clean_text_part(row.get("subject", ""))
        if not preview_text:
            continue

        delivered = int(float(row.get("delivered", 0) or 0))
        opens = int(float(row.get("opens", 0) or 0))
        if delivered <= 0:
            continue

        for keyword in extract_keywords(preview_text):
            rows.append(
                {
                    "keyword": keyword,
                    "delivered": delivered,
                    "opens": opens,
                    "email_id": row.get("email_id", ""),
                }
            )

    if not rows:
        return pd.DataFrame(columns=["keyword", "open_rate", "emails", "delivered", "opens"])

    frame = pd.DataFrame(rows)
    summary = (
        frame.groupby("keyword")
        .agg(
            delivered=("delivered", "sum"),
            opens=("opens", "sum"),
            emails=("email_id", "nunique"),
        )
        .reset_index()
    )
    summary["open_rate"] = summary["opens"] / summary["delivered"].replace(0, pd.NA)
    return (
        summary.dropna(subset=["open_rate"])
        .sort_values(["open_rate", "emails", "delivered"], ascending=False)
        .head(max_keywords)
    )


def extract_keywords(text: str) -> list[str]:
    tokens = re.findall(r"[a-zA-Z][a-zA-Z0-9']{2,}", str(text).lower())
    keywords = []
    seen = set()
    for token in tokens:
        token = token.strip("'")
        if token in STOPWORDS or len(token) < 3:
            continue
        if token not in seen:
            seen.add(token)
            keywords.append(token)
    return keywords


def clean_text_part(value: object) -> str:
    if value is None:
        return ""
    try:
        if pd.isna(value):
            return ""
    except TypeError:
        pass
    text = str(value).strip()
    if text.lower() in {"nan", "none", "null"}:
        return ""
    return text


def article_key(url: object) -> str:
    parsed = urlparse(str(url))
    domain = parsed.netloc.lower().removeprefix("www.")
    path = unquote(parsed.path).rstrip("/").lower()
    return f"{domain}{path}"
