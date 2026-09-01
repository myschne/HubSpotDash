# HubSpot Email Performance Dashboard

## What this dashboard is for

This dashboard gives the marketing team one place to review HubSpot marketing email performance. It includes email volume, delivery and engagement metrics, performance trends, clicked links, keywords, and individual email details.

The dashboard reads information from HubSpot. It does **not** send emails, edit campaigns, or change HubSpot records.

## Quick start for dashboard users

1. Open the dashboard using the link provided by the dashboard owner.
2. Use the controls on the left to choose a reporting period and email type.
3. Leave **Use local cache when available** checked for normal use. This loads the most recently saved data quickly.
4. Select **Refresh from HubSpot** when you need the newest available results.
5. Review the dashboard tabs:
   - **Overview** summarizes performance by email type.
   - **Trends** shows daily, weekly, and monthly changes.
   - **Top Links** shows which links received the most clicks.
   - **Keywords** compares wording with engagement.
   - **Email Detail** shows results for individual emails.

Refreshing may take a few minutes. Do not repeatedly select the refresh button while it is working.

## How the data works

- **HubSpot is the source of truth.** A refresh requests current marketing email data from the company HubSpot account.
- **Google Sheets is the shared saved copy.** When configured, refreshed results are stored in a Google Sheet so the team can load them again without making a new HubSpot request.
- **CSV files are the backup copy.** Files in `data/cache/` are used if the Google Sheet is unavailable or has not been configured.
- The **Last refresh** message in the left panel indicates when the saved data was last updated.
- The dashboard groups emails using their names. Newsletters named like `MW m/d/yy` and advertising/custom emails named like `Company Custom Email` are recognized. Emails that do not match a known naming pattern may appear as **Unclassified**.

## Routine ownership

Assign these responsibilities before the current owner leaves:

| Responsibility | Recommended owner |
| --- | --- |
| Use the dashboard and check results | Marketing operations |
| Refresh the data | Marketing operations |
| Maintain the HubSpot service key and permissions | HubSpot super admin or user with Developer Tools access |
| Maintain dashboard hosting and secrets | IT or the person who administers the hosted dashboard |
| Maintain the Google Sheet and Google service account | IT or Google Workspace administrator |
| Investigate code errors or change dashboard behavior | Internal developer or outside technical support |

Record the current names and contact information here during handoff:

- Business owner: **[add name/contact]**
- HubSpot administrator: **[add name/contact]**
- Hosting/IT owner: **[add name/contact]**
- Technical support contact: **[add name/contact]**
- Dashboard link: **[add link]**
- Shared Google Sheet: **[add link]**

## Troubleshooting

### The dashboard opens but the information is old

Check the **Last refresh** message, select the required reporting period, and then select **Refresh from HubSpot**. If the refresh fails, keep **Use local cache when available** checked so the team can continue viewing the last successful copy.

### "HubSpot token is missing" appears

The dashboard host does not have the HubSpot credential it needs. Contact the hosting/IT owner. Do not paste the credential into the dashboard, README, email, or chat.

### HubSpot rejects the token or a permissions error appears

Ask the HubSpot administrator to confirm that the service key still exists and has the required marketing email permissions. If the key was rotated, the hosting/IT owner must replace the saved dashboard secret with the new value.

### The refresh works, but Google Sheets reports an error

The dashboard may still save a local CSV backup. Ask the Google Workspace or IT owner to confirm that:

- the Google Sheet still exists;
- the Google service account still has access to it; and
- the dashboard's saved Google credentials are current.

### An email appears under the wrong type or as "Unclassified"

First check the email name in HubSpot. Classification depends on naming conventions. If the name is correct but the category is still wrong, send the email name and expected category to technical support.

### Results do not exactly match another HubSpot screen

Confirm that both views use the same date range and email population. HubSpot metrics can also change after an email is sent as later opens and clicks are recorded. Refresh the dashboard before escalating the difference.

## Credentials and security

The dashboard relies on two machine credentials:

1. A **HubSpot service key or access token** used to read marketing email data.
2. A **Google service account** used to save and retrieve the shared cache.

These credentials must be stored only in the hosting platform's secret settings or in the local `.streamlit/secrets.toml` file. Never place their values in this README, source code, tickets, email, or chat.

The application currently expects the HubSpot credential under the setting name `HUBSPOT_PRIVATE_APP_TOKEN`. That setting name is retained for compatibility even when the credential supplied is a newer HubSpot service key.

A HubSpot service key is account-level rather than tied to the employee who created it, so disabling that employee's individual HubSpot user should not by itself stop the dashboard. A HubSpot administrator should nevertheless confirm access, document the key, and know how to rotate it. Service keys are currently a HubSpot public-beta feature and should be reviewed periodically.

## Administrator handoff checklist

Before the current owner leaves, confirm that:

- [ ] The dashboard URL has been added above and shared with the team.
- [ ] A business owner, HubSpot administrator, hosting owner, and technical support contact have been named.
- [ ] At least one remaining HubSpot administrator can view and manage the service key.
- [ ] The HubSpot key has the permissions required to read marketing email data.
- [ ] The hosting owner can access the dashboard's secret settings and deployment controls.
- [ ] The shared Google Sheet URL has been added above and ownership is not dependent on the departing employee.
- [ ] The Google service account has access to the shared Google Sheet.
- [ ] The new team has successfully opened, filtered, and refreshed the dashboard.
- [ ] Credentials have been transferred through an approved password manager or secret-management process, not through email or chat.
- [ ] A test refresh succeeds after all ownership changes are complete.

## Technical setup and recovery

This section is for IT or technical support. Day-to-day dashboard users do not need it.

### Required software

- Python
- The packages listed in `requirements.txt`

Install the packages from PowerShell:

```powershell
pip install -r requirements.txt
```

Start the dashboard locally:

```powershell
streamlit run app.py
```

### Required settings

For local use, copy `.streamlit/secrets.toml.example` to `.streamlit/secrets.toml` and provide the real values. For a hosted Streamlit deployment, add the same settings to the hosting platform's secret-management area.

Required HubSpot setting:

```toml
HUBSPOT_PRIVATE_APP_TOKEN = "stored-secret-value"
```

An optional fallback credential can be supplied as `HUBSPOT_SECONDARY_PRIVATE_APP_TOKEN`.

Google Sheets cache settings:

```toml
GOOGLE_SHEETS_CACHE_ENABLED = "true"
GOOGLE_SHEETS_SPREADSHEET_ID = "google-sheet-id"
GOOGLE_SHEETS_EMAILS_WORKSHEET = "hubspot_emails"
GOOGLE_SHEETS_LINKS_WORKSHEET = "hubspot_link_clicks"
```

For local use, `GOOGLE_SERVICE_ACCOUNT_FILE` can point to the service-account JSON file. For hosted use, store the JSON fields in `GOOGLE_SERVICE_ACCOUNT_JSON` as shown in `.streamlit/secrets.toml.example`.

After changing a credential, restart or redeploy the dashboard and perform a test refresh.

## Important files

| File or folder | Purpose |
| --- | --- |
| `app.py` | Dashboard screens and reporting logic |
| `src/` | HubSpot connection, classification, calculations, and cache logic |
| `.streamlit/secrets.toml.example` | Example setting names; contains placeholders only |
| `.streamlit/secrets.toml` | Local credentials; private and excluded from Git |
| `data/cache/` | Local backup of the last refreshed email and link data |
| `requirements.txt` | Software packages required to run the dashboard |

Do not manually edit the cache files unless technical support specifically directs you to do so.
