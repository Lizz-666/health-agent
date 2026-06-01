import json
from pathlib import Path

_DATA_DIR = Path(__file__).parent / "data"

CATEGORY_MAP = {
    "head_neck": "头颈部",
    "shoulder_thorax": "肩胸区",
    "pelvis_spine": "骨盆腰椎",
    "lower_limb": "下肢",
    "compound": "复合综合征",
}

_FILE_MAP = {
    "head_neck": "head_neck.json",
    "shoulder_thorax": "shoulder_thorax.json",
    "pelvis_spine": "pelvis_spine.json",
    "lower_limb": "lower_limb.json",
    "compound": "compound.json",
}

_ISSUES_CACHE: list[dict] | None = None


def _load_all() -> list[dict]:
    global _ISSUES_CACHE
    if _ISSUES_CACHE is not None:
        return _ISSUES_CACHE
    issues = []
    for filename in _FILE_MAP.values():
        filepath = _DATA_DIR / filename
        with open(filepath, "r", encoding="utf-8") as f:
            issues.extend(json.load(f))
    _ISSUES_CACHE = issues
    return _ISSUES_CACHE


def get_all_issues(category: str | None = None) -> list[dict]:
    issues = _load_all()
    if category:
        return [i for i in issues if i["category"] == category]
    return issues


def get_issue_by_id(issue_id: str) -> dict | None:
    for i in _load_all():
        if i["id"] == issue_id:
            return i
    return None
