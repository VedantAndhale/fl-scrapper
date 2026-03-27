from __future__ import annotations

import json
import logging
from decimal import Decimal, InvalidOperation
from typing import Optional

from config import INVENTORY_API_BASE
from http_client import HttpClient


def fetch_inventory_total(client: HttpClient, sku: Optional[str]) -> Optional[Decimal]:
    if not sku:
        return None

    url = f"{INVENTORY_API_BASE}/{sku}"
    try:
        response = client.get(url)
    except Exception as exc:  # noqa: BLE001
        logging.warning("Inventory fetch exception for sku=%s: %s", sku, exc)
        return None

    if response.status_code != 200:
        logging.warning("Inventory fetch failed for sku=%s [%s]", sku, response.status_code)
        return None

    try:
        payload = response.json()
    except json.JSONDecodeError:
        logging.warning("Inventory JSON decode failed for sku=%s", sku)
        return None

    if not isinstance(payload, dict):
        return None

    if "total" in payload:
        total = _to_decimal(payload.get("total"))
        if total is not None:
            return total

    summed = Decimal("0")
    had_value = False
    for key, value in payload.items():
        if key == "total":
            continue
        numeric = _to_decimal(value)
        if numeric is None:
            continue
        had_value = True
        summed += numeric

    return summed if had_value else None


def _to_decimal(value: object) -> Optional[Decimal]:
    if value is None:
        return None
    try:
        return Decimal(str(value))
    except (InvalidOperation, ValueError):
        return None
