from __future__ import annotations

import re
from collections import Counter, defaultdict
from statistics import multimode

from app.models.document import ParagraphData, ParagraphType, ParsedDocxDocument
from app.models.profile import Profile, Rule
from app.models.violation import Violation


NBSP = "\u00a0"
END_SIGNS = (".", "!", "?", "…")

UNITS = (
    "мм", "см", "м", "км", "г", "кг", "мг", "с", "мин", "ч", "л", "мл",
    "К", "K", "Вт", "кВт", "Дж", "кДж", "Па", "кПа", "МПа", "В", "кВ",
    "А", "Гц", "кГц", "МГц", "моль", "Н", "пт",
)
UNIT_PATTERN = "|".join(sorted(map(re.escape, UNITS), key=len, reverse=True))

REPEATED_SPACES_PATTERN = re.compile(r" {2,}")
REPEATED_TABS_PATTERN = re.compile(r"\t{2,}")
SPACE_AFTER_OPEN_PATTERN = re.compile(r"[(\[{«„]\s+")
SPACE_BEFORE_CLOSE_PATTERN = re.compile(r"\s+[)\]}»“]")
SPACE_BEFORE_PUNCTUATION_PATTERN = re.compile(r"\s+([.,;:!?])")
NUMBER_LETTER_SPACE_PATTERN = re.compile(
    r"\b(рис\.|табл\.|п\.|ст\.|§|№)\s+(\d+)\s+([а-яa-z])\b",
    re.IGNORECASE,
)
ABBR_NORMAL_SPACE_PATTERN = re.compile(
    r"\b(?P<abbr>г|ул|пер|дер|пос|с|р|д|к|стр|кв|ч|гл|ст|п|пп)\. (?=\S)"
)
INITIALS_NORMAL_SPACE_PATTERN = re.compile(
    r"\b[А-ЯЁA-Z]\. [А-ЯЁA-Z]\.(?: [А-ЯЁA-Z][A-Za-zА-ЯЁа-яё-]+)?"
)
NUMBER_SIGN_NORMAL_SPACE_PATTERN = re.compile(r"(№) (\d+)")
PARAGRAPH_SIGN_NORMAL_SPACE_PATTERN = re.compile(r"(§) (\d+)")
FIGURE_TABLE_NORMAL_SPACE_PATTERN = re.compile(
    r"\b(рис\.|рисунок|табл\.|таблица) (\d+(?:\.\d+)*)",
    re.IGNORECASE,
)
NUMBER_UNIT_NORMAL_SPACE_PATTERN = re.compile(
    rf"\b(\d+(?:[,.]\d+)?) ({UNIT_PATTERN}|%|‰)\b",
    re.IGNORECASE,
)

EQUATION_NUMBER_PATTERN = re.compile(r"\((\d+(?:\.\d+)*)\)\s*$")
EQUATION_REFERENCE_PATTERN = re.compile(
    r"\b(?:формул[аеуы]|уравнени[ея]|см\.)\s*\((\d+(?:\.\d+)*)\)",
    re.IGNORECASE,
)
MATH_OPERATOR_BAD_SPACE_PATTERN = re.compile(
    rf"(?<=[A-Za-z0-9])(?: |{NBSP})?([+±×·=])(?: |{NBSP})?(?=[A-Za-z0-9])"
    rf"|(?<=\d)(?: |{NBSP})?:(?: |{NBSP})?(?=\d)"
)
SLASH_SPACED_PATTERN = re.compile(r"(?<=\w)\s+/\s+(?=\w)")
WRONG_MULTIPLICATION_PATTERN = re.compile(r"(?<=\d)\s*[*xX]\s*(?=\d|[a-zA-Zа-яА-Я])")
HYPHEN_MINUS_PATTERN = re.compile(r"(?:(?<=[=+\u00a0 ])-\d|(?<=\w)\s-\s(?=\w))")
DECIMAL_DOT_PATTERN = re.compile(r"\b\d+\.\d+\b")
SCIENTIFIC_DOT10_PATTERN = re.compile(r"\d+,\d+\s*[·×]\s*10")
SCIENTIFIC_E_PATTERN = re.compile(r"\d+,\d+[Ee][+-]?\d+")

WRONG_DEGREE_PATTERN = re.compile(r"\b\d+(?:[,.]\d+)?\s*[oO](?=\s*(?:C|F|С|К|K)\b)")
VARIABLE_PATTERN = re.compile(r"\b[a-zA-Z]\b")
FUNCTION_PATTERN = re.compile(r"\b(sin|cos|tg|tan|ln|log|exp|grad)\b", re.IGNORECASE)
CHEMICAL_PATTERN = re.compile(r"\b([A-Z][a-z]?\d*){2,}\b")
WRONG_RANGE_HYPHEN_PATTERN = re.compile(r"\b\d+\s*-\s*\d+\b")
WRONG_RANGE_SPACED_DASH_PATTERN = re.compile(r"\b\d+\s+[–—]\s+\d+\b")
NEGATIVE_RANGE_PATTERN = re.compile(r"[-−]\d+\s*[–—-]\s*[+-]?\d+")
TEMPERATURE_NO_SPACE_PATTERN = re.compile(r"\b\d+(?:[,.]\d+)?°[CFС]\b")
DEGREE_WITH_SPACE_PATTERN = re.compile(r"\b\d+(?:[,.]\d+)?\s+°(?![CFС])")
PERCENT_NORMAL_SPACE_PATTERN = re.compile(r"\b\d+(?:[,.]\d+)? [%‰]")
VALUE_SIGN_SPACED_PATTERN = re.compile(r"(?<!\w)[+±×]\s+\d")
DIMENSION_OPERATOR_PATTERN = re.compile(r"\b[А-Яа-яA-Za-z]+[·×][А-Яа-яA-Za-z]+")
UNIT_DOT_PATTERN = re.compile(
    rf"\b\d+(?:[,.]\d+)?(?: |{NBSP})({UNIT_PATTERN})\.(?=\s+[а-яa-z])",
    re.IGNORECASE,
)
VARIABLE_UNIT_MISSING_COMMA = re.compile(
    r"\b([A-Za-zА-Яа-я])\s+(Дж|Вт|Па|Н|м|см|кг|г)\b"
)
LOG_UNIT_PATTERN = re.compile(r"\b(ln|log)\s+\w+\s+(?!\[)", re.IGNORECASE)
REPEATED_UNITS_IN_SERIES = re.compile(
    r"\b\d+\s*(мм|см|м|г|кг|Вт|В)\s*,\s*\d+\s*\1"
)
LONG_NUMBER_PATTERN = re.compile(r"(?<![\w.])[-−]?\d{5,}(?![\w.])")

