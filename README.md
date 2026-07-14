# HubSpot Email Dashboard

Streamlit dashboard scaffold for HubSpot marketing email performance across:

- Newsletters named like `MW m/d/yy`
- Advertising/custom emails named like `Company Custom Email`
- Digital deployment emails, currently scaffolded with a placeholder classifier

## Setup

1. Create `.streamlit/secrets.toml` from `.streamlit/secrets.toml.example`.
2. Fill in `HUBSPOT_PRIVATE_APP_TOKEN`.
3. Optionally fill in `HUBSPOT_SECONDARY_PRIVATE_APP_TOKEN` for future endpoints that need the second private app.
4. Install dependencies:

```powershell
pip install -r requirements.txt
```

5. Run locally:

```powershell
streamlit run app.py
```

## Notes

- The app uses a manual **Refresh from HubSpot** button.
- Refreshed data is cached locally at `data/cache/hubspot_emails.csv`.
- Streamlit Community Cloud should use the same secret names in app settings.
- Digital deployment matching is intentionally conservative until the naming/source rule is confirmed.
