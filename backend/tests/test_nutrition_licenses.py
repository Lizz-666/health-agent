from __future__ import annotations

import hashlib
from pathlib import Path

from PIL import Image

from app.nutrition.knowledge import load_media_manifest, load_source_manifest

ROOT = Path(__file__).resolve().parents[2]
DATA = ROOT / "backend/app/nutrition/data"


def test_every_source_subset_checksum_and_license_is_auditable():
    manifest = load_source_manifest(DATA / "source_manifest.v1.json")
    for source in manifest.sources:
        path = DATA / source.local_subset_file
        assert hashlib.sha256(path.read_bytes()).hexdigest() == source.raw_sha256
        assert source.license in {"CC0-1.0", "Public Domain", "project-authored"}
        assert source.url.startswith("https://fdc.nal.usda.gov/")


def test_media_inventory_is_local_reviewed_and_exactly_hashed():
    manifest = load_media_manifest(DATA / "media_manifest.v1.json")
    assert sum(item.kind == "ingredient" for item in manifest.media) >= 12
    assert sum(item.kind == "prepared_meal" for item in manifest.media) >= 3
    for item in manifest.media:
        path = ROOT / "app" / item.asset_key
        assert path.is_file()
        assert hashlib.sha256(path.read_bytes()).hexdigest() == item.sha256
        with Image.open(path) as image:
            assert image.size == (item.width, item.height) == (800, 600)
            assert image.format == "JPEG"
        assert item.license in {"CC0-1.0", "Public Domain"}
        assert item.source_page_url.startswith("https://commons.wikimedia.org/wiki/File:")


def test_no_disallowed_dataset_or_code_license_is_registered():
    text = (DATA / "source_manifest.v1.json").read_text(encoding="utf-8").lower()
    assert "open food facts" not in text
    assert "odbl" not in text
    assert "gpl" not in text
    assert "branded" not in text


def test_runtime_nutrition_modules_have_no_network_client():
    runtime = ROOT / "backend/app/nutrition"
    for path in runtime.glob("*.py"):
        text = path.read_text(encoding="utf-8")
        assert "requests." not in text
        assert "httpx." not in text
        assert "urlopen(" not in text
        assert "api_key" not in text.lower()