SPACED_HYPHEN_PATTERN = re.compile(r"\w\s-\s\w")
LINE_END_HYPHEN_PATTERN = re.compile(r"\w-\s*$")
UNSPACED_DASH_PATTERN = re.compile(r"\w—\w")
HYPHEN_AS_DASH_PATTERN = re.compile(r"\w\s-\s\w")
STRAIGHT_QUOTES_PATTERN = re.compile(r'"[^"]+"')
NESTED_QUOTES_PATTERN = re.compile(r"«[^»]*«[^»]+»[^»]*»")
WRONG_NUMBER_SIGN_PATTERN = re.compile(r"\b(N|No|#)\s*\d+", re.IGNORECASE)
SLASH_PARENTHESES_PATTERN = re.compile(r"\b\w+/[^/\s]+/")
SQUARE_BRACKETS_PATTERN = re.compile(r"\[[^\]]+\]")
WRONG_OMISSION_PATTERN = re.compile(r"(\[\s*\.{3}\s*\]|…|\[\s*…\s*\])")
PHONE_PATTERN = re.compile(r"(\+7|8)?\s?\(?\d{3}\)?[\s-]?\d{3}[\s-]?\d{2}[\s-]?\d{2}")
VALID_PHONE_PATTERN = re.compile(r"((\+7|8)\s)?\d{3}\s\d{3}-\d{2}-\d{2}")
MUSIC_TERM_PATTERN = re.compile(r"\b[A-Ha-h]-?(?:dur|moll)\b")


TYPOGRAPHY_PARAMETERS = {
    "repeated_spaces", "paragraph_edge_spaces", "spaces_near_punctuation",
    "repeated_tabs", "spaces_inside_brackets_quotes", "number_letter_no_space",
    "nbsp_after_abbreviations", "nbsp_between_initials", "nbsp_after_number_sign",
    "nbsp_after_paragraph_sign", "nbsp_after_figure_table_reference",
    "nbsp_between_number_and_unit", "list_marker_allowed",
    "list_marker_dash_required", "hyphen_list_marker_not_recommended",
    "list_marker_consistency", "list_indent_equals_main_text",
    "list_punctuation_policy", "automatic_list_numbering_required",
    "equations_editable", "long_equation_standalone", "equation_alignment_left",
    "equation_number_right", "numbered_equation_has_reference", "math_operator_nbsp",
    "slash_without_spaces", "wrong_multiplication_symbols", "hyphen_instead_of_minus",
    "multiplication_sign_consistency", "equation_line_break_rule",
    "decimal_separator_comma", "degree_symbol", "multiplication_symbol",
    "minus_symbol", "variable_italic", "function_and_chemical_regular",
    "numeric_range_dash", "unit_nbsp", "temperature_nbsp", "percent_nbsp",
    "dimension_operator_spacing", "dimension_consistency", "no_dot_after_units",
    "variable_unit_comma", "unit_only_after_last_number", "index_language_consistency",
    "scientific_notation_consistency", "digit_grouping_nbsp",
    "footnotes_processor_required", "footnotes_format_consistency",
    "footnotes_continuous_decimal_numbering", "footnote_font_family_and_size",
    "hyphen_spacing", "manual_hyphenation_forbidden", "dash_spacing",
    "hyphen_instead_of_dash", "russian_quotes", "nested_quotes",
    "number_sign_symbol", "number_sign_nbsp", "parentheses_not_slash",
    "square_brackets_usage", "citation_omission_format",
    "dot_after_footnote_or_note", "no_dot_after_udc_keywords_table_title",
    "music_terms_typography", "phone_number_format", "phone_country_code_consistency",
}


class TypographyChecker:
    """Проверяет текстовые требования ГОСТ Р 7.0.110-2025, разделы 9 и 12-16."""

    def check(self, document: ParsedDocxDocument, profile: Profile) -> list[Violation]:
        rules: dict[str, Rule] = {}
        for rule in profile.rules:
            if not getattr(rule, "enabled", True):
                continue
            if rule.parameter in TYPOGRAPHY_PARAMETERS:
                rules[rule.parameter] = rule
            elif rule.id in TYPOGRAPHY_PARAMETERS:
                rules[rule.id] = rule
        if not rules:
            return []

        violations: list[Violation] = []
        main_indent = _dominant_value(
            p.first_line_indent_cm
            for p in document.paragraphs
            if p.paragraph_type == ParagraphType.MAIN_TEXT
        )
        main_font = _dominant_value(
            p.font_family
            for p in document.paragraphs
            if p.paragraph_type == ParagraphType.MAIN_TEXT
        )
        main_size = _dominant_value(
            p.font_size_pt
            for p in document.paragraphs
            if p.paragraph_type == ParagraphType.MAIN_TEXT
        )

        for paragraph in document.paragraphs:
            if not _should_check_paragraph(paragraph):
                continue
            self._check_paragraph(paragraph, rules, violations, main_indent, main_font, main_size)
            self._check_runs(paragraph, rules, violations)

        self._check_document_level(document, rules, violations, main_font, main_size)
        return violations

    def _check_paragraph(
        self,
        paragraph: ParagraphData,
        rules: dict[str, Rule],
        violations: list[Violation],
        main_indent: float | None,
        main_font: str | None,
        main_size: float | None,
    ) -> None:
        text = paragraph.text
        _check_basic_spaces(paragraph, text, rules, violations)
        _check_nbsp_rules(paragraph, text, rules, violations)
        _check_list_rules(paragraph, main_indent, rules, violations)
        _check_equation_paragraph_rules(paragraph, text, rules, violations)
        _check_math_and_values(paragraph, text, rules, violations)
        _check_text_elements(paragraph, text, rules, violations)
        _check_phone(paragraph, text, rules, violations)
        _check_footnote_or_note_text(paragraph, rules, violations, main_font, main_size)

    def _check_runs(self, paragraph: ParagraphData, rules: dict[str, Rule], violations: list[Violation]) -> None:
        if "variable_italic" in rules:
            _check_variable_runs(paragraph, rules["variable_italic"], violations)
        if "function_and_chemical_regular" in rules:
            _check_function_and_chemical_runs(paragraph, rules["function_and_chemical_regular"], violations)
        if "index_language_consistency" in rules:
            _check_index_runs(paragraph, rules["index_language_consistency"], violations)

    def _check_document_level(
        self,
        document: ParsedDocxDocument,
        rules: dict[str, Rule],
        violations: list[Violation],
        main_font: str | None,
        main_size: float | None,
    ) -> None:
        _check_equation_references(document, rules, violations)
        _check_multiplication_consistency(document, rules, violations)
        _check_dimension_consistency(document, rules, violations)
        _check_scientific_notation_consistency(document, rules, violations)
        _check_phone_country_consistency(document, rules, violations)
        _check_footnotes(document, rules, violations, main_font, main_size)
        _check_list_punctuation_policy(document, rules, violations)
        _check_list_marker_consistency(document, rules, violations)
        _check_list_indent_consistency(document, rules, violations)


def _dominant_value(values) -> float | str | None:
    normalized = [round(v, 2) if isinstance(v, float) else v for v in values if v not in (None, "")]
    if not normalized:
        return None
    modes = multimode(normalized)
    return modes[0] if modes else None


def _should_check_paragraph(paragraph: ParagraphData) -> bool:
    if paragraph.paragraph_type == ParagraphType.TITLE_PAGE:
        return False
    if _is_bibliography_paragraph(paragraph) or _is_code_paragraph(paragraph):
        return False
    return bool(paragraph.text)


def _is_warning(rule: Rule) -> bool:
    return getattr(rule.modality, "value", rule.modality) == "recommended"


