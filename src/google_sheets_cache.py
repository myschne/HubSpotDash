from __future__ import annotations

import ast
import json
from pathlib import Path
from collections.abc import Mapping

import pandas as pd

from src.config import GoogleSheetsCacheSettings


class GoogleSheetsCacheError(RuntimeError):
    pass


def is_configured(settings: GoogleSheetsCacheSettings | None) -> bool:
    return bool(settings and settings.enabled and settings.spreadsheet_id)


def missing_config(settings: GoogleSheetsCacheSettings | None) -> list[str]:
    if not settings or not settings.enabled:
        return ["GOOGLE_SHEETS_CACHE_ENABLED"]
    missing = []
    if not settings.spreadsheet_id:
        missing.append("GOOGLE_SHEETS_SPREADSHEET_ID")
    if not settings.service_account_json and not settings.service_account_file:
        missing.append("GOOGLE_SERVICE_ACCOUNT_JSON or GOOGLE_SERVICE_ACCOUNT_FILE")
    return missing


def load_worksheet(
    settings: GoogleSheetsCacheSettings | None,
    worksheet_name: str,
) -> pd.DataFrame | None:
    if not is_configured(settings):
        return None

    worksheet = _worksheet(settings, worksheet_name, create=False)
    if worksheet is None:
        return None
    values = worksheet.get_all_values()
    if not values:
        return None

    headers = values[0]
    rows = values[1:]
    if not headers:
        return None
    return pd.DataFrame(rows, columns=headers).fillna("")


def save_worksheet(
    frame: pd.DataFrame,
    settings: GoogleSheetsCacheSettings | None,
    worksheet_name: str,
) -> None:
    if not is_configured(settings):
        return

    worksheet = _worksheet(settings, worksheet_name, create=True)
    safe_frame = frame.fillna("").copy()
    values = [safe_frame.columns.tolist()] + safe_frame.astype(str).values.tolist()
    worksheet.clear()
    if values:
        worksheet.update(values=values, range_name="A1")


def upsert_worksheet(
    frame: pd.DataFrame,
    settings: GoogleSheetsCacheSettings | None,
    worksheet_name: str,
    key_columns: list[str],
) -> None:
    if not is_configured(settings) or frame.empty:
        return
    if not key_columns:
        save_worksheet(frame, settings, worksheet_name)
        return

    worksheet = _worksheet(settings, worksheet_name, create=True)
    safe_frame = frame.fillna("").astype(str).copy()
    target_headers = safe_frame.columns.tolist()
    values = worksheet.get_all_values()

    if not values:
        worksheet.update(values=[target_headers] + safe_frame.values.tolist(), range_name="A1")
        return

    existing_headers = values[0]
    headers = existing_headers + [column for column in target_headers if column not in existing_headers]
    if headers != existing_headers:
        worksheet.update(values=[headers], range_name="A1")

    existing_rows = [_pad_row(row, len(headers)) for row in values[1:]]
    existing_by_key = {}
    for index, row in enumerate(existing_rows, start=2):
        key = _row_key(dict(zip(headers, row)), key_columns)
        if key:
            existing_by_key[key] = (index, row)

    updates = []
    appends = []
    for row in safe_frame.to_dict(orient="records"):
        key = _row_key(row, key_columns)
        if not key:
            continue
        row_values = [str(row.get(header, "")) for header in headers]
        existing = existing_by_key.get(key)
        if existing is None:
            appends.append(row_values)
            continue

        row_number, existing_values = existing
        if row_values != existing_values:
            updates.append(
                {
                    "range": f"A{row_number}:{_column_letter(len(headers))}{row_number}",
                    "values": [row_values],
                }
            )

    if updates:
        worksheet.batch_update(updates)
    if appends:
        worksheet.append_rows(appends, value_input_option="RAW")


def append_worksheet_row(
    row: dict,
    settings: GoogleSheetsCacheSettings | None,
    worksheet_name: str,
) -> None:
    if not is_configured(settings):
        return

    worksheet = _worksheet(settings, worksheet_name, create=True)
    values = worksheet.get_all_values()
    headers = list(row.keys())
    if not values:
        worksheet.update(values=[headers], range_name="A1")
    else:
        existing_headers = values[0]
        headers = existing_headers + [column for column in headers if column not in existing_headers]
        if headers != existing_headers:
            worksheet.update(values=[headers], range_name="A1")

    worksheet.append_rows([[str(row.get(header, "")) for header in headers]], value_input_option="RAW")


def _worksheet(settings: GoogleSheetsCacheSettings, worksheet_name: str, create: bool):
    spreadsheet = _client(settings).open_by_key(settings.spreadsheet_id)
    try:
        return spreadsheet.worksheet(worksheet_name)
    except Exception:
        if not create:
            return None
        return spreadsheet.add_worksheet(title=worksheet_name, rows=1, cols=1)


def _client(settings: GoogleSheetsCacheSettings):
    try:
        import gspread
    except ImportError as error:
        raise GoogleSheetsCacheError(
            "Google Sheets cache requires gspread. Run pip install -r requirements.txt."
        ) from error

    credentials = _credentials(settings)
    if credentials:
        return gspread.service_account_from_dict(credentials)
    if settings.service_account_file:
        return gspread.service_account(filename=str(_service_account_path(settings)))
    raise GoogleSheetsCacheError(
        "Google Sheets cache is enabled but no service account JSON or file path is configured."
    )


def _credentials(settings: GoogleSheetsCacheSettings) -> dict | None:
    if settings.service_account_json:
        if isinstance(settings.service_account_json, Mapping):
            return dict(settings.service_account_json)

        raw_json = str(settings.service_account_json).strip()
        try:
            return json.loads(raw_json)
        except json.JSONDecodeError:
            try:
                parsed = ast.literal_eval(raw_json)
            except (SyntaxError, ValueError) as error:
                raise GoogleSheetsCacheError(
                    "GOOGLE_SERVICE_ACCOUNT_JSON is not valid JSON. "
                    "Paste the full service account JSON as one TOML multiline string, "
                    "or use a [GOOGLE_SERVICE_ACCOUNT_JSON] secrets table."
                ) from error
            if isinstance(parsed, Mapping):
                return dict(parsed)
            raise GoogleSheetsCacheError(
                "GOOGLE_SERVICE_ACCOUNT_JSON parsed, but it is not a service account object."
            )

    if not settings.service_account_file:
        return None
    path = _service_account_path(settings)
    if not path.exists():
        return None
    return None


def _service_account_path(settings: GoogleSheetsCacheSettings) -> Path:
    path = Path(settings.service_account_file)
    if path.is_absolute():
        return path
    return Path(__file__).resolve().parents[1] / path


def _row_key(row: dict, key_columns: list[str]) -> tuple[str, ...]:
    values = tuple(str(row.get(column, "")).strip() for column in key_columns)
    if not all(values):
        return ()
    return values


def _pad_row(row: list[str], length: int) -> list[str]:
    return row + [""] * max(0, length - len(row))


def _column_letter(column_number: int) -> str:
    letters = ""
    while column_number:
        column_number, remainder = divmod(column_number - 1, 26)
        letters = chr(65 + remainder) + letters
    return letters
