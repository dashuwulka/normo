import re
from pathlib import Path
from typing import Any

from docx import Document
from docx.enum.text import WD_ALIGN_PARAGRAPH
from docx.enum.style import WD_STYLE_TYPE
from docx.oxml import OxmlElement
from docx.oxml.ns import qn
from docx.shared import Cm, Pt, RGBColor

from app.models.document import ParagraphType
from app.models.profile import Profile
from app.parsers.docx_parser import DocxParser
from app.services.profile_utils import (
    get_allowed_values as _get_allowed_values,
    get_equals_value as _get_equals_value,
    get_max_value as _get_max_value,
    get_min_value as _get_min_value,
    get_paragraph_value as _get_paragraph_value,
    get_rules as _get_rules,
    is_value_allowed_by_profile as _is_value_allowed_by_profile,
    normalize_value as _normalize_value,
)
from app.services.parameter_registry import apply_paragraph_value
from collections import Counter

ALIGNMENT_TO_WORD = {
    "left": WD_ALIGN_PARAGRAPH.LEFT,
    "center": WD_ALIGN_PARAGRAPH.CENTER,
    "right": WD_ALIGN_PARAGRAPH.RIGHT,
    "justify": WD_ALIGN_PARAGRAPH.JUSTIFY,
}


NORMCONTROL_MAIN_TEXT_STYLE = "NormControl Main Text"
NORMCONTROL_HEADING_STYLE_PREFIX = "NormControl Heading"
ROLE_HEADING_STYLE_NAMES = {
    "structural_heading": "NormControl Structural Heading",
    "section_heading": "NormControl Section Heading",
    "subsection_heading": "NormControl Subsection Heading",
    "point_heading": "NormControl Point Heading",
    "appendix_heading": "NormControl Appendix Heading",
}


def _is_allowed_value(actual: Any, allowed_values: list[Any] | None) -> bool:
    """Проверяет, входит ли значение в список допустимых."""

    if allowed_values is None:
        return True

    if actual is None:
        return False

    actual_text = str(actual).strip().lower()

    return any(actual_text == str(value).strip().lower() for value in allowed_values)


def _get_paragraph_parameter_value(parsed_paragraph, parameter: str) -> Any:
    """Возвращает значение параметра абзаца для анализа единообразия."""

    return _get_paragraph_value(parsed_paragraph, parameter)


def _find_dominant_value(
    parsed_paragraphs,
    parameter: str,
    profile: Profile | None = None,
) -> Any | None:
    """
    Находит значение, к которому нужно привести параметр.

    Для межстрочного интервала применяется правило:
    если 1.5 встречается минимум в 30% основного текста,
    выбираем 1.5.
    """

    values = []

    for parsed_paragraph in parsed_paragraphs:
        if parsed_paragraph.paragraph_type != ParagraphType.MAIN_TEXT:
            continue

        if not parsed_paragraph.text.strip():
            continue

        value = _normalize_value(
            _get_paragraph_parameter_value(parsed_paragraph, parameter)
        )

        if value is not None:
            values.append(value)

    if not values:
        return None

    counter = Counter(values)
    total = sum(counter.values())

    if parameter == "line_spacing":
        preferred_value = 1.5
        preferred_count = counter.get(preferred_value, 0)
        preferred_ratio = preferred_count / total

        if preferred_ratio >= 0.3:
            return preferred_value

    if profile is not None:
        for value, _count in counter.most_common():
            if _is_value_allowed_by_profile(value, profile, "main_text", parameter):
                return value

    dominant_value, dominant_count = counter.most_common(1)[0]

    same_count_values = [
        value for value, count in counter.items()
        if count == dominant_count
    ]

    if len(same_count_values) > 1:
        return None

    return dominant_value


def _get_main_text_consistency_parameter_strategy(
    profile: Profile,
    parameter: str,
) -> dict[str, Any]:
    for rule in profile.rules:
        if (
            rule.category == "consistency"
            and rule.target == "main_text"
            and rule.operator == "consistent"
        ):
            strategy = rule.consistency_strategy or {}
            parameter_strategy = strategy.get(parameter)
            if isinstance(parameter_strategy, dict):
                return parameter_strategy

    return {}


def _choose_first_line_indent_for_autofix(profile: Profile) -> float | None:
    exact_value = _get_equals_value(profile, "main_text", "first_line_indent")
    if exact_value is not None:
        return float(exact_value)

    strategy = _get_main_text_consistency_parameter_strategy(
        profile,
        "first_line_indent",
    )

    fallback_value = strategy.get("fallback_value")
    if fallback_value is not None:
        return float(fallback_value)

    preferred_value = strategy.get("preferred_value")
    if preferred_value is not None:
        return float(preferred_value)

    return None


def _apply_consistency_to_main_text(
    paragraph,
    parsed_paragraph,
    dominant_values: dict[str, Any],
    profile: Profile | None = None,
) -> None:
    """
    Приводит абзац основного текста к преобладающим параметрам документа.
    """

    dominant_font_family = dominant_values.get("font_family")
    dominant_font_size = dominant_values.get("font_size")
    dominant_alignment = dominant_values.get("alignment")
    dominant_first_line_indent = dominant_values.get("first_line_indent")
    dominant_line_spacing = dominant_values.get("line_spacing")

    if (
        (profile is None or _get_equals_value(profile, "main_text", "font_family") is None)
        and
        dominant_font_family is not None
        and _normalize_value(parsed_paragraph.font_family) != dominant_font_family
    ):
        _apply_font_family(paragraph, str(dominant_font_family))

    if (
        (profile is None or _get_equals_value(profile, "main_text", "font_size") is None)
        and
        dominant_font_size is not None
        and _normalize_value(parsed_paragraph.font_size_pt) != dominant_font_size
    ):
        _apply_font_size(paragraph, float(dominant_font_size))

    if (
        (profile is None or _get_equals_value(profile, "main_text", "alignment") is None)
        and
        dominant_alignment is not None
        and _normalize_value(parsed_paragraph.alignment) != dominant_alignment
    ):
        _set_alignment(paragraph, str(dominant_alignment))

    if (
        (profile is None or _get_equals_value(profile, "main_text", "first_line_indent") is None)
        and
        dominant_first_line_indent is not None
        and _normalize_value(parsed_paragraph.first_line_indent_cm) != dominant_first_line_indent
    ):
        paragraph.paragraph_format.first_line_indent = Cm(float(dominant_first_line_indent))

    if (
        (profile is None or _get_equals_value(profile, "main_text", "line_spacing") is None)
        and
        dominant_line_spacing is not None
        and _normalize_value(parsed_paragraph.line_spacing) != dominant_line_spacing
    ):
        paragraph.paragraph_format.line_spacing = float(dominant_line_spacing)


def _get_or_create_paragraph_style(document, style_name: str):
    styles = document.styles

    if style_name in styles:
        style = styles[style_name]
    else:
        style = styles.add_style(style_name, WD_STYLE_TYPE.PARAGRAPH)

    style.hidden = False
    style.quick_style = True
    style.unhide_when_used = True

    return style


def _preferred_main_text_alignment(profile: Profile, dominant_values: dict[str, Any] | None = None) -> str:
    exact_alignment = _get_equals_value(profile, "main_text", "alignment")
    if exact_alignment is not None:
        return str(exact_alignment)

    allowed_alignments = _get_allowed_values(profile, "main_text", "alignment")
    if allowed_alignments and "justify" in allowed_alignments:
        return "justify"

    if dominant_values and dominant_values.get("alignment") is not None:
        return str(dominant_values["alignment"])

    return "justify"


def _set_style_alignment(style, alignment: str | None) -> None:
    if alignment is None:
        return

    word_alignment = ALIGNMENT_TO_WORD.get(alignment)
    if word_alignment is not None:
        style.paragraph_format.alignment = word_alignment


def _is_regular_heading_level_allowed(profile: Profile, level: int | None) -> bool:
    if level is None:
        return False

    for rule in _get_rules(profile, "heading", "bold"):
        strategy = rule.consistency_strategy or {}
        allowed_regular_levels = strategy.get("allow_regular_levels", [])
        if level in allowed_regular_levels:
            return True

    return False


def _choose_heading_bold_for_autofix(profile: Profile, level: int | None) -> bool | None:
    bold_value = _get_equals_value(profile, "heading", "bold")
    if bold_value is None:
        return None

    if _is_regular_heading_level_allowed(profile, level):
        return False

    return bool(bold_value)


def _choose_heading_alignment_for_autofix(
    profile: Profile,
    level: int | None,
    is_structural_heading: bool = False,
    role_target: str | None = None,
) -> str | None:
    preferred = "center" if is_structural_heading else "left"

    if role_target is not None:
        role_alignment = _get_equals_value(profile, role_target, "alignment")
        if role_alignment is not None:
            return str(role_alignment)

    if level is not None:
        exact_level_alignment = _get_equals_value(profile, f"heading_level_{level}", "alignment")
        if exact_level_alignment is not None:
            exact_value = str(exact_level_alignment)
            if is_structural_heading and exact_value == "left":
                return preferred
            return exact_value

    allowed_heading_alignments = _get_allowed_values(profile, "heading", "alignment")

    if not allowed_heading_alignments or preferred in allowed_heading_alignments:
        return preferred

    return str(allowed_heading_alignments[0])


