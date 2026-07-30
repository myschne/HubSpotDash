from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

import pandas as pd

from src.config import GoogleSheetsCacheSettings
from src.google_sheets_cache import append_worksheet_row, load_worksheet, save_worksheet, upsert_worksheet


PROJECT_ROOT = Path(__file__).resolve().parents[1]
CACHE_DIR = PROJECT_ROOT / "data" / "cache"
CACHE_FILE = CACHE_DIR / "hubspot_emails.csv"
LINK_CACHE_FILE = CACHE_DIR / "hubspot_link_clicks.csv"


@dataclass(frozen=True)
class CacheStatus:
    cache_buster: int

    @classmethod
    def from_cache_buster(cls, cache_buster: int) -> "CacheStatus":
        return cls(cache_buster=cache_buster)


def load_cached_emails(
    path: Path = CACHE_FILE,
    google_cache: GoogleSheetsCacheSettings | None = None,
) -> pd.DataFrame:
    try:
        sheet_frame = load_worksheet(
            google_cache,
            google_cache.emails_worksheet if google_cache else "",
        )
    except Exception:
        sheet_frame = None
    if sheet_frame is not None:
        return sheet_frame
    if not path.exists():
        return pd.DataFrame()
    return pd.read_csv(path).fillna("")


def save_cached_emails(
    frame: pd.DataFrame,
    path: Path = CACHE_FILE,
    google_cache: GoogleSheetsCacheSettings | None = None,
) -> None:
    CACHE_DIR.mkdir(parents=True, exist_ok=True)
    frame.to_csv(path, index=False)
    upsert_worksheet(
        frame,
        google_cache,
        google_cache.emails_worksheet if google_cache else "",
        ["email_id"],
    )


def merge_cached_emails(new_frame: pd.DataFrame, cached_frame: pd.DataFrame) -> pd.DataFrame:
    return merge_cache_rows(new_frame, cached_frame, ["email_id"])


def load_cached_link_clicks(
    path: Path = LINK_CACHE_FILE,
    google_cache: GoogleSheetsCacheSettings | None = None,
) -> pd.DataFrame:
    try:
        sheet_frame = load_worksheet(
            google_cache,
            google_cache.links_worksheet if google_cache else "",
        )
    except Exception:
        sheet_frame = None
    if sheet_frame is not None:
        return sheet_frame
    if not path.exists():
        return pd.DataFrame()
    return pd.read_csv(path).fillna("")


def save_cached_link_clicks(
    frame: pd.DataFrame,
    path: Path = LINK_CACHE_FILE,
    google_cache: GoogleSheetsCacheSettings | None = None,
) -> None:
    CACHE_DIR.mkdir(parents=True, exist_ok=True)
    frame.to_csv(path, index=False)
    upsert_worksheet(
        frame,
        google_cache,
        google_cache.links_worksheet if google_cache else "",
        ["email_id", "link"],
    )


def save_google_cache_sheet(
    frame: pd.DataFrame,
    google_cache: GoogleSheetsCacheSettings | None,
    worksheet_name: str,
    key_columns: list[str] | None = None,
) -> None:
    if key_columns:
        upsert_worksheet(frame, google_cache, worksheet_name, key_columns)
    else:
        save_worksheet(frame, google_cache, worksheet_name)


def append_google_cache_row(
    row: dict,
    google_cache: GoogleSheetsCacheSettings | None,
    worksheet_name: str,
) -> None:
    append_worksheet_row(row, google_cache, worksheet_name)


def merge_cached_link_clicks(new_frame: pd.DataFrame, cached_frame: pd.DataFrame) -> pd.DataFrame:
    return merge_cache_rows(new_frame, cached_frame, ["email_id", "link"])


def merge_cache_rows(
    new_frame: pd.DataFrame,
    cached_frame: pd.DataFrame,
    key_columns: list[str],
) -> pd.DataFrame:
    if cached_frame.empty:
        combined = new_frame.copy()
    elif new_frame.empty:
        combined = cached_frame.copy()
    else:
        combined = pd.concat([cached_frame, new_frame], ignore_index=True)

    if combined.empty:
        return combined
    existing_keys = [column for column in key_columns if column in combined.columns]
    if not existing_keys:
        return combined
    return combined.drop_duplicates(subset=existing_keys, keep="last").reset_index(drop=True)
