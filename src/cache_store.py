from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

import pandas as pd


CACHE_DIR = Path("data") / "cache"
CACHE_FILE = CACHE_DIR / "hubspot_emails.csv"


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
