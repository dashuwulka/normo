from math import isclose
import re
from collections import Counter
from typing import Any

from app.checkers.typography_checker import TYPOGRAPHY_PARAMETERS
from app.models.document import (
    ParagraphData,
    ParsedDocxDocument,
    ParagraphType,
    SectionData,
)
from app.models.profile import Profile, Rule
from app.models.violation import Violation
from app.services.parameter_registry import (
    ADDITIONAL_TEXT_PARAGRAPH_TYPES,
    TARGET_TO_HEADING_LEVEL,
    TARGET_TO_PARAGRAPH_TYPE,
    format_value as registry_format_value,
    get_parameter_label,
    get_paragraph_value as registry_get_paragraph_value,
    get_section_value as registry_get_section_value,
)


TOLERANCE = 0.02
TOLERANCE_LENGTH_CM = 0.05
TOLERANCE_SIZE_PT = 0.5
TOLERANCE_RATIO = 0.05

RUN_LEVEL_PARAMETERS = {
    "font_size",
    "font_color",
    "underline",
    "strike",
    "double_strike",
    "small_caps",
    "all_caps",
    "character_spacing",
    "emphasis_character_style",
    "uppercase_emphasis",
}

ADDITIONAL_TEXT_TARGET = "additional_text"
HEADING_ROLE_TARGETS = {
    "structural_heading",
    "section_heading",
    "subsection_heading",
    "point_heading",
    "appendix_heading",
}

TABLE_CAPTION_ADDITIONAL_TEXT_PARAMETERS = {
    "bold",
    "italic",
    "font_size",
    "alignment",
    "line_spacing",
    "first_line_indent",
    "left_indent",
    "right_indent",
}

# Эти параметры проверяются отдельными чекерами или дают слишком много
# ложных срабатываний без визуальной вёрстки. FormatChecker не должен
# превращать их в общее "найдено: не определено".
FORMAT_CHECKER_DISABLED_DOCUMENT_PARAMETERS = {
    "empty_paragraph_between_content",
    "empty_paragraph_around_heading",
    "additional_spacing_limit",
    "required_document_structure",
    "references_min_count",
    "heading_english_not_allowed",
    "front_matter_page_numbers_hidden_until_intro",
    "toc_headings_match_text",
    "introduction_required_content",
    "conclusion_required_content",
}

EMPHASIS_METHOD_LABELS = {
    "bold": "полужирное",
    "italic": "курсив",
    "bold_italic": "полужирный курсив",
    "color": "цвет",
    "underline": "подчёркивание",
    "all_caps": "прописные буквы",
    "small_caps": "капитель",
    "strike": "зачёркивание",
    "character_spacing": "разрядка",
}

HEADING_NUMBERING_PATTERN = re.compile(
    r"^\s*(?P<number>\d+(?:\.\d+)*)(?P<dot>\.)?(?P<space>\s*)(?P<title>.*)$"
)
FIGURE_REFERENCE_PATTERN = re.compile(r"\b(?:рис\.|рисунок)\s*(\d+(?:\.\d+)*)", re.IGNORECASE)
TABLE_REFERENCE_PATTERN = re.compile(r"\b(?:табл\.|таблица)\s*(\d+(?:\.\d+)*)", re.IGNORECASE)
FIGURE_CAPTION_DASH_PATTERN = re.compile(r"^(Рис\.|Рисунок)\s+\d+(?:\.\d+)*\s*[\u2014-]")
TABLE_CONTINUATION_PATTERN = re.compile(r"\b(?:Продолжение|Окончание)\s+таблицы\b", re.IGNORECASE)




def _format_value(value: Any, unit: str | None = None) -> str:
    return registry_format_value(value, unit)


def _format_expected_value(value: Any, unit: str | None = None) -> str:
    if isinstance(value, list):
        return " или ".join(_format_value(item, unit) for item in value)

    return _format_value(value, unit)

def _is_recommended(rule: Rule) -> bool:
    return getattr(rule.modality, "value", rule.modality) == "recommended"


def _get_tolerance(unit: str | None = None) -> float:
    if unit == "cm":
        return TOLERANCE_LENGTH_CM

    if unit == "pt":
        return TOLERANCE_SIZE_PT

    if unit in {"ratio", "lines"}:
        return TOLERANCE_RATIO

    return TOLERANCE


def _compare_values(
    actual: Any,
    expected: Any,
    operator: str,
    unit: str | None = None,
) -> bool:
    """Сравнивает фактическое и ожидаемое значение по оператору правила."""

    if actual is None:
        return False

    if operator == "equals":
        if isinstance(actual, bool) or isinstance(expected, bool):
            return bool(actual) == bool(expected)

        if isinstance(actual, (int, float)) and isinstance(expected, (int, float)):
            return isclose(
                float(actual),
                float(expected),
                abs_tol=_get_tolerance(unit),
            )

        return str(actual).strip().lower() == str(expected).strip().lower()

    if operator == "min":
        return float(actual) >= float(expected) - _get_tolerance(unit)

    if operator == "max":
        return float(actual) <= float(expected) + _get_tolerance(unit)

    if operator == "in":
        if not isinstance(expected, list):
            return False

        for item in expected:
            if _compare_values(actual, item, "equals", unit):
                return True

        return False

    return False


def _get_section_value(section: SectionData, parameter: str) -> Any:
    return registry_get_section_value(section, parameter)


def _is_table_caption(paragraph: ParagraphData) -> bool:
    return (
        paragraph.paragraph_type == ParagraphType.CAPTION
        and paragraph.caption_kind == "table"
    )


def _make_violation(
    rule: Rule,
    actual: Any,
    paragraph: ParagraphData | None = None,
    section_index: int | None = None,
) -> Violation:
    """Создаёт объект нарушения с понятным сообщением."""

    parameter_label = get_parameter_label(rule.parameter)

    expected_text = _format_expected_value(rule.value, rule.unit)
    actual_text = _format_value(actual, rule.unit)
    is_warning = _is_recommended(rule)

    paragraph_index = paragraph.index if paragraph is not None else None

    if paragraph is not None:
        if paragraph.paragraph_type == ParagraphType.HEADING:
            location = f"Абзац {paragraph.index}, заголовок уровня {paragraph.heading_level}"
        else:
            location = f"Абзац {paragraph.index}"
    elif section_index is not None:
        location = f"Секция {section_index}"
    else:
        location = "Документ"

    return Violation(
        rule_id=rule.id,
                source_section=rule.source_section,
        target=rule.target,
        parameter=rule.parameter,
        location=location,
        paragraph_index=paragraph_index,
        section_index=section_index,
        expected=expected_text,
        actual=actual_text,
        severity="warning" if is_warning else "error",
        violation_type="recommendation" if is_warning else "formatting",
        message=(
            f"{parameter_label}: найдено {actual_text}, "
            f"требуется {expected_text}."
        ),
    )


def _check_rule_for_paragraph(rule: Rule, paragraph: ParagraphData) -> Violation | None:
    """Проверяет одно правило для одного абзаца."""

    if (
        rule.target == "heading"
        and rule.parameter == "bold"
        and paragraph.bold is not True
    ):
        strategy = rule.consistency_strategy or {}
        allowed_regular_levels = strategy.get("allow_regular_levels", [])
        if paragraph.heading_level in allowed_regular_levels:
            return None

    actual = registry_get_paragraph_value(paragraph, rule.parameter)

    if _compare_values(actual, rule.value, rule.operator, rule.unit):
        return None
    
    return _make_violation(rule, actual, paragraph=paragraph)


def _parse_heading_numbering(text: str) -> re.Match[str] | None:
    match = HEADING_NUMBERING_PATTERN.match(text)
    if match is None:
        return None

    title = match.group("title") or ""
    if not title.strip():
        return None

    return match


def _strip_heading_numbering(text: str) -> str:
    match = _parse_heading_numbering(text)
    if match is None:
        return text.strip()

    return (match.group("title") or "").strip()


def _starts_with_capital(text: str) -> bool | None:
    checked_text = _strip_heading_numbering(text)
    for char in checked_text:
        if char.isalpha():
            return char.isupper()

    return None


def _check_heading_numbering_terminal_dot_rule(
    rule: Rule,
    paragraph: ParagraphData,
) -> Violation | None:
    match = _parse_heading_numbering(paragraph.text)
    if match is None:
        return None

    has_dot = match.group("dot") == "."
    has_space_after_dot = bool(match.group("space"))

    if has_dot and has_space_after_dot:
        return None

    actual = "точка и пробел есть" if has_dot and has_space_after_dot else "точка или пробел отсутствует"

    return Violation(
        rule_id=rule.id,
        source_section=rule.source_section,
        target=rule.target,
        parameter=rule.parameter,
        location=f"Абзац {paragraph.index}, заголовок уровня {paragraph.heading_level}",
        paragraph_index=paragraph.index,
        expected="после нумерационной части стоит точка и пробел",
        actual=actual,
        message=(
            "В конце нумерационной части заголовка ставят точку, "
            "после неё должен быть пробел."
        ),
        severity="error",
        violation_type="formatting",
    )


def _check_heading_starts_with_capital_rule(
    rule: Rule,
    paragraph: ParagraphData,
) -> Violation | None:
    starts_with_capital = _starts_with_capital(paragraph.text)
    if starts_with_capital is None or starts_with_capital:
        return None

    checked_text = _strip_heading_numbering(paragraph.text)

    return Violation(
        rule_id=rule.id,
        source_section=rule.source_section,
        target=rule.target,
        parameter=rule.parameter,
        location=f"Абзац {paragraph.index}, заголовок уровня {paragraph.heading_level}",
        paragraph_index=paragraph.index,
        expected="первая буква заголовка прописная",
        actual=checked_text,
        message="Заголовок начинают с прописной буквы.",
        severity="error",
        violation_type="formatting",
    )


def _get_main_text_font_size(document: ParsedDocxDocument) -> float | None:
    sizes = [
        paragraph.font_size_pt
        for paragraph in document.paragraphs
        if paragraph.paragraph_type == ParagraphType.MAIN_TEXT
        and paragraph.text.strip()
        and paragraph.font_size_pt is not None
    ]

    if not sizes:
        return None

    return max(set(sizes), key=sizes.count)


def _get_expected_heading_font_sizes(
    document: ParsedDocxDocument,
) -> dict[int, float]:
    main_size = _get_main_text_font_size(document)
    if main_size is None:
        return {}

    levels = sorted({
        paragraph.heading_level
        for paragraph in document.paragraphs
        if paragraph.paragraph_type == ParagraphType.HEADING
        and paragraph.heading_level is not None
        and paragraph.text.strip()
    })

    if not levels:
        return {}

    if len(levels) == 1:
        return {levels[0]: main_size + 2}

    if len(levels) == 2:
        lower_level = max(levels)
        return {
            level: main_size + 2 * (lower_level - level + 1)
            for level in levels
        }

    lowest_level = max(levels)
    return {
        level: main_size + 2 * (lowest_level - level)
        for level in levels
    }


def _check_heading_font_size_hierarchy(
    rule: Rule,
    document: ParsedDocxDocument,
) -> list[Violation]:
    violations: list[Violation] = []
    expected_by_level = _get_expected_heading_font_sizes(document)

    if not expected_by_level:
        return violations

    for paragraph in document.paragraphs:
        if (
            paragraph.paragraph_type != ParagraphType.HEADING
            or paragraph.heading_level is None
            or not paragraph.text.strip()
        ):
            continue

        expected = expected_by_level.get(paragraph.heading_level)
        if expected is None or _compare_values(
            paragraph.font_size_pt,
            expected,
            "equals",
            "pt",
        ):
            continue

        violations.append(
            Violation(
                rule_id=rule.id,
                source_section=rule.source_section,
                target=rule.target,
                parameter=rule.parameter,
                location=f"Абзац {paragraph.index}, заголовок уровня {paragraph.heading_level}",
                paragraph_index=paragraph.index,
                expected=_format_value(expected, "pt"),
                actual=_format_value(paragraph.font_size_pt, "pt"),
                message=(
                    f"Кегль заголовка уровня {paragraph.heading_level}: найдено "
                    f"{_format_value(paragraph.font_size_pt, 'pt')}, требуется "
                    f"{_format_value(expected, 'pt')} по схеме соподчинённости с шагом 2 пт."
                ),
                severity="error",
                violation_type="formatting",
            )
        )

    return violations


def _profile_has_role_specific_heading_sizes(profile: Profile) -> bool:
    return any(
        rule.target in HEADING_ROLE_TARGETS
        and rule.parameter == "font_size"
        and getattr(rule, "enabled", True)
        for rule in profile.rules
    )


def _profile_has_role_specific_heading_spacing(profile: Profile) -> bool:
    return any(
        rule.target in HEADING_ROLE_TARGETS
        and rule.parameter in {"space_before", "space_after"}
        and getattr(rule, "enabled", True)
        for rule in profile.rules
    )


