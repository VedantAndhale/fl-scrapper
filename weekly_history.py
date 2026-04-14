from __future__ import annotations

import argparse
import csv
import json
from dataclasses import dataclass
from datetime import date, datetime, timedelta
from decimal import Decimal, InvalidOperation
from pathlib import Path
from zoneinfo import ZoneInfo

OUTPUT_DIR = Path("output")
DAILY_CSV_PATH = OUTPUT_DIR / "products.csv"
ARCHIVE_DIR = OUTPUT_DIR / "archive"
YEARLY_ARCHIVE_DIR_NAME = "yearly"
STATE_DIR = OUTPUT_DIR / "state"
PENDING_STATE_PATH = STATE_DIR / "pending_weekly_snapshot.json"
STATUS_CSV_PATH = OUTPUT_DIR / "weekly_snapshot_status.csv"
LONG_CSV_PATH = OUTPUT_DIR / "weekly_inventory_long.csv"
WIDE_CSV_PATH = OUTPUT_DIR / "weekly_inventory_wide.csv"

STATUS_COLUMNS = ["week_date", "source_date", "status", "fallback_used", "row_count"]
LONG_COLUMNS = ["week_date", "source_date", "product_id", "product_name", "category_name", "inventory"]
WIDE_PREFIX_COLUMNS = ["product_id", "product_name", "category_name"]
MISSING_INVENTORY_VALUE = "N/A"
IST = ZoneInfo("Asia/Kolkata")


@dataclass(frozen=True)
class CsvTable:
    fieldnames: list[str]
    rows: list[dict[str, str]]


@dataclass(frozen=True)
class PendingSnapshot:
    week_date: date
    created_on: date


@dataclass(frozen=True)
class SnapshotFile:
    week_date: date
    path: Path


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Build weekly inventory history outputs.")
    parser.add_argument("--output-dir", default=str(OUTPUT_DIR), help="Base output directory")
    parser.add_argument("--today", help="Override IST date in YYYY-MM-DD format")
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    output_dir = Path(args.output_dir)
    today = _parse_today(args.today) if args.today else _ist_today()
    process_weekly_history(output_dir=output_dir, today=today)


def process_weekly_history(output_dir: Path, today: date) -> None:
    daily_csv_path = output_dir / DAILY_CSV_PATH.name
    archive_dir = output_dir / ARCHIVE_DIR.name
    state_dir = output_dir / STATE_DIR.name
    pending_state_path = state_dir / PENDING_STATE_PATH.name
    status_csv_path = output_dir / STATUS_CSV_PATH.name
    long_csv_path = output_dir / LONG_CSV_PATH.name
    wide_csv_path = output_dir / WIDE_CSV_PATH.name

    state_dir.mkdir(parents=True, exist_ok=True)
    archive_dir.mkdir(parents=True, exist_ok=True)

    daily_table = read_csv_table(daily_csv_path)
    pending = load_pending_snapshot(pending_state_path)
    status_rows = load_status_rows(status_csv_path)
    status_rows = archive_completed_years(output_dir, status_rows, current_year=today.year)

    pending, status_rows = finalize_stale_pending_snapshot(
        today=today,
        pending=pending,
        pending_state_path=pending_state_path,
        status_rows=status_rows,
    )

    if daily_table.rows:
        pending, status_rows = maybe_capture_weekly_snapshot(
            output_dir=output_dir,
            today=today,
            daily_table=daily_table,
            pending=pending,
            status_rows=status_rows,
        )

    current_snapshots = [
        snapshot
        for snapshot in list_weekly_snapshot_files(archive_dir)
        if snapshot.week_date.year == today.year
    ]
    status_rows = filter_status_rows_for_year(status_rows, today.year)
    status_rows = backfill_status_rows_from_snapshots(current_snapshots, status_rows)
    write_status_rows(status_csv_path, status_rows)
    rebuild_history_outputs_from_snapshots(current_snapshots, status_rows, long_csv_path, wide_csv_path)


