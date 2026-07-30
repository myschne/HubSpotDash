from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import date, timedelta

import altair as alt
import pandas as pd
import streamlit as st

from src.cache_store import (
    CacheStatus,
    load_cached_emails,
    load_cached_link_clicks,
    merge_cached_emails,
    merge_cached_link_clicks,
    save_cached_emails,
    save_cached_link_clicks,
)
from src.config import HubSpotSettings, load_settings
from src.email_content import canonical_url, link_metadata
from src.email_classifier import EMAIL_TYPES, classify_email
from src.hubspot_client import HubSpotClient, HubSpotClientError
from src.keywords import (
    click_distribution_histogram,
    is_advanced_manufacturing_link,
    keyword_article_distribution,
    keyword_clicks,
    preview_keyword_open_rates,
)
from src.link_names import article_or_site_name
from src.metrics import add_derived_metrics, summarize_metrics


REFRESH_MODES = [
    "Incremental refresh",
    "Full refresh",
    "Fast summary only",
    "Clicked links only",
]


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
def cached_frame(cache_buster: int) -> tuple[pd.DataFrame, pd.DataFrame, CacheStatus]:
    return (
        load_cached_emails(),
        load_cached_link_clicks(),
        CacheStatus.from_cache_buster(cache_buster),
    )


def fetch_live_data(
    settings: HubSpotSettings,
    start_date: date,
    end_date: date,
    selected_email_types: list[str],
    refresh_mode: str,
    cached_emails: pd.DataFrame,
    cached_links: pd.DataFrame,
    progress_bar=None,
    status_text=None,
) -> tuple[pd.DataFrame, pd.DataFrame, str, list[str]]:
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

    cached_email_by_id = cached_rows_by_id(cached_emails, "email_id")
    cached_links_by_email_id = grouped_cached_rows(cached_links, "email_id")
    rows = cached_emails.to_dict(orient="records") if not cached_emails.empty else []
    link_rows = cached_links.to_dict(orient="records") if not cached_links.empty else []
    new_rows = []
    new_link_rows = []

    candidate_emails = []
    for email in emails:
        email_date = client.email_date(email)
        email_type = classify_email(email)
        if email_date and not (start_date <= email_date <= end_date):
            continue
        if email_type not in selected_email_types:
            continue
        candidate_emails.append(email)

    total_emails = len(candidate_emails)
    if status_text is not None:
        status_text.write(f"Found {total_emails:,} email(s) to inspect.")

    tasks = []
    reused_count = 0
    with ThreadPoolExecutor(max_workers=4) as executor:
        for email in candidate_emails:
            email_id = str(email.get("id") or email.get("emailId") or "")
            cached_email = cached_email_by_id.get(email_id)
            cached_email_links = cached_links_by_email_id.get(email_id, [])
            cached_links_have_positions = bool(cached_email_links) and all(
                str(row.get("position", "")).strip()
                for row in cached_email_links
            )
            cached_links_have_metadata = bool(cached_email_links) and all(
                (
                    not is_advanced_manufacturing_link(str(row.get("link", "")))
                    or str(row.get("title", "") or row.get("blurb", "")).strip()
                )
                for row in cached_email_links
            )
            can_reuse_summary = refresh_mode in {"Incremental refresh", "Clicked links only"} and cached_email
            can_reuse_links = (
                refresh_mode == "Incremental refresh"
                and cached_links_have_positions
                and cached_links_have_metadata
            )

            if can_reuse_summary and can_reuse_links:
                reused_count += 1
                continue

            tasks.append(
                executor.submit(
                    build_email_records,
                    client,
                    email,
                    start_date,
                    end_date,
                    refresh_mode,
                    cached_email,
                    cached_email_links,
                )
            )

        completed = 0
        for future in as_completed(tasks):
            completed += 1
            email_row, email_link_rows = future.result()
            if email_row:
                new_rows.append(email_row)
            new_link_rows.extend(email_link_rows)

            processed = reused_count + completed
            if status_text is not None:
                name = email_row.get("email_name", "cached email") if email_row else "email"
                status_text.write(f"Processed {processed:,} of {total_emails:,}: {name}")
            if progress_bar is not None and total_emails:
                progress_bar.progress(processed / total_emails)

    if new_rows:
        rows = merge_cached_emails(pd.DataFrame(new_rows), pd.DataFrame(rows)).to_dict(orient="records")
    if new_link_rows:
        link_rows = merge_cached_link_clicks(
            pd.DataFrame(new_link_rows),
            pd.DataFrame(link_rows),
        ).to_dict(orient="records")

    frame = add_derived_metrics(pd.DataFrame(rows))
    link_frame = pd.DataFrame(link_rows)
    if not link_frame.empty and "link" in link_frame.columns:
        link_frame["article_or_site"] = link_frame["link"].map(article_or_site_name)
    save_cached_emails(frame)
    save_cached_link_clicks(link_frame)
    warnings = sorted(set(client.event_warnings + client.detail_warnings))
    return frame, link_frame, token_label, warnings


