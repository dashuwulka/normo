from collections import Counter
from typing import Any

from app.models.document import ParsedDocxDocument, ParagraphData
from app.models.profile import Profile, Rule
from app.models.violation import Violation
from app.services.profile_utils import (
    collect_value_counters,
    get_allowed_values,
    get_main_text_paragraphs,
    get_parameter_strategy,
    get_paragraph_value,
    get_rules,
    is_value_allowed_by_profile,
    normalize_value,
)
from app.services.parameter_registry import (
    format_value as registry_format_value,
    get_parameter_label,
)




def _format_value(value: Any) -> str:
    """Форматирует значение для отчёта."""

    return registry_format_value(value)


def _get_allowed_values_from_profile(
    profile: Profile,
    target: str,
    parameter: str,
) -> list[Any]:
    """
    Возвращает список допустимых значений, собранный из правил `in`
    категории formatting. Используется как fallback-кандидат при подборе
    единого значения параметра.
    """

    allowed_values: list[Any] = []

    for rule in get_rules(profile, target, parameter):
        if rule.category != "formatting":
            continue

        if rule.operator == "in" and isinstance(rule.value, list):
            allowed_values.extend(rule.value)

    return [normalize_value(value) for value in allowed_values]


def _choose_default_valid_value(
    profile: Profile,
    target: str,
    parameter: str,
    consistency_rule: Rule,
) -> Any | None:
    """
    Выбирает значение по умолчанию, если преобладающее значение не подходит.

    Логика выбора одинакова для всех параметров: сначала пробуем preferred_value,
    затем fallback_value из стратегии; оба значения должны быть допустимы по профилю.
    Если ничего не подошло — берём первое значение из правил `in`.
    """

    parameter_strategy = get_parameter_strategy(consistency_rule, parameter)

    for key in ("preferred_value", "fallback_value"):
        candidate = parameter_strategy.get(key)

        if candidate is None:
            continue

        candidate = normalize_value(candidate)

        if is_value_allowed_by_profile(candidate, profile, target, parameter):
            return candidate

    # Исторический дефолт для абзацного отступа, если в стратегии ничего не задано.
    if parameter == "first_line_indent" and not parameter_strategy:
        candidate = normalize_value(1.25)
        if is_value_allowed_by_profile(candidate, profile, target, parameter):
            return candidate

    allowed_values = _get_allowed_values_from_profile(profile, target, parameter)

    if allowed_values:
        return allowed_values[0]

    return None


def _choose_consistent_value(
    counts: Counter,
    profile: Profile,
    target: str,
    parameter: str,
    consistency_rule: Rule,
) -> tuple[Any | None, str]:
    """
    Выбирает значение, к которому нужно привести параметр.

    Логика:
    1. Для line_spacing: если 1.5 встречается минимум в 30% абзацев и допустимо ГОСТом,
       выбираем 1.5.
    2. Иначе выбираем преобладающее допустимое значение.
    3. Если преобладающее значение недопустимо, выбираем fallback из профиля.
    """

    if not counts:
        return None, "нет данных для анализа"

    total = sum(counts.values())
    dominant_value, dominant_count = counts.most_common(1)[0]

    if parameter in {"alignment", "first_line_indent"}:
        configured_value = _choose_default_valid_value(
            profile=profile,
            target=target,
            parameter=parameter,
            consistency_rule=consistency_rule,
        )

        if configured_value is not None:
            return (
                configured_value,
                (
                    f"для параметра выбрано профильное значение "
                    f"{_format_value(configured_value)}"
                ),
            )

    if parameter == "line_spacing":
        line_spacing_strategy = get_parameter_strategy(consistency_rule, "line_spacing")
        preferred_value = normalize_value(
            line_spacing_strategy.get("preferred_value", 1.5)
        )
        preferred_threshold = float(
            line_spacing_strategy.get("preferred_threshold", 0.3)
        )

        preferred_count = counts.get(preferred_value, 0)
        preferred_ratio = preferred_count / total

        if (
            preferred_ratio >= preferred_threshold
            and is_value_allowed_by_profile(
                preferred_value,
                profile,
                target,
                parameter,
            )
        ):
            return (
                preferred_value,
                (
                    f"значение {_format_value(preferred_value)} используется "
                    f"в {preferred_count} из {total} абзацев "
                    f"и выбрано как предпочтительное"
                ),
            )

    if is_value_allowed_by_profile(dominant_value, profile, target, parameter):
        return (
            dominant_value,
            (
                f"значение {_format_value(dominant_value)} используется "
                f"в {dominant_count} из {total} абзацев"
            ),
        )

    fallback_value = _choose_default_valid_value(
        profile=profile,
        target=target,
        parameter=parameter,
        consistency_rule=consistency_rule,
    )

    if fallback_value is not None:
        return (
            fallback_value,
            (
                f"преобладающее значение {_format_value(dominant_value)} "
                f"не соответствует профилю, поэтому выбрано допустимое значение "
                f"{_format_value(fallback_value)}"
            ),
        )

    return (
        None,
        (
            f"преобладающее значение {_format_value(dominant_value)} "
            f"не соответствует профилю, а допустимое значение не задано"
        ),
    )