def _heading_role_target(parsed_paragraph) -> str | None:
    text = (parsed_paragraph.text or "").strip().lower()

    if text.startswith("приложение"):
        return "appendix_heading"
    if parsed_paragraph.is_structural_heading:
        return "structural_heading"
    if parsed_paragraph.is_numbered_heading and parsed_paragraph.heading_level == 1:
        return "section_heading"
    if parsed_paragraph.is_numbered_heading and parsed_paragraph.heading_level == 2:
        return "subsection_heading"
    if parsed_paragraph.is_numbered_heading and parsed_paragraph.heading_level == 3:
        return "point_heading"

    return None


def _first_profile_value(profile: Profile, targets: list[str | None], parameter: str) -> Any | None:
    for target in targets:
        if target is None:
            continue
        value = _get_equals_value(profile, target, parameter)
        if value is not None:
            return value
    return None


def _target_order_for_heading(parsed_paragraph) -> list[str | None]:
    role_target = _heading_role_target(parsed_paragraph)
    level_target = (
        f"heading_level_{parsed_paragraph.heading_level}"
        if parsed_paragraph.heading_level is not None
        else None
    )
    return [role_target, level_target, "heading"]


def _heading_specific_target_order(parsed_paragraph) -> list[str | None]:
    role_target = _heading_role_target(parsed_paragraph)
    level_target = (
        f"heading_level_{parsed_paragraph.heading_level}"
        if parsed_paragraph.heading_level is not None
        else None
    )
    return [role_target, level_target]


def _get_autocorrect_protected_indexes(parsed_document) -> set[int]:
    protected: set[int] = set()

    for paragraph in parsed_document.paragraphs:
        if getattr(paragraph, "logical_section", None) == "toc":
            protected.add(paragraph.index)

    first_main_text_position: int | None = None
    for position, paragraph in enumerate(parsed_document.paragraphs):
        if (
            paragraph.paragraph_type == ParagraphType.MAIN_TEXT
            and paragraph.text.strip()
        ):
            first_main_text_position = position
            break

    if first_main_text_position is None:
        return protected

    real_start_index: int | None = None
    for paragraph in reversed(parsed_document.paragraphs[:first_main_text_position]):
        if paragraph.text.strip():
            real_start_index = paragraph.index
            break

    if real_start_index is None:
        return protected

    leading_headings = [
        paragraph
        for paragraph in parsed_document.paragraphs
        if paragraph.index < real_start_index
        and paragraph.text.strip()
        and paragraph.paragraph_type == ParagraphType.HEADING
    ]
    leading_non_headings = [
        paragraph
        for paragraph in parsed_document.paragraphs
        if paragraph.index < real_start_index
        and paragraph.text.strip()
        and paragraph.paragraph_type not in {ParagraphType.HEADING, ParagraphType.TITLE_PAGE}
    ]

    if len(leading_headings) >= 3 and not leading_non_headings:
        protected.update(paragraph.index for paragraph in leading_headings)

    return protected


def _configure_main_text_style(style, dominant_values: dict[str, Any], profile: Profile) -> None:
    font_family = (
        _get_equals_value(profile, "main_text", "font_family")
        or dominant_values.get("font_family")
        or "Times New Roman"
    )
    font_size = (
        _get_equals_value(profile, "main_text", "font_size")
        or dominant_values.get("font_size")
        or 14
    )
    font_size = _clamp_value(
        float(font_size),
        _get_min_value(profile, "main_text", "font_size"),
        _get_max_value(profile, "main_text", "font_size"),
    ) or 14

    style.font.name = str(font_family)
    style.font.size = Pt(float(font_size))
    style.font.bold = False
    style.font.italic = False
    style.font.color.rgb = RGBColor.from_string("000000")

    paragraph_format = style.paragraph_format
    _set_style_alignment(style, _preferred_main_text_alignment(profile, dominant_values))
    paragraph_format.first_line_indent = Cm(float(_get_equals_value(profile, "main_text", "first_line_indent") or dominant_values.get("first_line_indent") or 1.25))
    paragraph_format.left_indent = Cm(float(_get_equals_value(profile, "main_text", "left_indent") or 0))
    paragraph_format.right_indent = Cm(float(_get_equals_value(profile, "main_text", "right_indent") or 0))
    paragraph_format.line_spacing = float(_get_equals_value(profile, "main_text", "line_spacing") or dominant_values.get("line_spacing") or 1.5)
    paragraph_format.space_before = Pt(float(_get_equals_value(profile, "main_text", "space_before") or 0))
    paragraph_format.space_after = Pt(float(_get_equals_value(profile, "main_text", "space_after") or 0))


def _configure_heading_style(
    style,
    level: int,
    heading_font_sizes: dict[int, float],
    profile: Profile,
) -> None:
    heading_size = heading_font_sizes.get(level)
    if heading_size is None:
        main_size = 14
        heading_size = main_size + 2 * max(0, 3 - level)

    style.font.name = "Times New Roman"
    style.font.size = Pt(float(heading_size))
    style.font.bold = _choose_heading_bold_for_autofix(profile, level)
    style.font.italic = False
    style.font.color.rgb = RGBColor.from_string("000000")

    paragraph_format = style.paragraph_format
    alignment = _choose_heading_alignment_for_autofix(profile, level)
    word_alignment = ALIGNMENT_TO_WORD.get(alignment or "")
    if word_alignment is not None:
        paragraph_format.alignment = word_alignment

    # ГОСТ 7.6: заголовок оформляется без абзацных уступов и втяжек.
    # Не ставим first_line_indent равный основному тексту, чтобы H2/H3
    # не выглядели «съехавшими» по сравнению с H1.
    paragraph_format.first_line_indent = Cm(0)
    paragraph_format.left_indent = Cm(0)
    paragraph_format.right_indent = Cm(0)
    paragraph_format.line_spacing = 1.0
    paragraph_format.space_before = Pt(float(heading_size))
    paragraph_format.space_after = Pt(float(heading_size) / 2)
    paragraph_format.keep_with_next = True
    paragraph_format.keep_together = True
    paragraph_format.page_break_before = level == 1


def _configure_role_heading_style(
    style,
    role_target: str,
    level: int | None,
    heading_font_sizes: dict[int, float],
    profile: Profile,
) -> None:
    level_target = f"heading_level_{level}" if level is not None else None
    targets = [role_target, level_target, "heading"]

    font_family = (
        _first_profile_value(profile, targets, "font_family")
        or _get_equals_value(profile, "main_text", "font_family")
        or "Times New Roman"
    )
    font_size = _first_profile_value(profile, targets, "font_size")
    if font_size is None and level is not None:
        font_size = heading_font_sizes.get(level)
    if font_size is None:
        font_size = _get_equals_value(profile, "main_text", "font_size") or 14

    bold = _first_profile_value(profile, targets, "bold")
    if bold is None:
        bold = _choose_heading_bold_for_autofix(profile, level)

    style.font.name = str(font_family)
    style.font.size = Pt(float(font_size))
    style.font.bold = bool(bold) if bold is not None else True
    style.font.italic = False
    style.font.color.rgb = RGBColor.from_string(
        str(_first_profile_value(profile, targets, "font_color") or "000000")
    )

    paragraph_format = style.paragraph_format
    alignment = _choose_heading_alignment_for_autofix(
        profile,
        level,
        is_structural_heading=role_target == "structural_heading",
        role_target=role_target,
    )
    word_alignment = ALIGNMENT_TO_WORD.get(alignment or "")
    if word_alignment is not None:
        paragraph_format.alignment = word_alignment

    paragraph_format.first_line_indent = Cm(float(_first_profile_value(profile, targets, "first_line_indent") or 0))
    paragraph_format.left_indent = Cm(float(_first_profile_value(profile, targets, "left_indent") or 0))
    paragraph_format.right_indent = Cm(float(_first_profile_value(profile, targets, "right_indent") or 0))
    paragraph_format.line_spacing = float(_first_profile_value(profile, targets, "line_spacing") or 1.0)
    paragraph_format.space_before = Pt(float(_first_profile_value(profile, targets, "space_before") or float(font_size)))
    paragraph_format.space_after = Pt(float(_first_profile_value(profile, targets, "space_after") or float(font_size) / 2))
    paragraph_format.keep_with_next = bool(_first_profile_value(profile, targets, "keep_with_next") if _first_profile_value(profile, targets, "keep_with_next") is not None else True)
    paragraph_format.keep_together = bool(_first_profile_value(profile, targets, "keep_together") if _first_profile_value(profile, targets, "keep_together") is not None else True)
    page_break_value = _first_profile_value(profile, [role_target, level_target], "page_break_before")
    paragraph_format.page_break_before = bool(page_break_value) if page_break_value is not None else role_target in {"structural_heading", "section_heading", "appendix_heading"}


def _prepare_normcontrol_styles(
    document,
    dominant_values: dict[str, Any],
    heading_font_sizes: dict[int, float],
    profile: Profile,
) -> dict[str, Any]:
    styles: dict[str, Any] = {}

    main_style = _get_or_create_paragraph_style(document, NORMCONTROL_MAIN_TEXT_STYLE)
    _configure_main_text_style(main_style, dominant_values, profile)
    styles["main_text"] = main_style

    heading_levels = set(heading_font_sizes) | {1, 2, 3}
    for level in sorted(heading_levels):
        style = _get_or_create_paragraph_style(
            document,
            f"{NORMCONTROL_HEADING_STYLE_PREFIX} {level}",
        )
        _configure_heading_style(style, level, heading_font_sizes, profile)
        styles[f"heading_{level}"] = style

    role_levels = {
        "structural_heading": 1,
        "section_heading": 1,
        "subsection_heading": 2,
        "point_heading": 3,
        "appendix_heading": 1,
    }
    for role_target, level in role_levels.items():
        style = _get_or_create_paragraph_style(
            document,
            ROLE_HEADING_STYLE_NAMES[role_target],
        )
        _configure_role_heading_style(
            style=style,
            role_target=role_target,
            level=level,
            heading_font_sizes=heading_font_sizes,
            profile=profile,
        )
        styles[role_target] = style

    return styles