def maybe_capture_weekly_snapshot(
    output_dir: Path,
    today: date,
    daily_table: CsvTable,
    pending: PendingSnapshot | None,
    status_rows: list[dict[str, str]],
) -> tuple[PendingSnapshot | None, list[dict[str, str]]]:
    archive_dir = output_dir / ARCHIVE_DIR.name
    pending_state_path = output_dir / STATE_DIR.name / PENDING_STATE_PATH.name
    row_count = len(daily_table.rows)
    zero_inventory = all_zero_inventory(daily_table.rows)

    if today.weekday() == 0:
        week_date = today
        existing_snapshot_path = snapshot_path_for_week(archive_dir, week_date)
        if zero_inventory:
            existing_snapshot_path.unlink(missing_ok=True)
            save_pending_snapshot(
                pending_state_path,
                PendingSnapshot(week_date=week_date, created_on=today),
            )
            return PendingSnapshot(week_date=week_date, created_on=today), status_rows

        write_snapshot_csv(snapshot_path_for_week(archive_dir, week_date), daily_table)
        status_rows = upsert_status_row(
            status_rows,
            week_date=week_date,
            source_date=today,
            status="captured",
            fallback_used=False,
            row_count=row_count,
        )
        clear_pending_snapshot(pending_state_path)
        return None, status_rows

    if today.weekday() == 1 and pending and today == pending.week_date + timedelta(days=1):
        if zero_inventory:
            status_rows = upsert_status_row(
                status_rows,
                week_date=pending.week_date,
                source_date=None,
                status="skipped_zero_on_monday_and_tuesday",
                fallback_used=True,
                row_count=row_count,
            )
            clear_pending_snapshot(pending_state_path)
            return None, status_rows

        write_snapshot_csv(snapshot_path_for_week(archive_dir, pending.week_date), daily_table)
        status_rows = upsert_status_row(
            status_rows,
            week_date=pending.week_date,
            source_date=today,
            status="captured_from_tuesday",
            fallback_used=True,
            row_count=row_count,
        )
        clear_pending_snapshot(pending_state_path)
        return None, status_rows

    if today.weekday() == 1:
        monday_week_date = today - timedelta(days=1)
        monday_snapshot_path = snapshot_path_for_week(archive_dir, monday_week_date)
        if monday_snapshot_path.exists() and csv_path_has_all_zero_inventory(monday_snapshot_path):
            if zero_inventory:
                monday_snapshot_path.unlink(missing_ok=True)
                status_rows = upsert_status_row(
                    status_rows,
                    week_date=monday_week_date,
                    source_date=None,
                    status="skipped_zero_on_monday_and_tuesday",
                    fallback_used=True,
                    row_count=row_count,
                )
                return None, status_rows

            write_snapshot_csv(monday_snapshot_path, daily_table)
            status_rows = upsert_status_row(
                status_rows,
                week_date=monday_week_date,
                source_date=today,
                status="captured_from_tuesday",
                fallback_used=True,
                row_count=row_count,
            )
            return None, status_rows

    return pending, status_rows


def finalize_stale_pending_snapshot(
    today: date,
    pending: PendingSnapshot | None,
    pending_state_path: Path,
    status_rows: list[dict[str, str]],
) -> tuple[PendingSnapshot | None, list[dict[str, str]]]:
    if not pending:
        return None, status_rows

    if today <= pending.week_date + timedelta(days=1):
        return pending, status_rows

    status_rows = upsert_status_row(
        status_rows,
        week_date=pending.week_date,
        source_date=None,
        status="skipped_zero_on_monday_and_tuesday",
        fallback_used=True,
        row_count=0,
    )
    clear_pending_snapshot(pending_state_path)
    return None, status_rows


def rebuild_history_outputs(
    output_dir: Path,
    status_rows: list[dict[str, str]],
    long_csv_path: Path,
    wide_csv_path: Path,
) -> None:
    archive_dir = output_dir / ARCHIVE_DIR.name
    retained_snapshots = list_weekly_snapshot_files(archive_dir)
    rebuild_history_outputs_from_snapshots(retained_snapshots, status_rows, long_csv_path, wide_csv_path)


