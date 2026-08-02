from __future__ import annotations

import json
import shutil
from pathlib import Path

import pytest
from pydantic import ValidationError

from app.nutrition.knowledge import (
    NutritionDataError, audit_release, load_catalog, load_media_manifest,
    load_policy, load_source_manifest,
)
from app.nutrition.schemas import FoodRecord, NutrientsPer100g

ROOT = Path(__file__).resolve().parents[2]
DATA = ROOT / "backend/app/nutrition/data"


def test_canonical_release_passes_full_audit():
    audit_release(DATA, ROOT / "app")


def test_catalog_has_reviewed_minimum_and_exchange_depth():
    catalog = load_catalog(DATA / "foods.v1.json")
    groups: dict[str, set[str]] = {}
    for food in catalog.foods:
        if food.generation_eligible:
            groups.setdefault(food.exchange_group, set()).add(food.food_id)
    assert len(catalog.foods) >= 24
    assert groups and all(len(ids) >= 3 for ids in groups.values())
    assert sum(f.dark_vegetable for f in catalog.foods) >= 2


def test_all_catalog_sources_and_media_are_registered():
    catalog = load_catalog(DATA / "foods.v1.json")
    sources = load_source_manifest(DATA / "source_manifest.v1.json")
    media = load_media_manifest(DATA / "media_manifest.v1.json")
    assert {f.source_id for f in catalog.foods} <= {s.source_id for s in sources.sources}
    assert {f.image_key for f in catalog.foods if f.image_key} <= {m.asset_key for m in media.media}


def test_policy_exclusions_are_explicit_food_id_sets():
    policy = load_policy(DATA / "nutrition_policy.v1.json")
    assert set(policy.exclusion_food_ids) == {"avoid_pork", "avoid_beef"}
    assert all(values and len(values) == len(set(values)) for values in policy.exclusion_food_ids.values())


def test_special_diet_claims_are_out_of_scope():
    policy = load_policy(DATA / "nutrition_policy.v1.json")
    special_diet_codes = {"vegetarian", "lacto_vegetarian", "vegan", "halal", "kosher"}
    assert set(policy.exclusion_food_ids).isdisjoint(special_diet_codes)


def test_unknown_catalog_field_is_rejected(tmp_path):
    payload = json.loads((DATA / "foods.v1.json").read_text(encoding="utf-8"))
    payload["unexpected"] = True
    path = tmp_path / "catalog.json"
    path.write_text(json.dumps(payload), encoding="utf-8")
    with pytest.raises(NutritionDataError):
        load_catalog(path)


def test_duplicate_food_id_is_rejected(tmp_path):
    payload = json.loads((DATA / "foods.v1.json").read_text(encoding="utf-8"))
    payload["foods"].append(payload["foods"][0])
    path = tmp_path / "catalog.json"
    path.write_text(json.dumps(payload), encoding="utf-8")
    with pytest.raises(NutritionDataError, match="duplicate food"):
        load_catalog(path)


def test_chinese_names_cannot_be_question_mark_placeholders():
    catalog = load_catalog(DATA / "foods.v1.json")
    assert all(any("\u4e00" <= char <= "\u9fff" for char in food.name_zh)
               for food in catalog.foods)


def test_release_audit_rejects_catalog_drift_from_pinned_source(tmp_path):
    copied_data = tmp_path / "data"
    shutil.copytree(DATA, copied_data)
    catalog_path = copied_data / "foods.v1.json"
    payload = json.loads(catalog_path.read_text(encoding="utf-8"))
    payload["foods"][0]["nutrients_per_100g"]["energy_kcal"] += 1
    catalog_path.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")
    with pytest.raises(NutritionDataError, match="projection differs"):
        audit_release(copied_data, ROOT / "app")


def test_release_audit_rejects_exclusion_metadata_drift(tmp_path):
    copied_data = tmp_path / "data"
    shutil.copytree(DATA, copied_data)
    catalog_path = copied_data / "foods.v1.json"
    payload = json.loads(catalog_path.read_text(encoding="utf-8"))
    pork = next(food for food in payload["foods"] if food["food_id"] == "pork_tenderloin")
    pork["exclusion_codes"].remove("avoid_pork")
    catalog_path.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")
    with pytest.raises(NutritionDataError, match="policy differs"):
        audit_release(copied_data, ROOT / "app")


@pytest.mark.parametrize("value", [float("nan"), float("inf"), -1.0])
def test_invalid_nutrients_are_rejected(value):
    with pytest.raises(ValidationError):
        NutrientsPer100g(energy_kcal=value, protein_g=1, carbohydrate_g=1, fat_g=1)


def test_incomplete_core_nutrients_cannot_be_generation_eligible():
    raw = load_catalog(DATA / "foods.v1.json").foods[0].model_dump(mode="json")
    raw["nutrients_per_100g"]["energy_kcal"] = None
    with pytest.raises(ValidationError, match="incomplete core nutrients"):
        FoodRecord.model_validate(raw)


def test_disallowed_source_license_is_rejected(tmp_path):
    payload = json.loads((DATA / "source_manifest.v1.json").read_text(encoding="utf-8"))
    payload["sources"][0]["license"] = "ODbL-1.0"
    path = tmp_path / "sources.json"
    path.write_text(json.dumps(payload), encoding="utf-8")
    with pytest.raises(NutritionDataError, match="license"):
        load_source_manifest(path)