def _violation(
    rule: Rule,
    paragraph: ParagraphData,
    actual: str,
    expected: str,
    message: str,
    severity: str | None = None,
) -> Violation:
    resolved_severity = severity or ("warning" if _is_warning(rule) else "error")
    return Violation(
        rule_id=rule.id,
        source_section=rule.source_section,
        target=rule.target,
        parameter=rule.parameter,
        location=f"Абзац {paragraph.index}",
        paragraph_index=paragraph.index,
        expected=expected,
        actual=actual,
        message=message,
        severity=resolved_severity,
        violation_type="recommendation" if resolved_severity == "warning" else "formatting",
    )


def _document_violation(
    rule: Rule,
    actual: str,
    expected: str,
    message: str,
    severity: str | None = None,
) -> Violation:
    resolved_severity = severity or ("warning" if _is_warning(rule) else "error")
    return Violation(
        rule_id=rule.id,
        source_section=rule.source_section,
        target=rule.target,
        parameter=rule.parameter,
        location="Документ",
        expected=expected,
        actual=actual,
        message=message,
        severity=resolved_severity,
        violation_type="recommendation" if resolved_severity == "warning" else "formatting",
    )


def _message(section: str | None, text: str) -> str:
    return f"Раздел {section}: {text}" if section else text


def _first_match_text(pattern: re.Pattern[str], text: str) -> str | None:
    match = pattern.search(text)
    return match.group(0) if match else None


def _check_basic_spaces(
    paragraph: ParagraphData,
    text: str,
    rules: dict[str, Rule],
    violations: list[Violation],
) -> None:
    if "repeated_spaces" in rules and REPEATED_SPACES_PATTERN.search(text):
        rule = rules["repeated_spaces"]
        violations.append(_violation(
            rule, paragraph, "несколько пробелов подряд", "один пробел",
            _message(rule.source_section, f"использование двух или более пробелов подряд недопустимо. Абзац {paragraph.index}: найдено несколько пробелов подряд."),
        ))

    if "paragraph_edge_spaces" in rules and text != text.strip(" "):
        rule = rules["paragraph_edge_spaces"]
        violations.append(_violation(
            rule, paragraph, "пробел по краю абзаца", "без пробела по краю",
            _message(rule.source_section, f"пробелы в начале и конце абзаца не допускаются. Абзац {paragraph.index}: найден пробел в начале или конце абзаца."),
        ))

    if "spaces_near_punctuation" in rules:
        fragment = _first_match_text(SPACE_BEFORE_PUNCTUATION_PATTERN, text)
        if fragment:
            rule = rules["spaces_near_punctuation"]
            violations.append(_violation(
                rule, paragraph, fragment, "без пробела перед знаком",
                _message(rule.source_section, f"пробел перед знаком препинания не ставится. Абзац {paragraph.index}: найден лишний пробел перед \"{fragment.strip()}\"."),
            ))

    if "spaces_inside_brackets_quotes" in rules:
        fragment = _first_match_text(SPACE_AFTER_OPEN_PATTERN, text) or _first_match_text(SPACE_BEFORE_CLOSE_PATTERN, text)
        if fragment:
            rule = rules["spaces_inside_brackets_quotes"]
            violations.append(_violation(
                rule, paragraph, fragment, "без пробелов внутри кавычек и скобок",
                _message(rule.source_section, f"кавычки и скобки не отделяются пробелами от заключённых в них слов. Абзац {paragraph.index}: найден фрагмент \"{fragment}\"."),
            ))

    if "repeated_tabs" in rules and REPEATED_TABS_PATTERN.search(text):
        rule = rules["repeated_tabs"]
        violations.append(_violation(
            rule, paragraph, "несколько табуляций подряд", "одна табуляция или табличная структура",
            _message(rule.source_section, f"две и более табуляции подряд допускаются только при пропущенной позиции. Абзац {paragraph.index}: найдены несколько табуляций подряд."),
            severity="warning",
        ))


def _check_nbsp_rules(
    paragraph: ParagraphData,
    text: str,
    rules: dict[str, Rule],
    violations: list[Violation],
) -> None:
    checks = (
        ("number_letter_no_space", NUMBER_LETTER_SPACE_PATTERN, "числа с буквами в обозначениях набирают без пробелов", "запись без пробела между числом и буквой"),
        ("nbsp_after_abbreviations", ABBR_NORMAL_SPACE_PATTERN, "после сокращения должен стоять неразрывный пробел", "неразрывный пробел"),
        ("nbsp_between_initials", INITIALS_NORMAL_SPACE_PATTERN, "между инициалами, а также между инициалами и фамилией должен стоять неразрывный пробел", "неразрывный пробел"),
        ("nbsp_after_number_sign", NUMBER_SIGN_NORMAL_SPACE_PATTERN, "между знаком номера и числом должен стоять неразрывный пробел", "№\u00a0N"),
        ("nbsp_after_paragraph_sign", PARAGRAPH_SIGN_NORMAL_SPACE_PATTERN, "между знаком параграфа и числом должен стоять неразрывный пробел", "§\u00a0N"),
        ("nbsp_after_figure_table_reference", FIGURE_TABLE_NORMAL_SPACE_PATTERN, "между номером рисунка или таблицы и числом должен стоять неразрывный пробел", "неразрывный пробел"),
        ("nbsp_between_number_and_unit", NUMBER_UNIT_NORMAL_SPACE_PATTERN, "между числом и единицей измерения должен стоять неразрывный пробел", "неразрывный пробел"),
    )
    for parameter, pattern, message, expected in checks:
        if parameter not in rules:
            continue
        fragment = _first_match_text(pattern, text)
        if not fragment:
            continue
        rule = rules[parameter]
        violations.append(_violation(
            rule, paragraph, fragment, expected,
            _message(rule.source_section, f"{message}. Абзац {paragraph.index}: найдено \"{fragment}\"."),
        ))


