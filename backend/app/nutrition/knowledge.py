"""Fail-closed loaders and release audit for curated nutrition data."""
from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Type, TypeVar

from pydantic import BaseModel, ValidationError

from app.nutrition.importers import normalize_fdc_record
from app.nutrition.schemas import (
    FoodCatalog,
    MediaManifest,
    NutritionPolicy,
    SourceManifest,
)
from app.nutrition.validator import validate_manifest_pins

SUPPORTED_VERSIONS = {"v1"}
ALLOWED_SOURCE_LICENSES = {"CC0-1.0", "Public Domain", "project-authored"}
ALLOWED_MEDIA_LICENSES = {"CC0-1.0", "Public Domain"}
T = TypeVar("T", bound=BaseModel)


class NutritionDataError(ValueError):
    pass


def _load(path: Path, model: Type[T]) -> T:
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        return model.model_validate(data)
    except (OSError, json.JSONDecodeError, ValidationError) as exc:
        raise NutritionDataError(f"invalid nutrition data file: {path.name}") from exc


def load_catalog(path: str | Path) -> FoodCatalog:
    catalog = _load(Path(path), FoodCatalog)
    if catalog.schema_version not in SUPPORTED_VERSIONS:
        raise NutritionDataError("unsupported catalog schema version")
    ids = [food.food_id for food in catalog.foods]
    if len(ids) != len(set(ids)):
        raise NutritionDataError("duplicate food id")
    if len(catalog.foods) < 24:
        raise NutritionDataError("catalog must contain at least 24 foods")
    return catalog


def load_source_manifest(path: str | Path) -> SourceManifest:
    manifest = _load(Path(path), SourceManifest)
    if manifest.manifest_version not in SUPPORTED_VERSIONS:
        raise NutritionDataError("unsupported source manifest version")
    ids = [source.source_id for source in manifest.sources]
    if len(ids) != len(set(ids)):
        raise NutritionDataError("duplicate source id")
    for source in manifest.sources:
        if source.license not in ALLOWED_SOURCE_LICENSES:
            raise NutritionDataError("source license is not allowed")
        if source.review_status.value != "approved":
            raise NutritionDataError("source row is not approved")
        if source.source_type in {"branded", "open_food_facts", "gpl_derived"}:
            raise NutritionDataError("source type is excluded")
    return manifest


def load_media_manifest(path: str | Path) -> MediaManifest:
    manifest = _load(Path(path), MediaManifest)
    if manifest.manifest_version not in SUPPORTED_VERSIONS:
        raise NutritionDataError("unsupported media manifest version")
    ids = [item.media_id for item in manifest.media]
    assets = [item.asset_key for item in manifest.media]
    if len(ids) != len(set(ids)) or len(assets) != len(set(assets)):
        raise NutritionDataError("duplicate media id or asset")
    for item in manifest.media:
        if item.license not in ALLOWED_MEDIA_LICENSES:
            raise NutritionDataError("media license is not allowed")
        if item.review_status.value != "approved":
            raise NutritionDataError("media row is not approved")
    return manifest


def load_policy(path: str | Path) -> NutritionPolicy:
    policy = _load(Path(path), NutritionPolicy)
    if policy.policy_version not in SUPPORTED_VERSIONS:
        raise NutritionDataError("unsupported nutrition policy version")
    return policy


def _load_source_records(path: Path) -> dict[str, dict]:
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
        records = raw if isinstance(raw, list) else raw.get("foods", [])
        normalized = [normalize_fdc_record(record) for record in records]
    except (OSError, json.JSONDecodeError, AttributeError, TypeError, ValueError) as exc:
        raise NutritionDataError(f"invalid nutrition source subset: {path.name}") from exc
    ids = [record["source_record_id"] for record in normalized]
    if len(ids) != len(set(ids)):
        raise NutritionDataError("source subset contains duplicate FDC ids")
    return {record["source_record_id"]: record for record in normalized}


