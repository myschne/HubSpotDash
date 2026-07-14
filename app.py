from __future__ import annotations

from datetime import date, timedelta

import pandas as pd
import streamlit as st

from src.cache_store import CacheStatus, load_cached_emails, save_cached_emails
from src.config import HubSpotSettings, load_settings
from src.email_classifier import EMAIL_TYPES, classify_email
from src.hubspot_client import HubSpotClient, HubSpotClientError
from src.metrics import add_derived_metrics, summarize_metrics


st.set_page_config(
    page_title="HubSpot Email Dashboard",
    page_icon=":bar_chart:",
    layout="wide",
)


def default_date_range(period_label: str) -> tuple[date, date]:
    end_date = date.today()
    days = {
        "Last 7 days": 7,
        "Last 30 days": 30,
        "Last 90 days": 90,
        "Year to date": max(1, (end_date - date(end_date.year, 1, 1)).days + 1),
    }[period_label]
    return end_date - timedelta(days=days - 1), end_date


@st.cache_data(show_spinner=False)
def cached_frame(cache_buster: int) -> tuple[pd.DataFrame, CacheStatus]:
    return load_cached_emails(), CacheStatus.from_cache_buster(cache_buster)


def fetch_live_data(
    settings: HubSpotSettings,
    start_date: date,
    end_date: date,
) -> tuple[pd.DataFrame, str, list[str]]:
    errors = []
    client = None
    emails = []

    for token_label, token in settings.token_options():
        candidate = HubSpotClient(token, base_url=settings.base_url, use_legacy_events=True)
        try:
            emails = candidate.marketing_emails(created_after=start_date)
            client = candidate
            break
        except HubSpotClientError as error:
            errors.append(f"{token_label}: {error}")

    if client is None:
        raise HubSpotClientError("No configured HubSpot token could fetch marketing emails. " + " | ".join(errors))

    rows = []

    for email in emails:
        detail = client.email_detail(str(email.get("id")))
        merged = {**email, **detail}
        email_date = client.email_date(merged)
        if email_date and not (start_date <= email_date <= end_date):
            continue

        event_totals = client.email_event_totals(merged)
        delivered = client.metric_value(
            merged,
            ["delivered", "deliveries", "deliveredCount", "successfulDeliveries", "sent"],
        )
        opens = event_totals.get("opens") or client.metric_value(
            merged,
            [
                "totalOpens",
                "totalOpen",
                "open",
                "openedTotal",
                "opensTotal",
                "opened",
                "opens",
                "openCount",
                "uniqueOpens",
            ],
        )
        clicks = event_totals.get("clicks") or client.metric_value(
            merged,
            [
                "totalClicks",
                "totalClick",
                "click",
                "clickedTotal",
                "clicksTotal",
                "clicks",
                "clicked",
                "clickCount",
                "uniqueClicks",
            ],
        )

        rows.append(
            {
                "email_id": str(merged.get("id") or merged.get("emailId") or ""),
                "email_name": client.email_name(merged),
                "subject": str(
                    client.first_value(merged, ["subject", "emailSubject", "previewText"])
                    or ""
                ),
                "email_type": classify_email(merged),
                "send_date": email_date.isoformat() if email_date else "",
                "delivered": delivered,
                "opens": opens,
                "clicks": clicks,
                "web_version_url": str(
                    client.first_value(
                        merged,
                        ["webVersionUrl", "webversionUrl", "publishedUrl", "absoluteUrl", "url"],
                    )
                    or ""
                ),
            }
        )

    frame = add_derived_metrics(pd.DataFrame(rows))
    save_cached_emails(frame)
    warnings = sorted(set(client.event_warnings + client.detail_warnings))
    return frame, token_label, warnings


st.title("HubSpot Email Performance")

settings = load_settings()