def _choose_main_text_first_line_indent(
    document: ParsedDocxDocument,
    profile: Profile,
) -> float:
    for rule in profile.rules:
        if (
            rule.category == "consistency"
            and rule.target == "main_text"
            and rule.operator == "consistent"
            and isinstance(rule.value, list)
            and "first_line_indent" in rule.value
        ):
            strategy = rule.consistency_strategy or {}
            parameter_strategy = strategy.get("first_line_indent")
            if isinstance(parameter_strategy, dict):
                preferred = parameter_strategy.get("preferred_value")
                fallback = parameter_strategy.get("fallback_value")
                if preferred is not None:
                    return float(preferred)
                if fallback is not None:
                    return float(fallback)

    values = [
        round(paragraph.first_line_indent_cm, 2)
        for paragraph in document.paragraphs
        if paragraph.paragraph_type == ParagraphType.MAIN_TEXT
        and paragraph.text.strip()
        and paragraph.first_line_indent_cm is not None
    ]

    if values:
        return max(set(values), key=values.count)

    return 1.25


def _get_allowed_heading_first_line_indents(
    paragraph: ParagraphData,
    document: ParsedDocxDocument,
    profile: Profile,
) -> list[float]:
    if paragraph.alignment == "center":
        return [0.0]

    return [0.0, _choose_main_text_first_line_indent(document, profile)]


def _check_heading_indent_policy_rule(
    rule: Rule,
    paragraph: ParagraphData,
    document: ParsedDocxDocument,
    profile: Profile,
) -> Violation | None:
    first = round(paragraph.first_line_indent_cm or 0.0, 2)
    left = round(paragraph.left_indent_cm or 0.0, 2)
    right = round(paragraph.right_indent_cm or 0.0, 2)
    main_indent = _choose_main_text_first_line_indent(document, profile)

    left_right_ok = (
        isclose(left, 0.0, abs_tol=TOLERANCE_LENGTH_CM)
        and isclose(right, 0.0, abs_tol=TOLERANCE_LENGTH_CM)
    )

    if paragraph.alignment == "center":
        if (
            left_right_ok
            and isclose(first, 0.0, abs_tol=TOLERANCE_LENGTH_CM)
        ):
            return None

        return Violation(
            rule_id=rule.id,
            source_section=rule.source_section,
            target=rule.target,
            parameter=rule.parameter,
            location=f"Абзац {paragraph.index}, заголовок уровня {paragraph.heading_level}",
            paragraph_index=paragraph.index,
            expected="first_line_indent=0 см, left_indent=0 см, right_indent=0 см",
            actual=(
                f"first_line_indent={_format_value(first, 'cm')}, "
                f"left_indent={_format_value(left, 'cm')}, "
                f"right_indent={_format_value(right, 'cm')}"
            ),
            message=(
                "Раздел 7.6: заголовок, выровненный по центру, должен быть "
                "без абзацных уступов и втяжек."
            ),
            severity="error",
            violation_type="formatting",
        )

    allowed_values = [0.0, main_indent]

    first_ok = any(
        isclose(first, allowed, abs_tol=TOLERANCE_LENGTH_CM)
        for allowed in allowed_values
    )
    if left_right_ok and first_ok:
        return None

    expected = ", ".join(_format_value(value, "cm") for value in allowed_values)

    return Violation(
        rule_id=rule.id,
        source_section=rule.source_section,
        target=rule.target,
        parameter=rule.parameter,
        location=f"Абзац {paragraph.index}, заголовок уровня {paragraph.heading_level}",
        paragraph_index=paragraph.index,
        expected=expected,
        actual=(
            f"first_line_indent={_format_value(first, 'cm')}, "
            f"left_indent={_format_value(left, 'cm')}, "
            f"right_indent={_format_value(right, 'cm')}"
        ),
        message=(
            "Раздел 7.6: заголовок, выровненный влево, должен быть без "
            "отступов либо с абзацным отступом, равным основному тексту."
        ),
        severity="error",
        violation_type="formatting",
    )


def _check_heading_level_1_page_break_before_rule(
    rule: Rule,
    paragraph: ParagraphData,
    document: ParsedDocxDocument,
) -> Violation | None:
    if paragraph.heading_level != 1:
        return None

    if paragraph.page_break_before is True:
        return None

    previous = next(
        (item for item in document.paragraphs if item.index == paragraph.index - 1),
        None,
    )
    if paragraph.has_page_break or (previous is not None and previous.has_page_break):
        return None

    return Violation(
        rule_id=rule.id,
        source_section=rule.source_section,
        target=rule.target,
        parameter=rule.parameter,
        location=f"Абзац {paragraph.index}, заголовок уровня {paragraph.heading_level}",
        paragraph_index=paragraph.index,
        expected='начинать раздел с новой страницы',
        actual="разрыв перед заголовком не найден",
        message=(
            "Заголовок крупного раздела должен начинаться с новой страницы. "
            f"Абзац {paragraph.index}: не найден параметр абзаца или разрыв страницы перед заголовком."
        ),
        severity="error",
        violation_type="formatting",
    )


def _check_heading_line_spacing_rule(
    rule: Rule,
    document: ParsedDocxDocument,
) -> list[Violation]:
    main_spacing_values = [
        paragraph.line_spacing
        for paragraph in document.paragraphs
        if paragraph.paragraph_type == ParagraphType.MAIN_TEXT
        and paragraph.text.strip()
        and paragraph.line_spacing is not None
    ]

    if not main_spacing_values:
        return []

    main_spacing = max(set(main_spacing_values), key=main_spacing_values.count)
    violations: list[Violation] = []

    for paragraph in document.paragraphs:
        if (
            paragraph.paragraph_type != ParagraphType.HEADING
            or not paragraph.text.strip()
            or paragraph.line_spacing is None
            or paragraph.line_spacing <= main_spacing + TOLERANCE_RATIO
        ):
            continue

        violations.append(
            Violation(
                rule_id=rule.id,
                source_section=rule.source_section,
                target=rule.target,
                parameter=rule.parameter,
                location=f"Абзац {paragraph.index}, заголовок уровня {paragraph.heading_level}",
                paragraph_index=paragraph.index,
                expected=f"не больше интерлиньяжа основного текста ({_format_value(main_spacing)})",
                actual=_format_value(paragraph.line_spacing),
                message="Интерлиньяж заголовка не должен быть больше интерлиньяжа основного текста.",
                severity="error",
                violation_type="formatting",
            )
        )

    return violations


def _check_heading_spacing_order_rule(
    rule: Rule,
    document: ParsedDocxDocument,
) -> list[Violation]:
    violations: list[Violation] = []

    for paragraph in document.paragraphs:
        if paragraph.paragraph_type != ParagraphType.HEADING or not paragraph.text.strip():
            continue

        before = paragraph.space_before_pt or 0.0
        after = paragraph.space_after_pt or 0.0

        if before > after and after >= 0:
            continue

        violations.append(
            Violation(
                rule_id=rule.id,
                source_section=rule.source_section,
                target=rule.target,
                parameter=rule.parameter,
                location=f"Абзац {paragraph.index}, заголовок уровня {paragraph.heading_level}",
                paragraph_index=paragraph.index,
                expected="интервал перед заголовком больше интервала после",
                actual=f"перед {before:g} пт, после {after:g} пт",
                message="Для отделения заголовка интервал над ним должен быть больше интервала под ним.",
                severity="error",
                violation_type="formatting",
            )
        )

    return violations


def _is_heading_all_caps(text: str) -> bool:
    letters = [char for char in text if char.isalpha()]
    if len(letters) < 8:
        return False

    return all(not char.islower() for char in letters)


def _check_heading_all_caps_rule(
    rule: Rule,
    document: ParsedDocxDocument,
) -> list[Violation]:
    violations: list[Violation] = []

    for paragraph in document.paragraphs:
        if (
            paragraph.paragraph_type != ParagraphType.HEADING
            or not paragraph.text.strip()
            or not _is_heading_all_caps(paragraph.text)
        ):
            continue

        violations.append(
            Violation(
                rule_id=rule.id,
                source_section=rule.source_section,
                target=rule.target,
                parameter=rule.parameter,
                location=f"Абзац {paragraph.index}, заголовок уровня {paragraph.heading_level}",
                paragraph_index=paragraph.index,
                expected="не весь заголовок прописными буквами",
                actual=paragraph.text.strip(),
                message="Весь текст заголовка прописными буквами не набирают.",
                severity="error",
                violation_type="formatting",
            )
        )

    return violations


def _check_heading_color_only_rule(
    rule: Rule,
    document: ParsedDocxDocument,
) -> list[Violation]:
    violations: list[Violation] = []
    expected_sizes = _get_expected_heading_font_sizes(document)

    for paragraph in document.paragraphs:
        if paragraph.paragraph_type != ParagraphType.HEADING or not paragraph.text.strip():
            continue

        runs = [run for run in paragraph.runs if run.text.strip()]
        if not runs:
            continue

        all_colored = all(_is_non_black_color(run.font_color) for run in runs)
        expected_size = expected_sizes.get(paragraph.heading_level or 0)
        has_size_emphasis = (
            expected_size is not None
            and paragraph.font_size_pt is not None
            and isclose(paragraph.font_size_pt, expected_size, abs_tol=TOLERANCE_SIZE_PT)
        )

        if not (all_colored and not paragraph.bold and not has_size_emphasis):
            continue

        violations.append(
            Violation(
                rule_id=rule.id,
                source_section=rule.source_section,
                target=rule.target,
                parameter=rule.parameter,
                location=f"Абзац {paragraph.index}, заголовок уровня {paragraph.heading_level}",
                paragraph_index=paragraph.index,
                expected="заголовок выделен жирностью и кеглем, не только цветом",
                actual="выделение только цветом",
                message="Выделение заголовка только цветом недопустимо.",
                severity="error",
                violation_type="formatting",
            )
        )

    return violations


def _is_non_black_color(color: str | None) -> bool:
    if color is None:
        return False

    return color.upper() != "000000"


def _non_empty_runs(paragraph: ParagraphData):
    return [run for run in paragraph.runs if run.text.strip()]


def _is_whole_paragraph_colored(paragraph: ParagraphData) -> bool:
    runs = _non_empty_runs(paragraph)
    if not runs:
        return False

    colors = {run.font_color for run in runs}
    return len(colors) == 1 and next(iter(colors)) not in {None, "000000"}


def _run_location(paragraph: ParagraphData, run_index: int) -> str:
    if paragraph.paragraph_type == ParagraphType.HEADING:
        return f"Абзац {paragraph.index}, заголовок уровня {paragraph.heading_level}, фрагмент {run_index}"

    return f"Абзац {paragraph.index}, фрагмент {run_index}"


def _make_run_violation(
    rule: Rule,
    paragraph: ParagraphData,
    run_index: int,
    actual: str,
    message: str,
) -> Violation:
    is_warning = _is_recommended(rule)

    return Violation(
        rule_id=rule.id,
                source_section=rule.source_section,
        target=rule.target,
        parameter=rule.parameter,
        location=_run_location(paragraph, run_index),
        paragraph_index=paragraph.index,
        expected=_format_expected_value(rule.value, rule.unit),
        actual=actual,
        severity="warning" if is_warning else "error",
        violation_type="recommendation" if is_warning else "formatting",
        message=message,
    )


def _has_uppercase_emphasis(text: str) -> bool:
    known_short_terms = {"ГОСТ", "DOCX", "PDF", "XML", "JSON", "HTML", "CSS", "API"}
    words = re.findall(r"[A-Z\u0410-\u042f\u0401]{4,}", text)

    long_words = [
        word
        for word in words
        if word not in known_short_terms and len(word) >= 8
    ]

    return bool(long_words)