def audit_release(data_dir: str | Path, app_dir: str | Path) -> None:
    data_root = Path(data_dir)
    app_root = Path(app_dir)
    catalog = load_catalog(data_root / "foods.v1.json")
    sources = load_source_manifest(data_root / "source_manifest.v1.json")
    media = load_media_manifest(data_root / "media_manifest.v1.json")
    policy = load_policy(data_root / "nutrition_policy.v1.json")
    pins = validate_manifest_pins(catalog, sources, media)
    if not pins.valid:
        raise NutritionDataError("manifest version mismatch")
    source_by_id = {source.source_id: source for source in sources.sources}
    source_records: dict[str, dict[str, dict]] = {}
    for source in sources.sources:
        subset = data_root / source.local_subset_file
        if not subset.is_file():
            raise NutritionDataError("source subset is missing")
        if hashlib.sha256(subset.read_bytes()).hexdigest() != source.raw_sha256:
            raise NutritionDataError("source subset checksum mismatch")
        records = _load_source_records(subset)
        expected_type = {
            "fdc_foundation": "Foundation",
            "fdc_sr_legacy": "SR Legacy",
        }.get(source.source_type)
        if expected_type is None or any(
            record["source_data_type"] != expected_type for record in records.values()
        ):
            raise NutritionDataError("source subset type does not match its manifest")
        source_records[source.source_id] = records
    catalog_ids = {food.food_id for food in catalog.foods}
    for food_ids in policy.exclusion_food_ids.values():
        if not food_ids or not set(food_ids) <= catalog_ids:
            raise NutritionDataError("exclusion policy has unknown or empty food ids")
    if not set(policy.whole_grain_food_ids) <= catalog_ids:
        raise NutritionDataError("whole grain policy has unknown food ids")
    if any(
        food.category.value != "grain"
        for food in catalog.foods
        if food.food_id in policy.whole_grain_food_ids
    ):
        raise NutritionDataError("whole grain policy references a non-grain food")
    media_by_asset = {item.asset_key: item for item in media.media}
    ingredient_count = 0
    for food in catalog.foods:
        if food.source_id not in source_by_id:
            raise NutritionDataError("food references an unknown source")
        source_record = source_records[food.source_id].get(food.source_record_id)
        if source_record is None:
            raise NutritionDataError("food references an absent source record")
        catalog_projection = {
            "source_record_id": food.source_record_id,
            "source_data_type": food.source_data_type,
            "source_description_en": food.source_description_en,
            "source_publication_date": food.source_publication_date.isoformat(),
            "nutrients_per_100g": food.nutrients_per_100g.model_dump(),
        }
        if catalog_projection != source_record:
            raise NutritionDataError("food source projection differs from the pinned record")
        for exclusion_code in food.exclusion_codes:
            if food.food_id not in policy.exclusion_food_ids[exclusion_code]:
                raise NutritionDataError("food exclusion code differs from policy")
        if food.image_key:
            item = media_by_asset.get(food.image_key)
            if item is None or item.kind != "ingredient":
                raise NutritionDataError("food image is absent or not an ingredient")
            ingredient_count += 1
    for exclusion_code, food_ids in policy.exclusion_food_ids.items():
        for food_id in food_ids:
            food = next(item for item in catalog.foods if item.food_id == food_id)
            if exclusion_code not in food.exclusion_codes:
                raise NutritionDataError("exclusion policy differs from food metadata")
    referenced = {food.image_key for food in catalog.foods if food.image_key}
    for item in media.media:
        if item.kind == "ingredient" and item.asset_key not in referenced:
            raise NutritionDataError("orphan ingredient media")
        asset = app_root / item.asset_key
        if not asset.is_file():
            raise NutritionDataError("media asset is missing")
        digest = hashlib.sha256(asset.read_bytes()).hexdigest()
        if digest != item.sha256:
            raise NutritionDataError("media checksum mismatch")
    if ingredient_count < 12:
        raise NutritionDataError("at least 12 foods need ingredient photos")
    if sum(item.kind == "prepared_meal" for item in media.media) < 3:
        raise NutritionDataError("at least three prepared meal photos are required")
    eligible = [food for food in catalog.foods if food.generation_eligible]
    groups: dict[str, set[str]] = {}
    for food in eligible:
        groups.setdefault(food.exchange_group, set()).add(food.food_id)
    if any(len(values) < 3 for values in groups.values()):
        raise NutritionDataError("each exchange group needs three eligible candidates")
    if sum(food.dark_vegetable for food in eligible if food.category.value == "vegetable") < 2:
        raise NutritionDataError("catalog lacks reviewed dark vegetables")
