"""
Deterministic merging of incrementally extracted facts.

The extractor only returns what is new in the latest exchange, and this module folds that
delta into the facts we already have. Facts are never dropped because the LLM forgot them.
"""
import logging
import re
from typing import List, Optional

from models import models

logger = logging.getLogger(__name__)

_COMPANY_SUFFIXES = re.compile(r"\b(inc|llc|ltd|limited|corp|corporation|co|gmbh|plc)\b\.?")


def norm(text: Optional[str]) -> str:
    if not text:
        return ""
    return re.sub(r"[^a-z0-9+#]+", " ", text.lower()).strip()


def entry_key(text: Optional[str]) -> str:
    """Normalised name used to match entries, so 'Acme Inc.' == 'acme'."""
    return norm(_COMPANY_SUFFIXES.sub("", (text or "").lower()))


def merge_unique(existing: List[str], new: List[str]) -> List[str]:
    """Append items from `new` not already present (case/punctuation-insensitive)."""
    result = list(existing)
    seen = {norm(item) for item in existing}
    for item in new:
        if not item or not item.strip():
            continue
        key = norm(item)
        if key and key not in seen:
            seen.add(key)
            result.append(item.strip())
    return result


def _merge_scalars(target, delta, skip=()):
    """Copy every non-empty scalar field of `delta` onto `target` (corrections win)."""
    for name in type(delta).model_fields:
        if name in skip:
            continue
        value = getattr(delta, name)
        if isinstance(value, list):
            setattr(target, name, merge_unique(getattr(target, name), value))
        elif value is not None and value != "":
            setattr(target, name, value)


def _find(items: list, delta, primary: str, secondary: Optional[str]) -> Optional[int]:
    """
    Locate the existing entry `delta` refers to, e.g. primary=company, secondary=position.
    Returns None when it is a new entry (including a new position at a known company).
    """
    p = entry_key(getattr(delta, primary))
    s = entry_key(getattr(delta, secondary)) if secondary else ""

    if p:
        same = [i for i, item in enumerate(items) if entry_key(getattr(item, primary)) == p]
        if not same:
            return None
        if not s:
            return same[-1]
        for i in same:
            if entry_key(getattr(items[i], secondary)) == s:
                return i
        for i in same:
            if not entry_key(getattr(items[i], secondary)):
                return i  # entry existed without a position/degree yet
        return None

    if s:
        same = [i for i, item in enumerate(items) if entry_key(getattr(item, secondary)) == s]
        if len(same) == 1:
            return same[0]
    return None


def _merge_entries(existing: list, deltas: list, primary: str, secondary: Optional[str], label: str) -> list:
    result = [e.model_copy(deep=True) for e in existing]
    for delta in deltas:
        if delta == type(delta)():
            continue
        index = _find(result, delta, primary, secondary)
        has_identity = getattr(delta, primary) or (secondary and getattr(delta, secondary))
        if index is None and not has_identity:
            if len(result) == 1:
                index = 0  # only one entry it could be referring to
            else:
                logger.warning("Dropping %s without identifying fields: %s", label, delta.model_dump(exclude_defaults=True))
                continue
        if index is None:
            result.append(delta.model_copy(deep=True))
        else:
            _merge_scalars(result[index], delta)
    return result


def merge_facts(current: models.ResumeFacts, delta: models.ResumeFacts) -> models.ResumeFacts:
    merged = current.model_copy(deep=True)

    _merge_scalars(merged.personal_details, delta.personal_details)

    merged.profession = _merge_entries(merged.profession, delta.profession, "company", "position", "experience")
    merged.education = _merge_entries(merged.education, delta.education, "university", "degree", "education")
    merged.projects = _merge_entries(merged.projects, delta.projects, "name", None, "project")
    merged.awards = _merge_entries(merged.awards, delta.awards, "name", None, "award")
    merged.other_details = _merge_entries(merged.other_details, delta.other_details, "name", None, "other detail")

    role_tech = [t for role in delta.profession for t in role.technologies]
    project_tech = [t for project in delta.projects for t in project.technologies]
    merged.skills = merge_unique(merged.skills, delta.skills + role_tech + project_tech)

    for role in merged.profession:
        if role.is_current:
            role.end_month = None
            role.end_year = None

    return merged


def is_empty(facts: models.ResumeFacts) -> bool:
    return facts == models.ResumeFacts()