def _check_run_rule_for_paragraph(
    rule: Rule,
    paragraph: ParagraphData,
) -> list[Violation]:
    violations: list[Violation] = []

    for run in paragraph.runs:
        if not run.text.strip():
            continue

        if rule.parameter == "font_size":
            if run.font_size_pt is None:
                continue

            if _compare_values(run.font_size_pt, rule.value, rule.operator, rule.unit):
                continue

            paragraph_size_is_wrong = (
                paragraph.font_size_pt is not None
                and not _compare_values(paragraph.font_size_pt, rule.value, rule.operator, rule.unit)
            )
            if paragraph_size_is_wrong:
                continue

            violations.append(
                _make_run_violation(
                    rule,
                    paragraph,
                    run.index,
                    _format_value(run.font_size_pt, rule.unit),
                    (
                        "Размер шрифта отдельного фрагмента основного текста "
                        "выходит за допустимый диапазон ГОСТ."
                    ),
                )
            )

        elif rule.parameter == "font_color":
            # ГОСТ 6.3: цветной шрифт можно использовать как способ выделения по 6.4.
            # Поэтому ругаемся только когда ВЕСЬ абзац оформлен цветом как основной,
            # а не на отдельный цветной фрагмент.
            if _is_recommended(rule) and not _is_whole_paragraph_colored(paragraph):
                continue

            if _is_non_black_color(run.font_color):
                violations.append(
                    _make_run_violation(
                        rule,
                        paragraph,
                        run.index,
                        run.font_color or "не определено",
                        "Рекомендуемый цвет шрифта — чёрный. Обнаружен другой цвет; проверьте обоснованность выделения.",
                    )
                )
                # Одного сообщения на абзац достаточно, не дублируем для каждого run.
                if _is_recommended(rule):
                    break

        elif rule.parameter == "underline" and run.underline:
            violations.append(
                _make_run_violation(
                    rule,
                    paragraph,
                    run.index,
                    "подчёркивание",
                    "Подчёркивание как способ выделения нежелательно.",
                )
            )

        elif rule.parameter == "strike" and run.strike:
            violations.append(
                _make_run_violation(
                    rule,
                    paragraph,
                    run.index,
                    "зачёркивание",
                    "Зачёркивание как способ выделения не допускается.",
                )
            )

        elif rule.parameter == "double_strike" and run.double_strike:
            violations.append(
                _make_run_violation(
                    rule,
                    paragraph,
                    run.index,
                    "двойное зачёркивание",
                    "Двойное зачёркивание как способ выделения не допускается.",
                )
            )

        elif rule.parameter == "small_caps" and run.small_caps:
            violations.append(
                _make_run_violation(
                    rule,
                    paragraph,
                    run.index,
                    "капитель",
                    "Капитель как способ выделения не допускается.",
                )
            )

        elif rule.parameter == "all_caps" and run.all_caps:
            violations.append(
                _make_run_violation(
                    rule,
                    paragraph,
                    run.index,
                    "свойство all caps",
                    "Выделение прописными буквами не допускается.",
                )
            )

        elif rule.parameter == "character_spacing" and run.character_spacing not in {None, 0}:
            violations.append(
                _make_run_violation(
                    rule,
                    paragraph,
                    run.index,
                    str(run.character_spacing),
                    "Разрядка как способ выделения не допускается.",
                )
            )

        elif rule.parameter == "uppercase_emphasis" and _has_uppercase_emphasis(run.text):
            violations.append(
                _make_run_violation(
                    rule,
                    paragraph,
                    run.index,
                    run.text.strip(),
                    "В основном тексте найден длинный фрагмент прописными буквами. Проверьте, не используется ли он как недопустимый способ выделения.",
                )
            )

        elif rule.parameter == "emphasis_character_style":
            has_emphasis = bool(run.bold or run.italic or _is_non_black_color(run.font_color))
            if has_emphasis and run.has_direct_formatting and not run.has_character_style:
                violations.append(
                    _make_run_violation(
                        rule,
                        paragraph,
                        run.index,
                        "прямое форматирование",
                        "Выделение рекомендуется выполнять символьным стилем, а не прямым форматированием.",
                    )
                )

    return violations


def _check_mixed_font_sizes_in_paragraphs(
    rule: Rule,
    document: ParsedDocxDocument,
) -> list[Violation]:
    violations: list[Violation] = []

    for paragraph in document.paragraphs:
        if paragraph.paragraph_type in {ParagraphType.TITLE_PAGE, ParagraphType.EMPTY, ParagraphType.TABLE_CELL}:
            continue
        if not paragraph.text.strip():
            continue

        sizes = [
            round(float(run.font_size_pt), 1)
            for run in paragraph.runs
            if run.text.strip() and run.font_size_pt is not None
        ]
        unique_sizes = sorted(set(sizes))
        if len(unique_sizes) <= 1:
            continue

        dominant_size, dominant_count = Counter(sizes).most_common(1)[0]
        fragments = [
            run.text.strip()[:35]
            for run in paragraph.runs
            if run.text.strip()
            and run.font_size_pt is not None
            and not isclose(float(run.font_size_pt), dominant_size, abs_tol=TOLERANCE_SIZE_PT)
        ]
        fragment_preview = "; ".join(f"«{fragment}»" for fragment in fragments[:3])

        violations.append(
            Violation(
                rule_id=rule.id,
                source_section=rule.source_section,
                target=rule.target,
                parameter=rule.parameter,
                location=f"Абзац {paragraph.index}",
                paragraph_index=paragraph.index,
                expected=f"один размер шрифта в абзаце, обычно {dominant_size:g} пт",
                actual=", ".join(f"{size:g} пт" for size in unique_sizes),
                message=(
                    f"В одном абзаце использованы разные размеры шрифта: "
                    f"{', '.join(f'{size:g} пт' for size in unique_sizes)}. "
                    f"Основной размер в абзаце — {dominant_size:g} пт "
                    f"({dominant_count} фрагм.)."
                    + (f" Отличающиеся фрагменты: {fragment_preview}." if fragment_preview else "")
                ),
                severity="error",
                violation_type="formatting",
            )
        )

    return violations


GROUPED_TABLE_CELL_PARAMETERS = {
    "font_size",
    "alignment",
    "line_spacing",
    "first_line_indent",
    "left_indent",
    "right_indent",
}


def _is_grouped_table_cell_rule(rule: Rule) -> bool:
    return rule.target == "table_cell" and rule.parameter in GROUPED_TABLE_CELL_PARAMETERS


def _check_grouped_table_cell_rule(
    rule: Rule,
    document: ParsedDocxDocument,
) -> list[Violation]:
    violations: list[Violation] = []
    bad_by_table: dict[int, dict[str, Any]] = {}

    for paragraph in document.paragraphs:
        if paragraph.paragraph_type != ParagraphType.TABLE_CELL:
            continue
        if not paragraph.text.strip():
            continue

        if rule.parameter == "alignment" and paragraph.table_row_index == 0:
            continue

        actual = registry_get_paragraph_value(paragraph, rule.parameter)
        if _compare_values(actual, rule.value, rule.operator, rule.unit):
            continue

        table_index = paragraph.table_index if paragraph.table_index is not None else -1
        bucket = bad_by_table.setdefault(
            table_index,
            {
                "count": 0,
                "first_paragraph_index": paragraph.index,
                "values": {},
            },
        )
        bucket["count"] += 1
        bucket["first_paragraph_index"] = min(bucket["first_paragraph_index"], paragraph.index)
        actual_text = _format_value(actual, rule.unit)
        bucket["values"][actual_text] = bucket["values"].get(actual_text, 0) + 1

    parameter_label = get_parameter_label(rule.parameter)
    expected_text = _format_expected_value(rule.value, rule.unit)
    for table_index, data in sorted(bad_by_table.items()):
        label = _table_label(table_index) if table_index >= 0 else "Таблица"
        display_label = _table_display_label(document, table_index) if table_index >= 0 else label
        values_text = ", ".join(
            f"{value} — {count} яч."
            for value, count in sorted(data["values"].items())
        )
        count = data["count"]
        violations.append(
            _make_document_violation(
                rule,
                label,
                values_text,
                expected_text,
                (
                    f"{parameter_label.capitalize()} в таблице не соответствует профилю проверки. "
                    f"{display_label}: найдено {count} яч. с отличающимся оформлением "
                    f"({values_text}); требуется {expected_text}."
                ),
                data["first_paragraph_index"],
                severity="warning" if _is_recommended(rule) else "error",
            )
        )

    return violations


def _get_run_emphasis_methods(paragraph: ParagraphData) -> set[str]:
    methods: set[str] = set()

    for run in paragraph.runs:
        if not run.text.strip():
            continue

        if run.bold and run.italic:
            methods.add("bold_italic")
        elif run.bold:
            methods.add("bold")
        elif run.italic:
            methods.add("italic")

        if _is_non_black_color(run.font_color):
            methods.add("color")

        if run.underline:
            methods.add("underline")

        if run.strike or run.double_strike:
            methods.add("strike")

        if run.small_caps:
            methods.add("small_caps")

        if run.all_caps or _has_uppercase_emphasis(run.text):
            methods.add("all_caps")

        if run.character_spacing not in {None, 0}:
            methods.add("character_spacing")

    return methods


def _check_emphasis_methods_consistency(
    rule: Rule,
    document: ParsedDocxDocument,
) -> list[Violation]:
    methods: set[str] = set()

    for paragraph in document.paragraphs:
        if paragraph.paragraph_type != ParagraphType.MAIN_TEXT:
            continue

        methods.update(_get_run_emphasis_methods(paragraph))

    if len(methods) <= 1:
        return []

    method_text = ", ".join(
        EMPHASIS_METHOD_LABELS.get(method, method)
        for method in sorted(methods)
    )

    return [
        Violation(
            rule_id=rule.id,
                source_section=rule.source_section,
            target=rule.target,
            parameter=rule.parameter,
            location="Документ",
            expected="по возможности один способ выделения",
            actual=method_text,
            message=(
                f"В документе используется несколько способов выделения: {method_text}. "
                "ГОСТ рекомендует по возможности применять единый способ; проверьте обоснованность."
            ),
            severity="warning",
            violation_type="recommendation",
        )
    ]


def _check_rule_for_section(rule: Rule, section: SectionData) -> Violation | None:
    """Проверяет одно правило для одной секции документа."""

    if rule.parameter == "continuous_page_numbering":
        first_section_bad_start = section.index == 0 and section.page_number_start not in {
            None,
            1,
        }
        restarted_later = section.index > 0 and section.page_number_start is not None

        if not first_section_bad_start and not restarted_later:
            return None

        actual = (
            f"нумерация начинается с {section.page_number_start}"
            if section.page_number_start is not None
            else "перезапуск нумерации"
        )

        return Violation(
            rule_id=rule.id,
                source_section=rule.source_section,
            target=rule.target,
            parameter=rule.parameter,
            location=f"Секция {section.index}",
            section_index=section.index,
            expected="непрерывная нумерация",
            actual=actual,
            message=(
                "Нумерация страниц должна быть непрерывной: титульная страница "
                "включается в общий счёт, даже если номер на ней не отображается."
            ),
            severity="error",
            violation_type="formatting",
        )

    if rule.parameter == "page_number_alignment" and not section.has_footer_page_number:
        return None

    actual = _get_section_value(section, rule.parameter)

    if rule.parameter == "page_number_area" and not section.has_page_number:
        return Violation(
            rule_id=rule.id,
                source_section=rule.source_section,
            target=rule.target,
            parameter=rule.parameter,
            location=f"Секция {section.index}",
            section_index=section.index,
            expected="нумерация страниц в нижнем колонтитуле",
            actual="нумерация страниц отсутствует",
            message=(
                f"Раздел 5.2: нумерация страниц в секции отсутствует. "
                f"Секция {section.index}: поле PAGE не найдено в колонтитулах."
            ),
            severity="error",
            violation_type="formatting",
        )

    if _compare_values(actual, rule.value, rule.operator, rule.unit):
        return None

    if rule.parameter == "page_number_area":
        return Violation(
            rule_id=rule.id,
            source_section=rule.source_section,
            target=rule.target,
            parameter=rule.parameter,
            location=f"Секция {section.index}",
            section_index=section.index,
            expected="footer",
            actual=str(actual),
            message=(
                "Раздел 5.2: колонцифры должны размещаться в нижнем поле "
                f"страницы. Секция {section.index}: номер страницы найден в "
                f"{actual}, требуется footer."
            ),
            severity="error",
            violation_type="formatting",
        )

    if rule.parameter == "footer_distance":
        return Violation(
            rule_id=rule.id,
            source_section=rule.source_section,
            target=rule.target,
            parameter=rule.parameter,
            location=f"Секция {section.index}",
            section_index=section.index,
            expected=_format_value(rule.value, rule.unit),
            actual=_format_value(actual, rule.unit),
            message=(
                "Раздел 5.2: колонцифры должны располагаться на расстоянии "
                f"не менее 1 см от края листа. Секция {section.index}: найдено "
                f"{_format_value(actual, rule.unit)}."
            ),
            severity="error",
            violation_type="formatting",
        )

    return _make_violation(rule, actual, section_index=section.index)


def _check_header_short_title_rule(
    rule: Rule,
    section: SectionData,
) -> Violation | None:
    if not section.has_header:
        return None

    return Violation(
        rule_id=rule.id,
                source_section=rule.source_section,
        target=rule.target,
        parameter=rule.parameter,
        location=f"Секция {section.index}",
        section_index=section.index,
        expected="краткое название документа",
        actual=section.header_text,
        message=(
            "В верхнем колонтитуле найден текст. Проверьте, что в нём "
            "указано краткое название документа."
        ),
        severity="warning",
        violation_type="recommendation",
    )


def _find_content_bounds(document: ParsedDocxDocument) -> tuple[int | None, int | None]:
    """
    Возвращает индексы первого и последнего непустого содержательного абзаца.

    Содержательным считается непустой абзац, не являющийся частью титульного листа.
    Если таких абзацев нет, возвращается (None, None).
    """

    first_index: int | None = None
    last_index: int | None = None

    for paragraph in document.paragraphs:
        if paragraph.paragraph_type in {ParagraphType.TITLE_PAGE, ParagraphType.TABLE_CELL}:
            continue

        if not paragraph.text.strip():
            continue

        if first_index is None:
            first_index = paragraph.index

        last_index = paragraph.index

    return first_index, last_index


