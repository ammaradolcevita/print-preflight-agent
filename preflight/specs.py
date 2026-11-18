"""Load print specifications and products from specs/print_specs.yaml."""

from __future__ import annotations

from functools import lru_cache
from pathlib import Path

import yaml

from .models import ClassSpec, Product

SPECS_PATH = Path(__file__).resolve().parent.parent / "specs" / "print_specs.yaml"

PT_PER_MM = 72 / 25.4  # PDF units are points: 72 per inch, 25.4 mm per inch


def pt_to_mm(value: float) -> float:
    return value / PT_PER_MM


def mm_to_pt(value: float) -> float:
    return value * PT_PER_MM


@lru_cache(maxsize=4)
def load_specs(path: str | None = None) -> dict:
    with open(path or SPECS_PATH, encoding="utf-8") as f:
        return yaml.safe_load(f)


def tolerances() -> dict:
    return load_specs()["tolerances"]


def all_products() -> list[Product]:
    data = load_specs()
    classes = {name: ClassSpec(**vals) for name, vals in data["classes"].items()}
    return [
        Product(
            id=p["id"],
            name=p["name"],
            product_class=p["class"],
            trim_mm=tuple(p["trim_mm"]),
            max_pages=p["max_pages"],
            url=p["url"],
            keywords=p["keywords"],
            spec=classes[p["class"]],
        )
        for p in data["products"]
    ]


def get_product(product_id: str) -> Product:
    for p in all_products():
        if p.id == product_id:
            return p
    known = ", ".join(p.id for p in all_products())
    raise KeyError(f"Unknown product '{product_id}'. Known products: {known}")