def rebuild_history_outputs_from_snapshots(
    retained_snapshots: list[SnapshotFile],
    status_rows: list[dict[str, str]],
    long_csv_path: Path,
    wide_csv_path: Path,
) -> None:
    status_by_week = {row["week_date"]: row for row in status_rows}

    week_dates: list[str] = []
    product_week_inventory: dict[str, dict[str, str]] = {}
    latest_product_metadata: dict[str, tuple[str, str, str]] = {}
    week_source_dates: dict[str, str] = {}

    for snapshot in retained_snapshots:
        week_key = snapshot.week_date.isoformat()
        week_dates.append(week_key)
        table = read_csv_table(snapshot.path)
        status_row = status_by_week.get(week_key, {})
        week_source_dates[week_key] = status_row.get("source_date") or week_key

        for row in sorted(
            table.rows,
            key=lambda item: (
                item.get("product_name", "").lower(),
                item.get("product_id", ""),
            ),
        ):
            product_id = row.get("product_id", "").strip()
            if not product_id:
                continue

            product_name = row.get("product_name", "")
            category_name = row.get("category_name", "")
            inventory = row.get("inventory", "")

            product_week_inventory.setdefault(product_id, {})[week_key] = inventory
            latest_product_metadata[product_id] = (week_key, product_name, category_name)

    product_ids = sorted(
        product_week_inventory,
        key=lambda pid: (
            latest_product_metadata[pid][1].lower(),
            pid,
        ),
    )

    long_rows: list[dict[str, str]] = []
    for week_date in week_dates:
        for product_id in product_ids:
            _, product_name, category_name = latest_product_metadata[product_id]
            inventory = product_week_inventory[product_id].get(week_date, MISSING_INVENTORY_VALUE)
            long_rows.append(
                {
                    "week_date": week_date,
                    "source_date": week_source_dates.get(week_date, week_date),
                    "product_id": product_id,
                    "product_name": product_name,
                    "category_name": category_name,
                    "inventory": inventory,
                }
            )

    write_csv_rows(long_csv_path, LONG_COLUMNS, long_rows)

    wide_columns = [*WIDE_PREFIX_COLUMNS, *week_dates]
    wide_rows: list[dict[str, str]] = []
    for product_id in product_ids:
        _, product_name, category_name = latest_product_metadata[product_id]
        row = {
            "product_id": product_id,
            "product_name": product_name,
            "category_name": category_name,
        }
        for week_date in week_dates:
            row[week_date] = product_week_inventory[product_id].get(week_date, MISSING_INVENTORY_VALUE)
        wide_rows.append(row)

    write_csv_rows(wide_csv_path, wide_columns, wide_rows)


def backfill_status_rows_from_snapshots(
    snapshots: list[SnapshotFile],
    rows: list[dict[str, str]],
) -> list[dict[str, str]]:
    backfilled_rows = list(rows)
    existing_weeks = {row.get("week_date", "") for row in rows}

    for snapshot in snapshots:
        week_key = snapshot.week_date.isoformat()
        if week_key in existing_weeks:
            continue
        row_count = len(read_csv_table(snapshot.path).rows)
        backfilled_rows = upsert_status_row(
            backfilled_rows,
            week_date=snapshot.week_date,
            source_date=snapshot.week_date,
            status="captured",
            fallback_used=False,
            row_count=row_count,
        )
        existing_weeks.add(week_key)

    return backfilled_rows


def archive_completed_years(
    output_dir: Path,
    status_rows: list[dict[str, str]],
    current_year: int,
) -> list[dict[str, str]]:
    archive_dir = output_dir / ARCHIVE_DIR.name
    yearly_root = archive_dir / YEARLY_ARCHIVE_DIR_NAME
    active_snapshots = list_weekly_snapshot_files(archive_dir)
    years_to_archive = sorted(
        {
            snapshot.week_date.year
            for snapshot in active_snapshots
            if snapshot.week_date.year < current_year
        }
        | {
            parsed_week_date.year
            for row in status_rows
            if (parsed_week_date := try_parse_week_date(row.get("week_date", ""))) is not None
            and parsed_week_date.year < current_year
        }
    )

    for year in years_to_archive:
        year_dir = yearly_root / str(year)
        year_snapshot_dir = year_dir / "snapshots"
        year_snapshot_dir.mkdir(parents=True, exist_ok=True)

        for snapshot in active_snapshots:
            if snapshot.week_date.year != year:
                continue
            destination = year_snapshot_dir / snapshot.path.name
            if snapshot.path != destination:
                snapshot.path.replace(destination)

        archived_snapshots = list_weekly_snapshot_files(year_snapshot_dir)
        archived_status_rows = filter_status_rows_for_year(status_rows, year)
        archived_status_rows = backfill_status_rows_from_snapshots(archived_snapshots, archived_status_rows)
        write_status_rows(year_dir / STATUS_CSV_PATH.name, archived_status_rows)
        rebuild_history_outputs_from_snapshots(
            archived_snapshots,
            archived_status_rows,
            year_dir / LONG_CSV_PATH.name,
            year_dir / WIDE_CSV_PATH.name,
        )

    return filter_status_rows_for_year(status_rows, current_year)


def filter_status_rows_for_year(rows: list[dict[str, str]], target_year: int) -> list[dict[str, str]]:
    filtered_rows: list[dict[str, str]] = []
    for row in rows:
        week_date = try_parse_week_date(row.get("week_date", ""))
        if week_date is None:
            filtered_rows.append(row)
            continue
        if week_date.year == target_year:
            filtered_rows.append(row)
    return filtered_rows