def _document_has_title_page(document: ParsedDocxDocument) -> bool:
    return any(
        paragraph.paragraph_type == ParagraphType.TITLE_PAGE
        for paragraph in document.paragraphs
    )


def _check_first_page_no_page_number_rule(
    rule: Rule,
    document: ParsedDocxDocument,
) -> list[Violation]:
    if not _document_has_title_page(document) or not document.sections:
        return []

    first_section = document.sections[0]
    visible_by_shared_footer = (
        not first_section.different_first_page_header_footer
        and first_section.has_page_number
    )
    visible_by_first_page_part = first_section.has_first_page_page_number

    if not visible_by_shared_footer and not visible_by_first_page_part:
        return []

    actual = (
        first_section.first_page_page_number_area
        if visible_by_first_page_part
        else first_section.page_number_area
    )

    return [
        Violation(
            rule_id=rule.id,
                source_section=rule.source_section,
            target=rule.target,
            parameter=rule.parameter,
            location="Первая страница",
            section_index=0,
            expected="номер на титульной странице не отображается",
            actual=f"номер отображается в области: {actual or 'не определено'}",
            message=(
                "Раздел 5.3: обнаружен титульный лист, но номер первой "
                "страницы визуально отображается или может отображаться через "
                "общий колонтитул. Титульный лист должен входить в общий счет "
                "страниц, при этом колонцифру на нем не отображают."
            ),
            severity="error",
            violation_type="formatting",
        )
    ]


def _is_introduction_paragraph(paragraph: ParagraphData) -> bool:
    text = paragraph.text.strip().lower().replace("ё", "е")
    text = re.sub(r"^\d+(?:\.\d+)*\.?\s+", "", text)
    return paragraph.logical_section == "introduction" or text == "введение"


def _check_front_matter_page_numbers_hidden_until_intro_rule(
    rule: Rule,
    document: ParsedDocxDocument,
) -> list[Violation]:
    if not document.sections:
        return []

    intro_paragraph = next(
        (paragraph for paragraph in document.paragraphs if _is_introduction_paragraph(paragraph)),
        None,
    )
    if intro_paragraph is None:
        return []

    front_matter_paragraphs = [
        paragraph
        for paragraph in document.paragraphs
        if paragraph.index < intro_paragraph.index
        and paragraph.paragraph_type != ParagraphType.TABLE_CELL
        and paragraph.text.strip()
    ]
    if not front_matter_paragraphs:
        return []

    first_section = document.sections[0]
    violations: list[Violation] = []

    visible_before_intro = (
        first_section.has_first_page_page_number
        or (first_section.has_page_number and not first_section.different_first_page_header_footer)
    )
    only_first_page_hidden = (
        first_section.has_page_number
        and first_section.different_first_page_header_footer
        and not first_section.has_first_page_page_number
        and len(front_matter_paragraphs) > 12
    )

    if visible_before_intro or only_first_page_hidden:
        if first_section.has_first_page_page_number:
            actual = f"номер есть в колонтитуле первой страницы: {first_section.first_page_page_number_area or 'не определено'}"
        elif first_section.has_page_number and not first_section.different_first_page_header_footer:
            actual = f"общий колонтитул с PAGE виден до введения: {first_section.page_number_area or 'не определено'}"
        else:
            actual = "скрытие задано только для первой страницы; до введения есть несколько начальных блоков"

        violations.append(
            Violation(
                rule_id=rule.id,
                source_section=rule.source_section,
                target=rule.target,
                parameter=rule.parameter,
                location="Документ",
                section_index=0,
                paragraph_index=intro_paragraph.index,
                expected="номера скрыты до раздела «Введение», а с «Введения» отображаются",
                actual=actual,
                message=(
                    f"Раздел {rule.source_section}: до раздела «Введение» номера страниц не должны "
                    f"отображаться, но должны входить в общий счёт. Абзац {intro_paragraph.index}: "
                    "найдено начало раздела «Введение»; проверьте колонтитулы начальных страниц."
                ),
                severity="error",
                violation_type="formatting",
            )
        )

    if not first_section.has_footer_page_number:
        actual_area = first_section.page_number_area or "нумерация не найдена"
        violations.append(
            Violation(
                rule_id=rule.id,
                source_section=rule.source_section,
                target=rule.target,
                parameter=rule.parameter,
                location="Документ",
                section_index=0,
                paragraph_index=intro_paragraph.index,
                expected="видимая нумерация с «Введения» в нижнем колонтитуле",
                actual=actual_area,
                message=(
                    f"Раздел {rule.source_section}: с раздела «Введение» нумерация должна "
                    f"продолжаться и отображаться внизу страницы. Абзац {intro_paragraph.index}: "
                    f"найдено «Введение», но поле PAGE в нижнем колонтитуле не найдено."
                ),
                severity="error",
                violation_type="formatting",
            )
        )

    return violations


def _normalize_requirement_text(text: str) -> str:
    return " ".join(text.lower().replace("ё", "е").split())


def _check_required_document_structure_rule(
    rule: Rule,
    document: ParsedDocxDocument,
) -> list[Violation]:
    expected_items = rule.value if isinstance(rule.value, list) else []
    if not expected_items:
        return []

    full_text = _normalize_requirement_text("\n".join(p.text for p in document.paragraphs))
    has_numbered_headings = any(
        paragraph.paragraph_type == ParagraphType.HEADING
        and paragraph.is_numbered_heading
        for paragraph in document.paragraphs
    )

    aliases = {
        "аннотацию": ("аннотация", "аннотацию"),
        "аннотация": ("аннотация", "аннотацию"),
        "список использованных источников": (
            "список использованных источников",
            "список источников",
            "список используемых источников",
            "библиографический список",
        ),
        "приложения": ("приложение", "приложения"),
        "основная часть": ("основная часть",),
        "разделы работы": ("раздел",),
    }

    missing: list[str] = []
    for raw_item in expected_items:
        item = _normalize_requirement_text(str(raw_item).strip(" .;:"))
        if not item:
            continue
        if item in {"основная часть", "разделы работы"} and has_numbered_headings:
            continue
        variants = aliases.get(item, (item,))
        if not any(variant in full_text for variant in variants):
            missing.append(str(raw_item))

    if not missing:
        return []

    return [
        Violation(
            rule_id=rule.id,
            source_section=rule.source_section,
            target=rule.target,
            parameter=rule.parameter,
            location="Документ",
            expected=", ".join(str(item) for item in expected_items),
            actual=f"не найдены элементы: {', '.join(missing)}",
            message=(
                "Состав выпускной квалификационной работы не полностью соответствует "
                "профилю требований. Не найдены обязательные структурные элементы: "
                f"{', '.join(missing)}."
            ),
            severity="warning" if _is_recommended(rule) else "error",
            violation_type="structure",
        )
    ]


def _looks_like_reference_entry(paragraph: ParagraphData) -> bool:
    text = paragraph.text.strip()
    if not text:
        return False
    if paragraph.paragraph_type in {ParagraphType.EMPTY, ParagraphType.HEADING, ParagraphType.TITLE_PAGE}:
        return False
    if paragraph.logical_section != "references":
        return False
    return bool(
        paragraph.list_marker_type
        or re.match(r"^\s*\d+[).]\s+\S", text)
        or re.search(r"\b(19|20)\d{2}\b", text)
        or "//" in text
        or "http" in text.lower()
    )


def _check_references_min_count_rule(
    rule: Rule,
    document: ParsedDocxDocument,
) -> list[Violation]:
    try:
        expected = int(rule.value)
    except (TypeError, ValueError):
        return []

    references_count = sum(
        1 for paragraph in document.paragraphs if _looks_like_reference_entry(paragraph)
    )
    if references_count >= expected:
        return []

    return [
        Violation(
            rule_id=rule.id,
            source_section=rule.source_section,
            target=rule.target,
            parameter=rule.parameter,
            location="Список источников",
            expected=f"не менее {expected} источников",
            actual=f"{references_count} источников",
            message=(
                "Список используемых источников должен содержать минимальное "
                f"количество позиций по профилю. Найдено {references_count}, "
                f"требуется не менее {expected}."
            ),
            severity="warning" if _is_recommended(rule) else "error",
            violation_type="structure",
        )
    ]


def _check_heading_english_not_allowed_rule(
    rule: Rule,
    document: ParsedDocxDocument,
) -> list[Violation]:
    violations: list[Violation] = []
    for paragraph in document.paragraphs:
        if paragraph.paragraph_type != ParagraphType.HEADING or paragraph.paragraph_type == ParagraphType.TITLE_PAGE:
            continue
        text = paragraph.text.strip()
        if not text:
            continue
        letters = re.findall(r"[A-Za-zА-Яа-яЁё]", text)
        latin = re.findall(r"[A-Za-z]", text)
        cyrillic = re.findall(r"[А-Яа-яЁё]", text)
        if not letters or not latin:
            continue
        if len(latin) <= len(cyrillic):
            continue
        violations.append(
            Violation(
                rule_id=rule.id,
                source_section=rule.source_section,
                target=rule.target,
                parameter=rule.parameter,
                location=f"Абзац {paragraph.index}, заголовок",
                paragraph_index=paragraph.index,
                expected="заголовок на русском языке",
                actual=text,
                message=(
                    "Заголовки на английском языке не допускаются. "
                    f"Абзац {paragraph.index}: найден заголовок «{text}»."
                ),
                severity="warning" if _is_recommended(rule) else "error",
                violation_type="text",
            )
        )
    return violations


def _check_empty_paragraphs_between_content(
    rule: Rule,
    document: ParsedDocxDocument,
) -> list[Violation]:
    violations: list[Violation] = []

    first_index, last_index = _find_content_bounds(document)

    if first_index is None or last_index is None:
        return violations

    for paragraph in document.paragraphs:
        if paragraph.paragraph_type == ParagraphType.TITLE_PAGE:
            continue

        if paragraph.text.strip():
            continue

        # Пустой абзац считается «между содержательным» только если
        # он находится строго между первым и последним непустым.
        if not (first_index < paragraph.index < last_index):
            continue

        violations.append(
            Violation(
                rule_id=rule.id,
                source_section=rule.source_section,
                target=rule.target,
                parameter=rule.parameter,
                location=f"Абзац {paragraph.index}",
                paragraph_index=paragraph.index,
                expected="нет пустого абзаца",
                actual="пустой абзац",
                message=(
                    "Пустой абзац между содержательными абзацами: "
                    "для интервалов нужно использовать параметры стиля, "
                    "а не пустые строки."
                ),
                severity="error",
                violation_type="structure",
            )
        )

    return violations


def _check_heading_space_after_min_rule(
    rule: Rule,
    document: ParsedDocxDocument,
) -> list[Violation]:
    violations: list[Violation] = []

    for paragraph in document.paragraphs:
        if paragraph.paragraph_type != ParagraphType.HEADING or not paragraph.text.strip():
            continue

        after = paragraph.space_after_pt or 0.0
        if after > 0:
            continue

        violations.append(
            Violation(
                rule_id=rule.id,
                source_section=rule.source_section,
                target=rule.target,
                parameter=rule.parameter,
                location=f"Абзац {paragraph.index}, заголовок уровня {paragraph.heading_level}",
                paragraph_index=paragraph.index,
                expected="после заголовка задан интервал",
                actual=f"после {after:g} пт",
                message=(
                    "Интервал между заголовком и следующим за ним текстом "
                    "должен быть задан параметрами стиля."
                ),
                severity="error",
                violation_type="formatting",
            )
        )

    return violations


def _is_empty_paragraph(paragraph: ParagraphData | None) -> bool:
    if paragraph is None:
        return False

    return paragraph.paragraph_type == ParagraphType.EMPTY or not paragraph.text.strip()


def _check_empty_paragraph_around_heading_rule(
    rule: Rule,
    document: ParsedDocxDocument,
) -> list[Violation]:
    violations: list[Violation] = []
    paragraphs_by_index = {
        paragraph.index: paragraph
        for paragraph in document.paragraphs
    }

    for paragraph in document.paragraphs:
        if (
            paragraph.paragraph_type != ParagraphType.HEADING
            or not paragraph.text.strip()
        ):
            continue

        previous_paragraph = paragraphs_by_index.get(paragraph.index - 1)
        next_paragraph = paragraphs_by_index.get(paragraph.index + 1)

        if (
            previous_paragraph is not None
            and previous_paragraph.paragraph_type == ParagraphType.TITLE_PAGE
        ):
            previous_paragraph = None

        if (
            next_paragraph is not None
            and next_paragraph.paragraph_type == ParagraphType.TITLE_PAGE
        ):
            next_paragraph = None

        has_empty_before = _is_empty_paragraph(previous_paragraph)
        has_empty_after = _is_empty_paragraph(next_paragraph)

        if not has_empty_before and not has_empty_after:
            continue

        if has_empty_before and has_empty_after:
            actual = "пустая строка перед и после заголовка"
        elif has_empty_before:
            actual = "пустая строка перед заголовком"
        else:
            actual = "пустая строка после заголовка"

        violations.append(
            Violation(
                rule_id=rule.id,
                source_section=rule.source_section,
                target=rule.target,
                parameter=rule.parameter,
                location=f"Абзац {paragraph.index}, заголовок уровня {paragraph.heading_level}",
                paragraph_index=paragraph.index,
                expected="интервалы вокруг заголовка заданы параметрами стиля",
                actual=actual,
                message=(
                    "Интервалы вокруг заголовков не допускается создавать "
                    "добавлением пустых строк."
                ),
                severity="error",
                violation_type="structure",
            )
        )

    return violations


