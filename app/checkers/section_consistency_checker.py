from collections import Counter
from typing import Any

from app.models.document import ParsedDocxDocument, SectionData
from app.models.profile import Profile, Rule
from app.models.violation import Violation
from app.services.parameter_registry import (
    format_value as registry_format_value,
    get_parameter_label,
    get_section_value,
)


MARGIN_PARAMETERS = [
    "top_margin",
    "bottom_margin",
    "left_margin",
    "right_margin",
]


def _format_cm(value: float | None) -> str:
    """Форматирует значение в сантиметрах."""

    return registry_format_value(value, "cm")


def _normalize_margin(value: float | None) -> float | None:
    """Нормализует значение поля."""

    if value is None:
        return None

    return round(value, 2)


def _get_section_margin(section: SectionData, parameter: str) -> float | None:
    """Возвращает значение поля секции."""

    value = get_section_value(section, parameter)
    return float(value) if value is not None else None


def _get_margin_pattern(section: SectionData) -> tuple[float | None, float | None, float | None, float | None]:
    """Возвращает набор полей секции."""

    return (
        _normalize_margin(section.top_margin_cm),
        _normalize_margin(section.bottom_margin_cm),
        _normalize_margin(section.left_margin_cm),
        _normalize_margin(section.right_margin_cm),
    )


def _format_margin_pattern(pattern: tuple[float | None, float | None, float | None, float | None]) -> str:
    """Форматирует набор полей для отчёта."""

    top, bottom, left, right = pattern

    return (
        f"{get_parameter_label('top_margin')} — {_format_cm(top)}, "
        f"{get_parameter_label('bottom_margin')} — {_format_cm(bottom)}, "
        f"{get_parameter_label('left_margin')} — {_format_cm(left)}, "
        f"{get_parameter_label('right_margin')} — {_format_cm(right)}"
    )


def _get_rules_for_margin(
    profile: Profile,
    parameter: str,
) -> list[Rule]:
    """Возвращает правила ГОСТ-профиля для конкретного поля страницы."""

    return [
        rule
        for rule in profile.rules
        if rule.category == "formatting"
        and rule.target == "page"
        and rule.parameter == parameter
    ]


def _is_margin_value_valid(
    value: float | None,
    profile: Profile,
    parameter: str,
) -> bool:
    """Проверяет, попадает ли поле в допустимый диапазон профиля."""

    if value is None:
        return False

    rules = _get_rules_for_margin(profile, parameter)

    for rule in rules:
        if rule.operator == "min" and value < float(rule.value):
            return False

        if rule.operator == "max" and value > float(rule.value):
            return False

        if rule.operator == "equals" and round(value, 2) != round(float(rule.value), 2):
            return False

    return True


def _is_margin_pattern_valid(
    pattern: tuple[float | None, float | None, float | None, float | None],
    profile: Profile,
) -> bool:
    """Проверяет, все ли поля секции соответствуют профилю."""

    for parameter, value in zip(MARGIN_PARAMETERS, pattern):
        if not _is_margin_value_valid(value, profile, parameter):
            return False

    return True


def _get_fallback_pattern(rule: Rule | None) -> tuple[float, float, float, float]:
    """Возвращает стандартные поля для исправления, если большинство определить нельзя."""

    default_pattern = (2.5, 2.5, 2.5, 2.5)

    if rule is None or not rule.consistency_strategy:
        return default_pattern

    fallback = rule.consistency_strategy.get("fallback_margins")

    if not isinstance(fallback, dict):
        return default_pattern

    return (
        float(fallback.get("top_margin", 2.5)),
        float(fallback.get("bottom_margin", 2.5)),
        float(fallback.get("left_margin", 2.5)),
        float(fallback.get("right_margin", 2.5)),
    )


def _find_section_margin_consistency_rule(profile: Profile) -> Rule | None:
    """Находит правило единообразия полей секций."""

    for rule in profile.rules:
        if (
            rule.category == "consistency"
            and rule.target == "page"
            and rule.parameter == "margins_consistency"
            and rule.operator == "consistent"
        ):
            return rule

    return None


def _choose_target_margin_pattern(
    sections: list[SectionData],
    profile: Profile,
    rule: Rule | None,
) -> tuple[tuple[float, float, float, float], str]:
    """
    Выбирает набор полей, к которому нужно привести секции.

    Если большинство секций оформлено одинаково и правильно, выбирается это большинство.
    Если такого большинства нет, используется стандарт 2.5 см со всех сторон.
    """

    patterns = [_get_margin_pattern(section) for section in sections]

    valid_patterns = [
        pattern
        for pattern in patterns
        if _is_margin_pattern_valid(pattern, profile)
    ]

    counter = Counter(valid_patterns)

    if counter:
        dominant_pattern, dominant_count = counter.most_common(1)[0]

        # Большинство — строго больше половины секций.
        if dominant_count > len(sections) / 2:
            target_pattern = tuple(float(value) for value in dominant_pattern)
            reason = (
                f"выбран вариант большинства: {_format_margin_pattern(dominant_pattern)}; "
                f"он используется в {dominant_count} из {len(sections)} секций"
            )
            return target_pattern, reason

    fallback_pattern = _get_fallback_pattern(rule)
    reason = (
        "явное корректное большинство секций не определено, "
        f"поэтому выбран стандартный вариант: {_format_margin_pattern(fallback_pattern)}"
    )

    return fallback_pattern, reason


class SectionConsistencyChecker:
    """Проверка единообразия параметров секций документа."""

    def check(
        self,
        document: ParsedDocxDocument,
        profile: Profile,
    ) -> list[Violation]:
        violations: list[Violation] = []

        rule = _find_section_margin_consistency_rule(profile)

        if rule is None:
            return violations

        sections = document.sections

        if len(sections) < 2:
            return violations

        target_pattern, reason = _choose_target_margin_pattern(
            sections=sections,
            profile=profile,
            rule=rule,
        )

        expected_text = _format_margin_pattern(target_pattern)

        for section in sections:
            actual_pattern = _get_margin_pattern(section)

            if actual_pattern == target_pattern:
                continue

            violations.append(
                Violation(
                    rule_id=rule.id,
                source_section=rule.source_section,
                    target="page",
                    parameter="margins_consistency",
                    location=f"Секция {section.index}",
                    section_index=section.index,
                    expected=expected_text,
                    actual=_format_margin_pattern(actual_pattern),
                    message=(
                        "Поля секции отличаются от единого оформления документа. "
                        f"{reason}."
                    ),
                    severity="error",
                    violation_type="consistency",
                )
            )

        return violations