def _check_list_rules(
    paragraph: ParagraphData,
    main_indent: float | None,
    rules: dict[str, Rule],
    violations: list[Violation],
) -> None:
    if paragraph.paragraph_type != ParagraphType.LIST_ITEM:
        return

    numbered_marker_types = {"number_bracket", "number_dot", "letter_bracket", "letter_dot"}

    def readable_marker(marker: str | None) -> str:
        if not marker:
            return "маркер не определён"
        if any(0xE000 <= ord(char) <= 0xF8FF for char in marker):
            return "нестандартный маркер Word"
        return marker

    if (
        "list_marker_allowed" in rules
        and paragraph.list_marker_type is None
        and not paragraph.is_automatic_list
    ):
        rule = rules["list_marker_allowed"]
        violations.append(_violation(
            rule, paragraph, "маркер не определён", "допустимый маркер списка",
            _message(rule.source_section, f"перед каждой позицией перечисления должен использоваться допустимый маркер. Абзац {paragraph.index}: маркер списка не определён."),
        ))

    if (
        "list_marker_dash_required" in rules
        and paragraph.list_marker_type not in numbered_marker_types
        and paragraph.list_marker_type != "dash"
    ):
        rule = rules["list_marker_dash_required"]
        actual = readable_marker(paragraph.list_marker) if paragraph.list_marker else (
            "автоматический маркер Word"
            if paragraph.is_automatic_list
            else "маркер не определён"
        )
        violations.append(_violation(
            rule, paragraph, actual, "длинное тире —",
            _message(rule.source_section, f"в качестве маркера перечисления должно использоваться длинное тире. Абзац {paragraph.index}: найдено \"{actual}\"."),
        ))

    if "hyphen_list_marker_not_recommended" in rules and paragraph.list_marker_type == "hyphen":
        rule = rules["hyphen_list_marker_not_recommended"]
        violations.append(_violation(
            rule, paragraph, "-", "длинное тире или маркер списка",
            _message(rule.source_section, f"использование дефиса в качестве маркера перечисления не рекомендуется. Абзац {paragraph.index}: найден дефис \"-\", рекомендуется использовать длинное тире или маркер списка."),
            severity="warning",
        ))

    if "list_indent_equals_main_text" in rules and main_indent is not None:
        actual = paragraph.first_line_indent_cm or 0.0
        if abs(actual - float(main_indent)) > 0.05:
            rule = rules["list_indent_equals_main_text"]
            violations.append(_violation(
                rule, paragraph, f"{actual:g} см", f"{float(main_indent):g} см",
                _message(rule.source_section, f"абзацный отступ перечисления должен быть равен абзацному отступу основного текста. Абзац {paragraph.index}: найдено {actual:g} см, требуется {float(main_indent):g} см."),
            ))


    if (
        "automatic_list_numbering_required" in rules
        and paragraph.list_marker_type in {"number_bracket", "number_dot", "letter_bracket", "letter_dot"}
        and not paragraph.is_automatic_list
    ):
        rule = rules["automatic_list_numbering_required"]
        violations.append(_violation(
            rule, paragraph, paragraph.list_marker or "ручной маркер", "автоматическая нумерация Word",
            _message(rule.source_section, f"для нумерованных списков следует применять автоматическую нумерацию текстового процессора. Абзац {paragraph.index}: найден вручную набранный маркер списка."),
        ))


LIST_MARKER_STRIP_CHARS = "-\u2013\u2014\u2022\u25aa\u25ab\u2023\uf02d\uf076\uf0b7"
LIST_MARKER_STRIP_PATTERN = re.compile(
    rf"^\s*(?:[{re.escape(LIST_MARKER_STRIP_CHARS)}]|\d+[\).]|[а-яА-ЯёЁ][\).])\s+"
)
LETTER_PATTERN = re.compile(r"[A-Za-zА-Яа-яЁё]")


def _list_item_body(paragraph: ParagraphData) -> str:
    text = paragraph.text.strip()
    return LIST_MARKER_STRIP_PATTERN.sub("", text, count=1).strip()


def _first_letter(text: str) -> str | None:
    match = LETTER_PATTERN.search(text)
    return match.group(0) if match else None


def _iter_list_groups(document: ParsedDocxDocument) -> list[list[ParagraphData]]:
    groups: list[list[ParagraphData]] = []
    current: list[ParagraphData] = []

    for paragraph in document.paragraphs:
        if paragraph.paragraph_type == ParagraphType.TITLE_PAGE:
            if current:
                groups.append(current)
                current = []
            continue

        if (
            paragraph.paragraph_type == ParagraphType.LIST_ITEM
            and paragraph.text.strip()
        ):
            current.append(paragraph)
            continue

        if current:
            groups.append(current)
            current = []

    if current:
        groups.append(current)

    return groups


def _previous_content_paragraph(
    document: ParsedDocxDocument,
    first_group_paragraph: ParagraphData,
) -> ParagraphData | None:
    for paragraph in reversed(document.paragraphs):
        if paragraph.index >= first_group_paragraph.index:
            continue
        if paragraph.paragraph_type in {ParagraphType.EMPTY, ParagraphType.TITLE_PAGE, ParagraphType.TABLE_CELL}:
            continue
        if paragraph.text.strip():
            return paragraph
    return None


def _check_list_punctuation_policy(
    document: ParsedDocxDocument,
    rules: dict[str, Rule],
    violations: list[Violation],
) -> None:
    if "list_punctuation_policy" not in rules:
        return

    rule = rules["list_punctuation_policy"]
    for group in _iter_list_groups(document):
        if not group:
            continue

        previous = _previous_content_paragraph(document, group[0])
        after_colon = bool(previous and previous.text.rstrip().endswith(":"))

        for position, paragraph in enumerate(group):
            body = _list_item_body(paragraph)
            if not body:
                continue

            first = _first_letter(body)
            is_last = position == len(group) - 1

            if after_colon and paragraph.list_marker_type in {"dash", "hyphen", "bullet"}:
                if first and not first.islower():
                    violations.append(_violation(
                        rule,
                        paragraph,
                        body[:40],
                        "строчная буква после двоеточия",
                        _message(
                            rule.source_section,
                            f"после двоеточия пункты маркированного списка пишут со строчной буквы. Абзац {paragraph.index}: пункт начинается с прописной буквы.",
                        ),
                    ))

                expected_end = "." if is_last else ";"
                if not body.rstrip().endswith(expected_end):
                    violations.append(_violation(
                        rule,
                        paragraph,
                        body[-20:],
                        f"окончание «{expected_end}»",
                        _message(
                            rule.source_section,
                            f"после двоеточия промежуточные пункты списка заканчивают точкой с запятой, последний пункт — точкой. Абзац {paragraph.index}: нарушено окончание пункта.",
                        ),
                    ))

            if paragraph.list_marker_type in {"number_dot", "letter_dot"}:
                if first and not first.isupper():
                    violations.append(_violation(
                        rule,
                        paragraph,
                        body[:40],
                        "прописная буква после цифры или буквы с точкой",
                        _message(
                            rule.source_section,
                            f"если пункту перечня предшествует цифра или буква с точкой, текст пункта начинается с прописной буквы. Абзац {paragraph.index}: пункт начинается со строчной буквы.",
                        ),
                    ))


LIST_MARKER_TYPE_LABELS = {
    "dash": "длинное тире",
    "hyphen": "дефис",
    "bullet": "маркер",
    "number_bracket": "число со скобкой",
    "number_dot": "число с точкой",
    "letter_bracket": "буква со скобкой",
    "letter_dot": "буква с точкой",
}


def _list_marker_type_label(marker_type: str | None) -> str:
    if marker_type is None:
        return "маркер не определён"
    return LIST_MARKER_TYPE_LABELS.get(marker_type, marker_type)


def _dominant_marker_type(group: list[ParagraphData]) -> str | None:
    values = [paragraph.list_marker_type for paragraph in group if paragraph.list_marker_type]
    if not values:
        return None
    counter = Counter(values)
    return counter.most_common(1)[0][0]


def _list_marker_signature(paragraph: ParagraphData) -> tuple[str | None, str | None]:
    marker_type = paragraph.list_marker_type
    marker = (paragraph.list_marker or "").strip() or None
    if marker_type in {"bullet", "dash", "hyphen", "other"}:
        return marker_type, marker
    return marker_type, None