def _make_document_violation(
    rule: Rule,
    location: str,
    actual: str,
    expected: str,
    message: str,
    paragraph_index: int | None = None,
    section_index: int | None = None,
    severity: str | None = None,
) -> Violation:
    is_warning = _is_recommended(rule)
    resolved_severity = severity or ("warning" if is_warning else "error")
    return Violation(
        rule_id=rule.id,
        source_section=rule.source_section,
        target=rule.target,
        parameter=rule.parameter,
        location=location,
        paragraph_index=paragraph_index,
        section_index=section_index,
        expected=expected,
        actual=actual,
        message=message,
        severity=resolved_severity,
        violation_type="recommendation" if resolved_severity == "warning" else "formatting",
    )


def _check_additional_text_font_size_relative(
    rule: Rule,
    document: ParsedDocxDocument,
) -> list[Violation]:
    main_size = _get_main_text_font_size(document)
    if main_size is None:
        return []

    violations: list[Violation] = []
    for paragraph in document.paragraphs:
        if paragraph.paragraph_type not in ADDITIONAL_TEXT_PARAGRAPH_TYPES or not paragraph.text.strip():
            continue
        if paragraph.paragraph_type == ParagraphType.TABLE_CELL or _is_table_caption(paragraph):
            continue

        actual = paragraph.font_size_pt
        if actual is None:
            continue

        same_size_other_font = (
            isclose(actual, main_size, abs_tol=TOLERANCE_SIZE_PT)
            and paragraph.font_family is not None
            and any(
                main.font_family
                and paragraph.font_family.strip().lower() != main.font_family.strip().lower()
                for main in document.paragraphs
                if main.paragraph_type == ParagraphType.MAIN_TEXT and main.font_family
            )
        )
        smaller_by_two = isclose(actual, main_size - 2, abs_tol=TOLERANCE_SIZE_PT)
        if smaller_by_two or same_size_other_font:
            continue

        violations.append(
            _make_document_violation(
                rule,
                location=f"Абзац {paragraph.index}",
                paragraph_index=paragraph.index,
                expected=(
                    f"{_format_value(main_size - 2, 'pt')} или "
                    f"{_format_value(main_size, 'pt')} при другой гарнитуре"
                ),
                actual=_format_value(actual, "pt"),
                message=(
                    "Раздел 6.6: кегль дополнительного текста должен быть на "
                    "2 пункта меньше основного текста или иметь тот же кегль "
                    f"при другой гарнитуре. Абзац {paragraph.index}: найдено "
                    f"{_format_value(actual, 'pt')}, основной текст "
                    f"{_format_value(main_size, 'pt')}."
                ),
            )
        )

    return violations


def _check_additional_spacing_limit_rule(
    rule: Rule,
    document: ParsedDocxDocument,
) -> list[Violation]:
    main_size = _get_main_text_font_size(document) or 14.0
    limit = float(rule.value) if isinstance(rule.value, (int, float)) else main_size
    violations: list[Violation] = []

    for paragraph in document.paragraphs:
        if paragraph.paragraph_type in {ParagraphType.TITLE_PAGE, ParagraphType.TABLE_CELL}:
            continue

        for value, label in (
            (paragraph.space_before_pt, "перед"),
            (paragraph.space_after_pt, "после"),
        ):
            if value is None or value <= limit + TOLERANCE_SIZE_PT:
                continue

            violations.append(
                _make_document_violation(
                    rule,
                    location=f"Абзац {paragraph.index}",
                    paragraph_index=paragraph.index,
                    expected=f"не больше {_format_value(limit, 'pt')}",
                    actual=_format_value(value, "pt"),
                    message=(
                        "Раздел 8.4: части текста допускается отделять одним "
                        f"дополнительным интервалом. Абзац {paragraph.index}: "
                        f"найден слишком большой дополнительный интервал {label} "
                        f"абзаца {_format_value(value, 'pt')}."
                    ),
                )
            )

    return violations


def _check_centered_text_no_indents_rule(rule: Rule, document: ParsedDocxDocument) -> list[Violation]:
    violations: list[Violation] = []
    for paragraph in document.paragraphs:
        if (
            paragraph.paragraph_type in {ParagraphType.TITLE_PAGE, ParagraphType.TABLE_CELL}
            or _is_table_caption(paragraph)
            or paragraph.alignment != "center"
        ):
            continue

        first = paragraph.first_line_indent_cm or 0.0
        left = paragraph.left_indent_cm or 0.0
        right = paragraph.right_indent_cm or 0.0
        if (
            isclose(first, 0.0, abs_tol=TOLERANCE_LENGTH_CM)
            and isclose(left, 0.0, abs_tol=TOLERANCE_LENGTH_CM)
            and isclose(right, 0.0, abs_tol=TOLERANCE_LENGTH_CM)
        ):
            continue

        violations.append(
            _make_document_violation(
                rule,
                location=f"Абзац {paragraph.index}",
                paragraph_index=paragraph.index,
                expected="центрированный абзац без отступов слева, справа и в первой строке",
                actual=(
                    f"абзацный отступ {_format_value(first, 'cm')}, "
                    f"левый отступ {_format_value(left, 'cm')}, "
                    f"правый отступ {_format_value(right, 'cm')}"
                ),
                message=(
                    "Раздел 8.6: в тексте, выровненном по центру, не используют "
                    "абзацные уступы и втяжки. "
                    f"Абзац {paragraph.index}: у центрированного текста есть отступы; "
                    "для такого абзаца они должны быть нулевыми."
                ),
            )
        )
    return violations


def _caption_title_is_valid(title: str | None) -> bool:
    if not title:
        return False
    stripped = title.strip()
    first_letter = next((char for char in stripped if char.isalpha()), None)
    return bool(first_letter and first_letter.isupper() and not stripped.endswith("."))


def _table_label(table_index: int) -> str:
    return f"Таблица {table_index + 1}"


def _table_display_label(document: ParsedDocxDocument, table_index: int) -> str:
    table = next((item for item in document.tables if item.index == table_index), None)
    if table is None or table.title_paragraph_index is None:
        return _table_label(table_index)

    title = next(
        (
            paragraph
            for paragraph in document.paragraphs
            if paragraph.index == table.title_paragraph_index
        ),
        None,
    )
    if title is not None and title.caption_number:
        return f"Таблица {title.caption_number}"

    return _table_label(table_index)


def _has_paragraph_indents(paragraph: ParagraphData) -> bool:
    first = paragraph.first_line_indent_cm or 0.0
    left = paragraph.left_indent_cm or 0.0
    right = paragraph.right_indent_cm or 0.0
    return any(
        not isclose(value, 0.0, abs_tol=TOLERANCE_LENGTH_CM)
        for value in (first, left, right)
    )


def _previous_non_empty_paragraph(
    document: ParsedDocxDocument,
    paragraph: ParagraphData,
) -> ParagraphData | None:
    for candidate in reversed(document.paragraphs):
        if candidate.index >= paragraph.index:
            continue
        if candidate.paragraph_type in {ParagraphType.EMPTY, ParagraphType.TABLE_CELL, ParagraphType.TITLE_PAGE}:
            continue
        if candidate.text.strip() or candidate.has_inline_image:
            return candidate
    return None


def _nearest_figure_for_caption(
    document: ParsedDocxDocument,
    caption: ParagraphData,
) -> ParagraphData | None:
    """
    Ищет рисунок, к которому относится подпись.

    В реальных DOCX подпись может идти:
    - в том же абзаце, что и изображение;
    - сразу после абзаца с изображением;
    - после пустой строки между рисунком и подписью.

    Поэтому одной проверки только предыдущего непустого абзаца недостаточно.
    """
    if caption.has_inline_image:
        return caption

    checked_meaningful = 0
    for candidate in reversed(document.paragraphs):
        if candidate.index >= caption.index:
            continue
        if candidate.paragraph_type in {
            ParagraphType.EMPTY,
            ParagraphType.TABLE_CELL,
            ParagraphType.TITLE_PAGE,
        }:
            continue
        if not candidate.text.strip() and not candidate.has_inline_image:
            continue

        checked_meaningful += 1
        if candidate.has_inline_image:
            return candidate

        # Если между подписью и рисунком встретился обычный текст,
        # считаем, что подпись уже не стоит непосредственно под рисунком.
        if candidate.caption_kind != "figure":
            return None

        if checked_meaningful >= 3:
            return None

    return None


