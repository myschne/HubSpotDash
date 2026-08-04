from __future__ import annotations

import pandas as pd


def dedupe_email_rows(frame: pd.DataFrame) -> pd.DataFrame:
    if frame.empty or "email_id" not in frame.columns:
        return frame.copy()
    return frame.drop_duplicates(subset=["email_id"], keep="last").reset_index(drop=True)


def add_derived_metrics(frame: pd.DataFrame) -> pd.DataFrame:
    enriched = dedupe_email_rows(frame)
    for column in ["delivered", "opens", "clicks"]:
        if column not in enriched.columns:
            enriched[column] = 0
        enriched[column] = pd.to_numeric(enriched[column], errors="coerce").fillna(0).astype(int)

    enriched["ctr"] = enriched.apply(
        lambda row: row["clicks"] / row["delivered"] if row["delivered"] else 0,
        axis=1,
    )
    enriched["open_rate"] = enriched.apply(
        lambda row: row["opens"] / row["delivered"] if row["delivered"] else 0,
        axis=1,
    )
    enriched["click_to_open_rate"] = enriched.apply(
        lambda row: row["clicks"] / row["opens"] if row["opens"] else 0,
        axis=1,
    )
    return enriched


def summarize_metrics(frame: pd.DataFrame) -> dict[str, int | float]:
    if frame.empty:
        return {
            "delivered": 0,
            "opens": 0,
            "clicks": 0,
            "ctr": 0.0,
            "open_rate": 0.0,
            "click_to_open_rate": 0.0,
            "emails": 0,
        }

    summarized = dedupe_email_rows(frame)
    delivered = int(summarized["delivered"].sum())
    opens = int(summarized["opens"].sum())
    clicks = int(summarized["clicks"].sum())
    return {
        "delivered": delivered,
        "opens": opens,
        "clicks": clicks,
        "ctr": clicks / delivered if delivered else 0.0,
        "open_rate": opens / delivered if delivered else 0.0,
        "click_to_open_rate": clicks / opens if opens else 0.0,
        "emails": int(len(summarized)),
    }
