from __future__ import annotations

import argparse
import logging
from collections import Counter

from config import CATEGORY_URLS, DEFAULT_OUTPUT_CSV
from export_csv import write_products_csv
from http_client import HttpClient
from listing_scraper import scrape_category_product_urls
from logging_config import setup_logging
from pipeline import attach_inventory, deduplicate, scrape_products


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Scrape prefab countertop products + live inventory")
    parser.add_argument("--output", default=DEFAULT_OUTPUT_CSV, help="Output CSV path")
    parser.add_argument("--verbose", action="store_true", help="Enable debug logging")
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    setup_logging(args.verbose)

    client = HttpClient()

    all_seeds = []
    for category_url in CATEGORY_URLS:
        seeds = scrape_category_product_urls(client, category_url)
        all_seeds.extend(seeds)

    # URL-level dedupe
    unique_seed_map = {seed.product_url: seed for seed in all_seeds}
    unique_seeds = sorted(unique_seed_map.values(), key=lambda s: s.product_url)
    logging.info("Discovered %d unique product URLs across %d categories", len(unique_seeds), len(CATEGORY_URLS))

    product_records = scrape_products(client, unique_seeds)
    logging.info("Parsed %d product pages", len(product_records))

    product_records = attach_inventory(client, product_records)
    final_records = deduplicate(product_records)
    logging.info("Final deduplicated rows: %d", len(final_records))
    category_counts = Counter(record.category_name for record in final_records)
    if category_counts:
        logging.info("Rows by category_name: %s", dict(sorted(category_counts.items())))

    write_products_csv(args.output, final_records)
    logging.info("CSV written to %s", args.output)


if __name__ == "__main__":
    main()
