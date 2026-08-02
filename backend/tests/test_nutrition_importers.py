from __future__ import annotations

import json
import pytest

from app.nutrition.importers import import_file, normalize_fdc_record


def _record(data_type="Foundation", energy=100.0):
    return {"fdcId": 123, "dataType": data_type, "description": "Generic test food",
            "publicationDate": "4/30/2026", "foodNutrients": [
                {"nutrient": {"name": "Energy", "unitName": "kJ"}, "amount": 999},
                {"nutrient": {"name": "Energy", "unitName": "kcal"}, "amount": energy},
                {"nutrient": {"name": "Protein", "unitName": "g"}, "amount": 2},
                {"nutrient": {"name": "Carbohydrate, by difference", "unitName": "g"}, "amount": 20},
                {"nutrient": {"name": "Total lipid (fat)", "unitName": "g"}, "amount": 1}]}


def test_normalizer_selects_kcal_and_preserves_missing_fibre():
    result = normalize_fdc_record(_record())
    assert result["nutrients_per_100g"]["energy_kcal"] == 100
    assert result["nutrients_per_100g"]["fibre_g"] is None
    assert result["source_publication_date"] == "2026-04-30"


@pytest.mark.parametrize("data_type", ["Branded", "Survey (FNDDS)", "Experimental"])
def test_import_rejects_disallowed_data_types(data_type):
    with pytest.raises(ValueError, match="Foundation and SR Legacy"):
        normalize_fdc_record(_record(data_type=data_type))


@pytest.mark.parametrize("energy", [float("nan"), float("inf"), -1])
def test_import_rejects_invalid_nutrients(energy):
    with pytest.raises(ValueError, match="negative or non-finite"):
        normalize_fdc_record(_record(energy=energy))


def test_import_output_is_deterministic_and_sorted(tmp_path):
    first, second = _record(), _record("SR Legacy")
    second["fdcId"] = 5
    source = tmp_path / "raw.json"
    source.write_text(json.dumps([first, second]), encoding="utf-8")
    a, b = tmp_path / "a.json", tmp_path / "b.json"
    import_file(source, a)
    import_file(source, b)
    assert a.read_bytes() == b.read_bytes()
    assert [x["source_record_id"] for x in json.loads(a.read_text())] == ["123", "5"]


@pytest.mark.parametrize("field", ["description", "publicationDate"])
def test_import_rejects_missing_lineage_fields(field):
    record = _record()
    record[field] = ""
    with pytest.raises(ValueError, match="lacks"):
        normalize_fdc_record(record)


def test_import_rejects_duplicate_fdc_ids(tmp_path):
    source = tmp_path / "raw.json"
    source.write_text(json.dumps([_record(), _record()]), encoding="utf-8")
    with pytest.raises(ValueError, match="duplicate FDC id"):
        import_file(source, tmp_path / "output.json")
