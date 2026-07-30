from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

import pandas as pd


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


def load_cached_emails(path: Path = CACHE_FILE) -> pd.DataFrame:
    if not path.exists():
        return pd.DataFrame()
    return pd.read_csv(path).fillna("")


def save_cached_emails(frame: pd.DataFrame, path: Path = CACHE_FILE) -> None:
    CACHE_DIR.mkdir(parents=True, exist_ok=True)
    frame.to_csv(path, index=False)


def merge_cached_emails(new_frame: pd.DataFrame, cached_frame: pd.DataFrame) -> pd.DataFrame:
    return merge_cache_rows(new_frame, cached_frame, ["email_id"])


def load_cached_link_clicks(path: Path = LINK_CACHE_FILE) -> pd.DataFrame:
    if not path.exists():
        return pd.DataFrame()
    return pd.read_csv(path).fillna("")


def save_cached_link_clicks(frame: pd.DataFrame, path: Path = LINK_CACHE_FILE) -> None:
    CACHE_DIR.mkdir(parents=True, exist_ok=True)
    frame.to_csv(path, index=False)


def merge_cached_link_clicks(new_frame: pd.DataFrame, cached_frame: pd.DataFrame) -> pd.DataFrame:
    return merge_cache_rows(new_frame, cached_frame, ["email_id", "link"])


def merge_cache_rows(
    new_frame: pd.DataFrame,
    cached_frame: pd.DataFrame,
    key_columns: list[str],
) -> pd.DataFrame:
    if cached_frame.empty:
        return new_frame.copy()
    if new_frame.empty:
        return cached_frame.copy()

    combined = pd.concat([cached_frame, new_frame], ignore_index=True)
    existing_keys = [column for column in key_columns if column in combined.columns]
    if not existing_keys:
        return combined
    return combined.drop_duplicates(subset=existing_keys, keep="last").reset_index(drop=True)