def _clamp_value(
    actual: float | None,
    minimum: float | None,
    maximum: float | None,
) -> float | None:
    """
    Приводит значение к допустимому диапазону.

    Если значение уже внутри диапазона, возвращает его без изменений.
    """

    if actual is None:
        if minimum is not None:
            return minimum
        if maximum is not None:
            return maximum
        return None

    corrected = actual

    if minimum is not None and corrected < minimum:
        corrected = minimum

    if maximum is not None and corrected > maximum:
        corrected = maximum

    return corrected


def _apply_font_family(paragraph, font_family: str) -> None:
    """Применяет шрифт ко всем фрагментам текста в абзаце."""

    apply_paragraph_value(paragraph, "font_family", font_family)


def _apply_font_size(paragraph, font_size: int | float) -> None:
    """Применяет размер шрифта ко всем фрагментам текста в абзаце."""

    apply_paragraph_value(paragraph, "font_size", font_size)


def _clear_direct_font_size(paragraph) -> None:
    for run in paragraph.runs:
        run.font.size = None


def _apply_bold(paragraph, bold: bool) -> None:
    """Применяет полужирное начертание ко всем фрагментам текста в абзаце."""

    apply_paragraph_value(paragraph, "bold", bold)


def _apply_italic(paragraph, italic: bool) -> None:
    """Применяет курсивное начертание ко всем фрагментам текста в абзаце."""

    apply_paragraph_value(paragraph, "italic", italic)


def _apply_font_color(paragraph, color: str = "000000") -> None:
    """Применяет цвет шрифта ко всем фрагментам текста в абзаце."""

    rgb = RGBColor.from_string(color)
    for run in paragraph.runs:
        run.font.color.rgb = rgb


def _non_empty_runs(parsed_paragraph):
    return [run for run in parsed_paragraph.runs if run.text.strip()]


def _is_whole_paragraph_colored(parsed_paragraph) -> bool:
    runs = _non_empty_runs(parsed_paragraph)
    if not runs:
        return False

    colors = {run.font_color for run in runs}
    return len(colors) == 1 and next(iter(colors)) not in {None, "000000"}


def _remove_terminal_dot(paragraph) -> None:
    """
    Убирает точку в конце заголовка.

    Ищет последнюю непустую часть текста и удаляет последнюю точку,
    не трогая остальной текст.
    """

    for run in reversed(paragraph.runs):
        if not run.text.strip():
            continue

        run.text = re.sub(r"\.\s*$", "", run.text)
        return


def _set_alignment(paragraph, alignment: str) -> None:
    """Устанавливает выравнивание абзаца."""

    apply_paragraph_value(paragraph, "alignment", alignment)


def _get_section_margin_pattern(parsed_section) -> tuple[float | None, float | None, float | None, float | None]:
    """Возвращает набор полей секции."""

    return (
        _normalize_value(parsed_section.top_margin_cm),
        _normalize_value(parsed_section.bottom_margin_cm),
        _normalize_value(parsed_section.left_margin_cm),
        _normalize_value(parsed_section.right_margin_cm),
    )


def _is_margin_value_valid_for_autofix(
    value: float | None,
    profile: Profile,
    parameter: str,
) -> bool:
    """Проверяет, соответствует ли поле диапазону профиля."""

    if value is None:
        return False

    minimum = _get_min_value(profile, "page", parameter)
    maximum = _get_max_value(profile, "page", parameter)

    if minimum is not None and value < minimum:
        return False

    if maximum is not None and value > maximum:
        return False

    return True


def _is_margin_pattern_valid_for_autofix(
    pattern: tuple[float | None, float | None, float | None, float | None],
    profile: Profile,
) -> bool:
    """Проверяет, что все поля секции соответствуют профилю."""

    parameters = [
        "top_margin",
        "bottom_margin",
        "left_margin",
        "right_margin",
    ]

    for parameter, value in zip(parameters, pattern):
        if not _is_margin_value_valid_for_autofix(value, profile, parameter):
            return False

    return True


def _get_margin_fallback_from_profile(profile: Profile) -> tuple[float, float, float, float]:
    """Возвращает стандартные поля из правила единообразия секций."""

    for rule in profile.rules:
        if (
            rule.category == "consistency"
            and rule.target == "page"
            and rule.parameter == "margins_consistency"
        ):
            strategy = rule.consistency_strategy or {}
            fallback = strategy.get("fallback_margins")

            if isinstance(fallback, dict):
                return (
                    float(fallback.get("top_margin", 2.5)),
                    float(fallback.get("bottom_margin", 2.5)),
                    float(fallback.get("left_margin", 2.5)),
                    float(fallback.get("right_margin", 2.5)),
                )

    return (2.5, 2.5, 2.5, 2.5)


def _get_exact_margin_pattern_from_profile(profile: Profile) -> tuple[float, float, float, float] | None:
    values = [
        _get_equals_value(profile, "page", "top_margin"),
        _get_equals_value(profile, "page", "bottom_margin"),
        _get_equals_value(profile, "page", "left_margin"),
        _get_equals_value(profile, "page", "right_margin"),
    ]
    if all(value is not None for value in values):
        return tuple(float(value) for value in values)  # type: ignore[arg-type]
    return None


def _choose_margin_pattern_for_autofix(
    parsed_document,
    profile: Profile,
) -> tuple[float, float, float, float]:
    """
    Выбирает поля для автоисправления секций.

    Если большинство секций имеет одинаковые корректные поля, берём это большинство.
    Если большинства нет, используем стандартные поля 2.5 см.
    """

    exact_pattern = _get_exact_margin_pattern_from_profile(profile)
    if exact_pattern is not None:
        return exact_pattern

    if not parsed_document.sections:
        return _get_margin_fallback_from_profile(profile)

    patterns = [
        _get_section_margin_pattern(section)
        for section in parsed_document.sections
    ]

    valid_patterns = [
        pattern
        for pattern in patterns
        if _is_margin_pattern_valid_for_autofix(pattern, profile)
    ]

    counter = Counter(valid_patterns)

    if counter:
        dominant_pattern, dominant_count = counter.most_common(1)[0]

        if dominant_count > len(parsed_document.sections) / 2:
            return tuple(float(value) for value in dominant_pattern)

    return _get_margin_fallback_from_profile(profile)


def _apply_margin_pattern_to_section(
    section,
    pattern: tuple[float, float, float, float],
) -> None:
    """Применяет набор полей к секции DOCX."""

    top_margin, bottom_margin, left_margin, right_margin = pattern

    section.top_margin = Cm(top_margin)
    section.bottom_margin = Cm(bottom_margin)
    section.left_margin = Cm(left_margin)
    section.right_margin = Cm(right_margin)


def _fix_page_margins(document, profile: Profile, parsed_document) -> None:
    """
    Исправляет поля секций.

    Логика:
    - если большинство секций оформлено одинаково и соответствует ГОСТу,
      все остальные секции приводятся к этому варианту;
    - если корректного большинства нет, устанавливаются поля 2.5 см со всех сторон.
    """

    target_pattern = _choose_margin_pattern_for_autofix(
        parsed_document=parsed_document,
        profile=profile,
    )

    for section in document.sections:
        _apply_margin_pattern_to_section(section, target_pattern)


def _paragraph_has_page_number(paragraph) -> bool:
    return "PAGE" in paragraph._p.xml


def _part_has_page_number(part) -> bool:
    return "PAGE" in part._element.xml


def _add_page_number_field(paragraph) -> None:
    run = paragraph.add_run()

    field_begin = OxmlElement("w:fldChar")
    field_begin.set(qn("w:fldCharType"), "begin")

    instr_text = OxmlElement("w:instrText")
    instr_text.set(qn("xml:space"), "preserve")
    instr_text.text = " PAGE "

    field_separate = OxmlElement("w:fldChar")
    field_separate.set(qn("w:fldCharType"), "separate")

    text = OxmlElement("w:t")
    text.text = "1"

    field_end = OxmlElement("w:fldChar")
    field_end.set(qn("w:fldCharType"), "end")

    run._r.append(field_begin)
    run._r.append(instr_text)
    run._r.append(field_separate)
    run._r.append(text)
    run._r.append(field_end)


def _ensure_footer_page_number(section, alignment: str = "right") -> None:
    footer = section.footer

    if _part_has_page_number(footer):
        for paragraph in footer.paragraphs:
            if _paragraph_has_page_number(paragraph):
                _set_alignment(paragraph, alignment)
        return

    paragraph = footer.paragraphs[0] if footer.paragraphs else footer.add_paragraph()
    if paragraph.text.strip():
        paragraph = footer.add_paragraph()

    _set_alignment(paragraph, alignment)
    _add_page_number_field(paragraph)


def _remove_page_number_restart(section) -> None:
    sect_pr = section._sectPr
    page_number_type = sect_pr.find(qn("w:pgNumType"))

    if page_number_type is not None:
        sect_pr.remove(page_number_type)


def _remove_page_number_paragraphs(part) -> None:
    for paragraph in list(part.paragraphs):
        if _paragraph_has_page_number(paragraph):
            _remove_paragraph(paragraph)


def _fix_header_footer_distances(document, profile: Profile) -> None:
    min_header_distance = _get_min_value(profile, "page", "header_distance")
    min_footer_distance = _get_min_value(profile, "page", "footer_distance")

    for section in document.sections:
        if min_header_distance is not None:
            section.header_distance = Cm(float(min_header_distance))

        if min_footer_distance is not None:
            section.footer_distance = Cm(float(min_footer_distance))