def _list_marker_signature_label(signature: tuple[str | None, str | None]) -> str:
    marker_type, marker = signature
    base = _list_marker_type_label(marker_type)
    if marker:
        if any(0xE000 <= ord(char) <= 0xF8FF for char in marker):
            return "нестандартный маркер Word"
        readable_marker = marker
        return f"{base} «{readable_marker}»"
    return base


def _check_list_marker_consistency(
    document: ParsedDocxDocument,
    rules: dict[str, Rule],
    violations: list[Violation],
) -> None:
    if "list_marker_consistency" not in rules:
        return

    rule = rules["list_marker_consistency"]
    for group in _iter_list_groups(document):
        signatures = {
            _list_marker_signature(paragraph)
            for paragraph in group
            if paragraph.list_marker_type is not None
        }
        if len(signatures) <= 1:
            continue

        values = [
            _list_marker_signature(paragraph)
            for paragraph in group
            if paragraph.list_marker_type is not None
        ]
        expected_signature = Counter(values).most_common(1)[0][0]
        expected = _list_marker_signature_label(expected_signature)
        for paragraph in group:
            actual_signature = _list_marker_signature(paragraph)
            if actual_signature == expected_signature:
                continue
            actual_label = _list_marker_signature_label(actual_signature)
            expected_label = expected
            if actual_label == expected_label:
                actual_label = "нестандартный маркер другого вида"
                expected_label = "основной маркер этого списка"
            violations.append(_violation(
                rule,
                paragraph,
                actual_label,
                expected_label,
                _message(
                    rule.source_section,
                    f"В одном списке должен использоваться один тип маркера. Абзац {paragraph.index}: найден «{actual_label}», в этом списке используется «{expected_label}».",
                ),
            ))


def _list_indent_signature(paragraph: ParagraphData) -> tuple[float, float]:
    return (
        round(float(paragraph.first_line_indent_cm or 0.0), 2),
        round(float(paragraph.left_indent_cm or 0.0), 2),
    )


def _format_list_indent_signature(signature: tuple[float, float]) -> str:
    first, left = signature
    return f"абзацный отступ {first:g} см, левый отступ {left:g} см"


def _check_list_indent_consistency(
    document: ParsedDocxDocument,
    rules: dict[str, Rule],
    violations: list[Violation],
) -> None:
    rule = rules.get("list_indent_equals_main_text")
    if rule is None:
        return

    for group in _iter_list_groups(document):
        if len(group) < 2:
            continue

        signatures = [_list_indent_signature(paragraph) for paragraph in group]
        unique_signatures = set(signatures)
        if len(unique_signatures) <= 1:
            continue

        expected_signature = Counter(signatures).most_common(1)[0][0]
        expected = _format_list_indent_signature(expected_signature)
        for paragraph in group:
            actual_signature = _list_indent_signature(paragraph)
            if actual_signature == expected_signature:
                continue
            actual = _format_list_indent_signature(actual_signature)
            violations.append(_violation(
                rule,
                paragraph,
                actual,
                expected,
                _message(
                    rule.source_section,
                    f"в пределах одного списка отступы пунктов должны быть единообразными. Абзац {paragraph.index}: найдено {actual}, в этом списке используется {expected}.",
                ),
            ))


def _check_equation_paragraph_rules(
    paragraph: ParagraphData,
    text: str,
    rules: dict[str, Rule],
    violations: list[Violation],
) -> None:
    if "equations_editable" in rules and paragraph.has_formula_like_image:
        rule = rules["equations_editable"]
        violations.append(_violation(
            rule, paragraph, "изображение, похожее на формулу", "редактируемая формула",
            _message(rule.source_section, f"математические выражения следует представлять в редактируемом виде, а не в виде изображения. Абзац {paragraph.index}: обнаружено изображение, похожее на формулу."),
            severity="warning",
        ))

    if "long_equation_standalone" in rules and not paragraph.has_equation and EQUATION_NUMBER_PATTERN.search(text):
        rule = rules["long_equation_standalone"]
        violations.append(_violation(
            rule, paragraph, "формула в обычном тексте", "отдельная строка",
            _message(rule.source_section, f"длинные или нумерованные формулы рекомендуется выносить в отдельную строку. Абзац {paragraph.index}: обнаружена формула, оформленная внутри обычного текста."),
            severity="warning",
        ))

    if not paragraph.is_standalone_equation:
        return

    if "equation_alignment_left" in rules and paragraph.alignment not in (None, "left"):
        rule = rules["equation_alignment_left"]
        violations.append(_violation(
            rule, paragraph, str(paragraph.alignment), "left",
            _message(rule.source_section, f"уравнения, вынесенные отдельной строкой, должны быть выровнены по левому краю. Абзац {paragraph.index}: найдено выравнивание {paragraph.alignment}."),
        ))

    if "equation_number_right" in rules and not EQUATION_NUMBER_PATTERN.search(text):
        rule = rules["equation_number_right"]
        violations.append(_violation(
            rule, paragraph, "номер не найден или оформлен неверно", "(1)",
            _message(rule.source_section, f"номер уравнения должен стоять у правого поля в круглых скобках. Абзац {paragraph.index}: номер формулы не найден или оформлен неверно."),
        ))

    if "equation_line_break_rule" in rules and paragraph.has_line_break:
        stripped = text.strip()
        valid = bool(re.search(r"[=+\-·×/:]\s*$", stripped))
        if not valid:
            rule = rules["equation_line_break_rule"]
            violations.append(_violation(
                rule, paragraph, "перенос без повторения знака", "перенос после знака операции с повторением",
                _message(rule.source_section, f"если уравнение переносится на новую строку, перенос выполняют после знака математической операции, а на новой строке знак повторяют. Абзац {paragraph.index}: найден перенос формулы без повторения знака операции."),
            ))


