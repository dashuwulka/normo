from collections import defaultdict
from collections.abc import Iterable
from typing import Any

from app.extraction.models import ExtractedRuleCandidate


SANITY = {
    "font_size": (6, 24),
    "top_margin": (0.5, 5),
    "bottom_margin": (0.5, 5),
    "left_margin": (0.5, 5),
    "right_margin": (0.5, 5),
    "line_spacing": (0.8, 3),
    "first_line_indent": (0, 3),
}


def _numeric_values(value: Any) -> list[float]:
    if isinstance(value, list):
        values = value
    else:
        values = [value]

    result: list[float] = []
    for item in values:
        if isinstance(item, bool):
            continue

        if isinstance(item, int | float):
            result.append(float(item))

    return result


def _value_key(value: Any) -> str:
    if isinstance(value, list):
        return repr(sorted(value, key=lambda item: str(item)))

    return repr(value)


def _is_outside_sanity(candidate: ExtractedRuleCandidate) -> bool:
    if candidate.parameter not in SANITY:
        return False

    minimum, maximum = SANITY[candidate.parameter]
    values = _numeric_values(candidate.value)
    return any(value < minimum or value > maximum for value in values)


def _is_on_sanity_boundary(candidate: ExtractedRuleCandidate) -> bool:
    if candidate.parameter not in SANITY:
        return False

    minimum, maximum = SANITY[candidate.parameter]
    values = _numeric_values(candidate.value)
    return any(value == minimum or value == maximum for value in values)


def _calculate_confidence(candidate: ExtractedRuleCandidate) -> float:
    confidence = 1.0

    if candidate.target is None:
        confidence -= 0.3

    if candidate.modality == "unknown":
        confidence -= 0.3

    if _is_on_sanity_boundary(candidate):
        confidence -= 0.2

    if _is_outside_sanity(candidate):
        confidence -= 0.3

    return max(0.0, min(1.0, confidence))


def _mark_conflicts(
    candidates: list[ExtractedRuleCandidate],
) -> list[ExtractedRuleCandidate]:
    groups: dict[tuple[str | None, str], list[ExtractedRuleCandidate]] = defaultdict(list)

    for candidate in candidates:
        if candidate.operator == "equals" and candidate.status not in {"unsupported", "rejected"}:
            groups[(candidate.target, candidate.parameter)].append(candidate)

    conflicts: set[str] = set()
    for group in groups.values():
        values = {_value_key(candidate.value) for candidate in group}
        if len(values) > 1:
            conflicts.update(candidate.id for candidate in group)

    return [
        candidate.model_copy(
            update={
                "status": "conflict",
                "explanation": "несколько разных значений для одного параметра",
            }
        )
        if candidate.id in conflicts
        else candidate
        for candidate in candidates
    ]


def _is_subset_value(left: Any, right: Any) -> bool:
    if not isinstance(left, list) or not isinstance(right, list):
        return False

    left_set = {str(item).strip().lower() for item in left}
    right_set = {str(item).strip().lower() for item in right}
    return bool(left_set) and left_set < right_set


def _remove_duplicate_and_subset_candidates(
    candidates: list[ExtractedRuleCandidate],
) -> list[ExtractedRuleCandidate]:
    result: list[ExtractedRuleCandidate] = []

    for candidate in sorted(
        candidates,
        key=lambda item: (
            item.target or "",
            item.parameter,
            -len(item.value) if isinstance(item.value, list) else 0,
            -item.confidence,
        ),
    ):
        duplicate_or_subset = False
        for existing in result:
            same_rule_slot = (
                existing.target == candidate.target
                and existing.parameter == candidate.parameter
                and existing.operator == candidate.operator
                and existing.modality == candidate.modality
            )
            if not same_rule_slot:
                continue

            if _value_key(existing.value) == _value_key(candidate.value):
                duplicate_or_subset = True
                break

            if _is_subset_value(candidate.value, existing.value):
                duplicate_or_subset = True
                break

        if not duplicate_or_subset:
            result.append(candidate)

    return result


def verify(
    candidates: Iterable[ExtractedRuleCandidate],
) -> list[ExtractedRuleCandidate]:
    """Verify extracted candidates and mark low-confidence cases."""

    verified: list[ExtractedRuleCandidate] = []

    for candidate in candidates:
        confidence = _calculate_confidence(candidate)
        updates: dict[str, Any] = {"confidence": confidence}

        if _is_outside_sanity(candidate):
            updates["status"] = "needs_review"
            updates["explanation"] = "значение вне типичного диапазона"
        elif candidate.status not in {"conflict", "unsupported", "needs_review"}:
            if confidence < 0.6:
                updates["status"] = "needs_review"
                updates["explanation"] = (
                    "низкая уверенность автоматического извлечения"
                )
            else:
                updates["status"] = "extracted"

        verified.append(candidate.model_copy(update=updates))

    return _mark_conflicts(_remove_duplicate_and_subset_candidates(verified))