def _fix_page_numbering(document, parsed_document, profile: Profile) -> None:
    page_area = _get_equals_value(profile, "page", "page_number_area")
    allowed_alignment = _get_allowed_values(profile, "page", "page_number_alignment")

    if page_area != "footer":
        return

    alignment = "right"
    if allowed_alignment and "right" not in allowed_alignment:
        alignment = str(allowed_alignment[0])

    has_title_page = any(
        paragraph.paragraph_type == ParagraphType.TITLE_PAGE
        for paragraph in parsed_document.paragraphs
    )
    hide_first_page_number = (
        has_title_page
        or _profile_has_parameter(profile, "front_matter_page_numbers_hidden_until_intro")
    )

    for index, section in enumerate(document.sections):
        section.different_first_page_header_footer = hide_first_page_number and index == 0
        if hide_first_page_number and index == 0:
            _remove_page_number_paragraphs(section.first_page_header)
            _remove_page_number_paragraphs(section.first_page_footer)

        _remove_page_number_restart(section)
        _ensure_footer_page_number(section, alignment)


def _remove_paragraph(paragraph) -> None:
    element = paragraph._element
    element.getparent().remove(element)
    paragraph._p = paragraph._element = None


def _remove_empty_paragraphs_between_content(document, parsed_document) -> None:
    content_indexes = [
        paragraph.index
        for paragraph in parsed_document.paragraphs
        if paragraph.paragraph_type != ParagraphType.TITLE_PAGE
        and paragraph.text.strip()
    ]

    if not content_indexes:
        return

    first_index = min(content_indexes)
    last_index = max(content_indexes)
    paragraph_indexes_to_remove = [
        paragraph.index
        for paragraph in parsed_document.paragraphs
        if paragraph.paragraph_type != ParagraphType.TITLE_PAGE
        and not paragraph.text.strip()
        and first_index < paragraph.index < last_index
    ]

    for index in sorted(paragraph_indexes_to_remove, reverse=True):
        if index < len(document.paragraphs):
            _remove_paragraph(document.paragraphs[index])


def _get_main_text_font_size(parsed_document) -> float | None:
    sizes = [
        paragraph.font_size_pt
        for paragraph in parsed_document.paragraphs
        if paragraph.paragraph_type == ParagraphType.MAIN_TEXT
        and paragraph.text.strip()
        and paragraph.font_size_pt is not None
    ]

    if not sizes:
        return None

    return max(set(sizes), key=sizes.count)