def _check_math_and_values(
    paragraph: ParagraphData,
    text: str,
    rules: dict[str, Rule],
    violations: list[Violation],
) -> None:
    checks = (
        ("math_operator_nbsp", MATH_OPERATOR_BAD_SPACE_PATTERN, "знаки математических операций должны отбиваться неразрывными пробелами с обеих сторон", "неразрывные пробелы вокруг оператора", None),
        ("slash_without_spaces", SLASH_SPACED_PATTERN, "знак деления в виде косой черты \"/\" пробелами не отбивают", "без пробелов вокруг /", None),
        ("wrong_multiplication_symbols", WRONG_MULTIPLICATION_PATTERN, "недопустимо использовать \"*\", \"x\" или \"X\" вместо знака умножения", "× или ·", None),
        ("hyphen_instead_of_minus", HYPHEN_MINUS_PATTERN, "в математических выражениях недопустимо использовать дефис вместо знака минуса", "знак минуса", "warning"),
        ("decimal_separator_comma", DECIMAL_DOT_PATTERN, "в русском тексте для разделения целой и дробной части числа должна использоваться запятая", "десятичная запятая", None),
        ("degree_symbol", WRONG_DEGREE_PATTERN, "знак градуса должен обозначаться символом \"°\", а не буквой или нулём", "°", None),
        ("multiplication_symbol", WRONG_MULTIPLICATION_PATTERN, "для обозначения умножения не допускаются символы \"*\", \"x\" и \"X\"", "× или ·", None),
        ("minus_symbol", HYPHEN_MINUS_PATTERN, "для обозначения минуса не следует использовать дефис", "знак минуса", "warning"),
        ("numeric_range_dash", WRONG_RANGE_HYPHEN_PATTERN, "при указании диапазонов числовых величин и дат используют тире без пробелов, дефис недопустим", "10–15", None),
        ("numeric_range_dash", WRONG_RANGE_SPACED_DASH_PATTERN, "при указании диапазонов числовых величин и дат используют тире без пробелов, дефис недопустим", "10–15", None),
        ("numeric_range_dash", NEGATIVE_RANGE_PATTERN, "при наличии в диапазоне знаков минуса предпочтительно использовать многоточие", "многоточие", "warning"),
        ("unit_nbsp", NUMBER_UNIT_NORMAL_SPACE_PATTERN, "между числом и единицей измерения должен стоять неразрывный пробел", "неразрывный пробел", None),
        ("temperature_nbsp", TEMPERATURE_NO_SPACE_PATTERN, "знак градуса со шкалой температуры °C или °F отделяется от числа неразрывным пробелом", "10\u00a0°C", None),
        ("temperature_nbsp", DEGREE_WITH_SPACE_PATTERN, "знак градуса без обозначения шкалы не отделяется пробелом от числа", "10°", None),
        ("percent_nbsp", PERCENT_NORMAL_SPACE_PATTERN, "знаки процента и промилле должны отделяться от числа неразрывным пробелом", "2\u00a0%", None),
        ("dimension_operator_spacing", DIMENSION_OPERATOR_PATTERN, "знаки операций в размерностях должны отбиваться пробелом в соответствии с правилами математических выражений", "пробелы вокруг операции", None),
        ("dimension_operator_spacing", VALUE_SIGN_SPACED_PATTERN, "символы \"+\", \"-\", \"±\" и \"×\", обозначающие знак величины, допуск или кратность увеличения, пробелом не отбивают", "+3", None),
        ("no_dot_after_units", UNIT_DOT_PATTERN, "после обозначений размерностей точку не ставят, кроме случая, когда размерность стоит в конце предложения", "размерность без точки", None),
        ("variable_unit_comma", VARIABLE_UNIT_MISSING_COMMA, "размерности переменных пишутся через запятую", "E, Дж", None),
        ("variable_unit_comma", LOG_UNIT_PATTERN, "размерности подлогарифмических величин указываются в квадратных скобках", "ln t [мин]", None),
        ("unit_only_after_last_number", REPEATED_UNITS_IN_SERIES, "при перечислении размерность приводят лишь для последнего числа, за исключением специальных случаев", "100, 200 и 500 г", "warning"),
        ("digit_grouping_nbsp", LONG_NUMBER_PATTERN, "цифры в более чем пятизначных числах должны разбиваться на группы неразрывным пробелом по три справа налево", "10\u00a0000", None),
    )

    for parameter, pattern, description, expected, severity in checks:
        if parameter not in rules:
            continue
        fragment = _first_match_text(pattern, text)
        if not fragment or _is_ignored_numeric_fragment(fragment, text):
            continue
        rule = rules[parameter]
        violations.append(_violation(
            rule, paragraph, fragment, expected,
            _message(rule.source_section, f"{description}. Абзац {paragraph.index}: найдено \"{fragment}\"."),
            severity=severity,
        ))


def _check_text_elements(
    paragraph: ParagraphData,
    text: str,
    rules: dict[str, Rule],
    violations: list[Violation],
) -> None:
    checks = (
        ("hyphen_spacing", SPACED_HYPHEN_PATTERN, "дефис не отбивают пробелами", "дефис без пробелов"),
        ("manual_hyphenation_forbidden", LINE_END_HYPHEN_PATTERN, "использование дефиса вместо знака переноса недопустимо", "без ручного переноса"),
        ("dash_spacing", UNSPACED_DASH_PATTERN, "длинное тире, кроме диапазонов, должно отбиваться пробелами", "слово — слово"),
        ("hyphen_instead_of_dash", HYPHEN_AS_DASH_PATTERN, "между частями предложения следует использовать длинное тире, а не дефис", "слово — слово"),
        ("russian_quotes", STRAIGHT_QUOTES_PATTERN, "в русском тексте используются кавычки «ёлочки»", "«ёлочки»"),
        ("nested_quotes", NESTED_QUOTES_PATTERN, "нарушена вложенность кавычек", "корректная вложенность кавычек"),
        ("number_sign_symbol", WRONG_NUMBER_SIGN_PATTERN, "для обозначения номера используют символ \"№\"; использование \"N\", \"No\" или \"#\" недопустимо", "№"),
        ("number_sign_nbsp", NUMBER_SIGN_NORMAL_SPACE_PATTERN, "между знаком номера и числом должен стоять неразрывный пробел", "№\u00a0N"),
        ("parentheses_not_slash", SLASH_PARENTHESES_PATTERN, "использование косой линии вместо обычных скобок недопустимо", "обычные скобки"),
        ("citation_omission_format", WRONG_OMISSION_PATTERN, "для обозначения пропусков в цитатах используют <...>", "<...>"),
    )
    for parameter, pattern, description, expected in checks:
        if parameter not in rules:
            continue
        fragment = _first_match_text(pattern, text)
        if not fragment:
            continue
        if parameter == "russian_quotes" and not re.search(r"[А-Яа-яЁё]", text):
            continue
        rule = rules[parameter]
        violations.append(_violation(
            rule, paragraph, fragment, expected,
            _message(rule.source_section, f"{description}. Абзац {paragraph.index}: найдено \"{fragment}\"."),
            severity="warning" if parameter in {"russian_quotes", "manual_hyphenation_forbidden"} else None,
        ))

    if "square_brackets_usage" in rules:
        for match in SQUARE_BRACKETS_PATTERN.finditer(text):
            fragment = match.group(0)
            if _is_reference_brackets(fragment):
                continue
            rule = rules["square_brackets_usage"]
            violations.append(_violation(
                rule, paragraph, fragment, "ручная проверка допустимости",
                _message(rule.source_section, f"квадратные скобки используются только в принятых для этого случаях. Абзац {paragraph.index}: найдено \"{fragment}\", требуется ручная проверка."),
                severity="warning",
            ))
            break

    if "no_dot_after_udc_keywords_table_title" in rules and _forbidden_terminal_dot_context(paragraph, text):
        rule = rules["no_dot_after_udc_keywords_table_title"]
        violations.append(_violation(
            rule, paragraph, "точка в конце", "без точки",
            _message(rule.source_section, f"после УДК, ключевых слов или названия таблицы точка не ставится. Абзац {paragraph.index}: найдено окончание точкой."),
        ))

    if "dot_after_footnote_or_note" in rules and paragraph.paragraph_type in {ParagraphType.NOTE, ParagraphType.FOOTNOTE}:
        if text.strip() and not text.strip().endswith(END_SIGNS):
            rule = rules["dot_after_footnote_or_note"]
            violations.append(_violation(
                rule, paragraph, "нет конечного знака", "точка или другой знак конца предложения",
                _message(rule.source_section, f"после сноски или примечания ставится точка. Абзац {paragraph.index}: текст не заканчивается знаком конца предложения."),
            ))

    if "music_terms_typography" in rules:
        fragment = _first_match_text(MUSIC_TERM_PATTERN, text)
        if fragment:
            rule = rules["music_terms_typography"]
            violations.append(_violation(
                rule, paragraph, fragment, "ручная проверка музыкального обозначения",
                _message(rule.source_section, f"музыкальные тональности на латыни набираются прямым шрифтом, а специальные музыкальные обозначения — курсивом. Абзац {paragraph.index}: требуется ручная проверка фрагмента \"{fragment}\"."),
                severity="warning",
            ))