def _check_image_rules(rule: Rule, document: ParsedDocxDocument) -> list[Violation]:
    violations: list[Violation] = []
    main_size = _get_main_text_font_size(document) or 14.0

    if rule.parameter == "image_format":
        allowed = {str(item).lower() for item in rule.value} if isinstance(rule.value, list) else {"png", "jpg", "jpeg"}
        for image in document.images:
            if image.extension is None or image.extension.lower() in allowed:
                continue
            violations.append(_make_document_violation(
                rule, f"Изображение {image.index}", image.extension,
                ", ".join(sorted(allowed)),
                f"Раздел 10.1: для включения в текстовый документ рекомендуются изображения PNG или JPEG/JPG. Изображение {image.index}: найден формат {image.extension}.",
                severity="warning",
            ))

    elif rule.parameter == "image_max_px":
        limit = int(rule.value) if isinstance(rule.value, int) else 1000
        for image in document.images:
            if image.width_px is None or image.height_px is None:
                continue
            actual = max(image.width_px, image.height_px)
            if actual <= limit:
                continue
            violations.append(_make_document_violation(
                rule, f"Изображение {image.index}", f"{actual} px", f"не более {limit} px",
                f"Раздел 10.1: рекомендуется использовать изображения не более 1000 точек по длинной стороне. Изображение {image.index}: найдено {actual} px.",
                severity="warning",
            ))

    elif rule.parameter == "image_paragraph_centered":
        for paragraph in document.paragraphs:
            if not paragraph.has_inline_image:
                continue
            if paragraph.alignment == "center" and not _has_paragraph_indents(paragraph):
                continue
            violations.append(_make_document_violation(
                rule, f"Абзац {paragraph.index}",
                f"выравнивание: {paragraph.alignment or 'не задано'}, отступы: {_format_value(paragraph.first_line_indent_cm or 0, 'cm')}",
                "по центру, без абзацного отступа",
                f"Раздел 10.3: изображение должно быть в отдельном абзаце по центру, без абзацного отступа. Абзац {paragraph.index}: оформление отличается.",
                paragraph_index=paragraph.index,
            ))

    elif rule.parameter in {"image_keep_with_next", "image_no_space_after_if_caption"}:
        by_index = {paragraph.index: paragraph for paragraph in document.paragraphs}
        for paragraph in document.paragraphs:
            next_paragraph = by_index.get(paragraph.index + 1)
            if not paragraph.has_inline_image or next_paragraph is None or next_paragraph.caption_kind != "figure":
                continue
            if rule.parameter == "image_keep_with_next" and paragraph.keep_with_next is not True:
                violations.append(_make_document_violation(
                    rule, f"Абзац {paragraph.index}",
                    "рисунок может оторваться от подписи",
                    "рисунок вместе с подписью",
                    f"Раздел 10.3: рисунок должен оставаться вместе со своей подписью. Абзац {paragraph.index}: удержание рисунка с подписью не включено.",
                    paragraph_index=paragraph.index,
                ))
            if rule.parameter == "image_no_space_after_if_caption" and (paragraph.space_after_pt or 0.0) > TOLERANCE_SIZE_PT:
                violations.append(_make_document_violation(
                    rule, f"Абзац {paragraph.index}", _format_value(paragraph.space_after_pt, "pt"),
                    "0 пт",
                    f"Раздел 10.3: при наличии подписи дополнительный интервал после изображения не ставят. Абзац {paragraph.index}: найден интервал после {_format_value(paragraph.space_after_pt, 'pt')}.",
                    paragraph_index=paragraph.index,
                ))

    elif rule.parameter == "image_size_consistency":
        widths = [image.width_cm for image in document.images if image.width_cm is not None]
        if widths:
            expected = max(set(round(width, 1) for width in widths), key=[round(width, 1) for width in widths].count)
            for image in document.images:
                if image.width_cm is None or isclose(image.width_cm, expected, abs_tol=0.2):
                    continue
                violations.append(_make_document_violation(
                    rule, f"Изображение {image.index}", _format_value(image.width_cm, "cm"),
                    _format_value(expected, "cm"),
                    f"Раздел 10.4: при отсутствии специального творческого решения изображения должны иметь единообразный размер. Изображение {image.index}: ширина {_format_value(image.width_cm, 'cm')} отличается от преобладающей ширины {_format_value(expected, 'cm')}.",
                    severity="warning",
                ))

    elif rule.parameter == "image_after_first_reference":
        first_references: dict[str, int] = {}
        captions_by_number = {
            paragraph.caption_number: paragraph
            for paragraph in document.paragraphs
            if paragraph.caption_kind == "figure" and paragraph.caption_number
        }
        for paragraph in document.paragraphs:
            if paragraph.paragraph_type in {ParagraphType.TITLE_PAGE, ParagraphType.CAPTION}:
                continue
            for match in FIGURE_REFERENCE_PATTERN.finditer(paragraph.text):
                first_references.setdefault(match.group(1), paragraph.index)

        for number, reference_index in first_references.items():
            caption = captions_by_number.get(number)
            if caption is None:
                violations.append(_make_document_violation(
                    rule,
                    "Документ",
                    f"ссылка на рисунок {number}",
                    "соответствующая подпись рисунка",
                    f"В тексте есть ссылка на рисунок {number}, но соответствующая подпись рисунка не найдена.",
                ))
                continue
            if caption.index < reference_index:
                violations.append(_make_document_violation(
                    rule,
                    f"Рисунок {number}",
                    f"подпись в абзаце {caption.index}, первая ссылка в абзаце {reference_index}",
                    "рисунок после первой ссылки",
                    f"Раздел 10.2: изображение должно размещаться после абзаца, в котором впервые дана ссылка на него. Рисунок {number}: изображение или подпись расположены раньше первой ссылки.",
                    paragraph_index=caption.index,
                    severity="warning",
                ))

    elif rule.parameter.startswith("figure_caption_"):
        figure_captions = [p for p in document.paragraphs if p.caption_kind == "figure"]
        prefixes = [p.caption_prefix for p in figure_captions if p.caption_prefix]
        dominant_prefix = max(set(prefixes), key=prefixes.count) if prefixes else None
        for paragraph in figure_captions:
            figure_anchor = _nearest_figure_for_caption(document, paragraph)
            if rule.parameter == "figure_caption_position" and figure_anchor is None:
                violations.append(_make_document_violation(rule, f"Абзац {paragraph.index}", "рядом с подписью не найден рисунок", "под рисунком", f"Раздел 10.5: подпись к рисунку должна располагаться сразу под соответствующим рисунком. Абзац {paragraph.index}: перед подписью не найден абзац с изображением.", paragraph.index))
            elif rule.parameter == "figure_caption_alignment" and (paragraph.alignment != "center" or _has_paragraph_indents(paragraph)):
                violations.append(_make_document_violation(rule, f"Абзац {paragraph.index}", f"выравнивание: {paragraph.alignment or 'не задано'}, отступы: {_format_value(paragraph.first_line_indent_cm or 0, 'cm')}", "по центру, без абзацного отступа", f"Раздел 10.5: подпись к рисунку должна быть выровнена по центру и оформлена без абзацного отступа. Абзац {paragraph.index}: оформление отличается.", paragraph.index))
            elif rule.parameter == "figure_caption_prefix":
                expected_prefix = str(rule.value)
                if paragraph.caption_prefix != expected_prefix:
                    violations.append(_make_document_violation(rule, f"Абзац {paragraph.index}", paragraph.caption_prefix or "не определено", expected_prefix, f"Подпись рисунка должна начинаться со слова \"{expected_prefix}\". Абзац {paragraph.index}: найдено \"{paragraph.caption_prefix or 'не определено'}\".", paragraph.index))
            elif rule.parameter == "figure_caption_separator":
                expected_separator = str(rule.value).lower()
                has_dash = bool(FIGURE_CAPTION_DASH_PATTERN.match(paragraph.text.strip()))
                has_dot = bool(re.match(r"^(Рис\.|Рисунок)\s+\d+(?:\.\d+)*\.\s+\S", paragraph.text.strip(), re.IGNORECASE))
                if ("dash" in expected_separator or "тире" in expected_separator) and not has_dash:
                    violations.append(_make_document_violation(rule, f"Абзац {paragraph.index}", "нет тире после номера", "тире после номера", f"В подписи рисунка после номера должно стоять тире. Абзац {paragraph.index}: найдено другое оформление.", paragraph.index))
                elif ("dot" in expected_separator or "точк" in expected_separator) and not has_dot:
                    violations.append(_make_document_violation(rule, f"Абзац {paragraph.index}", "нет точки после номера", "точка после номера", f"В подписи рисунка после номера должна стоять точка. Абзац {paragraph.index}: найдено другое оформление.", paragraph.index))
            elif rule.parameter == "figure_caption_terminal_dot" and bool(rule.value) is False and paragraph.text.strip().endswith("."):
                violations.append(_make_document_violation(rule, f"Абзац {paragraph.index}", "точка в конце подписи", "без точки в конце", f"Подпись рисунка не должна заканчиваться точкой. Абзац {paragraph.index}: точка в конце найдена.", paragraph.index))
            elif rule.parameter == "figure_caption_prefix_consistency" and dominant_prefix and paragraph.caption_prefix != dominant_prefix:
                violations.append(_make_document_violation(rule, f"Абзац {paragraph.index}", str(paragraph.caption_prefix), dominant_prefix, f"Раздел 10.5: подписи к рисункам должны начинаться единообразно по всему документу. Абзац {paragraph.index}: найдено \"{paragraph.caption_prefix}\", преобладающий вариант \"{dominant_prefix}\".", paragraph.index, severity="warning"))
            elif rule.parameter == "figure_caption_dot_after_number" and FIGURE_CAPTION_DASH_PATTERN.match(paragraph.text.strip()):
                violations.append(_make_document_violation(rule, f"Абзац {paragraph.index}", "тире после номера", "точка после номера", f"Раздел 10.5: после номера рисунка ставят точку, тире вместо точки не используется. Абзац {paragraph.index}: найдено тире после номера рисунка.", paragraph.index))
            elif rule.parameter == "figure_caption_title_format" and not _caption_title_is_valid(paragraph.caption_title):
                violations.append(_make_document_violation(rule, f"Абзац {paragraph.index}", paragraph.caption_title or "", "название с прописной буквы без точки в конце", f"Раздел 10.5: название рисунка должно начинаться с прописной буквы и не заканчиваться точкой. Абзац {paragraph.index}: нарушено оформление подписи.", paragraph.index))
            elif rule.parameter == "figure_caption_font_size" and paragraph.font_size_pt is not None and not (
                isclose(paragraph.font_size_pt, main_size - 1, abs_tol=TOLERANCE_SIZE_PT)
                or isclose(paragraph.font_size_pt, main_size - 2, abs_tol=TOLERANCE_SIZE_PT)
            ):
                violations.append(_make_document_violation(rule, f"Абзац {paragraph.index}", _format_value(paragraph.font_size_pt, "pt"), f"{main_size - 1:g} или {main_size - 2:g} пт", f"Раздел 10.7: кегль подписи к рисунку должен быть на 1 или 2 пункта меньше кегля основного текста. Абзац {paragraph.index}: найдено {_format_value(paragraph.font_size_pt, 'pt')}, основной текст {_format_value(main_size, 'pt')}.", paragraph.index))
            elif rule.parameter == "figure_caption_spacing":
                before_expected = main_size / 2
                after_expected = main_size
                before = paragraph.space_before_pt or 0.0
                after = paragraph.space_after_pt or 0.0
                if not isclose(before, before_expected, abs_tol=TOLERANCE_SIZE_PT):
                    violations.append(_make_document_violation(rule, f"Абзац {paragraph.index}", _format_value(before, "pt"), f"около {before_expected:g} пт", f"Раздел 10.7: интервал перед подписью к рисунку должен быть примерно равен половине кегля основного текста. Абзац {paragraph.index}: найдено {_format_value(before, 'pt')}, ожидается около {before_expected:g} пт.", paragraph.index))
                if not isclose(after, after_expected, abs_tol=TOLERANCE_SIZE_PT):
                    violations.append(_make_document_violation(rule, f"Абзац {paragraph.index}", _format_value(after, "pt"), f"около {after_expected:g} пт", f"Раздел 10.7: интервал после подписи к рисунку должен быть примерно равен кеглю основного текста. Абзац {paragraph.index}: найдено {_format_value(after, 'pt')}, ожидается около {after_expected:g} пт.", paragraph.index))

    return violations


