from typing import Optional, List
import json
from pathlib import Path
from pydantic import ValidationError

from app.posture.schemas import KnowledgeIssue

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

_ISSUES_CACHE: Optional[List[dict]] = None


def validate_issue(issue: dict) -> KnowledgeIssue:
    """Validate a single knowledge entry, including every structured source.

    Raises pydantic.ValidationError on any malformed field or source object.
    """
    return KnowledgeIssue.model_validate(issue)


def load_issues(raw_issues: List[dict]) -> List[dict]:
    """Validate a batch of knowledge entries, failing loudly on the first error.

    Used by the loader so that invalid source data blocks loading instead of
    being silently ignored or defaulted.
    """
    for issue in raw_issues:
        try:
            validate_issue(issue)
        except ValidationError as e:
            raise RuntimeError(
                f"知识库加载校验失败 (issue_id={issue.get('id', '<unknown>')}): {e}"
            ) from e
    return raw_issues


def _read_raw_issues() -> List[dict]:
    issues: List[dict] = []
    for filename in _FILE_MAP.values():
        filepath = _DATA_DIR / filename
        with open(filepath, "r", encoding="utf-8") as f:
            issues.extend(json.load(f))
    return issues


def _load_all() -> List[dict]:
    global _ISSUES_CACHE
    if _ISSUES_CACHE is not None:
        return _ISSUES_CACHE
    issues = _read_raw_issues()
    load_issues(issues)
    _ISSUES_CACHE = issues
    return _ISSUES_CACHE


def get_all_issues(category: Optional[str] = None) -> List[dict]:
    issues = _load_all()
    if category:
        return [i for i in issues if i["category"] == category]
    return issues


def get_issue_by_id(issue_id: str) -> Optional[dict]:
    for i in _load_all():
        if i["id"] == issue_id:
            return i
    return None


# Eager load-time validation: invalid source data in the shipped knowledge base
# blocks application startup (import) rather than failing later at request time.
_load_all()