with st.sidebar:
    st.header("Controls")
    period_label = st.selectbox(
        "Period",
        ["Last 7 days", "Last 30 days", "Last 90 days", "Year to date"],
        index=1,
    )
    start_date, end_date = default_date_range(period_label)
    selected_dates = st.date_input("Date range", value=(start_date, end_date))
    if isinstance(selected_dates, tuple) and len(selected_dates) == 2:
        start_date, end_date = selected_dates

    selected_types = st.multiselect(
        "Email type",
        EMAIL_TYPES,
        default=["Newsletter", "Advertising", "Digital Deployment", "Unclassified"],
    )

    st.divider()
    refresh = st.button("Refresh from HubSpot", type="primary", use_container_width=True)
    use_cache = st.checkbox("Use local cache when available", value=True)

if not settings.token_options():
    st.warning(
        "Add HUBSPOT_PRIVATE_APP_TOKEN to .streamlit/secrets.toml or your environment, "
        "then refresh from HubSpot."
    )

cache_buster = st.session_state.get("cache_buster", 0)
frame, cache_status = cached_frame(cache_buster)

if refresh:
    if not settings.token_options():
        st.error("HubSpot token is missing. Fill in .streamlit/secrets.toml first.")
    else:
        with st.spinner("Fetching HubSpot email data..."):
            try:
                frame, token_label, event_warnings = fetch_live_data(settings, start_date, end_date)
                st.session_state["cache_buster"] = cache_buster + 1
                st.success(f"HubSpot data refreshed with the {token_label} token and cached locally.")
                if event_warnings:
                    st.warning(
                        "Some HubSpot detail/event lookups were unavailable, "
                        "so the app used included email stats where available. "
                        + " ".join(event_warnings[:2])
                    )
            except HubSpotClientError as error:
                st.error(str(error))
elif frame.empty and not use_cache and settings.token_options():
    st.info("Click Refresh from HubSpot to load data for this period.")

if frame.empty:
    st.info("No cached HubSpot email data yet. Use the refresh button after adding a token.")
    st.stop()

frame = frame.copy()
frame["send_date"] = pd.to_datetime(frame["send_date"], errors="coerce")
filtered = frame[
    (frame["send_date"].dt.date >= start_date)
    & (frame["send_date"].dt.date <= end_date)
    & (frame["email_type"].isin(selected_types))
].copy()

summary = summarize_metrics(filtered)

metric_cols = st.columns(5)
metric_cols[0].metric("Delivered", f"{summary['delivered']:,}")
metric_cols[1].metric("Opens", f"{summary['opens']:,}")
metric_cols[2].metric("Open Rate", f"{summary['open_rate']:.2%}")
metric_cols[3].metric("CTR", f"{summary['ctr']:.2%}")
metric_cols[4].metric("Emails", f"{summary['emails']:,}")

tab_overview, tab_trends, tab_detail = st.tabs(["Overview", "Trends", "Email Detail"])

with tab_overview:
    by_type = (
        filtered.groupby("email_type", dropna=False)[["delivered", "opens", "clicks"]]
        .sum()
        .reset_index()
    )
    by_type = add_derived_metrics(by_type)

    left, right = st.columns([1, 1])
    with left:
        st.subheader("Performance by Type")
        st.bar_chart(by_type.set_index("email_type")[["delivered", "opens", "clicks"]])
    with right:
        st.subheader("CTR by Type")
        st.bar_chart(by_type.set_index("email_type")[["ctr"]])

with tab_trends:
    trend = (
        filtered.dropna(subset=["send_date"])
        .assign(day=lambda data: data["send_date"].dt.date)
        .groupby("day")[["delivered", "opens", "clicks"]]
        .sum()
        .reset_index()
    )
    st.subheader("Daily Trend")
    st.line_chart(trend.set_index("day")[["delivered", "opens", "clicks"]])

with tab_detail:
    st.subheader("Email Detail")
    display_columns = [
        "send_date",
        "email_type",
        "email_name",
        "subject",
        "delivered",
        "opens",
        "clicks",
        "ctr",
        "open_rate",
        "web_version_url",
    ]
    st.dataframe(
        filtered[display_columns].sort_values("send_date", ascending=False),
        use_container_width=True,
        hide_index=True,
    )