def _check_table_rules(rule: Rule, document: ParsedDocxDocument) -> list[Violation]:
    violations: list[Violation] = []
    main_size = _get_main_text_font_size(document) or 14.0

    if rule.parameter == "table_after_first_reference":
        first_references: dict[str, int] = {}
        captions_by_number = {
            paragraph.caption_number: paragraph
            for paragraph in document.paragraphs
            if paragraph.caption_kind == "table" and paragraph.caption_number
        }
        for paragraph in document.paragraphs:
            if paragraph.paragraph_type in {ParagraphType.TITLE_PAGE, ParagraphType.CAPTION, ParagraphType.TABLE_CELL}:
                continue
            for match in TABLE_REFERENCE_PATTERN.finditer(paragraph.text):
                first_references.setdefault(match.group(1), paragraph.index)

        for number, reference_index in first_references.items():
            caption = captions_by_number.get(number)
            if caption is None:
                violations.append(_make_document_violation(
                    rule,
                    "Документ",
                    f"ссылка на таблицу {number}",
                    "соответствующий заголовок таблицы",
                    f"В тексте есть ссылка на таблицу {number}, но соответствующий заголовок таблицы не найден.",
                ))
                continue
            if caption.index < reference_index:
                violations.append(_make_document_violation(
                    rule,
                    f"Таблица {number}",
                    f"заголовок в абзаце {caption.index}, первая ссылка в абзаце {reference_index}",
                    "таблица после первой ссылки",
                    f"Раздел 11.1: таблица должна помещаться после абзаца, в котором ссылка на неё дана впервые. Таблица {number}: таблица расположена раньше первой ссылки.",
                    paragraph_index=caption.index,
                    severity="warning",
                ))
        # ГОСТ 11.1: заголовок таблицы без ссылки в тексте — отдельный случай.
        for number, caption in captions_by_number.items():
            if number in first_references:
                continue
            violations.append(_make_document_violation(
                rule,
                f"Таблица {number}",
                f"заголовок в абзаце {caption.index} без ссылки в тексте",
                "ссылка на таблицу до её появления",
                f"Раздел 11.1: для таблицы {number} не найдено упоминание в тексте до её размещения.",
                paragraph_index=caption.index,
                severity="warning",
            ))
        return violations

    if rule.parameter == "no_continuation_table_titles":
        for paragraph in document.paragraphs:
            match = TABLE_CONTINUATION_PATTERN.search(paragraph.text)
            if match:
                fragment = match.group(0)
                violations.append(_make_document_violation(rule, f"Абзац {paragraph.index}", fragment, "нет таких надписей", f"Раздел 11.13: при разбиении большой таблицы не добавляют заголовки \"Продолжение таблицы\" и \"Окончание таблицы\". Абзац {paragraph.index}: найдено \"{fragment}\".", paragraph.index))
        return violations

    if rule.parameter == "table_grid_style":
        signatures = [(table.border_color, table.border_size) for table in document.tables if table.has_grid]
        dominant = max(set(signatures), key=signatures.count) if signatures else None
        for table in document.tables:
            label = _table_label(table.index)
            if table.has_grid is None:
                continue
            if not table.has_grid:
                violations.append(_make_document_violation(rule, label, "границы не обнаружены", "простая сетка", f"Раздел 11.2: таблица должна иметь видимую простую сетку. {label}: границы таблицы не обнаружены."))
            elif dominant and (table.border_color, table.border_size) != dominant:
                violations.append(_make_document_violation(rule, label, str((table.border_color, table.border_size)), str(dominant), f"Раздел 11.2: линии таблиц должны быть единообразны по всему документу. {label}: параметры границ отличаются от преобладающих.", severity="warning"))

    elif rule.parameter in {"table_title_position", "table_caption_position"}:
        for table in document.tables:
            if table.title_paragraph_index is not None:
                continue
            label = _table_label(table.index)
            violations.append(_make_document_violation(rule, label, "название перед таблицей не найдено", "название над таблицей", f"Раздел 11.3: название таблицы должно стоять непосредственно над таблицей. {label}: перед таблицей не найдено название."))

    elif rule.parameter in {
        "table_title_format",
        "table_title_font_size",
        "table_title_keep",
        "table_caption_alignment",
        "table_caption_prefix",
        "table_caption_separator",
        "table_caption_terminal_dot",
    }:
        table_captions = [paragraph for paragraph in document.paragraphs if paragraph.caption_kind == "table"]
        for paragraph in table_captions:
            if rule.parameter == "table_title_format":
                text = paragraph.text.strip()
                has_valid_prefix = paragraph.caption_prefix in {"Табл.", "Таблица", "табл.", "таблица"}
                has_dash_separator = re.match(r"^(Табл\.|Таблица)\s+\d+(?:\.\d+)*\s*[\u2014-]", text, re.IGNORECASE)
                if not has_valid_prefix or has_dash_separator:
                    violations.append(_make_document_violation(rule, f"Абзац {paragraph.index}", text, "\"Табл. N. Название\" или \"Таблица N. Название\"", f"Раздел 11.3: заголовок таблицы должен иметь вид \"Табл. N. Название\" или \"Таблица N. Название\". Абзац {paragraph.index}: найдено \"{text}\".", paragraph.index))
                if not _caption_title_is_valid(paragraph.caption_title):
                    violations.append(_make_document_violation(rule, f"Абзац {paragraph.index}", paragraph.caption_title or "", "название с прописной буквы без точки в конце", f"Раздел 11.3: тематическая часть заголовка таблицы должна начинаться с прописной буквы и не заканчиваться точкой. Абзац {paragraph.index}: нарушено оформление названия таблицы.", paragraph.index))
                if paragraph.alignment not in {None, "left"}:
                    violations.append(_make_document_violation(rule, f"Абзац {paragraph.index}", str(paragraph.alignment), "по левому краю", f"Раздел 11.3: заголовок таблицы, набранный в подбор, выравнивают по левому краю. Абзац {paragraph.index}: найдено выравнивание {paragraph.alignment}.", paragraph.index))
                first_indent = paragraph.first_line_indent_cm or 0.0
                if not isclose(first_indent, 0.0, abs_tol=TOLERANCE_LENGTH_CM):
                    violations.append(_make_document_violation(rule, f"Абзац {paragraph.index}", _format_value(first_indent, "cm"), "0 см", f"Раздел 11.3: заголовок таблицы должен быть оформлен без абзацного отступа. Абзац {paragraph.index}: найден отступ {_format_value(first_indent, 'cm')}.", paragraph.index))
                title_spacing = paragraph.line_spacing
                if title_spacing is not None and not isclose(title_spacing, 1.0, abs_tol=TOLERANCE_RATIO):
                    violations.append(_make_document_violation(rule, f"Абзац {paragraph.index}", f"{title_spacing:g}", "1,0", f"Раздел 11.3: заголовок таблицы оформляется с одинарным межстрочным интервалом. Абзац {paragraph.index}: найдено {title_spacing:g}.", paragraph.index))
            elif rule.parameter == "table_caption_alignment":
                expected_alignment = str(rule.value)
                if paragraph.alignment != expected_alignment:
                    violations.append(_make_document_violation(
                        rule,
                        f"Абзац {paragraph.index}",
                        paragraph.alignment or "не задано",
                        expected_alignment,
                        f"Название таблицы должно быть выровнено по левому краю. Абзац {paragraph.index}: найдено другое выравнивание.",
                        paragraph.index,
                    ))
            elif rule.parameter == "table_caption_prefix":
                expected_prefix = str(rule.value).lower()
                actual_prefix = (paragraph.caption_prefix or "").lower()
                if actual_prefix != expected_prefix:
                    violations.append(_make_document_violation(
                        rule,
                        f"Абзац {paragraph.index}",
                        paragraph.caption_prefix or "не найдено",
                        str(rule.value),
                        f"Название таблицы должно начинаться со слова «{rule.value}». Абзац {paragraph.index}: найден другой вариант.",
                        paragraph.index,
                    ))
            elif rule.parameter == "table_caption_separator":
                text = paragraph.text.strip()
                expected = str(rule.value).lower()
                has_dash = bool(re.match(r"^(Табл\.|Таблица)\s+\d+(?:\.\d+)*\s*[\u2014-]", text, re.IGNORECASE))
                has_dot = bool(re.match(r"^(Табл\.|Таблица)\s+\d+(?:\.\d+)*\.\s+\S", text, re.IGNORECASE))
                if ("тире" in expected and not has_dash) or ("точк" in expected and not has_dot):
                    violations.append(_make_document_violation(
                        rule,
                        f"Абзац {paragraph.index}",
                        text,
                        str(rule.value),
                        f"После номера таблицы должен использоваться разделитель «{rule.value}». Абзац {paragraph.index}: оформление названия таблицы отличается.",
                        paragraph.index,
                    ))
            elif rule.parameter == "table_caption_terminal_dot":
                should_have_dot = bool(rule.value)
                has_dot = paragraph.text.strip().endswith(".")
                if has_dot != should_have_dot:
                    expected = "с точкой в конце" if should_have_dot else "без точки в конце"
                    actual = "точка есть" if has_dot else "точки нет"
                    violations.append(_make_document_violation(
                        rule,
                        f"Абзац {paragraph.index}",
                        actual,
                        expected,
                        f"Название таблицы должно быть оформлено {expected}. Абзац {paragraph.index}: {actual}.",
                        paragraph.index,
                    ))
            elif rule.parameter == "table_title_font_size":
                if paragraph.font_size_pt is None or isclose(paragraph.font_size_pt, main_size, abs_tol=TOLERANCE_SIZE_PT):
                    continue
                violations.append(_make_document_violation(rule, f"Абзац {paragraph.index}", _format_value(paragraph.font_size_pt, "pt"), _format_value(main_size, "pt"), f"Раздел 11.3: заголовок таблицы должен быть набран тем же кеглем, что и основной текст. Абзац {paragraph.index}: найдено {_format_value(paragraph.font_size_pt, 'pt')}, требуется {_format_value(main_size, 'pt')}.", paragraph.index))
            elif rule.parameter == "table_title_keep":
                if paragraph.keep_with_next is True and paragraph.keep_together is True:
                    continue
                violations.append(_make_document_violation(
                    rule,
                    f"Абзац {paragraph.index}",
                    "название таблицы может оторваться от таблицы",
                    "название таблицы вместе с таблицей",
                    f"Раздел 11.3: название таблицы должно оставаться вместе с самой таблицей. Абзац {paragraph.index}: параметры удержания с таблицей не включены.",
                    paragraph.index,
                ))

    elif rule.parameter == "table_header_required":
        for table in document.tables:
            if table.has_header_row:
                continue
            label = _table_label(table.index)
            violations.append(_make_document_violation(rule, label, "строка с названиями столбцов не определена", "строка с названиями столбцов есть", f"Раздел 11.4: в таблице должна быть строка с названиями столбцов. {label}: такая строка не определена."))

    elif rule.parameter in {"table_text_spacing_indent", "table_text_line_spacing"}:
        # Группируем нарушения по таблицам: одна ошибка на таблицу с числом ячеек,
        # а не по сообщению на каждую ячейку.
        bad_cells_by_table: dict[int, dict[str, int]] = {}
        first_paragraph_by_table: dict[int, int] = {}
        for paragraph in document.paragraphs:
            if paragraph.paragraph_type != ParagraphType.TABLE_CELL:
                continue
            spacing = paragraph.line_spacing
            first = paragraph.first_line_indent_cm or 0.0
            left = paragraph.left_indent_cm or 0.0
            right = paragraph.right_indent_cm or 0.0
            is_header_cell = paragraph.table_row_index == 0
            bad_reasons: list[str] = []
            if spacing is not None and not isclose(spacing, 1.0, abs_tol=TOLERANCE_RATIO):
                bad_reasons.append("межстрочный интервал")
            if rule.parameter != "table_text_line_spacing":
                if not (
                    isclose(first, 0.0, abs_tol=TOLERANCE_LENGTH_CM)
                    and isclose(left, 0.0, abs_tol=TOLERANCE_LENGTH_CM)
                    and isclose(right, 0.0, abs_tol=TOLERANCE_LENGTH_CM)
                ):
                    bad_reasons.append("отступы")
                if not is_header_cell and paragraph.alignment not in {None, "left"}:
                    bad_reasons.append("выравнивание")

            if not bad_reasons:
                continue
            table_index = paragraph.table_index if paragraph.table_index is not None else -1
            stats = bad_cells_by_table.setdefault(table_index, {})
            for reason in bad_reasons:
                stats[reason] = stats.get(reason, 0) + 1
            first_paragraph_by_table.setdefault(table_index, paragraph.index)

        for table_index, reasons in sorted(bad_cells_by_table.items()):
            label = _table_label(table_index) if table_index >= 0 else "Таблица"
            display_label = (
                _table_display_label(document, table_index)
                if table_index >= 0
                else label
            )
            details = ", ".join(sorted(reasons))
            violations.append(_make_document_violation(
                rule,
                label,
                details,
                "одинарный интервал, без абзацного отступа, обычные ячейки по левому краю",
                f"Текст в таблице должен быть с одинарным межстрочным интервалом, без абзацных отступов; обычные ячейки выравниваются по левому краю. {display_label}: нарушены параметры {details}.",
                first_paragraph_by_table.get(table_index),
            ))

    elif rule.parameter in {"table_font_size", "table_text_font_size"}:
        if isinstance(rule.value, list):
            expected_values = [
                float(value)
                for value in rule.value
                if isinstance(value, int | float) and not isinstance(value, bool)
            ]
        elif isinstance(rule.value, int | float) and not isinstance(rule.value, bool):
            expected_values = [float(rule.value)]
        else:
            expected_values = [main_size, main_size - 2]
        if not expected_values:
            expected_values = [main_size, main_size - 2]

        bad_by_table: dict[int, tuple[int, float, int]] = {}
        for paragraph in document.paragraphs:
            if paragraph.paragraph_type != ParagraphType.TABLE_CELL or paragraph.font_size_pt is None:
                continue
            if any(
                isclose(paragraph.font_size_pt, expected, abs_tol=TOLERANCE_SIZE_PT)
                for expected in expected_values
            ):
                continue
            ti = paragraph.table_index if paragraph.table_index is not None else -1
            prev = bad_by_table.get(ti)
            if prev is None:
                bad_by_table[ti] = (1, float(paragraph.font_size_pt), paragraph.index)
            else:
                bad_by_table[ti] = (prev[0] + 1, prev[1], prev[2])
        for ti, (count, sample_size, first_idx) in sorted(bad_by_table.items()):
            label = _table_label(ti) if ti >= 0 else "Таблица"
            display_label = _table_display_label(document, ti) if ti >= 0 else label
            violations.append(_make_document_violation(
                rule,
                label,
                f"другой размер шрифта: {_format_value(sample_size, 'pt')}",
                " или ".join(_format_value(value, "pt") for value in expected_values),
                f"Кегль текста таблицы должен соответствовать профилю проверки. {display_label}: найден другой размер шрифта.",
                first_idx,
                severity="warning" if _is_recommended(rule) else "error",
            ))

    elif rule.parameter == "table_font_size_consistency":
        values = [round(p.font_size_pt, 1) for p in document.paragraphs if p.paragraph_type == ParagraphType.TABLE_CELL and p.font_size_pt is not None]
        if values:
            dominant = max(set(values), key=values.count)
            bad_by_table: dict[int, tuple[int, float, int]] = {}
            for paragraph in document.paragraphs:
                if paragraph.paragraph_type != ParagraphType.TABLE_CELL or paragraph.font_size_pt is None or isclose(paragraph.font_size_pt, dominant, abs_tol=TOLERANCE_SIZE_PT):
                    continue
                ti = paragraph.table_index if paragraph.table_index is not None else -1
                prev = bad_by_table.get(ti)
                if prev is None:
                    bad_by_table[ti] = (1, float(paragraph.font_size_pt), paragraph.index)
                else:
                    bad_by_table[ti] = (prev[0] + 1, prev[1], prev[2])
            for ti, (count, sample_size, first_idx) in sorted(bad_by_table.items()):
                label = _table_label(ti) if ti >= 0 else "Таблица"
                violations.append(_make_document_violation(
                    rule,
                    label,
                    f"другой кегль: {_format_value(sample_size, 'pt')}",
                    _format_value(dominant, "pt"),
                    f"Кегль текста таблиц должен быть одинаков по всему документу. {label}: найден другой кегль.",
                    first_idx,
                ))

    elif rule.parameter == "table_column_alignment_consistency":
        for table in document.tables:
            by_column: dict[int, list[ParagraphData]] = {}
            for paragraph in table.cell_paragraphs:
                if paragraph.table_column_index is None or paragraph.table_row_index == 0:
                    continue
                by_column.setdefault(paragraph.table_column_index, []).append(paragraph)

            for column_index, paragraphs in by_column.items():
                alignments = {paragraph.alignment for paragraph in paragraphs if paragraph.alignment}
                if len(alignments) > 1:
                    violations.append(_make_document_violation(rule, f"Таблица {table.index}, колонка {column_index}", ", ".join(sorted(alignments)), "одно выравнивание в колонке", f"Раздел 11.8: выравнивание в одной колонке должно быть одинаковым для всех ячеек. Таблица {table.index}, колонка {column_index}: найдены разные варианты выравнивания {', '.join(sorted(alignments))}."))

                non_empty_texts = [paragraph.text.strip() for paragraph in paragraphs if paragraph.text.strip()]
                if non_empty_texts and all(text in {"-", "—", "–"} for text in non_empty_texts):
                    for paragraph in paragraphs:
                        if paragraph.alignment == "center":
                            continue
                        violations.append(_make_document_violation(rule, f"Таблица {table.index}, строка {paragraph.table_row_index}, ячейка {column_index}", str(paragraph.alignment), "center", f"Раздел 11.8: прочерк в любой колонке выравнивают по центру. Таблица {table.index}, строка {paragraph.table_row_index}, ячейка {column_index}: найдено {paragraph.alignment}.", paragraph.index))

    elif rule.parameter == "table_width_within_text_area":
        if document.sections:
            section = document.sections[0]
            text_width = None
            if section.page_width_cm is not None and section.left_margin_cm is not None and section.right_margin_cm is not None:
                text_width = section.page_width_cm - section.left_margin_cm - section.right_margin_cm
            if text_width is not None:
                for table in document.tables:
                    if table.width_cm is None or table.width_cm <= text_width + TOLERANCE_LENGTH_CM:
                        continue
                    violations.append(_make_document_violation(rule, f"Таблица {table.index}", _format_value(table.width_cm, "cm"), _format_value(text_width, "cm"), f"Раздел 11.9: таблица не должна выходить за ширину полосы набора. Таблица {table.index}: ширина таблицы {_format_value(table.width_cm, 'cm')}, доступная ширина текста {_format_value(text_width, 'cm')}."))

    elif rule.parameter == "table_no_empty_rows":
        for table in document.tables:
            for row_index in table.empty_row_indexes:
                violations.append(_make_document_violation(rule, f"Таблица {table.index}", f"строка {row_index} пустая", "пустых строк нет", f"Раздел 11.10: пустых строк в тексте таблицы быть не должно. Таблица {table.index}: строка {row_index} пустая."))
            for row_index in table.enlarged_row_indexes:
                violations.append(_make_document_violation(rule, f"Таблица {table.index}", f"увеличенная высота строки {row_index}", "минимальная высота", f"Раздел 11.10: высота ячеек таблицы не должна превышать минимально необходимый размер. Таблица {table.index}: строка {row_index} имеет явно заданную увеличенную высоту.", severity="warning"))

    elif rule.parameter == "table_allow_row_break":
        for table in document.tables:
            if table.rows_count <= 8 or not table.has_cant_split_rows:
                continue
            violations.append(_make_document_violation(rule, f"Таблица {table.index}", "обнаружен запрет разбиения строк", "разрешить перенос строк", f"Раздел 11.11: в настройках таблицы должно быть включено условие \"Разрешить перенос строк на следующую страницу\". Таблица {table.index}: обнаружен запрет разбиения строк.", severity="warning"))

    elif rule.parameter == "table_repeat_header":
        for table in document.tables:
            if table.rows_count <= 8 or table.repeats_header:
                continue
            label = _table_label(table.index)
            display_label = _table_display_label(document, table.index)
            violations.append(_make_document_violation(rule, label, "повтор строки заголовков не включён", "повторять строку с названиями столбцов", f"Раздел 11.12: если таблица переходит на следующую страницу, строка с названиями столбцов должна повторяться. {display_label}: повтор строки заголовков не включён.", severity="warning"))

    return violations


