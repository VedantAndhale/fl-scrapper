from __future__ import annotations

import argparse
import csv
import json
import os
from pathlib import Path

from google.oauth2 import service_account
from googleapiclient.discovery import build

OUTPUT_DIR = Path("output")
SCOPES = ["https://www.googleapis.com/auth/spreadsheets"]
TAB_SPECS = (
    ("Current Inventory", "products.csv"),
    ("Weekly History Long", "weekly_inventory_long.csv"),
    ("Weekly History Wide", "weekly_inventory_wide.csv"),
    ("Snapshot Status", "weekly_snapshot_status.csv"),
)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Sync generated CSV outputs to Google Sheets.")
    parser.add_argument("--output-dir", default=str(OUTPUT_DIR), help="Directory containing generated CSV files")
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    output_dir = Path(args.output_dir)
    spreadsheet_id, service_account_json = load_settings_from_env()
    service = build_sheets_service(service_account_json)
    sync_csv_outputs_to_sheet(service, spreadsheet_id, output_dir)


def load_settings_from_env() -> tuple[str, str]:
    spreadsheet_id = os.environ.get("GOOGLE_SHEETS_SPREADSHEET_ID", "").strip()
    if not spreadsheet_id:
        raise RuntimeError("Missing GOOGLE_SHEETS_SPREADSHEET_ID environment variable.")

    service_account_json = os.environ.get("GOOGLE_SERVICE_ACCOUNT_JSON", "").strip()
    if not service_account_json:
        raise RuntimeError("Missing GOOGLE_SERVICE_ACCOUNT_JSON environment variable.")

    return spreadsheet_id, service_account_json


def build_sheets_service(service_account_json: str):
    credentials_info = json.loads(service_account_json)
    credentials = service_account.Credentials.from_service_account_info(credentials_info, scopes=SCOPES)
    return build("sheets", "v4", credentials=credentials, cache_discovery=False)


def sync_csv_outputs_to_sheet(service, spreadsheet_id: str, output_dir: Path) -> None:
    tab_specs = build_tab_specs(output_dir)
    ensure_sheet_tabs(service, spreadsheet_id, [tab_name for tab_name, _ in tab_specs])
    for tab_name, csv_path in tab_specs:
        values = load_csv_values(csv_path)
        clear_tab(service, spreadsheet_id, tab_name)
        update_tab(service, spreadsheet_id, tab_name, values)


def build_tab_specs(output_dir: Path) -> list[tuple[str, Path]]:
    return [(tab_name, output_dir / filename) for tab_name, filename in TAB_SPECS]


def load_csv_values(path: Path) -> list[list[str]]:
    if not path.exists():
        raise RuntimeError(f"Missing CSV for Google Sheets sync: {path}")

    with path.open("r", newline="", encoding="utf-8") as handle:
        reader = csv.reader(handle)
        rows = [list(row) for row in reader]

    if not rows:
        raise RuntimeError(f"CSV is empty and has no header row: {path}")
    return rows


def ensure_sheet_tabs(service, spreadsheet_id: str, required_titles: list[str]) -> None:
    existing_titles = get_existing_sheet_titles(service, spreadsheet_id)
    requests = build_add_sheet_requests(existing_titles, required_titles)
    if not requests:
        return

    service.spreadsheets().batchUpdate(
        spreadsheetId=spreadsheet_id,
        body={"requests": requests},
    ).execute()


def get_existing_sheet_titles(service, spreadsheet_id: str) -> set[str]:
    response = service.spreadsheets().get(
        spreadsheetId=spreadsheet_id,
        fields="sheets(properties(title))",
    ).execute()
    sheets = response.get("sheets", [])
    return {
        sheet.get("properties", {}).get("title", "")
        for sheet in sheets
        if sheet.get("properties", {}).get("title")
    }


def build_add_sheet_requests(existing_titles: set[str], required_titles: list[str]) -> list[dict]:
    requests: list[dict] = []
    for title in required_titles:
        if title in existing_titles:
            continue
        requests.append({"addSheet": {"properties": {"title": title}}})
    return requests


def clear_tab(service, spreadsheet_id: str, tab_name: str) -> None:
    service.spreadsheets().values().clear(
        spreadsheetId=spreadsheet_id,
        range=tab_range(tab_name),
        body={},
    ).execute()


def update_tab(service, spreadsheet_id: str, tab_name: str, values: list[list[str]]) -> None:
    service.spreadsheets().values().update(
        spreadsheetId=spreadsheet_id,
        range=f"{tab_range(tab_name)}!A1",
        valueInputOption="RAW",
        body={"majorDimension": "ROWS", "values": values},
    ).execute()


def tab_range(tab_name: str) -> str:
    escaped = tab_name.replace("'", "''")
    return f"'{escaped}'"


if __name__ == "__main__":
    main()
