from __future__ import annotations

import logging
from concurrent.futures import ThreadPoolExecutor, as_completed
from typing import Iterable

from config import INVENTORY_WORKERS, PRODUCT_WORKERS
from http_client import HttpClient
from inventory_client import fetch_inventory_total
from models import ProductRecord, ProductSeed
from product_scraper import scrape_product_page


def scrape_products(client: HttpClient, seeds: list[ProductSeed]) -> list[ProductRecord]:
    records: list[ProductRecord] = []
    with ThreadPoolExecutor(max_workers=PRODUCT_WORKERS) as executor:
        futures = {executor.submit(scrape_product_page, client, seed): seed for seed in seeds}
        for future in as_completed(futures):
            seed = futures[future]
            try:
                record = future.result()
            except Exception as exc:  # noqa: BLE001
                logging.warning("Unexpected scrape failure for %s: %s", seed.product_url, exc)
                continue
            if record:
                records.append(record)
    return records


def attach_inventory(client: HttpClient, records: list[ProductRecord]) -> list[ProductRecord]:
    with ThreadPoolExecutor(max_workers=INVENTORY_WORKERS) as executor:
        futures = {executor.submit(fetch_inventory_total, client, rec.sku): rec for rec in records}
        for future in as_completed(futures):
            rec = futures[future]
            try:
                rec.inventory = future.result()
            except Exception as exc:  # noqa: BLE001
                logging.warning("Unexpected inventory failure for %s: %s", rec.product_id, exc)
                rec.inventory = None
    return records


def deduplicate(records: Iterable[ProductRecord]) -> list[ProductRecord]:
    by_product_url: dict[str, ProductRecord] = {}

    for record in records:
        existing = by_product_url.get(record.product_url)
        if not existing:
            by_product_url[record.product_url] = record
            continue

        # Prefer the more complete row (fewer null fields) for exact URL collisions.
        if _completeness(record) > _completeness(existing):
            by_product_url[record.product_url] = record

    deduped = sorted(by_product_url.values(), key=lambda r: (r.product_name.lower(), r.product_id))
    return deduped


def _completeness(record: ProductRecord) -> int:
    score = 0
    if record.product_id:
        score += 1
    if record.product_name:
        score += 1
    if record.price is not None:
        score += 1
    if record.inventory is not None:
        score += 1
    if record.sku:
        score += 1
    return score