def _get_expected_heading_font_sizes(
    parsed_document,
    profile: Profile | None = None,
) -> dict[int, float]:
    main_size = _get_main_text_font_size(parsed_document)
    if main_size is None:
        return {}

    if profile is not None:
        main_size = _clamp_value(
            main_size,
            _get_min_value(profile, "main_text", "font_size"),
            _get_max_value(profile, "main_text", "font_size"),
        ) or main_size

    levels = sorted({
        paragraph.heading_level
        for paragraph in parsed_document.paragraphs
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


def _fix_main_text_paragraph(paragraph, parsed_paragraph, profile: Profile) -> None:
    """
    Исправляет основной текст.

    Для ГОСТ-профиля исправляются только безопасные нарушения:
    - абзацный отступ меньше минимального;
    - недопустимое выравнивание;
    - недопустимый межстрочный интервал.

    Для локальных профилей также поддерживаются точные правила equals
    для шрифта, размера, интервала и отступа.
    """

    # Точные значения для локальных профилей, если они есть
    font_family = _get_equals_value(profile, "main_text", "font_family")
    font_size = _get_equals_value(profile, "main_text", "font_size")
    exact_line_spacing = _get_equals_value(profile, "main_text", "line_spacing")
    exact_first_line_indent = _get_equals_value(profile, "main_text", "first_line_indent")
    exact_alignment = _get_equals_value(profile, "main_text", "alignment")
    exact_left_indent = _get_equals_value(profile, "main_text", "left_indent")
    exact_right_indent = _get_equals_value(profile, "main_text", "right_indent")

    _clear_direct_font_size(paragraph)

    if font_family is not None:
        _apply_font_family(paragraph, str(font_family))

    if _get_equals_value(profile, "main_text", "bold") is False and parsed_paragraph.bold:
        _apply_bold(paragraph, False)

    if _get_equals_value(profile, "main_text", "italic") is False and parsed_paragraph.italic:
        _apply_italic(paragraph, False)

    if _is_whole_paragraph_colored(parsed_paragraph):
        _apply_font_color(paragraph, "000000")

    exact_font_color = _get_equals_value(profile, "main_text", "font_color")
    if str(exact_font_color or "").lower() in {"000000", "black", "черный", "чёрный"}:
        _apply_font_color(paragraph, "000000")

    paragraph.paragraph_format.space_before = Pt(0)
    paragraph.paragraph_format.space_after = Pt(0)

    if font_size is not None:
        _apply_font_size(paragraph, float(font_size))

    min_font_size = _get_min_value(profile, "main_text", "font_size")
    max_font_size = _get_max_value(profile, "main_text", "font_size")
    corrected_font_size = _clamp_value(
        parsed_paragraph.font_size_pt,
        min_font_size,
        max_font_size,
    )

    if (
        corrected_font_size is not None
        and parsed_paragraph.font_size_pt != corrected_font_size
    ):
        _apply_font_size(paragraph, float(corrected_font_size))

    if exact_line_spacing is not None:
        paragraph.paragraph_format.line_spacing = float(exact_line_spacing)

    if exact_first_line_indent is not None:
        paragraph.paragraph_format.first_line_indent = Cm(float(exact_first_line_indent))

    if exact_alignment is not None:
        _set_alignment(paragraph, str(exact_alignment))

    if exact_left_indent is not None:
        paragraph.paragraph_format.left_indent = Cm(float(exact_left_indent))

    if exact_right_indent is not None:
        paragraph.paragraph_format.right_indent = Cm(float(exact_right_indent))
        
    # Диапазон для абзацного отступа
    min_indent = _get_min_value(profile, "main_text", "first_line_indent")

    if min_indent is not None:
        actual_indent = parsed_paragraph.first_line_indent_cm
        corrected_indent = _clamp_value(actual_indent, min_indent, None)

        if corrected_indent is not None and corrected_indent != actual_indent:
            paragraph.paragraph_format.first_line_indent = Cm(corrected_indent)

    # Допустимые варианты выравнивания
    allowed_alignments = _get_allowed_values(profile, "main_text", "alignment")

    if exact_alignment is None and allowed_alignments and "justify" in allowed_alignments:
        _set_alignment(paragraph, "justify")
    elif not _is_allowed_value(parsed_paragraph.alignment, allowed_alignments):
        if allowed_alignments:
            preferred = "justify" if "justify" in allowed_alignments else str(allowed_alignments[0])
            _set_alignment(paragraph, preferred)

    # Допустимые варианты межстрочного интервала
    allowed_line_spacing = _get_allowed_values(profile, "main_text", "line_spacing")

    if allowed_line_spacing is not None:
        actual_spacing = parsed_paragraph.line_spacing

        if not _is_allowed_value(actual_spacing, allowed_line_spacing):
            # Если интервал недопустим, выбираем 1.5, если он разрешён.
            # Иначе берём первый допустимый вариант.
            corrected_spacing = (
                1.5 if 1.5 in allowed_line_spacing else float(allowed_line_spacing[0])
            )
            paragraph.paragraph_format.line_spacing = corrected_spacing


def _fix_heading_paragraph(
    paragraph,
    parsed_paragraph,
    profile: Profile,
    heading_font_sizes: dict[int, float] | None = None,
) -> None:
    """
    Исправляет безопасные параметры заголовков.

    Для ГОСТ-профиля:
    - убирает точку в конце заголовка;
    - меняет недопустимое выравнивание на левое или первое разрешённое.

    Для локальных профилей также поддерживает точные правила equals
    для заголовков конкретного уровня.
    """

    # Общие правила для всех заголовков
    terminal_dot = _get_equals_value(profile, "heading", "terminal_dot")

    if terminal_dot is False and parsed_paragraph.text.strip().endswith("."):
        _remove_terminal_dot(paragraph)

    _apply_font_color(paragraph, "000000")

    targets = _target_order_for_heading(parsed_paragraph)
    role_target = targets[0]
    level_target = targets[1]

    heading_bold = _first_profile_value(profile, targets, "bold")
    if heading_bold is None:
        heading_bold = _choose_heading_bold_for_autofix(
            profile,
            parsed_paragraph.heading_level,
        )
    if heading_bold is not None:
        _apply_bold(paragraph, bool(heading_bold))

    exact_first_line_indent = _first_profile_value(profile, targets, "first_line_indent")
    exact_left_indent = _first_profile_value(profile, targets, "left_indent")
    exact_right_indent = _first_profile_value(profile, targets, "right_indent")
    heading_alignment = _choose_heading_alignment_for_autofix(
        profile,
        parsed_paragraph.heading_level,
        parsed_paragraph.is_structural_heading,
        role_target=role_target,
    )

    if heading_alignment is not None:
        _set_alignment(paragraph, heading_alignment)

    # ГОСТ 7.6: заголовок оформляется без абзацных уступов и втяжек.
    # Если профиль задаёт точное значение equals, используем его, иначе 0.
    if exact_first_line_indent is not None:
        paragraph.paragraph_format.first_line_indent = Cm(float(exact_first_line_indent))
    else:
        paragraph.paragraph_format.first_line_indent = Cm(0)

    if exact_left_indent is not None:
        paragraph.paragraph_format.left_indent = Cm(float(exact_left_indent))
    else:
        paragraph.paragraph_format.left_indent = Cm(0)

    if exact_right_indent is not None:
        paragraph.paragraph_format.right_indent = Cm(float(exact_right_indent))
    else:
        paragraph.paragraph_format.right_indent = Cm(0)

    allowed_heading_alignments = _get_allowed_values(profile, "heading", "alignment")

    if not _is_allowed_value(heading_alignment, allowed_heading_alignments):
        if allowed_heading_alignments:
            # Для универсального ГОСТ-профиля безопаснее выбрать левый край.
            preferred = (
                "left"
                if "left" in allowed_heading_alignments
                else str(allowed_heading_alignments[0])
            )
            _set_alignment(paragraph, preferred)

    font_family = _first_profile_value(profile, targets, "font_family")
    font_size = _first_profile_value(profile, targets, "font_size")
    bold = _first_profile_value(profile, targets, "bold")

    if font_family is not None:
        _apply_font_family(paragraph, str(font_family))

    if font_size is not None:
        _apply_font_size(paragraph, float(font_size))
    elif heading_font_sizes and parsed_paragraph.heading_level in heading_font_sizes:
        _apply_font_size(paragraph, heading_font_sizes[parsed_paragraph.heading_level])

    if bold is not None:
        _apply_bold(paragraph, bool(bold))

    exact_line_spacing = _first_profile_value(profile, targets, "line_spacing")
    exact_space_before = _first_profile_value(profile, targets, "space_before")
    exact_space_after = _first_profile_value(profile, targets, "space_after")
    exact_keep_with_next = _first_profile_value(profile, targets, "keep_with_next")
    exact_keep_together = _first_profile_value(profile, targets, "keep_together")
    exact_page_break = _first_profile_value(profile, _heading_specific_target_order(parsed_paragraph), "page_break_before")

    if exact_line_spacing is not None:
        paragraph.paragraph_format.line_spacing = float(exact_line_spacing)

    if exact_space_before is not None:
        paragraph.paragraph_format.space_before = Pt(float(exact_space_before))

    if exact_space_after is not None:
        paragraph.paragraph_format.space_after = Pt(float(exact_space_after))

    if heading_font_sizes and parsed_paragraph.heading_level in heading_font_sizes and (
        exact_line_spacing is None or exact_space_before is None or exact_space_after is None
    ):
        heading_size = heading_font_sizes[parsed_paragraph.heading_level]
        if exact_line_spacing is None:
            paragraph.paragraph_format.line_spacing = 1.0
        if exact_space_before is None:
            paragraph.paragraph_format.space_before = Pt(heading_size)
        if exact_space_after is None:
            paragraph.paragraph_format.space_after = Pt(heading_size / 2)

    paragraph.paragraph_format.keep_with_next = (
        bool(exact_keep_with_next) if exact_keep_with_next is not None else True
    )
    paragraph.paragraph_format.keep_together = (
        bool(exact_keep_together) if exact_keep_together is not None else True
    )
    if exact_page_break is not None:
        paragraph.paragraph_format.page_break_before = bool(exact_page_break)
    elif parsed_paragraph.heading_level == 1 or role_target in {"structural_heading", "section_heading", "appendix_heading"}:
        paragraph.paragraph_format.page_break_before = True
    else:
        paragraph.paragraph_format.page_break_before = False

    if parsed_paragraph.is_numbered_heading:
        fixed_numbering = re.sub(
            r"^(\d+(?:\.\d+)*),(\d+)(?=\s)",
            r"\1.\2",
            paragraph.text,
        )
        if fixed_numbering != paragraph.text:
            _replace_paragraph_text(paragraph, fixed_numbering)


def _fix_safe_typography(paragraph, profile: Profile) -> None:
    if not paragraph.runs:
        return

    original_paragraph_text = paragraph.text
    if original_paragraph_text.startswith("- ") and (
        _profile_has_parameter(profile, "list_marker_dash_required")
        or _profile_has_parameter(profile, "hyphen_list_marker_not_recommended")
    ):
        _replace_paragraph_text(paragraph, "— " + original_paragraph_text[2:])

    for run in paragraph.runs:
        text = run.text

        if _profile_has_parameter(profile, "repeated_spaces"):
            text = re.sub(r" {2,}", " ", text)

        if _profile_has_any_parameter(profile, {"spaces_near_punctuation", "spaces_inside_brackets_quotes"}):
            text = re.sub(r"\s+([.,;:!?])", r"\1", text)
            text = re.sub(r"([(\[{«„])\s+", r"\1", text)
            text = re.sub(r"\s+([)\]}»“])", r"\1", text)

        if _profile_has_any_parameter(profile, {"number_sign_symbol", "number_sign_nbsp", "nbsp_after_number_sign"}):
            text = re.sub(r"\b(?:N|No)\s*(\d+)", lambda m: f"№\u00a0{m.group(1)}", text, flags=re.IGNORECASE)
            text = re.sub(r"#\s*(\d+)", lambda m: f"№\u00a0{m.group(1)}", text)
            text = re.sub(r"(№) (\d+)", lambda m: f"{m.group(1)}\u00a0{m.group(2)}", text)

        if _profile_has_parameter(profile, "nbsp_after_paragraph_sign"):
            text = re.sub(r"(§) (\d+)", lambda m: f"{m.group(1)}\u00a0{m.group(2)}", text)

        if _profile_has_parameter(profile, "nbsp_after_figure_table_reference"):
            text = re.sub(r"\b(рис\.|табл\.) (\d+)", lambda m: f"{m.group(1)}\u00a0{m.group(2)}", text, flags=re.IGNORECASE)

        if _profile_has_parameter(profile, "nbsp_between_initials"):
            text = re.sub(r"\b([А-ЯЁA-Z]\.) ([А-ЯЁA-Z]\.)", lambda m: f"{m.group(1)}\u00a0{m.group(2)}", text)
            text = re.sub(r"\b([А-ЯЁA-Z]\.\u00a0[А-ЯЁA-Z]\.) ([А-ЯЁA-Za-zА-ЯЁа-яё-]+)", lambda m: f"{m.group(1)}\u00a0{m.group(2)}", text)

        if _profile_has_any_parameter(profile, {"wrong_multiplication_symbols", "multiplication_symbol"}):
            text = re.sub(r"\b(\d+(?:[,.]\d+)?)\*(?=\d)", r"\1×", text)
            text = re.sub(r"(?<=\d)\s*[xX]\s*(?=\d)", "×", text)

        if _profile_has_parameter(profile, "numeric_range_dash"):
            text = re.sub(r"(?<![\w.])(\d+)\s*-\s*(\d+)(?![\w.])", r"\1–\2", text)
            text = re.sub(r"(?<![\w.])(\d+)\s+[–—]\s+(\d+)(?![\w.])", r"\1–\2", text)

        if _profile_has_any_parameter(profile, {"hyphen_instead_of_dash", "dash_spacing"}):
            letters = r"A-Za-zА-Яа-яЁё"
            text = re.sub(rf"(?<=[{letters}])\s-\s(?=[{letters}])", " — ", text)
            text = re.sub(rf"(?<=[{letters}])—(?=[{letters}])", " — ", text)
            text = re.sub(rf"(?<=[{letters}])—\s+(?=[{letters}])", " — ", text)
            text = re.sub(rf"(?<=[{letters}])\s+—(?=[{letters}])", " — ", text)

        if _profile_has_parameter(profile, "decimal_separator_comma"):
            text = re.sub(r"\b(\d+(?:[,.]\d+)?)\.(\d+)(?=\s*(?:см|мм|м|км|г|кг|мг|л|мл|с|мин|ч|Вт|кВт|Па|кПа|МПа|%))", r"\1,\2", text, flags=re.IGNORECASE)

        if _profile_has_parameter(profile, "temperature_nbsp"):
            text = re.sub(r"\b(\d+(?:[,.]\d+)?)°([CFС])\b", lambda m: f"{m.group(1)}\u00a0°{m.group(2)}", text)
            text = re.sub(r"\b(\d+(?:[,.]\d+)?) °(?![CFС])", r"\1°", text)

        if _profile_has_parameter(profile, "percent_nbsp"):
            text = re.sub(r"\b(\d+(?:[,.]\d+)?) ([%‰])", lambda m: f"{m.group(1)}\u00a0{m.group(2)}", text)

        if _profile_has_any_parameter(profile, {"unit_nbsp", "nbsp_between_number_and_unit"}):
            text = re.sub(
                r"\b(\d+(?:[,.]\d+)?) (см|мм|м|км|г|кг|мг|л|мл|с|мин|ч|пт|К|K|Вт|кВт|Дж|кДж|Па|кПа|МПа|В|кВ|А|Гц|кГц|МГц|моль|%)\b",
                lambda m: f"{m.group(1)}\u00a0{m.group(2)}",
                text,
                flags=re.IGNORECASE,
            )

        if _profile_has_parameter(profile, "russian_quotes"):
            text = re.sub(r'"([^"\n]+)"', r"«\1»", text)

        if _profile_has_parameter(profile, "citation_omission_format"):
            text = re.sub(r"\[\s*(?:\.{3}|…)\s*\]", "<...>", text)

        if _profile_has_parameter(profile, "phone_number_format"):
            text = _format_plain_russian_phone(text)
        run.text = text

    if _profile_has_parameter(profile, "paragraph_edge_spaces"):
        paragraph.runs[0].text = paragraph.runs[0].text.lstrip(" ")
        paragraph.runs[-1].text = paragraph.runs[-1].text.rstrip(" ")


def _format_plain_russian_phone(text: str) -> str:
    def replace(match: re.Match) -> str:
        raw = match.group(0)
        digits = re.sub(r"\D", "", raw)
        if len(digits) == 11 and digits.startswith("7"):
            return f"+7 {digits[1:4]} {digits[4:7]}-{digits[7:9]}-{digits[9:11]}"
        if len(digits) == 11 and digits.startswith("8"):
            return f"8 {digits[1:4]} {digits[4:7]}-{digits[7:9]}-{digits[9:11]}"
        if len(digits) == 10:
            return f"{digits[0:3]} {digits[3:6]}-{digits[6:8]}-{digits[8:10]}"
        return raw

    return re.sub(r"(?<!\d)(?:\+?7|8)?\s?\(?\d{3}\)?[\s-]?\d{3}[\s-]?\d{2}[\s-]?\d{2}(?!\d)", replace, text)


def _replace_paragraph_text(paragraph, text: str) -> None:
    if not paragraph.runs:
        paragraph.add_run(text)
        return

    paragraph.runs[0].text = text
    for run in paragraph.runs[1:]:
        run.text = ""


def _remove_paragraph_numbering(paragraph) -> None:
    p_pr = paragraph._p.pPr
    if p_pr is not None and p_pr.numPr is not None:
        p_pr.remove(p_pr.numPr)


LIST_ITEM_MARKER_CHARS = "-\u2013\u2014\u2022\u25aa\u25ab\u2023\uf02d\uf076\uf0b7"
LIST_ITEM_TEXT_PATTERN = re.compile(
    rf"^(?P<prefix>\s*(?:[{re.escape(LIST_ITEM_MARKER_CHARS)}]|\d+[\).]|[а-яА-ЯёЁ][\).])\s+)(?P<body>.*)$"
)
LETTER_PATTERN = re.compile(r"[A-Za-zА-Яа-яЁё]")


NUMBERED_LIST_MARKER_TYPES = {"number_bracket", "number_dot", "letter_bracket", "letter_dot"}


def _profile_has_parameter(profile: Profile, parameter: str) -> bool:
    return any(rule.parameter == parameter and getattr(rule, "enabled", True) for rule in profile.rules)


def _profile_has_rule_id(profile: Profile, rule_id: str) -> bool:
    return any(rule.id == rule_id and getattr(rule, "enabled", True) for rule in profile.rules)


def _profile_has_any_parameter(profile: Profile, parameters: set[str]) -> bool:
    return any(_profile_has_parameter(profile, parameter) for parameter in parameters)


def _change_first_letter_case(text: str, *, upper: bool) -> str:
    match = LETTER_PATTERN.search(text)
    if not match:
        return text

    index = match.start()
    replacement = text[index].upper() if upper else text[index].lower()
    return text[:index] + replacement + text[index + 1:]


def _fix_list_item_text(
    text: str,
    marker_type: str | None,
    *,
    after_colon: bool,
    is_last: bool,
    force_dash_marker: bool = False,
    marker_text: str | None = None,
) -> str:
    match = LIST_ITEM_TEXT_PATTERN.match(text)
    if match:
        body = match.group("body").strip()
    else:
        body = text.strip()

    if not body:
        return text

    if force_dash_marker:
        marker_type = "dash"
        marker_text = "—"

    prefix = _list_prefix_for_marker_type(
        marker_type,
        0,
        marker_text=marker_text,
    ) or ""

    if after_colon and marker_type in {"dash", "hyphen", "bullet"}:
        body = _change_first_letter_case(body, upper=False)
        expected_end = "." if is_last else ";"
        body = body.rstrip(" .;,") + expected_end

    if marker_type in {"number_dot", "letter_dot"}:
        body = _change_first_letter_case(body, upper=True)

    return prefix + body


RUSSIAN_LIST_LETTERS = "абвгдежзиклмнопрстуфхцчшщэюя"


def _list_prefix_for_marker_type(
    marker_type: str | None,
    position: int,
    *,
    marker_text: str | None = None,
) -> str | None:
    if marker_type == "dash":
        return f"{(marker_text or '—').strip()} "
    if marker_type == "hyphen":
        return f"{(marker_text or '-').strip()} "
    if marker_type == "bullet":
        return f"{(marker_text or '•').strip()} "
    if marker_type == "number_dot":
        return f"{position + 1}. "
    if marker_type == "number_bracket":
        return f"{position + 1}) "
    if marker_type == "letter_dot":
        letter = RUSSIAN_LIST_LETTERS[position % len(RUSSIAN_LIST_LETTERS)]
        return f"{letter}. "
    if marker_type == "letter_bracket":
        letter = RUSSIAN_LIST_LETTERS[position % len(RUSSIAN_LIST_LETTERS)]
        return f"{letter}) "
    return None


def _extract_list_body(text: str) -> str:
    match = LIST_ITEM_TEXT_PATTERN.match(text)
    return match.group("body").strip() if match else text.strip()


def _list_marker_signature(parsed_paragraph) -> tuple[str | None, str | None]:
    marker_type = parsed_paragraph.list_marker_type
    marker = (parsed_paragraph.list_marker or "").strip() or None
    if marker_type in {"bullet", "dash", "hyphen", "other"}:
        return marker_type, marker
    return marker_type, None


def _dominant_list_marker_signature(group: list[Any]) -> tuple[str | None, str | None]:
    values = [_list_marker_signature(paragraph) for paragraph in group if paragraph.list_marker_type]
    if not values:
        return (None, None)
    counter = Counter(values)
    return counter.most_common(1)[0][0]


def _render_list_item_text(
    body: str,
    marker_type: str | None,
    position: int,
    *,
    after_colon: bool,
    is_last: bool,
    marker_text: str | None = None,
) -> str:
    body = body.strip()
    if not body:
        return body

    if after_colon and marker_type in {"dash", "hyphen", "bullet"}:
        body = _change_first_letter_case(body, upper=False)
        body = body.rstrip(" .;,") + ("." if is_last else ";")
    elif marker_type in NUMBERED_LIST_MARKER_TYPES:
        body = _change_first_letter_case(body, upper=True)

    prefix = _list_prefix_for_marker_type(
        marker_type,
        position,
        marker_text=marker_text,
    ) or ""
    return prefix + body


def _is_list_paragraph_for_autofix(parsed_paragraph, paragraph_count: int) -> bool:
    return (
        parsed_paragraph.text.strip()
        and parsed_paragraph.index < paragraph_count
        and parsed_paragraph.paragraph_type not in {ParagraphType.TITLE_PAGE, ParagraphType.TABLE_CELL}
        and (
            parsed_paragraph.paragraph_type == ParagraphType.LIST_ITEM
            or parsed_paragraph.is_automatic_list
            or parsed_paragraph.list_marker_type is not None
        )
    )


def _iter_autofix_list_groups(parsed_document, paragraph_count: int) -> list[list[Any]]:
    groups: list[list[Any]] = []
    current: list[Any] = []

    for parsed_paragraph in parsed_document.paragraphs:
        if _is_list_paragraph_for_autofix(parsed_paragraph, paragraph_count):
            current.append(parsed_paragraph)
            continue

        if current:
            groups.append(current)
            current = []

    if current:
        groups.append(current)

    return groups


def _dominant_indent_signature(group: list[Any]) -> tuple[float, float, float]:
    signatures = [
        (
            round(float(paragraph.first_line_indent_cm or 0.0), 2),
            round(float(paragraph.left_indent_cm or 0.0), 2),
            round(float(paragraph.right_indent_cm or 0.0), 2),
        )
        for paragraph in group
    ]
    if not signatures:
        return (0.0, 0.0, 0.0)
    return Counter(signatures).most_common(1)[0][0]


def _resolve_target_list_signature(
    group: list[Any],
    *,
    has_dash_marker_rule: bool,
    has_marker_consistency_rule: bool,
) -> tuple[str | None, str | None]:
    dominant_type, dominant_marker = _dominant_list_marker_signature(group)

    if dominant_type in NUMBERED_LIST_MARKER_TYPES:
        return dominant_type, None

    if has_dash_marker_rule:
        return "dash", "—"

    if has_marker_consistency_rule:
        if dominant_type == "dash":
            return "dash", "—"
        if dominant_type == "hyphen":
            return "hyphen", "-"
        if dominant_type == "bullet":
            return "bullet", dominant_marker or "•"
        return dominant_type, dominant_marker

    return (None, None)


def _fix_list_punctuation_policy(document, parsed_document, profile: Profile) -> None:
    has_punctuation_policy = _profile_has_parameter(profile, "list_punctuation_policy")
    has_dash_marker_rule = _profile_has_parameter(profile, "list_marker_dash_required")
    has_marker_consistency_rule = _profile_has_parameter(profile, "list_marker_consistency")
    has_indent_rule = _profile_has_rule_id(profile, "list_indent_equals_main_text")
    if not has_punctuation_policy and not has_dash_marker_rule and not has_marker_consistency_rule and not has_indent_rule:
        return

    groups = _iter_autofix_list_groups(parsed_document, len(document.paragraphs))

    for group in groups:
        target_marker_type, target_marker_text = _resolve_target_list_signature(
            group,
            has_dash_marker_rule=has_dash_marker_rule,
            has_marker_consistency_rule=has_marker_consistency_rule,
        )
        dominant_first_indent, dominant_left_indent, dominant_right_indent = _dominant_indent_signature(group)
        previous = next(
            (
                paragraph
                for paragraph in reversed(parsed_document.paragraphs)
                if paragraph.index < group[0].index
                and paragraph.paragraph_type not in {ParagraphType.EMPTY, ParagraphType.TITLE_PAGE, ParagraphType.TABLE_CELL}
                and paragraph.text.strip()
            ),
            None,
        )
        after_colon = bool(previous and previous.text.rstrip().endswith(":"))

        for position, parsed_paragraph in enumerate(group):
            paragraph = document.paragraphs[parsed_paragraph.index]
            if has_indent_rule:
                main_first_indent = _get_equals_value(profile, "main_text", "first_line_indent")
                main_left_indent = _get_equals_value(profile, "main_text", "left_indent")
                main_right_indent = _get_equals_value(profile, "main_text", "right_indent")
                paragraph.paragraph_format.first_line_indent = Cm(
                    float(main_first_indent if main_first_indent is not None else dominant_first_indent or 1.25)
                )
                paragraph.paragraph_format.left_indent = Cm(
                    float(main_left_indent if main_left_indent is not None else dominant_left_indent)
                )
                paragraph.paragraph_format.right_indent = Cm(
                    float(main_right_indent if main_right_indent is not None else dominant_right_indent)
                )
            elif has_marker_consistency_rule:
                paragraph.paragraph_format.first_line_indent = Cm(float(dominant_first_indent))
                paragraph.paragraph_format.left_indent = Cm(float(dominant_left_indent))
                paragraph.paragraph_format.right_indent = Cm(float(dominant_right_indent))

            current_signature = _list_marker_signature(parsed_paragraph)
            effective_signature = (
                target_marker_type,
                target_marker_text if target_marker_type in {"bullet", "dash", "hyphen"} else None,
            )
            should_replace_marker = target_marker_type is not None and current_signature != effective_signature

            if should_replace_marker and parsed_paragraph.is_automatic_list:
                _remove_paragraph_numbering(paragraph)
            elif has_dash_marker_rule and target_marker_type == "dash" and parsed_paragraph.is_automatic_list:
                _remove_paragraph_numbering(paragraph)

            effective_marker_type = target_marker_type or parsed_paragraph.list_marker_type
            effective_marker_text = (
                target_marker_text
                if target_marker_type in {"bullet", "dash", "hyphen"}
                else None
            )
            body = _extract_list_body(paragraph.text)
            preserve_existing_word_marker = (
                parsed_paragraph.is_automatic_list
                and not should_replace_marker
                and not (has_dash_marker_rule and target_marker_type == "dash")
            )

            if preserve_existing_word_marker:
                fixed_text = body.strip()
                if after_colon and effective_marker_type in {"dash", "hyphen", "bullet"}:
                    fixed_text = _change_first_letter_case(fixed_text, upper=False)
                    fixed_text = fixed_text.rstrip(" .;,") + ("." if position == len(group) - 1 else ";")
                elif effective_marker_type in NUMBERED_LIST_MARKER_TYPES:
                    fixed_text = _change_first_letter_case(fixed_text, upper=True)
            else:
                fixed_text = _render_list_item_text(
                    body,
                    effective_marker_type,
                    position,
                    after_colon=after_colon,
                    is_last=position == len(group) - 1,
                    marker_text=effective_marker_text,
                )
            if fixed_text != paragraph.text:
                _replace_paragraph_text(paragraph, fixed_text)


def _fix_caption_paragraph(paragraph, parsed_paragraph, profile: Profile) -> None:
    caption_target = (
        "figure_caption"
        if parsed_paragraph.caption_kind == "figure"
        else "table_caption"
        if parsed_paragraph.caption_kind == "table"
        else "caption"
    )
    targets = [caption_target, "caption"]

    caption_italic = _first_profile_value(profile, targets, "italic")
    if caption_italic is not None:
        _apply_italic(paragraph, bool(caption_italic))

    caption_bold = _first_profile_value(profile, targets, "bold")
    if caption_bold is not None:
        _apply_bold(paragraph, bool(caption_bold))

    caption_font_color = _first_profile_value(profile, targets, "font_color")
    if str(caption_font_color or "").lower() in {"000000", "black", "черный", "чёрный"}:
        _apply_font_color(paragraph, "000000")

    if _profile_has_any_parameter(profile, {"caption_line_spacing_single", "table_text_line_spacing"}):
        paragraph.paragraph_format.line_spacing = 1.0

    if parsed_paragraph.caption_kind == "figure" and _profile_has_parameter(profile, "figure_caption_alignment"):
        _set_alignment(paragraph, str(_get_equals_value(profile, "figure_caption", "figure_caption_alignment") or "center"))
    if parsed_paragraph.caption_kind == "table" and _profile_has_parameter(profile, "table_caption_alignment"):
        _set_alignment(paragraph, str(_get_equals_value(profile, "table_caption", "table_caption_alignment") or "left"))

    text = paragraph.text.strip()
    fixed_text = text

    if parsed_paragraph.caption_kind == "figure":
        expected_prefix = _get_equals_value(profile, "figure_caption", "figure_caption_prefix")
        if expected_prefix:
            fixed_text = re.sub(
                r"^(Рис\.)\s+",
                f"{expected_prefix} ",
                fixed_text,
                flags=re.IGNORECASE,
            )

        if _profile_has_parameter(profile, "figure_caption_separator"):
            separator = str(_get_equals_value(profile, "figure_caption", "figure_caption_separator") or "")
            if "тире" in separator:
                fixed_text = re.sub(
                    r"^(Рис\.|Рисунок)\s+(\d+(?:\.\d+)*)\.\s*",
                    r"\1 \2 — ",
                    fixed_text,
                    flags=re.IGNORECASE,
                )
            elif "точк" in separator:
                fixed_text = re.sub(
                    r"^(Рис\.|Рисунок)\s+(\d+(?:\.\d+)*)\s*[\u2014-]\s*",
                    r"\1 \2. ",
                    fixed_text,
                    flags=re.IGNORECASE,
                )

        if _profile_has_parameter(profile, "figure_caption_dot_after_number"):
            fixed_text = re.sub(
                r"^(Рис\.|Рисунок)\s+(\d+(?:\.\d+)*)\s*[\u2014-]\s*",
                r"\1 \2. ",
                fixed_text,
                flags=re.IGNORECASE,
            )
        if _profile_has_parameter(profile, "figure_caption_title_format") and fixed_text.endswith("."):
            fixed_text = fixed_text.rstrip(".").rstrip()
        if _profile_has_parameter(profile, "figure_caption_terminal_dot") and bool(_get_equals_value(profile, "figure_caption", "figure_caption_terminal_dot")) is False and fixed_text.endswith("."):
            fixed_text = fixed_text.rstrip(".").rstrip()

    if parsed_paragraph.caption_kind == "table":
        if _profile_has_parameter(profile, "table_title_format"):
            paragraph.paragraph_format.alignment = WD_ALIGN_PARAGRAPH.LEFT
            paragraph.paragraph_format.first_line_indent = Cm(0)
            paragraph.paragraph_format.left_indent = Cm(0)
            paragraph.paragraph_format.right_indent = Cm(0)
            paragraph.paragraph_format.line_spacing = 1.0
            paragraph.paragraph_format.keep_with_next = True
            paragraph.paragraph_format.keep_together = True

        if _profile_has_parameter(profile, "table_title_font_size"):
            title_font_size = float(_get_equals_value(profile, "main_text", "font_size") or 14)
            for run in paragraph.runs:
                run.font.size = Pt(title_font_size)

        expected_prefix = _get_equals_value(profile, "table_caption", "table_caption_prefix")
        if expected_prefix:
            fixed_text = re.sub(
                r"^(Табл\.)\s+",
                f"{expected_prefix} ",
                fixed_text,
                flags=re.IGNORECASE,
            )

        if _profile_has_parameter(profile, "table_caption_separator"):
            separator = str(_get_equals_value(profile, "table_caption", "table_caption_separator") or "")
            if "тире" in separator:
                fixed_text = re.sub(
                    r"^(Табл\.|Таблица)\s+(\d+(?:\.\d+)*)\.\s*",
                    r"\1 \2 — ",
                    fixed_text,
                    flags=re.IGNORECASE,
                )
            elif "точк" in separator:
                fixed_text = re.sub(
                    r"^(Табл\.|Таблица)\s+(\d+(?:\.\d+)*)\s*[\u2014-]\s*",
                    r"\1 \2. ",
                    fixed_text,
                    flags=re.IGNORECASE,
                )
        elif _profile_has_parameter(profile, "table_title_format"):
            fixed_text = re.sub(
                r"^(Табл\.|Таблица)\s+(\d+(?:\.\d+)*)\s*[\u2014-]\s*",
                r"\1 \2. ",
                fixed_text,
                flags=re.IGNORECASE,
            )

        if (
            _profile_has_parameter(profile, "table_caption_terminal_dot")
            or _profile_has_parameter(profile, "table_title_format")
            or _profile_has_parameter(profile, "no_dot_after_udc_keywords_table_title")
        ) and fixed_text.endswith("."):
            fixed_text = fixed_text.rstrip(".").rstrip()

    if _profile_has_parameter(profile, "no_dot_after_udc_keywords_table_title") and fixed_text.endswith("."):
        fixed_text = fixed_text.rstrip(".").rstrip()

    if fixed_text != text:
        _replace_paragraph_text(paragraph, fixed_text)


def _previous_paragraph_with_image(parsed_document, caption_index: int):
    checked = 0
    for candidate in reversed(parsed_document.paragraphs):
        if candidate.index >= caption_index:
            continue
        if not candidate.text.strip() and not candidate.has_inline_image:
            continue
        checked += 1
        if candidate.has_inline_image:
            return candidate
        if checked >= 5:
            return None
    return None


def _fix_object_caption_keep_rules(document, parsed_document, profile: Profile) -> None:
    if not _profile_has_any_parameter(
        profile,
        {
            "figure_caption_position",
            "figure_caption_alignment",
            "figure_caption_prefix",
            "figure_caption_separator",
            "figure_caption_terminal_dot",
            "image_keep_with_next",
            "table_caption_position",
            "table_caption_alignment",
            "table_caption_prefix",
            "table_caption_separator",
            "table_caption_terminal_dot",
            "table_title_keep",
        },
    ):
        return

    for parsed_paragraph in parsed_document.paragraphs:
        if (
            parsed_paragraph.paragraph_type != ParagraphType.CAPTION
            or parsed_paragraph.index >= len(document.paragraphs)
        ):
            continue

        paragraph = document.paragraphs[parsed_paragraph.index]
        paragraph.paragraph_format.keep_together = True

        if parsed_paragraph.caption_kind == "table":
            paragraph.paragraph_format.keep_with_next = True
            continue

        if parsed_paragraph.caption_kind == "figure":
            previous_image = _previous_paragraph_with_image(parsed_document, parsed_paragraph.index)
            if previous_image is not None and previous_image.index < len(document.paragraphs):
                image_paragraph = document.paragraphs[previous_image.index]
                image_paragraph.paragraph_format.keep_with_next = True
                image_paragraph.paragraph_format.keep_together = True


def _set_table_header_repeat(row) -> None:
    tr_pr = row._tr.get_or_add_trPr()
    tbl_header = tr_pr.find(qn("w:tblHeader"))
    if tbl_header is None:
        tbl_header = OxmlElement("w:tblHeader")
        tr_pr.append(tbl_header)
    tbl_header.set(qn("w:val"), "true")


def _allow_table_row_break(row) -> None:
    tr_pr = row._tr.trPr
    if tr_pr is None:
        return
    for cant_split in list(tr_pr.findall(qn("w:cantSplit"))):
        tr_pr.remove(cant_split)


def _fix_table_layout_rules(document, profile: Profile) -> None:
    repeat_header = _profile_has_parameter(profile, "table_repeat_header")
    allow_row_break = _profile_has_parameter(profile, "table_allow_row_break")
    if not repeat_header and not allow_row_break:
        return

    for table in document.tables:
        if repeat_header and table.rows:
            _set_table_header_repeat(table.rows[0])
        if allow_row_break:
            for row in table.rows:
                _allow_table_row_break(row)


def _fix_table_text(document, profile: Profile, main_text_font_size: float | None = None) -> None:
    """
    Автоисправление текста таблиц по ГОСТ 11.5 и 11.6.

    11.5: одинарный интервал, без абзацного и боковых отступов.
    11.6: кегль на 2 пункта меньше основного текста, если он известен.
    Шрифтовые правки головки (первая строка) не трогаются — там по 11.7
    допускается полужирное начертание и выравнивание по центру.
    """

    should_fix_spacing = _profile_has_any_parameter(
        profile,
        {"table_text_spacing_indent", "table_text_line_spacing", "table_text_line_spacing_single"},
    ) or _first_profile_value(profile, ["table_cell"], "line_spacing") is not None
    should_fix_alignment = _first_profile_value(profile, ["table_cell"], "alignment") is not None
    should_fix_indents = any(
        _first_profile_value(profile, ["table_cell"], parameter) is not None
        for parameter in ("first_line_indent", "left_indent", "right_indent")
    )
    should_fix_font_size = _profile_has_any_parameter(
        profile,
        {"table_font_size", "table_text_font_size"},
    ) or _first_profile_value(profile, ["table_cell"], "font_size") is not None or bool(_get_allowed_values(profile, "table_cell", "font_size"))
    if not should_fix_spacing and not should_fix_font_size and not should_fix_alignment and not should_fix_indents:
        return

    allowed_table_sizes = _get_allowed_values(profile, "table_cell", "font_size")
    exact_table_size = _first_profile_value(profile, ["table_cell"], "font_size")
    if exact_table_size is not None:
        expected_font_size = float(exact_table_size)
    elif allowed_table_sizes:
        numeric_sizes = sorted(float(value) for value in allowed_table_sizes if isinstance(value, int | float))
        expected_font_size = numeric_sizes[0] if numeric_sizes else None
    elif main_text_font_size is not None:
        expected_font_size = main_text_font_size - 2
    else:
        expected_font_size = None

    table_alignment = _first_profile_value(profile, ["table_cell"], "alignment")

    for table in document.tables:
        for row_index, row in enumerate(table.rows):
            is_header_row = row_index == 0
            for cell in row.cells:
                for paragraph in cell.paragraphs:
                    _fix_safe_typography(paragraph, profile)
                    if should_fix_spacing:
                        line_spacing = _first_profile_value(profile, ["table_cell"], "line_spacing")
                        paragraph.paragraph_format.line_spacing = float(line_spacing) if line_spacing is not None else 1.0
                    if should_fix_spacing or should_fix_indents:
                        paragraph.paragraph_format.first_line_indent = Cm(0)
                        paragraph.paragraph_format.left_indent = Cm(0)
                        paragraph.paragraph_format.right_indent = Cm(0)
                    if should_fix_alignment and not is_header_row:
                        _set_alignment(paragraph, str(table_alignment))

                    if not should_fix_font_size or expected_font_size is None:
                        continue

                    for run in paragraph.runs:
                        run.font.size = Pt(expected_font_size)


def autocorrect_docx(
    input_path: str | Path,
    output_path: str | Path,
    profile: Profile,
    parsed_document=None,
) -> Path:
    """
    Автоматически исправляет безопасные ошибки форматирования DOCX.

    Для ГОСТ-профиля исправляются только однозначные случаи:
    - поля страницы приводятся к диапазону 2–3 см;
    - абзацный отступ увеличивается до минимального значения;
    - недопустимое выравнивание заменяется на допустимое;
    - точка в конце заголовка удаляется.

    Если профиль содержит точные правила equals, они также применяются.
    """

    input_path = Path(input_path)
    output_path = Path(output_path)

    if input_path.suffix.lower() != ".docx":
        raise ValueError("Автоисправление доступно только для DOCX-файлов")

    if parsed_document is None:
        parsed_document = DocxParser().parse(input_path)

    dominant_values = {
    "font_family": _find_dominant_value(
        parsed_document.paragraphs,
        "font_family",
        profile,
    ),
    "font_size": _find_dominant_value(
        parsed_document.paragraphs,
        "font_size",
        profile,
    ),
    "alignment": _find_dominant_value(
        parsed_document.paragraphs,
        "alignment",
        profile,
    ),
       "line_spacing": _find_dominant_value(
        parsed_document.paragraphs,
        "line_spacing",
        profile,
    ),
    "first_line_indent": _choose_first_line_indent_for_autofix(profile),
}

    document = Document(input_path)
    heading_font_sizes = _get_expected_heading_font_sizes(parsed_document, profile)
    normcontrol_styles = _prepare_normcontrol_styles(
        document=document,
        dominant_values=dominant_values,
        heading_font_sizes=heading_font_sizes,
        profile=profile,
    )

    _fix_page_margins(document, profile, parsed_document)
    _fix_header_footer_distances(document, profile)
    _fix_page_numbering(document, parsed_document, profile)
    protected_indexes = _get_autocorrect_protected_indexes(parsed_document)

    for parsed_paragraph in parsed_document.paragraphs:
        if not parsed_paragraph.text.strip():
            continue

        if parsed_paragraph.paragraph_type == ParagraphType.TITLE_PAGE:
            continue

        if parsed_paragraph.index in protected_indexes:
            continue

        if parsed_paragraph.index >= len(document.paragraphs):
            continue

        paragraph = document.paragraphs[parsed_paragraph.index]
        _fix_safe_typography(paragraph, profile)

        if parsed_paragraph.paragraph_type == ParagraphType.MAIN_TEXT:
            paragraph.style = normcontrol_styles["main_text"]

            _fix_main_text_paragraph(
                paragraph=paragraph,
                parsed_paragraph=parsed_paragraph,
                profile=profile,
            )

            _apply_consistency_to_main_text(
                paragraph=paragraph,
                parsed_paragraph=parsed_paragraph,
                dominant_values=dominant_values,
                profile=profile,
            )

        elif parsed_paragraph.paragraph_type == ParagraphType.HEADING:
            role_target = _heading_role_target(parsed_paragraph)
            style = (
                normcontrol_styles.get(role_target)
                if role_target is not None
                else None
            )
            if style is None:
                style = normcontrol_styles.get(f"heading_{parsed_paragraph.heading_level}")
            if style is not None:
                paragraph.style = style

            _fix_heading_paragraph(
                paragraph=paragraph,
                parsed_paragraph=parsed_paragraph,
                profile=profile,
                heading_font_sizes=heading_font_sizes,
            )

        elif parsed_paragraph.paragraph_type == ParagraphType.CAPTION:
            _fix_caption_paragraph(paragraph, parsed_paragraph, profile)

    _fix_list_punctuation_policy(document, parsed_document, profile)
    _fix_object_caption_keep_rules(document, parsed_document, profile)
    _fix_table_layout_rules(document, profile)
    main_size = dominant_values.get("font_size")
    _fix_table_text(
        document,
        profile=profile,
        main_text_font_size=float(main_size) if main_size is not None else None,
    )

    document.save(output_path)
    return output_path