def _check_phone(
    paragraph: ParagraphData,
    text: str,
    rules: dict[str, Rule],
    violations: list[Violation],
) -> None:
    if "phone_number_format" not in rules:
        return
    for match in PHONE_PATTERN.finditer(text):
        fragment = match.group(0)
        if VALID_PHONE_PATTERN.fullmatch(fragment):
            continue
        rule = rules["phone_number_format"]
        violations.append(_violation(
            rule, paragraph, fragment, "+7 495 123-45-67",
            _message(rule.source_section, f"телефонный номер оформлен не по требованиям. Абзац {paragraph.index}: найдено \"{fragment}\", ожидаемый формат: +7 495 123-45-67."),
        ))
        break


def _check_variable_runs(paragraph: ParagraphData, rule: Rule, violations: list[Violation]) -> None:
    for run in paragraph.runs:
        if not run.text.strip() or run.italic:
            continue
        for match in VARIABLE_PATTERN.finditer(run.text):
            fragment = match.group(0)
            violations.append(_violation(
                rule, paragraph, fragment, "переменная курсивом",
                _message(rule.source_section, f"переменные физические величины должны набираться курсивом. Абзац {paragraph.index}: переменная \"{fragment}\" набрана прямым начертанием."),
                severity="warning",
            ))
            return


def _check_function_and_chemical_runs(paragraph: ParagraphData, rule: Rule, violations: list[Violation]) -> None:
    for run in paragraph.runs:
        if not run.text.strip() or not run.italic:
            continue
        match = FUNCTION_PATTERN.search(run.text) or CHEMICAL_PATTERN.search(run.text)
        if match:
            fragment = match.group(0)
            violations.append(_violation(
                rule, paragraph, fragment, "прямое начертание",
                _message(rule.source_section, f"названия функций и химические элементы должны набираться прямым начертанием. Абзац {paragraph.index}: фрагмент \"{fragment}\" набран курсивом."),
                severity="warning",
            ))


def _check_index_runs(paragraph: ParagraphData, rule: Rule, violations: list[Violation]) -> None:
    for run in paragraph.runs:
        if not run.subscript:
            continue
        fragment = run.text.strip()
        if not fragment:
            continue
        has_ru = bool(re.search(r"[А-Яа-яЁё]", fragment))
        has_lat = bool(re.search(r"[A-Za-z]", fragment))
        if has_ru and has_lat:
            violations.append(_violation(
                rule, paragraph, fragment, "индекс без смешения алфавитов",
                _message(rule.source_section, f"следует избегать смешанного употребления русских и латинских индексов. Абзац {paragraph.index}: найден индекс \"{fragment}\"."),
                severity="warning",
            ))
        if fragment.endswith("."):
            violations.append(_violation(
                rule, paragraph, fragment, "индекс без точки",
                _message(rule.source_section, f"в подстрочных индексах после простых сокращений точку не ставят. Абзац {paragraph.index}: найден индекс \"{fragment}\"."),
            ))


def _check_equation_references(
    document: ParsedDocxDocument,
    rules: dict[str, Rule],
    violations: list[Violation],
) -> None:
    if "numbered_equation_has_reference" not in rules:
        return
    equation_numbers = {
        p.equation_number
        for p in document.paragraphs
        if p.is_standalone_equation and p.equation_number
    }
    references = set()
    for paragraph in document.paragraphs:
        if not _should_check_paragraph(paragraph):
            continue
        references.update(match.group(1) for match in EQUATION_REFERENCE_PATTERN.finditer(paragraph.text))

    rule = rules["numbered_equation_has_reference"]
    for number in sorted(equation_numbers - references):
        violations.append(_document_violation(
            rule, f"формула ({number}) без ссылки", "ссылка в тексте",
            _message(rule.source_section, f"допускается нумеровать формулы, на которые есть ссылки в тексте. Формула {number}: ссылка на неё в тексте не найдена."),
            severity="warning",
        ))
    for number in sorted(references - equation_numbers):
        violations.append(_document_violation(
            rule, f"ссылка на формулу ({number})", "соответствующая формула",
            f"В тексте есть ссылка на формулу {number}, но формула с таким номером не найдена.",
        ))


def _check_multiplication_consistency(document: ParsedDocxDocument, rules: dict[str, Rule], violations: list[Violation]) -> None:
    if "multiplication_sign_consistency" not in rules:
        return
    signs = set()
    for paragraph in document.paragraphs:
        if not _should_check_paragraph(paragraph):
            continue
        if "×" in paragraph.text:
            signs.add("×")
        if "·" in paragraph.text:
            signs.add("·")
    if len(signs) > 1:
        rule = rules["multiplication_sign_consistency"]
        violations.append(_document_violation(
            rule, ", ".join(sorted(signs)), "единый знак умножения",
            _message(rule.source_section, f"для визуального отделения сомножителей следует единообразно использовать один способ. В документе одновременно используются {', '.join(sorted(signs))}."),
            severity="warning",
        ))


def _check_dimension_consistency(document: ParsedDocxDocument, rules: dict[str, Rule], violations: list[Violation]) -> None:
    if "dimension_consistency" not in rules:
        return
    variants = defaultdict(set)
    pattern = re.compile(rf"\d+(?:[,.]\d+)?(?: |{NBSP})?([А-Яа-яA-Za-z]+(?:[·/][А-Яа-яA-Za-z0-9-]+)+)")
    for paragraph in document.paragraphs:
        if not _should_check_paragraph(paragraph):
            continue
        for match in pattern.finditer(paragraph.text):
            value = match.group(1)
            key = re.sub(r"[·/\s0-9-]+", "", value).lower()
            variants[key].add(value)
    different = [sorted(values) for values in variants.values() if len(values) > 1]
    if different:
        actual = "; ".join(", ".join(values) for values in different[:3])
        rule = rules["dimension_consistency"]
        violations.append(_document_violation(
            rule, actual, "единая запись размерности",
            _message(rule.source_section, f"одна размерность должна быть записана одинаково по всему тексту. Найдены разные варианты записи: {actual}."),
            severity="warning",
        ))


