from __future__ import annotations

import csv
import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from google_sheets_sync import (
    TAB_SPECS,
    build_add_sheet_requests,
    build_tab_specs,
    load_settings_from_env,
    sync_csv_outputs_to_sheet,
)


class GoogleSheetsSyncTests(unittest.TestCase):
    def test_build_tab_specs_maps_expected_csv_files(self) -> None:
        output_dir = Path("/tmp/output")
        self.assertEqual(
            build_tab_specs(output_dir),
            [(tab_name, output_dir / filename) for tab_name, filename in TAB_SPECS],
        )

    def test_build_add_sheet_requests_only_for_missing_tabs(self) -> None:
        requests = build_add_sheet_requests(
            {"Current Inventory", "Weekly History Long"},
            ["Current Inventory", "Weekly History Long", "Weekly History Wide", "Snapshot Status"],
        )
        self.assertEqual(
            requests,
            [
                {"addSheet": {"properties": {"title": "Weekly History Wide"}}},
                {"addSheet": {"properties": {"title": "Snapshot Status"}}},
            ],
        )

    def test_missing_env_settings_raise_clear_errors(self) -> None:
        with patch.dict(os.environ, {}, clear=True):
            with self.assertRaisesRegex(RuntimeError, "GOOGLE_SHEETS_SPREADSHEET_ID"):
                load_settings_from_env()

        with patch.dict(os.environ, {"GOOGLE_SHEETS_SPREADSHEET_ID": "sheet-123"}, clear=True):
            with self.assertRaisesRegex(RuntimeError, "GOOGLE_SERVICE_ACCOUNT_JSON"):
                load_settings_from_env()

    def test_sync_csv_outputs_creates_missing_tabs_and_overwrites_each_tab(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            output_dir = Path(tmp) / "output"
            for _, filename in TAB_SPECS:
                write_csv(output_dir / filename, [["col1", "col2"], ["a", "b"]])

            service = FakeSheetsService(existing_titles={"Current Inventory"})
            sync_csv_outputs_to_sheet(service, "sheet-123", output_dir)

            self.assertEqual(len(service.batch_updates), 1)
            self.assertEqual(
                service.batch_updates[0]["requests"],
                [
                    {"addSheet": {"properties": {"title": "Weekly History Long"}}},
                    {"addSheet": {"properties": {"title": "Weekly History Wide"}}},
                    {"addSheet": {"properties": {"title": "Snapshot Status"}}},
                ],
            )

            self.assertEqual(
                [item["range"] for item in service.clears],
                [
                    "'Current Inventory'",
                    "'Weekly History Long'",
                    "'Weekly History Wide'",
                    "'Snapshot Status'",
                ],
            )
            self.assertEqual(
                [item["range"] for item in service.updates],
                [
                    "'Current Inventory'!A1",
                    "'Weekly History Long'!A1",
                    "'Weekly History Wide'!A1",
                    "'Snapshot Status'!A1",
                ],
            )
            self.assertEqual(service.updates[0]["body"]["values"], [["col1", "col2"], ["a", "b"]])


class FakeSheetsService:
    def __init__(self, existing_titles: set[str]) -> None:
        self.existing_titles = existing_titles
        self.batch_updates: list[dict] = []
        self.clears: list[dict] = []
        self.updates: list[dict] = []
        self._spreadsheets = FakeSpreadsheetsApi(self)

    def spreadsheets(self) -> "FakeSpreadsheetsApi":
        return self._spreadsheets


class FakeSpreadsheetsApi:
    def __init__(self, parent: FakeSheetsService) -> None:
        self.parent = parent
        self._values = FakeValuesApi(parent)

    def get(self, spreadsheetId: str, fields: str) -> "FakeRequest":
        response = {
            "sheets": [{"properties": {"title": title}} for title in sorted(self.parent.existing_titles)]
        }
        return FakeRequest(response)

    def batchUpdate(self, spreadsheetId: str, body: dict) -> "FakeRequest":
        self.parent.batch_updates.append(body)
        return FakeRequest({})

    def values(self) -> "FakeValuesApi":
        return self._values


class FakeValuesApi:
    def __init__(self, parent: FakeSheetsService) -> None:
        self.parent = parent

    def clear(self, spreadsheetId: str, range: str, body: dict) -> "FakeRequest":
        self.parent.clears.append(
            {"spreadsheetId": spreadsheetId, "range": range, "body": body}
        )
        return FakeRequest({})

    def update(
        self,
        spreadsheetId: str,
        range: str,
        valueInputOption: str,
        body: dict,
    ) -> "FakeRequest":
        self.parent.updates.append(
            {
                "spreadsheetId": spreadsheetId,
                "range": range,
                "valueInputOption": valueInputOption,
                "body": body,
            }
        )
        return FakeRequest({})


class FakeRequest:
    def __init__(self, payload: dict) -> None:
        self.payload = payload

    def execute(self) -> dict:
        return self.payload


def write_csv(path: Path, rows: list[list[str]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.writer(handle)
        writer.writerows(rows)


if __name__ == "__main__":
    unittest.main()
