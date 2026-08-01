"""Deterministic explicit importer for a pinned local FDC export subset."""
from __future__ import annotations

import json
import math
from datetime import datetime
from pathlib import Path
from typing import Any

ALLOWED_DATA_TYPES = {"Foundation", "SR Legacy"}
CORE_NUTRIENTS = {
    "Energy": "energy_kcal",
    "Protein": "protein_g",
    "Carbohydrate, by difference": "carbohydrate_g",
    "Total lipid (fat)": "fat_g",
    "Fiber, total dietary": "fibre_g",
}


def normalize_fdc_record(record: dict[str, Any]) -> dict[str, Any]:
    if record.get("dataType") not in ALLOWED_DATA_TYPES:
        raise ValueError("only Foundation and SR Legacy records are accepted")
    if not str(record.get("fdcId", "")).isdigit():
        raise ValueError("record lacks a pinned FDC id")
    nutrients = {value: None for value in CORE_NUTRIENTS.values()}
    for nutrient in record.get("foodNutrients", []):
        nutrient_meta = nutrient.get("nutrient", {})
        name = nutrient_meta.get("name") or nutrient.get("name")
        target = CORE_NUTRIENTS.get(name)
        if target is None:
            continue
        unit = nutrient_meta.get("unitName") or nutrient.get("unitName")
        if target == "energy_kcal" and str(unit).lower() != "kcal":
            continue
        if target != "energy_kcal" and str(unit).lower() not in {"g", "gram"}:
            continue
        amount = nutrient.get("amount")
        if amount is not None:
            amount = float(amount)
            if not math.isfinite(amount) or amount < 0:
                raise ValueError("nutrient is negative or non-finite")
        nutrients[target] = amount
    description = str(record.get("description", "")).strip()
    if not description:
        raise ValueError("record lacks a source description")
    publication_date = record.get("publicationDate")
    if not publication_date:
        raise ValueError("record lacks a publication date")
    try:
        publication_date = datetime.strptime(
            publication_date, "%m/%d/%Y"
        ).date().isoformat()
    except ValueError:
        try:
            publication_date = datetime.strptime(
                publication_date, "%m/%d/%y"
            ).date().isoformat()
        except ValueError as exc:
            raise ValueError("invalid FDC publication date") from exc
    return {
        "source_record_id": str(record["fdcId"]),
        "source_data_type": record["dataType"],
        "source_description_en": description,
        "source_publication_date": publication_date,
        "nutrients_per_100g": nutrients,
    }


def import_file(input_path: str | Path, output_path: str | Path) -> None:
    raw = json.loads(Path(input_path).read_text(encoding="utf-8"))
    records = raw if isinstance(raw, list) else raw.get("foods", [])
    normalized = sorted(
        (normalize_fdc_record(record) for record in records),
        key=lambda item: (item["source_data_type"], int(item["source_record_id"])),
    )
    ids = [item["source_record_id"] for item in normalized]
    if len(ids) != len(set(ids)):
        raise ValueError("duplicate FDC id")
    Path(output_path).write_text(
        json.dumps(normalized, ensure_ascii=False, sort_keys=True, indent=2) + "\n",
        encoding="utf-8",
    )
