"""
Общие утилиты для работы с профилями проверки.

Используются и в чекерах (ConsistencyChecker, FormatChecker),
и в автокорректоре. Вынесены в один модуль, чтобы избежать дублирования
и расхождения логики между местами, где правила профиля интерпретируются.

Профиль хранится как dict[str, Any] в consistency_strategy — это сделано
сознательно, чтобы пользователи могли загружать собственные методички
с произвольной структурой стратегии. Здесь только аккуратные геттеры,
а не строгая валидация схемы.
"""

from collections import Counter
from typing import Any, Iterable

from app.models.document import ParagraphData, ParagraphType
from app.models.profile import Profile, Rule
from app.services.parameter_registry import (
    PARAMETER_REGISTRY,
    get_paragraph_value as registry_get_paragraph_value,
)


PARAGRAPH_PARAMETER_GETTERS = {
    parameter_id: definition.getter
    for parameter_id, definition in PARAMETER_REGISTRY.items()
    if definition.target_kind == "paragraph" and definition.getter is not None
}


def normalize_value(value: Any) -> Any:
    """
    Нормализует значение для сравнения.

    Это нужно, чтобы 1.251 и 1.25 не считались разными значениями
    из-за особенностей хранения DOCX, а строки сравнивались без учёта регистра
    и пробелов по краям.
    """

    if value is None:
        return None

    if isinstance(value, float):
        return round(value, 2)

    if isinstance(value, str):
        return value.strip().lower()

    return value


def get_paragraph_value(paragraph: ParagraphData, parameter: str) -> Any:
    """Возвращает значение параметра абзаца по имени правила."""

    return registry_get_paragraph_value(paragraph, parameter)


def get_rules(profile: Profile, target: str, parameter: str) -> list[Rule]:
    """Возвращает все правила профиля для указанного объекта и параметра."""

    return [
        rule
        for rule in profile.rules
        if rule.target == target and rule.parameter == parameter
    ]


def get_rule_by_operator(
    profile: Profile,
    target: str,
    parameter: str,
    operator: str,
) -> Rule | None:
    """Возвращает первое правило с нужным оператором."""

    for rule in get_rules(profile, target, parameter):
        if rule.operator == operator:
            return rule

    return None


def get_equals_value(profile: Profile, target: str, parameter: str) -> Any | None:
    """Возвращает значение правила equals, если оно есть."""

    rule = get_rule_by_operator(profile, target, parameter, "equals")
    return rule.value if rule is not None else None


def get_min_value(profile: Profile, target: str, parameter: str) -> float | None:
    """Возвращает минимально допустимое значение, если оно есть."""

    rule = get_rule_by_operator(profile, target, parameter, "min")
    if rule is None:
        return None

    return float(rule.value)


def get_max_value(profile: Profile, target: str, parameter: str) -> float | None:
    """Возвращает максимально допустимое значение, если оно есть."""

    rule = get_rule_by_operator(profile, target, parameter, "max")
    if rule is None:
        return None

    return float(rule.value)


def get_allowed_values(profile: Profile, target: str, parameter: str) -> list[Any] | None:
    """Возвращает список допустимых значений из правила in, если оно есть."""

    rule = get_rule_by_operator(profile, target, parameter, "in")
    if rule is None:
        return None

    if isinstance(rule.value, list):
        return rule.value

    return None


def is_value_allowed_by_profile(
    value: Any,
    profile: Profile,
    target: str,
    parameter: str,
) -> bool:
    """
    Проверяет, удовлетворяет ли значение всем правилам профиля для параметра.

    Если для параметра нет правил, считаем значение допустимым.
    """

    if value is None:
        return False

    normalized_value = normalize_value(value)
    rules = get_rules(profile, target, parameter)

    if not rules:
        return True

    in_rules = [rule for rule in rules if rule.operator == "in"]
    other_rules = [rule for rule in rules if rule.operator != "in"]

    for rule in other_rules:
        if rule.operator == "equals":
            if normalize_value(rule.value) != normalized_value:
                return False

        elif rule.operator == "min":
            try:
                if float(normalized_value) < float(rule.value):
                    return False
            except (TypeError, ValueError):
                return False

        elif rule.operator == "max":
            try:
                if float(normalized_value) > float(rule.value):
                    return False
            except (TypeError, ValueError):
                return False

    if in_rules:
        for rule in in_rules:
            if not isinstance(rule.value, list):
                return False

            allowed_values = [normalize_value(item) for item in rule.value]
            if normalized_value in allowed_values:
                return True

        return False

    return True


# ---- consistency_strategy: безопасный доступ -------------------------------


def get_strategy(rule: Rule) -> dict[str, Any]:
    """Возвращает словарь стратегии правила или пустой словарь."""

    return rule.consistency_strategy or {}


def get_parameter_strategy(rule: Rule, parameter: str) -> dict[str, Any]:
    """Возвращает раздел стратегии для конкретного параметра."""

    strategy = get_strategy(rule)
    parameter_strategy = strategy.get(parameter)

    if isinstance(parameter_strategy, dict):
        return parameter_strategy

    return {}


def get_strategy_value(rule: Rule, parameter: str, key: str) -> Any | None:
    """
    Возвращает значение из стратегии: rule.consistency_strategy[parameter][key].

    Возвращает None, если что-то по пути отсутствует.
    """

    return get_parameter_strategy(rule, parameter).get(key)


def find_consistency_rule(
    profile: Profile,
    target: str,
    parameter: str,
) -> Rule | None:
    """Находит правило consistency для указанного объекта и параметра."""

    for rule in profile.rules:
        if (
            rule.category == "consistency"
            and rule.target == target
            and rule.parameter == parameter
            and rule.operator == "consistent"
        ):
            return rule

    return None


# ---- работа с абзацами основного текста ------------------------------------


def get_main_text_paragraphs(paragraphs: Iterable[ParagraphData]) -> list[ParagraphData]:
    """Возвращает непустые абзацы основного текста."""

    return [
        paragraph
        for paragraph in paragraphs
        if paragraph.paragraph_type == ParagraphType.MAIN_TEXT
        and paragraph.text.strip()
    ]


def collect_value_counters(
    paragraphs: list[ParagraphData],
    parameters: Iterable[str],
) -> dict[str, Counter]:
    """
    Собирает счётчики значений для нескольких параметров за один проход
    по абзацам. Возвращает словарь parameter -> Counter.
    """

    parameters_list = list(parameters)
    counters: dict[str, Counter] = {parameter: Counter() for parameter in parameters_list}

    for paragraph in paragraphs:
        for parameter in parameters_list:
            value = normalize_value(get_paragraph_value(paragraph, parameter))

            if value is None:
                continue

            counters[parameter][value] += 1

    return counters