class ConsistencyChecker:
    """Проверка единообразия оформления документа."""

    def check(
        self,
        document: ParsedDocxDocument,
        profile: Profile,
    ) -> list[Violation]:
        violations: list[Violation] = []

        consistency_rules = [
            rule
            for rule in profile.rules
            if rule.category == "consistency"
            and rule.target == "main_text"
            and rule.operator == "consistent"
        ]

        if not consistency_rules:
            return violations

        main_text_paragraphs = get_main_text_paragraphs(document.paragraphs)

        if len(main_text_paragraphs) < 2:
            return violations

        # Собираем все параметры всех правил единообразия и считаем
        # их счётчики за один проход по абзацам.
        parameters_to_count: list[str] = []
        for rule in consistency_rules:
            if not isinstance(rule.value, list):
                continue
            for parameter in rule.value:
                if parameter not in parameters_to_count:
                    parameters_to_count.append(parameter)

        counters = collect_value_counters(main_text_paragraphs, parameters_to_count)

        for rule in consistency_rules:
            if not isinstance(rule.value, list):
                continue

            for parameter in rule.value:
                counts = counters.get(parameter, Counter())

                chosen_value, reason = _choose_consistent_value(
                    counts=counts,
                    profile=profile,
                    target="main_text",
                    parameter=parameter,
                    consistency_rule=rule,
                )

                if chosen_value is None:
                    continue

                parameter_label = get_parameter_label(parameter)
                expected_text = _format_value(chosen_value)

                for paragraph in main_text_paragraphs:
                    actual_value = normalize_value(
                        get_paragraph_value(paragraph, parameter)
                    )

                    if actual_value is None:
                        continue

                    if actual_value == chosen_value:
                        if parameter == "font_size":
                            for run in paragraph.runs:
                                if not run.text.strip() or run.font_size_pt is None:
                                    continue

                                run_value = normalize_value(run.font_size_pt)
                                if run_value == chosen_value:
                                    continue

                                run_actual_text = _format_value(run_value)
                                violations.append(
                                    Violation(
                                        rule_id=rule.id,
                source_section=rule.source_section,
                                        target="main_text",
                                        parameter=parameter,
                                        location=(
                                            f"Абзац {paragraph.index}, "
                                            f"фрагмент {run.index}"
                                        ),
                                        paragraph_index=paragraph.index,
                                        expected=expected_text,
                                        actual=run_actual_text,
                                        message=(
                                            f"{parameter_label}: фрагмент имеет "
                                            f"{run_actual_text}, требуется "
                                            f"единообразное значение {expected_text}. "
                                            "Прямое изменение кегля внутри основного "
                                            "текста конфликтует со стилем."
                                        ),
                                        severity="error",
                                        violation_type="consistency",
                                    )
                                )
                        continue

                    actual_text = _format_value(actual_value)

                    violations.append(
                        Violation(
                            rule_id=rule.id,
                source_section=rule.source_section,
                            target="main_text",
                            parameter=parameter,
                            location=f"Абзац {paragraph.index}",
                            paragraph_index=paragraph.index,
                            expected=expected_text,
                            actual=actual_text,
                            message=(
                                f"{parameter_label}: найдено {actual_text}, "
                                f"требуется единообразное значение {expected_text}. "
                                f"{reason}."
                            ),
                            severity="error",
                            violation_type="consistency",
                        )
                    )

        return violations