def build_email_records(
    client: HubSpotClient,
    email: dict,
    start_date: date,
    end_date: date,
    refresh_mode: str,
    cached_email: dict | None,
    cached_email_links: list[dict],
) -> tuple[dict, list[dict]]:
    email_id = str(email.get("id") or email.get("emailId") or "")
    fetch_summary_events = refresh_mode in {"Incremental refresh", "Full refresh"}
    fetch_links = refresh_mode in {"Incremental refresh", "Full refresh", "Clicked links only"}

    detail = client.email_detail(str(email.get("id")))
    merged = {**email, **detail}
    metadata_by_link = link_metadata(merged)

    if refresh_mode == "Clicked links only" and cached_email:
        summary_row = cached_email
    else:
        email_name = client.email_name(merged)
        email_date = client.email_date(merged)
        if email_date and not (start_date <= email_date <= end_date):
            return {}, []

        event_opens = client.email_event_count(merged, "OPEN") if fetch_summary_events else 0
        delivered = client.metric_value(
            merged,
            ["delivered", "deliveries", "deliveredCount", "successfulDeliveries", "sent"],
        )
        opens = event_opens or client.metric_value(
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
        clicks = client.metric_value(
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

        email_type = classify_email(merged)
        send_date_text = email_date.isoformat() if email_date else ""
        subject = str(client.first_value(merged, ["subject", "emailSubject"]) or "")
        preview_text = str(
            client.first_value(
                merged,
                ["previewText", "preview_text", "preheader", "preheaderText"],
            )
            or ""
        )
        summary_row = {
            "email_id": email_id,
            "email_name": email_name,
            "subject": subject,
            "preview_text": preview_text,
            "email_type": email_type,
            "send_date": send_date_text,
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

    if not fetch_links:
        return summary_row, cached_email_links

    email_name = client.email_name(merged)
    email_date = client.email_date(merged)
    email_type = classify_email(merged)
    send_date_text = email_date.isoformat() if email_date else ""
    link_click_totals = client.email_link_click_totals(merged)
    link_rows = []
    for item in link_click_totals:
        link = str(item["link"])
        link_key = canonical_url(link)
        metadata = metadata_by_link.get(link_key, {})
        title = str(metadata.get("title", "") or article_or_site_name(link))
        blurb = str(metadata.get("blurb", "") or "")
        link_rows.append(
            {
                "send_date": send_date_text,
                "email_type": email_type,
                "email_id": email_id,
                "email_name": email_name,
                "article_or_site": article_or_site_name(link),
                "title": title,
                "blurb": blurb,
                "is_advanced_manufacturing": is_advanced_manufacturing_link(link),
                "position": metadata.get("position", ""),
                "link": link,
                "clicks": int(item["clicks"]),
            }
        )

    if link_click_totals and refresh_mode != "Clicked links only":
        summary_row = {**summary_row, "clicks": sum(int(item["clicks"]) for item in link_click_totals)}
    return summary_row, link_rows


def cached_rows_by_id(frame: pd.DataFrame, id_column: str) -> dict[str, dict]:
    if frame.empty or id_column not in frame.columns:
        return {}
    return {
        str(row.get(id_column)): row
        for row in frame.to_dict(orient="records")
        if str(row.get(id_column, "")).strip()
    }


def grouped_cached_rows(frame: pd.DataFrame, id_column: str) -> dict[str, list[dict]]:
    if frame.empty or id_column not in frame.columns:
        return {}
    grouped: dict[str, list[dict]] = {}
    for row in frame.to_dict(orient="records"):
        row_id = str(row.get(id_column, "")).strip()
        if row_id:
            grouped.setdefault(row_id, []).append(row)
    return grouped


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

    refresh_mode = st.selectbox(
        "Refresh mode",
        REFRESH_MODES,
        index=0,
        help=(
            "Incremental reuses cached email/link rows. Full recalculates the selected period. "
            "Fast summary skips event/link calls. Clicked links only preserves cached KPI rows."
        ),
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
frame, link_frame, cache_status = cached_frame(cache_buster)

if refresh:
    if not settings.token_options():
        st.error("HubSpot token is missing. Fill in .streamlit/secrets.toml first.")
    else:
        with st.spinner("Fetching HubSpot email data..."):
            try:
                refresh_progress = st.progress(0)
                refresh_status = st.empty()
                frame, link_frame, token_label, event_warnings = fetch_live_data(
                    settings,
                    start_date,
                    end_date,
                    selected_types,
                    refresh_mode,
                    frame,
                    link_frame,
                    progress_bar=refresh_progress,
                    status_text=refresh_status,
                )
                refresh_progress.progress(1.0)
                refresh_status.write("Refresh complete.")
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
if "preview_text" not in frame.columns:
    frame["preview_text"] = ""
frame["send_date"] = pd.to_datetime(frame["send_date"], errors="coerce")
filtered = frame[
    (frame["send_date"].dt.date >= start_date)
    & (frame["send_date"].dt.date <= end_date)
    & (frame["email_type"].isin(selected_types))
].copy()

link_frame = link_frame.copy()
if not link_frame.empty:
    if "link" in link_frame.columns:
        link_frame["article_or_site"] = link_frame["link"].map(article_or_site_name)
        link_frame["is_advanced_manufacturing"] = link_frame["link"].map(
            is_advanced_manufacturing_link
        )
    if "position" not in link_frame.columns:
        link_frame["position"] = ""
    if "title" not in link_frame.columns:
        link_frame["title"] = link_frame.get("article_or_site", "")
    if "blurb" not in link_frame.columns:
        link_frame["blurb"] = ""
    link_frame["send_date"] = pd.to_datetime(link_frame["send_date"], errors="coerce")
    filtered_links = link_frame[
        (link_frame["send_date"].dt.date >= start_date)
        & (link_frame["send_date"].dt.date <= end_date)
        & (link_frame["email_type"].isin(selected_types))
    ].copy()
else:
    filtered_links = pd.DataFrame()

summary = summarize_metrics(filtered)

metric_cols = st.columns(5)
metric_cols[0].metric("Delivered", f"{summary['delivered']:,}")
metric_cols[1].metric("Opens", f"{summary['opens']:,}")
metric_cols[2].metric("Open Rate", f"{summary['open_rate']:.2%}")
metric_cols[3].metric("CTR", f"{summary['ctr']:.2%}")
metric_cols[4].metric("Emails", f"{summary['emails']:,}")

tab_overview, tab_trends, tab_links, tab_keywords, tab_detail = st.tabs(
    ["Overview", "Trends", "Clicked Links", "Keywords", "Email Detail"]
)

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

with tab_links:
    st.subheader("Top Clicked Links")
    if filtered_links.empty:
        st.info("No clicked-link data is cached yet. Refresh from HubSpot to collect link clicks.")
    else:
        link_summary = (
            filtered_links.groupby(
                ["article_or_site", "title", "blurb", "position", "link"],
                dropna=False,
            )["clicks"]
            .sum()
            .reset_index()
            .sort_values("clicks", ascending=False)
        )
        link_summary["position"] = pd.to_numeric(
            link_summary["position"],
            errors="coerce",
        )
        positioned = link_summary.dropna(subset=["position"]).copy()
        if not positioned.empty:
            positioned["position"] = positioned["position"].astype(int)
            position_summary = (
                positioned.groupby("position")["clicks"]
                .sum()
                .reset_index()
                .sort_values("position")
            )
            st.subheader("Clicks by Email Position")
            st.bar_chart(position_summary.set_index("position")[["clicks"]])

        st.dataframe(
            link_summary.rename(
                columns={
                    "article_or_site": "Article / Site",
                    "title": "Title",
                    "blurb": "Blurb",
                    "position": "Position",
                    "link": "Link",
                    "clicks": "Total Clicks",
                }
            ),
            use_container_width=True,
            hide_index=True,
            column_config={
                "Link": st.column_config.LinkColumn("Link"),
                "Position": st.column_config.NumberColumn("Position", format="%d"),
                "Total Clicks": st.column_config.NumberColumn("Total Clicks", format="%d"),
            },
        )

with tab_keywords:
    st.subheader("Advanced Manufacturing Keywords by Clicks")
    if filtered_links.empty:
        st.info("No clicked-link data is cached yet. Refresh from HubSpot to collect keyword data.")
    else:
        keyword_links = filtered_links.copy()
        if (
            "email_id" in keyword_links.columns
            and "delivered" not in keyword_links.columns
            and "email_id" in filtered.columns
            and "delivered" in filtered.columns
        ):
            keyword_links = keyword_links.merge(
                filtered[["email_id", "delivered"]].drop_duplicates("email_id"),
                on="email_id",
                how="left",
            )
        keyword_summary = keyword_clicks(keyword_links)
        if keyword_summary.empty:
            st.info("No Advanced Manufacturing keyword data is available for the selected period.")
        else:
            keyword_chart_left, keyword_chart_right = st.columns(2)
            with keyword_chart_left:
                st.subheader("Keyword Clicks")
                clicks_chart = (
                    alt.Chart(keyword_summary)
                    .mark_bar()
                    .encode(
                        x=alt.X("keyword:N", sort="-y", title="Keyword"),
                        y=alt.Y("clicks:Q", title="Total Clicks"),
                        tooltip=[
                            alt.Tooltip("keyword:N", title="Keyword"),
                            alt.Tooltip("clicks:Q", title="Total Clicks", format=",d"),
                            alt.Tooltip("links:Q", title="Linked Articles", format=",d"),
                        ],
                    )
                )
                st.altair_chart(clicks_chart, use_container_width=True)
            with keyword_chart_right:
                st.subheader("Keyword CTR")
                ctr_chart = (
                    alt.Chart(keyword_summary)
                    .mark_bar()
                    .encode(
                        x=alt.X("keyword:N", sort="-y", title="Keyword"),
                        y=alt.Y("ctr:Q", axis=alt.Axis(format=".2%"), title="CTR"),
                        tooltip=[
                            alt.Tooltip("keyword:N", title="Keyword"),
                            alt.Tooltip("ctr:Q", title="CTR", format=".2%"),
                            alt.Tooltip("clicks:Q", title="Total Clicks", format=",d"),
                            alt.Tooltip("delivered:Q", title="Delivered", format=",d"),
                        ],
                    )
                )
                st.altair_chart(ctr_chart, use_container_width=True)
            keyword_display = keyword_summary.copy()
            keyword_display["ctr"] = keyword_display["ctr"] * 100
            keyword_display = keyword_display.rename(
                columns={
                    "keyword": "Keyword",
                    "clicks": "Total Clicks",
                    "average_clicks": "Average Clicks",
                    "median_clicks": "Median Clicks",
                    "links": "Linked Articles",
                    "delivered": "Delivered",
                    "ctr": "CTR",
                }
            )
            keyword_event = st.dataframe(
                keyword_display,
                use_container_width=True,
                hide_index=True,
                key="advanced_manufacturing_keyword_table",
                on_select="rerun",
                selection_mode="single-row",
                column_config={
                    "Total Clicks": st.column_config.NumberColumn("Total Clicks", format="%d"),
                    "Average Clicks": st.column_config.NumberColumn("Average Clicks", format="%.1f"),
                    "Median Clicks": st.column_config.NumberColumn("Median Clicks", format="%.1f"),
                    "Linked Articles": st.column_config.NumberColumn("Linked Articles", format="%d"),
                    "Delivered": st.column_config.NumberColumn("Delivered", format="%d"),
                    "CTR": st.column_config.NumberColumn("CTR", format="%.2f%%"),
                },
            )
            selected_keyword = ""
            selection = getattr(keyword_event, "selection", None)
            if selection is None and isinstance(keyword_event, dict):
                selection = keyword_event.get("selection")
            selected_rows = getattr(selection, "rows", [])
            if not selected_rows and isinstance(selection, dict):
                selected_rows = selection.get("rows", [])
            if selected_rows:
                selected_keyword = str(keyword_summary.iloc[selected_rows[0]]["keyword"])

            keyword_options = keyword_summary["keyword"].tolist()
            keyword_index = 0
            if selected_keyword in keyword_options:
                keyword_index = keyword_options.index(selected_keyword)
                if st.session_state.get("keyword_distribution_select") != selected_keyword:
                    st.session_state["keyword_distribution_select"] = selected_keyword
            fallback_keyword = st.selectbox(
                "Keyword distribution",
                keyword_options,
                index=keyword_index,
                key="keyword_distribution_select",
            )
            selected_keyword = fallback_keyword
            distribution = keyword_article_distribution(keyword_links, selected_keyword)
            if not distribution.empty:
                st.subheader(f"Clicks Distribution for '{selected_keyword}'")
                histogram = click_distribution_histogram(distribution)
                chart = (
                    alt.Chart(histogram)
                    .mark_bar()
                    .encode(
                        x=alt.X("Click Range:N", sort=histogram["Click Range"].tolist()),
                        y=alt.Y("Articles:Q"),
                        tooltip=["Click Range", "Articles"],
                    )
                )
                st.altair_chart(chart, use_container_width=True)
                st.dataframe(
                    distribution.rename(
                        columns={
                            "article_or_site": "Article / Site",
                            "title": "Title",
                            "link": "Link",
                            "clicks": "Clicks",
                        }
                    ),
                    use_container_width=True,
                    hide_index=True,
                    column_config={
                        "Link": st.column_config.LinkColumn("Link"),
                        "Clicks": st.column_config.NumberColumn("Clicks", format="%d"),
                    },
                )

    st.subheader("Preview Text Keywords by Open Rate")
    preview_summary = preview_keyword_open_rates(filtered)
    if preview_summary.empty:
        st.info("No preview text keyword data is available for the selected period.")
    else:
        preview_chart = (
            alt.Chart(preview_summary)
            .mark_bar()
            .encode(
                x=alt.X("keyword:N", sort="-y", title="Keyword"),
                y=alt.Y("open_rate:Q", axis=alt.Axis(format=".2%"), title="Open Rate"),
                tooltip=[
                    alt.Tooltip("keyword:N", title="Keyword"),
                    alt.Tooltip("open_rate:Q", title="Open Rate", format=".2%"),
                    alt.Tooltip("emails:Q", title="Emails", format=",d"),
                    alt.Tooltip("delivered:Q", title="Delivered", format=",d"),
                    alt.Tooltip("opens:Q", title="Opens", format=",d"),
                ],
            )
        )
        st.altair_chart(preview_chart, use_container_width=True)
        preview_display = preview_summary.copy()
        preview_display["open_rate"] = preview_display["open_rate"] * 100
        st.dataframe(
            preview_display.rename(
                columns={
                    "keyword": "Keyword",
                    "open_rate": "Open Rate",
                    "emails": "Emails",
                    "delivered": "Delivered",
                    "opens": "Opens",
                }
            ),
            use_container_width=True,
            hide_index=True,
            column_config={
                "Open Rate": st.column_config.NumberColumn("Open Rate", format="%.2f%%"),
                "Emails": st.column_config.NumberColumn("Emails", format="%d"),
                "Delivered": st.column_config.NumberColumn("Delivered", format="%d"),
                "Opens": st.column_config.NumberColumn("Opens", format="%d"),
            },
        )

with tab_detail:
    st.subheader("Email Detail")
    display_columns = [
        "send_date",
        "email_type",
        "email_name",
        "subject",
        "preview_text",
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
