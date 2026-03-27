from __future__ import annotations

import csv
from decimal import Decimal
from pathlib import Path
from typing import Iterable

from models import ProductRecord

CSV_COLUMNS = ["product_id", "product_name", "price", "inventory", "category_name"]


def write_products_csv(output_path: str, records: Iterable[ProductRecord]) -> None:
    path = Path(output_path)
    path.parent.mkdir(parents=True, exist_ok=True)

    with path.open("w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=CSV_COLUMNS)
        writer.writeheader()

        for rec in records:
            writer.writerow(
                {
                    "product_id": rec.product_id,
                    "product_name": rec.product_name,
                    "price": _fmt_decimal(rec.price),
                    "inventory": _fmt_decimal(rec.inventory),
                    "category_name": rec.category_name,
                }
            )


def _fmt_decimal(value: Decimal | None) -> str:
    return "" if value is None else format(value, "f")
