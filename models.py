from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal
from typing import Optional


@dataclass
class ProductSeed:
    category_url: str
    product_url: str


@dataclass
class ProductRecord:
    category_url: str
    category_name: str
    product_url: str
    product_id: str
    product_name: str
    price: Optional[Decimal]
    sku: Optional[str]
    inventory: Optional[Decimal] = None
