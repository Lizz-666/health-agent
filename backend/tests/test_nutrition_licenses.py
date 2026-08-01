from __future__ import annotations

import hashlib
from pathlib import Path

from app.nutrition.knowledge import load_media_manifest, load_source_manifest

ROOT = Path(__file__).resolve().parents[2]
DATA = ROOT / "backend/app/nutrition/data"

SOF_MARKERS = {
    0xC0, 0xC1, 0xC2, 0xC3, 0xC5, 0xC6, 0xC7,
    0xC9, 0xCA, 0xCB, 0xCD, 0xCE, 0xCF,
}


def _jpeg_dimensions(path: Path) -> tuple[int, int]:
    data = path.read_bytes()
    if not data.startswith(b"\xff\xd8"):
        raise AssertionError("media is not a JPEG")
    position = 2
    while position < len(data):
        while position < len(data) and data[position] != 0xFF:
            position += 1
        while position < len(data) and data[position] == 0xFF:
            position += 1
        if position >= len(data):
            break
        marker = data[position]
        position += 1
        if marker in {0x01, *range(0xD0, 0xDA)}:
            continue
        if position + 2 > len(data):
            break
        segment_length = int.from_bytes(data[position:position + 2], "big")
        if segment_length < 2 or position + segment_length > len(data):
            break
        if marker in SOF_MARKERS:
            if segment_length < 7:
                break
            height = int.from_bytes(data[position + 3:position + 5], "big")
            width = int.from_bytes(data[position + 5:position + 7], "big")
            return width, height
        position += segment_length
    raise AssertionError("JPEG dimensions are absent or malformed")


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
        assert _jpeg_dimensions(path) == (item.width, item.height) == (800, 600)
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
