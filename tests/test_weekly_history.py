from __future__ import annotations

import csv
import tempfile
import unittest
from datetime import date
from pathlib import Path

from weekly_history import (
    all_zero_inventory,
    process_weekly_history,
    rebuild_history_outputs,
    upsert_status_row,
)

PRODUCT_COLUMNS = ["product_id", "product_name", "price", "inventory", "category_name"]


class WeeklyHistoryTests(unittest.TestCase):
    def test_monday_valid_inventory_creates_snapshot_and_status(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            output_dir = Path(tmp) / "output"
            write_products_csv(
                output_dir / "products.csv",
                [
                    ["A1", "Alpha", "10.0", "3", "quartz"],
                    ["B2", "Beta", "20.0", "0", "granite"],
                ],
            )

            process_weekly_history(output_dir, date(2026, 4, 13))

            snapshot = output_dir / "archive" / "products_2026-04-13.csv"
            self.assertTrue(snapshot.exists())
            self.assertFalse((output_dir / "state" / "pending_weekly_snapshot.json").exists())

            status_rows = read_csv_rows(output_dir / "weekly_snapshot_status.csv")
            self.assertEqual(
                status_rows,
                [
                    {
                        "week_date": "2026-04-13",
                        "source_date": "2026-04-13",
                        "status": "captured",
                        "fallback_used": "false",
                        "row_count": "2",
                    }
                ],
            )

            long_rows = read_csv_rows(output_dir / "weekly_inventory_long.csv")
            self.assertEqual(len(long_rows), 2)
            self.assertEqual(long_rows[0]["week_date"], "2026-04-13")
            self.assertEqual(long_rows[0]["source_date"], "2026-04-13")

            wide_rows = read_csv_rows(output_dir / "weekly_inventory_wide.csv")
            self.assertEqual(len(wide_rows), 2)
            self.assertEqual(wide_rows[0]["2026-04-13"], "3")

    def test_monday_all_zero_creates_pending_state_without_snapshot(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            output_dir = Path(tmp) / "output"
            write_products_csv(
                output_dir / "products.csv",
                [
                    ["A1", "Alpha", "10.0", "0", "quartz"],
                    ["B2", "Beta", "20.0", "0.0", "granite"],
                ],
            )

            process_weekly_history(output_dir, date(2026, 4, 13))

            self.assertFalse((output_dir / "archive" / "products_2026-04-13.csv").exists())
            self.assertTrue((output_dir / "state" / "pending_weekly_snapshot.json").exists())
            self.assertEqual(read_csv_rows(output_dir / "weekly_snapshot_status.csv"), [])

    def test_tuesday_uses_valid_fallback_data_for_monday_week(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            output_dir = Path(tmp) / "output"
            write_products_csv(
                output_dir / "products.csv",
                [["A1", "Alpha", "10.0", "0", "quartz"]],
            )
            process_weekly_history(output_dir, date(2026, 4, 13))

            write_products_csv(
                output_dir / "products.csv",
                [["A1", "Alpha", "10.0", "9", "quartz"]],
            )
            process_weekly_history(output_dir, date(2026, 4, 14))

            snapshot_rows = read_csv_rows(output_dir / "archive" / "products_2026-04-13.csv")
            self.assertEqual(snapshot_rows[0]["inventory"], "9")
            self.assertFalse((output_dir / "state" / "pending_weekly_snapshot.json").exists())
            self.assertEqual(
                read_csv_rows(output_dir / "weekly_snapshot_status.csv"),
                [
                    {
                        "week_date": "2026-04-13",
                        "source_date": "2026-04-14",
                        "status": "captured_from_tuesday",
                        "fallback_used": "true",
                        "row_count": "1",
                    }
                ],
            )

    def test_tuesday_replaces_existing_bad_monday_snapshot_without_pending_state(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            output_dir = Path(tmp) / "output"
            archive_dir = output_dir / "archive"
            archive_dir.mkdir(parents=True)

            write_products_csv(
                archive_dir / "products_2026-04-13.csv",
                [["A1", "Alpha", "10.0", "0", "quartz"]],
            )
            write_products_csv(
                output_dir / "products.csv",
                [["A1", "Alpha", "10.0", "9", "quartz"]],
            )

            process_weekly_history(output_dir, date(2026, 4, 14))

            snapshot_rows = read_csv_rows(archive_dir / "products_2026-04-13.csv")
            self.assertEqual(snapshot_rows[0]["inventory"], "9")
            self.assertEqual(
                read_csv_rows(output_dir / "weekly_snapshot_status.csv"),
                [
                    {
                        "week_date": "2026-04-13",
                        "source_date": "2026-04-14",
                        "status": "captured_from_tuesday",
                        "fallback_used": "true",
                        "row_count": "1",
                    }
                ],
            )

    def test_tuesday_all_zero_after_bad_monday_marks_week_skipped(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            output_dir = Path(tmp) / "output"
            write_products_csv(
                output_dir / "products.csv",
                [["A1", "Alpha", "10.0", "0", "quartz"]],
            )
            process_weekly_history(output_dir, date(2026, 4, 13))
            process_weekly_history(output_dir, date(2026, 4, 14))

            self.assertFalse((output_dir / "archive" / "products_2026-04-13.csv").exists())
            self.assertFalse((output_dir / "state" / "pending_weekly_snapshot.json").exists())
            self.assertEqual(
                read_csv_rows(output_dir / "weekly_snapshot_status.csv"),
                [
                    {
                        "week_date": "2026-04-13",
                        "source_date": "",
                        "status": "skipped_zero_on_monday_and_tuesday",
                        "fallback_used": "true",
                        "row_count": "1",
                    }
                ],
            )

    def test_tuesday_removes_existing_bad_monday_snapshot_when_tuesday_is_also_zero(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            output_dir = Path(tmp) / "output"
            archive_dir = output_dir / "archive"
            archive_dir.mkdir(parents=True)

            write_products_csv(
                archive_dir / "products_2026-04-13.csv",
                [["A1", "Alpha", "10.0", "0", "quartz"]],
            )
            write_products_csv(
                output_dir / "products.csv",
                [["A1", "Alpha", "10.0", "0", "quartz"]],
            )

            process_weekly_history(output_dir, date(2026, 4, 14))

            self.assertFalse((archive_dir / "products_2026-04-13.csv").exists())
            self.assertEqual(
                read_csv_rows(output_dir / "weekly_snapshot_status.csv"),
                [
                    {
                        "week_date": "2026-04-13",
                        "source_date": "",
                        "status": "skipped_zero_on_monday_and_tuesday",
                        "fallback_used": "true",
                        "row_count": "1",
                    }
                ],
            )

    def test_blank_inventory_does_not_count_as_all_zero(self) -> None:
        self.assertFalse(all_zero_inventory([{"inventory": "0"}, {"inventory": ""}]))

    def test_existing_monday_archives_backfill_status_rows(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            output_dir = Path(tmp) / "output"
            archive_dir = output_dir / "archive"
            archive_dir.mkdir(parents=True)

            write_products_csv(
                archive_dir / "products_2026-04-06.csv",
                [["A1", "Alpha", "10.0", "5", "quartz"]],
            )
            write_products_csv(
                output_dir / "products.csv",
                [["A1", "Alpha", "10.0", "2", "quartz"]],
            )

            process_weekly_history(output_dir, date(2026, 4, 15))

            self.assertEqual(
                read_csv_rows(output_dir / "weekly_snapshot_status.csv"),
                [
                    {
                        "week_date": "2026-04-06",
                        "source_date": "2026-04-06",
                        "status": "captured",
                        "fallback_used": "false",
                        "row_count": "1",
                    }
                ],
            )

    def test_rebuild_history_ignores_non_monday_snapshots_and_marks_missing_values_as_na(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            output_dir = Path(tmp) / "output"
            archive_dir = output_dir / "archive"
            archive_dir.mkdir(parents=True)

            write_products_csv(
                archive_dir / "products_2026-04-06.csv",
                [
                    ["A1", "Alpha", "10.0", "5", "quartz"],
                    ["B2", "Beta", "20.0", "7", "granite"],
                ],
            )
            write_products_csv(
                archive_dir / "products_2026-04-13.csv",
                [["A1", "Alpha", "10.0", "8", "quartz"]],
            )
            write_products_csv(
                archive_dir / "products_2026-04-10.csv",
                [["Z9", "Legacy", "10.0", "99", "marble"]],
            )

            status_rows: list[dict[str, str]] = []
            status_rows = upsert_status_row(
                status_rows,
                week_date=date(2026, 4, 6),
                source_date=date(2026, 4, 6),
                status="captured",
                fallback_used=False,
                row_count=2,
            )
            status_rows = upsert_status_row(
                status_rows,
                week_date=date(2026, 4, 13),
                source_date=date(2026, 4, 14),
                status="captured_from_tuesday",
                fallback_used=True,
                row_count=1,
            )

            rebuild_history_outputs(
                output_dir,
                status_rows,
                output_dir / "weekly_inventory_long.csv",
                output_dir / "weekly_inventory_wide.csv",
            )

            long_rows = read_csv_rows(output_dir / "weekly_inventory_long.csv")
            self.assertEqual(len(long_rows), 4)
            self.assertEqual({row["week_date"] for row in long_rows}, {"2026-04-06", "2026-04-13"})
            self.assertNotIn("2026-04-10", {row["week_date"] for row in long_rows})
            beta_latest_week = next(
                row
                for row in long_rows
                if row["product_id"] == "B2" and row["week_date"] == "2026-04-13"
            )
            self.assertEqual(beta_latest_week["inventory"], "N/A")

            wide_rows = read_csv_rows(output_dir / "weekly_inventory_wide.csv")
            beta_row = next(row for row in wide_rows if row["product_id"] == "B2")
            self.assertEqual(beta_row["2026-04-06"], "7")
            self.assertEqual(beta_row["2026-04-13"], "N/A")

    def test_year_rollover_moves_old_snapshots_into_yearly_archive(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            output_dir = Path(tmp) / "output"
            archive_dir = output_dir / "archive"
            archive_dir.mkdir(parents=True)

            write_products_csv(
                archive_dir / "products_2025-12-22.csv",
                [["A1", "Alpha", "10.0", "4", "quartz"]],
            )
            write_products_csv(
                archive_dir / "products_2025-12-29.csv",
                [["B2", "Beta", "20.0", "0", "granite"]],
            )
            write_products_csv(
                output_dir / "products.csv",
                [["A1", "Alpha", "10.0", "3", "quartz"]],
            )

            process_weekly_history(output_dir, date(2026, 1, 2))

            self.assertFalse((archive_dir / "products_2025-12-22.csv").exists())
            self.assertFalse((archive_dir / "products_2025-12-29.csv").exists())
            self.assertTrue((archive_dir / "yearly" / "2025" / "snapshots" / "products_2025-12-22.csv").exists())
            self.assertTrue((archive_dir / "yearly" / "2025" / "snapshots" / "products_2025-12-29.csv").exists())

            archived_status = read_csv_rows(archive_dir / "yearly" / "2025" / "weekly_snapshot_status.csv")
            self.assertEqual(
                archived_status,
                [
                    {
                        "week_date": "2025-12-22",
                        "source_date": "2025-12-22",
                        "status": "captured",
                        "fallback_used": "false",
                        "row_count": "1",
                    },
                    {
                        "week_date": "2025-12-29",
                        "source_date": "2025-12-29",
                        "status": "captured",
                        "fallback_used": "false",
                        "row_count": "1",
                    },
                ],
            )
            self.assertEqual(read_csv_rows(output_dir / "weekly_snapshot_status.csv"), [])


def write_products_csv(path: Path, rows: list[list[str]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.writer(handle)
        writer.writerow(PRODUCT_COLUMNS)
        writer.writerows(rows)


def read_csv_rows(path: Path) -> list[dict[str, str]]:
    with path.open("r", newline="", encoding="utf-8") as handle:
        reader = csv.DictReader(handle)
        return list(reader)


if __name__ == "__main__":
    unittest.main()
