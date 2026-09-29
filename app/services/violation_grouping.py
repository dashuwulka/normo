from collections import OrderedDict
from typing import Any

from app.models.violation import Violation
from app.services.parameter_registry import get_parameter_label


def _plural_ru(count: int, one: str, few: str, many: str) -> str:
    if 11 <= count % 100 <= 14:
        return many

    last_digit = count % 10
    if last_digit == 1:
        return one
    if 2 <= last_digit <= 4:
        return few
    return many


def _section_sort_key(section: str) -> tuple[int, list[int], str]:
    if not section:
        return (1, [], "")

    parts = section.split(".")
    if all(part.isdigit() for part in parts):
        return (0, [int(part) for part in parts], section)

    return (0, [], section)


def _violation_sort_key(violation: Violation) -> tuple[int, int, str]:
    if violation.paragraph_index is not None:
        return (0, violation.paragraph_index, violation.location)
    if violation.section_index is not None:
        return (1, violation.section_index, violation.location)
    return (2, 0, violation.location)


def _format_indexes(label: str, indexes: list[int]) -> str:
    unique_indexes = sorted(set(indexes))
    if not unique_indexes:
        return ""

    preview = ", ".join(str(index) for index in unique_indexes[:12])
    if len(unique_indexes) > 12:
        preview += ", ..."

    return f"{label} {preview}"


def _format_affected_locations(violations: list[Violation]) -> str:
    paragraph_indexes = [
        violation.paragraph_index
        for violation in violations
        if violation.paragraph_index is not None
    ]
    section_indexes = [
        violation.section_index
        for violation in violations
        if violation.section_index is not None
    ]

    if paragraph_indexes:
        label = _plural_ru(len(set(paragraph_indexes)), "абзац", "абзацы", "абзацы")
        return _format_indexes(label, paragraph_indexes)

    if section_indexes:
        label = _plural_ru(len(set(section_indexes)), "секция", "секции", "секции")
        return _format_indexes(label, section_indexes)

    locations = []
    for violation in violations:
        if violation.location not in locations:
            locations.append(violation.location)

    preview = ", ".join(locations[:8])
    if len(locations) > 8:
        preview += ", ..."

    return preview or "документ"


def _clean_value(value: str | None) -> str:
    if not value:
        return "не указано"
    replacements = {
        "line_spacing": "межстрочный интервал",
        "first_line_indent": "абзацный отступ",
        "left_indent": "левый отступ",
        "right_indent": "правый отступ",
        "keep_with_next": "не отрывать от следующего",
        "keep_together": "не разрывать абзац",
        "tblHeader": "повторять строку с названиями столбцов",
        "center": "по центру",
        "justify": "по ширине",
        "left": "по левому краю",
        "right": "по правому краю",
        "000000": "чёрный",
        "True": "да",
        "False": "нет",
        "None": "не задано",
        "not set": "не задано",
    }
    text = str(value)
    for technical, readable in replacements.items():
        text = text.replace(technical, readable)
    return text


def _clean_message(message: str, section: str | None) -> str:
    text = message or "Нарушение правила профиля"
    if section:
        prefix = f"Раздел {section}:"
        if text.startswith(prefix):
            text = text[len(prefix):].strip()
    return _clean_value(text)


def count_by_severity(violations: list[Violation]) -> dict[str, int]:
    return {
        "error": sum(1 for violation in violations if violation.severity == "error"),
        "warning": sum(1 for violation in violations if violation.severity == "warning"),
    }


def group_violations_by_section(violations: list[Violation]) -> list[dict[str, Any]]:
    by_section: dict[str, list[Violation]] = OrderedDict()

    for violation in sorted(
        violations,
        key=lambda item: (
            _section_sort_key(item.source_section or ""),
            item.rule_id,
            _violation_sort_key(item),
        ),
    ):
        section = violation.source_section or "Без раздела"
        by_section.setdefault(section, []).append(violation)

    grouped_sections = []

    for section, section_violations in by_section.items():
        by_rule: dict[str, list[Violation]] = OrderedDict()
        for violation in section_violations:
            by_rule.setdefault(violation.rule_id, []).append(violation)

        rule_groups = []
        for rule_id, rule_violations in by_rule.items():
            sorted_violations = sorted(rule_violations, key=_violation_sort_key)
            first = sorted_violations[0]
            count = len(sorted_violations)
            count_word = _plural_ru(count, "нарушение", "нарушения", "нарушений")
            affected = _format_affected_locations(sorted_violations)

            severities = count_by_severity(sorted_violations)
            actual_values = {
                violation.actual
                for violation in sorted_violations
                if violation.actual is not None
            }
            expected_values = {violation.expected for violation in sorted_violations}

            rule_groups.append(
                {
                    "rule_id": rule_id,
                    "source_section": section,
                    "count": count,
                    "count_word": count_word,
                    "severity": first.severity,
                    "errors_count": severities["error"],
                    "warnings_count": severities["warning"],
                    "parameter": get_parameter_label(first.parameter),
                    "message": _clean_message(first.message, section),
                    "actual": _clean_value(next(iter(actual_values))) if len(actual_values) == 1 else "разные значения",
                    "expected": _clean_value(next(iter(expected_values))) if len(expected_values) == 1 else "разные значения",
                    "affected": affected,
                    "summary": f"{_clean_message(first.message, section)} — {count} {count_word}; {affected}",
                    "violations": sorted_violations,
                }
            )

        severities = count_by_severity(section_violations)
        grouped_sections.append(
            {
                "source_section": section,
                "count": len(section_violations),
                "errors_count": severities["error"],
                "warnings_count": severities["warning"],
                "rule_groups": rule_groups,
            }
        )

    return grouped_sections
