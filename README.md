# HubSpot Email Dashboard

Streamlit dashboard scaffold for HubSpot marketing email performance across:

- Newsletters named like `MW m/d/yy`
- Advertising/custom emails named like `Company Custom Email`
- Digital deployment emails, currently scaffolded with a placeholder classifier

## Setup

1. Create `.streamlit/secrets.toml` from `.streamlit/secrets.toml.example`.
2. Fill in `HUBSPOT_PRIVATE_APP_TOKEN`.
3. Optionally fill in `HUBSPOT_SECONDARY_PRIVATE_APP_TOKEN` for future endpoints that need the second private app.
4. To use Google Sheets as the primary cache, create a Google Sheet and share it with the service account email from `stable-hologram-497015-i9-45282bfa717e.json`.
5. Fill in these cache secrets:

```toml
GOOGLE_SHEETS_CACHE_ENABLED = "true"
GOOGLE_SHEETS_SPREADSHEET_ID = "paste-google-sheet-id-here"
GOOGLE_SHEETS_EMAILS_WORKSHEET = "hubspot_emails"
GOOGLE_SHEETS_LINKS_WORKSHEET = "hubspot_link_clicks"
GOOGLE_SERVICE_ACCOUNT_FILE = "stable-hologram-497015-i9-45282bfa717e.json"
```

For Streamlit Cloud, paste the full service account JSON into `GOOGLE_SERVICE_ACCOUNT_JSON` instead of relying on the local JSON file.

6. Install dependencies:

```powershell
pip install -r requirements.txt
```

7. Run locally:

```powershell
streamlit run app.py
```

## Notes

- The app uses a manual **Refresh from HubSpot** button.
- When Google Sheets cache is configured, refreshed data is saved to Google Sheets and mirrored to local CSV.
- CSV files in `data/cache/` are used as a fallback when Google Sheets cache is not configured or unavailable.
- Streamlit Community Cloud should use the same secret names in app settings.
- Digital deployment matching is intentionally conservative until the naming/source rule is confirmed.