def list_weekly_snapshot_files(archive_dir: Path) -> list[SnapshotFile]:
    snapshots: list[SnapshotFile] = []
    for path in sorted(archive_dir.glob("products_*.csv")):
        week_date = parse_snapshot_week_date(path)
        if week_date is None:
            continue
        if week_date.weekday() != 0:
            continue
        snapshots.append(SnapshotFile(week_date=week_date, path=path))
    snapshots.sort(key=lambda item: item.week_date)
    return snapshots


def parse_snapshot_week_date(path: Path) -> date | None:
    stem = path.stem
    prefix = "products_"
    if not stem.startswith(prefix):
        return None
    date_fragment = stem[len(prefix) :]
    try:
        return datetime.strptime(date_fragment, "%Y-%m-%d").date()
    except ValueError:
        return None


def snapshot_path_for_week(archive_dir: Path, week_date: date) -> Path:
    return archive_dir / f"products_{week_date.isoformat()}.csv"


def try_parse_week_date(raw_value: str) -> date | None:
    try:
        return _parse_today(raw_value)
    except ValueError:
        return None


def read_csv_table(path: Path) -> CsvTable:
    if not path.exists():
        return CsvTable(fieldnames=[], rows=[])

    with path.open("r", newline="", encoding="utf-8") as handle:
        reader = csv.DictReader(handle)
        rows = [{key: value or "" for key, value in row.items()} for row in reader]
        fieldnames = list(reader.fieldnames or [])
    return CsvTable(fieldnames=fieldnames, rows=rows)


def write_snapshot_csv(path: Path, table: CsvTable) -> None:
    write_csv_rows(path, table.fieldnames, table.rows)


def csv_path_has_all_zero_inventory(path: Path) -> bool:
    return all_zero_inventory(read_csv_table(path).rows)


def write_status_rows(path: Path, rows: list[dict[str, str]]) -> None:
    ordered_rows = sorted(rows, key=lambda row: row["week_date"])
    write_csv_rows(path, STATUS_COLUMNS, ordered_rows)


def load_status_rows(path: Path) -> list[dict[str, str]]:
    table = read_csv_table(path)
    if not table.rows:
        return []
    return [{column: row.get(column, "") for column in STATUS_COLUMNS} for row in table.rows]


def upsert_status_row(
    rows: list[dict[str, str]],
    *,
    week_date: date,
    source_date: date | None,
    status: str,
    fallback_used: bool,
    row_count: int,
) -> list[dict[str, str]]:
    next_rows = [row for row in rows if row.get("week_date") != week_date.isoformat()]
    next_rows.append(
        {
            "week_date": week_date.isoformat(),
            "source_date": source_date.isoformat() if source_date else "",
            "status": status,
            "fallback_used": "true" if fallback_used else "false",
            "row_count": str(row_count),
        }
    )
    return next_rows


def load_pending_snapshot(path: Path) -> PendingSnapshot | None:
    if not path.exists():
        return None

    with path.open("r", encoding="utf-8") as handle:
        payload = json.load(handle)
    return PendingSnapshot(
        week_date=_parse_today(payload["week_date"]),
        created_on=_parse_today(payload["created_on"]),
    )


def save_pending_snapshot(path: Path, pending: PendingSnapshot) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        "week_date": pending.week_date.isoformat(),
        "created_on": pending.created_on.isoformat(),
    }
    with path.open("w", encoding="utf-8") as handle:
        json.dump(payload, handle, indent=2, sort_keys=True)
        handle.write("\n")


def clear_pending_snapshot(path: Path) -> None:
    path.unlink(missing_ok=True)


def write_csv_rows(path: Path, fieldnames: list[str], rows: list[dict[str, str]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        for row in rows:
            writer.writerow({field: row.get(field, "") for field in fieldnames})


def all_zero_inventory(rows: list[dict[str, str]]) -> bool:
    if not rows:
        return False

    for row in rows:
        numeric = parse_inventory_value(row.get("inventory", ""))
        if numeric is None or numeric != 0:
            return False
    return True


def parse_inventory_value(raw_value: str) -> Decimal | None:
    value = raw_value.strip()
    if not value:
        return None
    try:
        return Decimal(value)
    except (InvalidOperation, ValueError):
        return None


def _parse_today(raw_value: str) -> date:
    return datetime.strptime(raw_value, "%Y-%m-%d").date()


def _ist_today() -> date:
    return datetime.now(IST).date()


if __name__ == "__main__":
    main()