def _check_scientific_notation_consistency(document: ParsedDocxDocument, rules: dict[str, Rule], violations: list[Violation]) -> None:
    if "scientific_notation_consistency" not in rules:
        return
    variants = set()
    for paragraph in document.paragraphs:
        if not _should_check_paragraph(paragraph):
            continue
        if SCIENTIFIC_DOT10_PATTERN.search(paragraph.text):
            variants.add("·10")
        if SCIENTIFIC_E_PATTERN.search(paragraph.text):
            variants.add("E")
    if len(variants) > 1:
        rule = rules["scientific_notation_consistency"]
        actual = ", ".join(sorted(variants))
        violations.append(_document_violation(
            rule, actual, "единая нормализованная запись",
            _message(rule.source_section, f"нормализованная запись значений должна быть единообразной по всему документу. Найдены разные варианты записи: {actual}."),
            severity="warning",
        ))


def _check_phone_country_consistency(document: ParsedDocxDocument, rules: dict[str, Rule], violations: list[Violation]) -> None:
    if "phone_country_code_consistency" not in rules:
        return
    variants = set()
    for paragraph in document.paragraphs:
        if not _should_check_paragraph(paragraph):
            continue
        for match in PHONE_PATTERN.finditer(paragraph.text):
            value = match.group(0).strip()
            if value.startswith("+7"):
                variants.add("+7")
            elif value.startswith("8"):
                variants.add("8")
            else:
                variants.add("без кода")
    if len(variants) > 1:
        rule = rules["phone_country_code_consistency"]
        actual = ", ".join(sorted(variants))
        violations.append(_document_violation(
            rule, actual, "единый способ записи кода страны",
            _message(rule.source_section, f"способ записи кода страны должен быть единообразным по всему тексту. В документе одновременно используются варианты: {actual}."),
            severity="warning",
        ))


def _check_footnotes(
    document: ParsedDocxDocument,
    rules: dict[str, Rule],
    violations: list[Violation],
    main_font: str | None,
    main_size: float | None,
) -> None:
    if "footnotes_processor_required" in rules and not document.has_footnotes_part:
        manual = any(re.search(r"\[\d+\]|\b\d+\)", p.text) for p in document.paragraphs if p.paragraph_type != ParagraphType.TITLE_PAGE)
        if manual:
            rule = rules["footnotes_processor_required"]
            violations.append(_document_violation(
                rule, "признаки ручных сносок", "автоматические сноски Word",
                _message(rule.source_section, "сноски должны вставляться специализированными средствами текстового процессора. В документе обнаружены признаки ручных сносок без автоматической привязки."),
                severity="warning",
            ))

    if not document.footnotes:
        return

    if "footnotes_continuous_decimal_numbering" in rules:
        rule = rules["footnotes_continuous_decimal_numbering"]
        number_format = document.footnote_number_format
        restart = document.footnote_number_restart
        if number_format not in (None, "decimal"):
            violations.append(_document_violation(
                rule, str(number_format), "decimal",
                _message(rule.source_section, f"для нумерации сносок используют арабские цифры. Найден формат нумерации \"{number_format}\"."),
            ))
        if restart not in (None, "continuous"):
            violations.append(_document_violation(
                rule, str(restart), "continuous",
                _message(rule.source_section, "нумерация сносок должна быть сквозной по всему документу. Найден перезапуск нумерации сносок."),
            ))

    for footnote in document.footnotes:
        _check_footnote_or_note_text(footnote, rules, violations, main_font, main_size)

    if "footnotes_format_consistency" in rules:
        rule = rules["footnotes_format_consistency"]
        for parameter in ("font_family", "font_size_pt", "line_spacing", "first_line_indent_cm", "alignment"):
            values = [getattr(f, parameter, None) for f in document.footnotes if getattr(f, parameter, None) is not None]
            expected = _dominant_value(values)
            if expected is None:
                continue
            for footnote in document.footnotes:
                actual = getattr(footnote, parameter, None)
                if actual is not None and actual != expected:
                    violations.append(_violation(
                        rule, footnote, str(actual), str(expected),
                        _message(rule.source_section, f"оформление сносок по всему документу должно быть единообразным. Сноска {footnote.index}: параметр \"{parameter}\" имеет значение {actual}, ожидается {expected}."),
                    ))


def _check_footnote_or_note_text(
    paragraph: ParagraphData,
    rules: dict[str, Rule],
    violations: list[Violation],
    main_font: str | None,
    main_size: float | None,
) -> None:
    if paragraph.paragraph_type != ParagraphType.FOOTNOTE:
        return
    if "footnote_font_family_and_size" in rules and main_size is not None:
        expected_size = float(main_size) - 2
        size_ok = paragraph.font_size_pt is None or abs(float(paragraph.font_size_pt) - expected_size) <= 0.5
        font_ok = not main_font or paragraph.font_family in (None, main_font)
        if not (size_ok and font_ok):
            rule = rules["footnote_font_family_and_size"]
            actual = f"{paragraph.font_family}, {paragraph.font_size_pt} пт"
            expected = f"{main_font}, {expected_size:g} пт"
            violations.append(_violation(
                rule, paragraph, actual, expected,
                _message(rule.source_section, f"текст сноски должен быть набран той же гарнитурой, что основной текст, и кеглем на 2 пункта меньше. Сноска {paragraph.index}: найдено {actual}; требуется {expected}."),
            ))


def _is_ignored_numeric_fragment(fragment: str, text: str) -> bool:
    return (
        _is_url(text)
        or _is_email(text)
        or _is_version_number(fragment)
        or _is_gost_number(text)
        or re.fullmatch(r"\d{4}", fragment or "") is not None
    )


def _is_url(text_fragment: str) -> bool:
    return bool(re.search(r"https?://|www\.", text_fragment, re.IGNORECASE))


def _is_email(text_fragment: str) -> bool:
    return bool(re.search(r"\b[\w.+-]+@[\w.-]+\.\w+\b", text_fragment))


def _is_version_number(text_fragment: str) -> bool:
    return bool(re.fullmatch(r"\d+(?:\.\d+){1,3}", text_fragment))


def _is_gost_number(text_fragment: str) -> bool:
    return bool(re.search(r"ГОСТ\s+Р?\s*\d+(?:\.\d+)*[-–]\d{4}", text_fragment, re.IGNORECASE))


def _is_reference_brackets(text_fragment: str) -> bool:
    return bool(re.fullmatch(r"\[\d+(?:,\s*с\.\s*\d+)?(?:;\s*\d+)*\]", text_fragment, re.IGNORECASE))


def _is_code_paragraph(paragraph: ParagraphData) -> bool:
    style = (paragraph.style_name or "").lower()
    text = paragraph.text
    return "code" in style or "код" in style or bool(re.search(r"^\s*(def |class |import |from |if \(|for \()", text))


def _is_bibliography_paragraph(paragraph: ParagraphData) -> bool:
    style = (paragraph.style_name or "").lower()
    text = paragraph.text.strip().lower()
    return "bibliography" in style or "литератур" in style or bool(re.match(r"^\[\d+\]\s+", text))


def _is_title_page_paragraph(paragraph: ParagraphData) -> bool:
    return paragraph.paragraph_type == ParagraphType.TITLE_PAGE


def _forbidden_terminal_dot_context(paragraph: ParagraphData, text: str) -> bool:
    stripped = text.strip()
    if not stripped.endswith("."):
        return False
    lowered = stripped.lower()
    return (
        paragraph.caption_kind == "table"
        or lowered.startswith("удк")
        or lowered.startswith("ключевые слова")
    )