def _get_paragraphs_for_target(
    document: ParsedDocxDocument,
    target: str,
) -> list[ParagraphData]:
    """Возвращает абзацы, к которым применяется правило."""

    if target == ADDITIONAL_TEXT_TARGET:
        return [
            paragraph
            for paragraph in document.paragraphs
            if paragraph.paragraph_type in ADDITIONAL_TEXT_PARAGRAPH_TYPES
            and paragraph.text.strip()
        ]

    paragraph_type = TARGET_TO_PARAGRAPH_TYPE.get(target)
    if paragraph_type is None:
        return []

    heading_level = TARGET_TO_HEADING_LEVEL.get(target)

    return [
        paragraph
        for paragraph in document.paragraphs
        if paragraph.paragraph_type == paragraph_type
        and paragraph.text.strip()
        and (
            target != "structural_heading"
            or paragraph.is_structural_heading
        )
        and (
            target != "section_heading"
            or (paragraph.is_numbered_heading and paragraph.heading_level == 1)
        )
        and (
            target != "subsection_heading"
            or (paragraph.is_numbered_heading and paragraph.heading_level == 2)
        )
        and (
            target != "point_heading"
            or (paragraph.is_numbered_heading and paragraph.heading_level == 3)
        )
        and (
            target != "appendix_heading"
            or paragraph.text.strip().lower().startswith("приложение")
        )
        and (
            heading_level is None
            or paragraph.heading_level == heading_level
        )
    ]


class FormatChecker:
    """Проверка форматирования DOCX-документа по профилю."""

    def check(self, document: ParsedDocxDocument, profile: Profile) -> list[Violation]:
        violations: list[Violation] = []

        paragraph_rules = [
            rule
            for rule in profile.rules
            if rule.category in {"formatting", "text"}
            and rule.parameter not in TYPOGRAPHY_PARAMETERS
            and (
                rule.target in TARGET_TO_PARAGRAPH_TYPE
                or rule.target == ADDITIONAL_TEXT_TARGET
            )
        ]

        page_rules = [
            rule
            for rule in profile.rules
            if rule.category in {"formatting", "text"}
            and rule.target == "page"
        ]

        document_rules = [
            rule
            for rule in profile.rules
            if rule.category in {"formatting", "structure", "text", "consistency"}
            and rule.parameter not in FORMAT_CHECKER_DISABLED_DOCUMENT_PARAMETERS
            and rule.target == "document"
        ]

        table_cell_parameters = {
            rule.parameter
            for rule in paragraph_rules
            if rule.target == "table_cell"
        }
        skip_document_table_parameters: set[str] = set()
        if "font_size" in table_cell_parameters:
            skip_document_table_parameters.add("table_text_font_size")
        if table_cell_parameters.intersection(
            {"alignment", "first_line_indent", "left_indent", "right_indent"}
        ):
            skip_document_table_parameters.update(
                {"table_text_spacing_indent", "table_text_line_spacing"}
            )
        elif "line_spacing" in table_cell_parameters:
            skip_document_table_parameters.add("table_text_line_spacing")

        for rule in paragraph_rules:
            if _is_grouped_table_cell_rule(rule):
                continue

            target_paragraphs = _get_paragraphs_for_target(document, rule.target)

            for paragraph in target_paragraphs:
                # ГОСТ 11.7: головка и боковик таблицы могут быть выделены жирным
                # начертанием и выравниваться по центру. Поэтому правила «обычное
                # начертание» для дополнительного текста не должны срабатывать
                # на ячейках первой строки (головки) и первой колонки (боковика).
                if (
                    rule.target == ADDITIONAL_TEXT_TARGET
                    and rule.parameter in {"bold", "italic", "font_color"}
                    and paragraph.paragraph_type == ParagraphType.TABLE_CELL
                    and (
                        paragraph.table_row_index == 0
                        or paragraph.table_column_index == 0
                    )
                ):
                    continue
                if (
                    rule.target == ADDITIONAL_TEXT_TARGET
                    and paragraph.paragraph_type == ParagraphType.TABLE_CELL
                    and rule.parameter in {
                        "font_size",
                        "alignment",
                        "line_spacing",
                        "first_line_indent",
                        "left_indent",
                        "right_indent",
                    }
                ):
                    continue
                if (
                    rule.target in {ADDITIONAL_TEXT_TARGET, "caption"}
                    and _is_table_caption(paragraph)
                    and rule.parameter in TABLE_CAPTION_ADDITIONAL_TEXT_PARAMETERS
                ):
                    continue

                if rule.parameter == "font_size":
                    violation = _check_rule_for_paragraph(rule, paragraph)
                    if violation is not None:
                        violations.append(violation)
                    violations.extend(_check_run_rule_for_paragraph(rule, paragraph))
                elif rule.target == "heading" and rule.parameter == "numbering_terminal_dot":
                    violation = _check_heading_numbering_terminal_dot_rule(
                        rule,
                        paragraph,
                    )
                    if violation is not None:
                        violations.append(violation)
                elif rule.target == "heading" and rule.parameter == "starts_with_capital":
                    violation = _check_heading_starts_with_capital_rule(
                        rule,
                        paragraph,
                    )
                    if violation is not None:
                        violations.append(violation)
                elif rule.parameter in RUN_LEVEL_PARAMETERS:
                    violations.extend(_check_run_rule_for_paragraph(rule, paragraph))
                elif rule.target == "heading" and rule.parameter in {"first_line_indent", "heading_indent_policy"}:
                    violation = _check_heading_indent_policy_rule(
                        rule,
                        paragraph,
                        document,
                        profile,
                    )
                    if violation is not None:
                        violations.append(violation)
                elif rule.target == "heading" and rule.parameter == "page_break_before":
                    violation = _check_heading_level_1_page_break_before_rule(
                        rule,
                        paragraph,
                        document,
                    )
                    if violation is not None:
                        violations.append(violation)
                else:
                    violation = _check_rule_for_paragraph(rule, paragraph)
                    if violation is not None:
                        violations.append(violation)

        font_size_rule = next(
            (
                rule
                for rule in paragraph_rules
                if rule.parameter == "font_size"
                and rule.target in {"main_text", "additional_text", "caption"}
            ),
            None,
        )
        if font_size_rule is not None:
            violations.extend(
                _check_mixed_font_sizes_in_paragraphs(font_size_rule, document)
            )

        for rule in paragraph_rules:
            if _is_grouped_table_cell_rule(rule):
                violations.extend(_check_grouped_table_cell_rule(rule, document))

        for section in document.sections:
            for rule in page_rules:
                if rule.parameter == "header_short_title":
                    violation = _check_header_short_title_rule(rule, section)
                else:
                    violation = _check_rule_for_section(rule, section)

                if violation is not None:
                    violations.append(violation)

        for rule in document_rules:
            if rule.parameter in skip_document_table_parameters:
                continue

            if rule.parameter == "empty_paragraph_between_content":
                violations.extend(
                    _check_empty_paragraphs_between_content(rule, document)
                )
            elif rule.parameter == "empty_paragraph_around_heading":
                violations.extend(
                    _check_empty_paragraph_around_heading_rule(rule, document)
                )
            elif rule.parameter == "first_page_no_page_number":
                violations.extend(
                    _check_first_page_no_page_number_rule(rule, document)
                )
            elif rule.parameter == "emphasis_methods_consistency":
                violations.extend(
                    _check_emphasis_methods_consistency(rule, document)
                )
            elif rule.parameter == "heading_font_size_hierarchy":
                if not _profile_has_role_specific_heading_sizes(profile):
                    violations.extend(
                        _check_heading_font_size_hierarchy(rule, document)
                    )
            elif rule.parameter == "heading_line_spacing_max_main":
                violations.extend(
                    _check_heading_line_spacing_rule(rule, document)
                )
            elif rule.parameter == "heading_spacing_order":
                if not _profile_has_role_specific_heading_spacing(profile):
                    violations.extend(
                        _check_heading_spacing_order_rule(rule, document)
                    )
            elif rule.parameter == "heading_space_after_min_single":
                if not _profile_has_role_specific_heading_spacing(profile):
                    violations.extend(
                        _check_heading_space_after_min_rule(rule, document)
                    )
            elif rule.parameter == "heading_all_caps":
                if not _profile_has_role_specific_heading_sizes(profile):
                    violations.extend(
                        _check_heading_all_caps_rule(rule, document)
                    )
            elif rule.parameter == "heading_color_only":
                violations.extend(
                    _check_heading_color_only_rule(rule, document)
                )
            elif rule.parameter == "additional_text_font_size_relative":
                violations.extend(
                    _check_additional_text_font_size_relative(rule, document)
                )
            elif rule.parameter == "font_size":
                violations.extend(
                    _check_mixed_font_sizes_in_paragraphs(rule, document)
                )
            elif rule.parameter == "additional_spacing_limit":
                violations.extend(
                    _check_additional_spacing_limit_rule(rule, document)
                )
            elif rule.parameter == "centered_text_no_indents":
                violations.extend(
                    _check_centered_text_no_indents_rule(rule, document)
                )
            elif rule.parameter.startswith("image_") or rule.parameter.startswith("figure_caption_"):
                violations.extend(
                    _check_image_rules(rule, document)
                )
            elif rule.parameter.startswith("table_") or rule.parameter == "no_continuation_table_titles":
                violations.extend(
                    _check_table_rules(rule, document)
                )

        return violations
