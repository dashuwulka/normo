import re
from collections import defaultdict
from collections.abc import Iterable
from typing import Any

from app.extraction.models import ExtractedRuleCandidate, NormativeStatement


VOLUME_PATTERN = re.compile(
    r"для\s+([^–—-]+)[–—-]\s*(\d+)\s*[–—-]\s*(\d+)\s+страниц",
    re.IGNORECASE,
)

STRUCTURE_ELEMENTS = (
    "титульный лист",
    "задание",
    "календарный план",
    "реферат",
    "аннотацию",
    "аннотация",
    "содержание",
    "определения",
    "обозначения",
    "сокращения",
    "введение",
    "основная часть",
    "заключение",
    "список использованных источников",
    "приложения",
)

CHECKABLE_STRUCTURE_PARAMETERS = {
    "required_document_structure",
    "references_min_count",
    "introduction_required_content",
    "conclusion_required_content",
    "toc_headings_match_text",
    "heading_english_not_allowed",
    "front_matter_page_numbers_hidden_until_intro",
    "automatic_list_numbering_required",
    "list_punctuation_policy",
    "list_marker_dash_required",
    "dash_spacing",
    "hyphen_instead_of_dash",
    "numeric_range_dash",
    "number_sign_symbol",
    "russian_quotes",
    "no_dot_after_udc_keywords_table_title",
    "image_after_first_reference",
    "image_keep_with_next",
    "figure_caption_position",
    "figure_caption_alignment",
    "figure_caption_prefix",
    "figure_caption_separator",
    "figure_caption_terminal_dot",
    "figure_caption_title_format",
    "table_caption_position",
    "table_caption_alignment",
    "table_caption_prefix",
    "table_caption_separator",
    "table_caption_terminal_dot",
    "table_text_font_size",
    "table_text_line_spacing",
    "table_grid_style",
    "table_header_required",
    "table_title_keep",
    "table_text_spacing_indent",
    "table_repeat_header",
}

CHECKABLE_LINGUISTIC_PARAMETERS = {
    "initial_verb_form",
    "forbidden_phrases",
    "completed_action_form",
}

FORBIDDEN_PHRASE_VALUES = [
    "я",
    "мы",
    "ты",
    "вы",
    "мой",
    "наш",
    "ваш",
    "мне кажется",
    "на мой взгляд",
    "хороший",
    "отличный",
    "нажмите",
    "откройте",
    "выберите",
]


def _normalize(text: str) -> str:
    return " ".join(text.lower().split())


def _clean_item(text: str) -> str:
    text = re.sub(r"^\s*\d+(?:\.\d+)*\.?\s*", "", text)
    text = re.sub(r"^[\uf02d\-–—•▪▫‣]\s*", "", text.strip())
    text = text.strip(" .;:")
    return text


def _source_text(statements: list[NormativeStatement]) -> str:
    return " ".join(statement.text for statement in statements)[:1200]


def _full_text(statements: list[NormativeStatement]) -> str:
    return " ".join(statement.text for statement in statements)


def _modality(statements: list[NormativeStatement]) -> str:
    for statement in statements:
        if statement.inherited_modality in {"mandatory", "recommended", "allowed"}:
            return statement.inherited_modality
    return "unknown"


def _candidate(
    *,
    parameter: str,
    value: Any,
    statements: list[NormativeStatement],
    source_document: str,
    target: str = "document",
    modality: str | None = None,
    confidence: float = 0.55,
) -> ExtractedRuleCandidate:
    is_checkable = parameter in CHECKABLE_STRUCTURE_PARAMETERS | CHECKABLE_LINGUISTIC_PARAMETERS
    return ExtractedRuleCandidate(
        target=target,
        parameter=parameter,
        operator="equals",
        value=value,
        unit=None,
        modality=modality or _modality(statements),
        source_text=_source_text(statements),
        source_section=statements[0].source_section if statements else None,
        source_document=source_document,
        confidence=confidence,
        status="extracted" if is_checkable else "unsupported",
        explanation=(
            "требование можно сохранить в профиль и проверить автоматически"
            if is_checkable
            else "требование найдено, но для автоматической проверки нужен отдельный "
            "структурный или лингвистический модуль"
        ),
    )


def _unsupported_candidate(
    *,
    parameter: str,
    value: Any,
    statements: list[NormativeStatement],
    source_document: str,
    target: str = "document",
    modality: str | None = None,
    confidence: float = 0.5,
) -> ExtractedRuleCandidate:
    candidate = _candidate(
        parameter=parameter,
        value=value,
        statements=statements,
        source_document=source_document,
        target=target,
        modality=modality,
        confidence=confidence,
    )
    return candidate.model_copy(
        update={
            "status": "unsupported",
            "explanation": (
                "требование найдено и показано для контроля, но в текущей версии "
                "оно не добавляется в профиль автоматически"
            ),
        }
    )


def _section_groups(
    statements: Iterable[NormativeStatement],
) -> dict[str | None, list[NormativeStatement]]:
    groups: dict[str | None, list[NormativeStatement]] = defaultdict(list)
    for statement in statements:
        if statement.fragment_type == "requirement":
            groups[statement.source_section].append(statement)
    return groups


def _extract_structure_elements(
    section_statements: list[NormativeStatement],
) -> list[str]:
    elements: list[str] = []
    full_text = _normalize(_full_text(section_statements))

    if "библиографическое описание" in full_text:
        return elements

    has_structure_intro = (
        "имеет следующую структуру" in full_text
        or "следующие структурные части" in full_text
        or re.search(r"состав\w*.{0,80}(?:работ|диссертац|вкр|курсов)", full_text)
        or re.search(r"(?:работа|диссертац\w*|вкр).{0,40}состоит", full_text)
    )
    if not has_structure_intro:
        return elements

    if not (
        ("структур" in full_text or "состав" in full_text)
        and ("включ" in full_text or "состоит" in full_text)
    ):
        return elements

    for statement in section_statements:
        normalized = _normalize(statement.text)
        for element in STRUCTURE_ELEMENTS:
            if element in normalized and element not in elements:
                elements.append(element)

    return elements


def _extract_intro_items(text: str) -> list[str]:
    items = []
    normalized = _normalize(text)
    if "актуальност" in normalized:
        items.append("обоснование актуальности")
    if "цел" in normalized and "задач" in normalized:
        items.append("цели и задачи")
    if "объект" in normalized and "предмет" in normalized:
        items.append("объект и предмет")
    return items


def _extract_volume_items(text: str) -> list[str]:
    items = []
    for match in VOLUME_PATTERN.finditer(text):
        work_type = _clean_item(match.group(1))
        items.append(f"{work_type}: {match.group(2)}–{match.group(3)} страниц")
    return items


def extract_structure_candidates(
    statements: Iterable[NormativeStatement],
    source_document: str,
) -> list[ExtractedRuleCandidate]:
    candidates: list[ExtractedRuleCandidate] = []

    for section_statements in _section_groups(statements).values():
        if not section_statements:
            continue

        text = _full_text(section_statements)
        normalized = _normalize(text)

        structure_elements = _extract_structure_elements(section_statements)
        if structure_elements:
            candidates.append(
                _candidate(
                    parameter="required_document_structure",
                    value=structure_elements,
                    statements=section_statements,
                    source_document=source_document,
                    confidence=0.7,
                )
            )

        volume_items = _extract_volume_items(text)
        if volume_items:
            candidates.append(
                _candidate(
                    parameter="recommended_work_volume",
                    value=volume_items,
                    statements=section_statements,
                    source_document=source_document,
                    modality="recommended",
                    confidence=0.68,
                )
            )

        intro_items = _extract_intro_items(text)
        if "введени" in normalized and intro_items:
            candidates.append(
                _candidate(
                    parameter="introduction_required_content",
                    value=intro_items,
                    statements=section_statements,
                    source_document=source_document,
                    confidence=0.68,
                )
            )

        if "заключение" in normalized and "должно содержать" in normalized:
            candidates.append(
                _candidate(
                    parameter="conclusion_required_content",
                    value="основные результаты, выводы по поставленным задачам и полученным результатам",
                    statements=section_statements,
                    source_document=source_document,
                    confidence=0.68,
                )
            )

        if (
            "задач" in normalized
            and (
                "неопределенн" in normalized
                or "неопределен" in normalized
                or "что нужно сделать" in normalized
            )
        ):
            candidates.append(
                _candidate(
                    parameter="initial_verb_form",
                    value="infinitive",
                    statements=section_statements,
                    source_document=source_document,
                    target="introduction_tasks",
                    modality="mandatory",
                    confidence=0.78,
                )
            )

        references_match = re.search(
            r"(?:минимум|не\s+менее|не\s+меньше|необходим[оа]?\s+не\s+менее)\s+(\d+)\s+источник",
            normalized,
        )
        if references_match:
            candidates.append(
                _candidate(
                    parameter="references_min_count",
                    value=int(references_match.group(1)),
                    statements=section_statements,
                    source_document=source_document,
                    target="document",
                    modality="mandatory",
                    confidence=0.78,
                )
            )

        if "заголов" in normalized and "английск" in normalized and (
            "недопуст" in normalized or "не допуска" in normalized
        ):
            candidates.append(
                _candidate(
                    parameter="heading_english_not_allowed",
                    value=True,
                    statements=section_statements,
                    source_document=source_document,
                    target="document",
                    modality="mandatory",
                    confidence=0.74,
                )
            )

        if "в качестве маркера" in normalized and "только тире" in normalized:
            candidates.append(
                _candidate(
                    parameter="list_marker_dash_required",
                    value=True,
                    statements=section_statements,
                    source_document=source_document,
                    target="document",
                    modality="mandatory",
                    confidence=0.74,
                )
            )

        if (
            "тире" in normalized
            and ("длинн" in normalized or "дефис" in normalized)
            and ("коротк" in normalized or "предел" in normalized or "между числами" in normalized)
        ):
            for parameter, value in (
                ("hyphen_instead_of_dash", True),
                ("dash_spacing", True),
                ("numeric_range_dash", True),
            ):
                candidates.append(
                    _candidate(
                        parameter=parameter,
                        value=value,
                        statements=section_statements,
                        source_document=source_document,
                        target="main_text",
                        modality="mandatory",
                        confidence=0.68,
                    )
                )

        if "латинской буквы n" in normalized and "не допуска" in normalized:
            candidates.append(
                _candidate(
                    parameter="number_sign_symbol",
                    value=True,
                    statements=section_statements,
                    source_document=source_document,
                    target="main_text",
                    modality="mandatory",
                    confidence=0.72,
                )
            )

        if "парные кавычки" in normalized or "«…»" in normalized:
            candidates.append(
                _candidate(
                    parameter="russian_quotes",
                    value=True,
                    statements=section_statements,
                    source_document=source_document,
                    target="main_text",
                    modality="mandatory",
                    confidence=0.66,
                )
            )

        if (
            "точк" in normalized
            and ("подпис" in normalized or "рисун" in normalized or "названи" in normalized and "таблиц" in normalized)
            and ("не став" in normalized or "не ставить" in normalized)
        ):
            candidates.append(
                _candidate(
                    parameter="no_dot_after_udc_keywords_table_title",
                    value=True,
                    statements=section_statements,
                    source_document=source_document,
                    target="document",
                    modality="mandatory",
                    confidence=0.66,
                )
            )

        if "рисун" in normalized and ("подпис" in normalized or "подпись" in normalized or "названи" in normalized):
            if "под рисун" in normalized or "под изображ" in normalized or "снизу" in normalized:
                candidates.append(
                    _candidate(
                        parameter="figure_caption_position",
                        value="под рисунком",
                        statements=section_statements,
                        source_document=source_document,
                        target="document",
                        modality="mandatory",
                        confidence=0.68,
                    )
                )

            if (
                ("отрыв" in normalized or "отдел" in normalized or "вместе" in normalized or "одной страниц" in normalized)
                and ("подпис" in normalized or "подпись" in normalized or "названи" in normalized)
            ):
                candidates.append(
                    _candidate(
                        parameter="image_keep_with_next",
                        value=True,
                        statements=section_statements,
                        source_document=source_document,
                        target="document",
                        modality="mandatory",
                        confidence=0.68,
                    )
                )

            if "по центру" in normalized or "центр" in normalized:
                candidates.append(
                    _candidate(
                        parameter="figure_caption_alignment",
                        value="center",
                        statements=section_statements,
                        source_document=source_document,
                        target="document",
                        modality="mandatory",
                        confidence=0.68,
                    )
                )

            if "рисунок" in normalized:
                candidates.append(
                    _candidate(
                        parameter="figure_caption_prefix",
                        value="Рисунок",
                        statements=section_statements,
                        source_document=source_document,
                        target="figure_caption",
                        modality="mandatory",
                        confidence=0.6,
                    )
                )

            if "тире" in normalized and ("номер" in normalized or "после номера" in normalized):
                candidates.append(
                    _candidate(
                        parameter="figure_caption_separator",
                        value="тире после номера",
                        statements=section_statements,
                        source_document=source_document,
                        target="figure_caption",
                        modality="mandatory",
                        confidence=0.58,
                    )
                )

            if "точк" in normalized and ("не став" in normalized or "не ставить" in normalized):
                candidates.append(
                    _candidate(
                        parameter="figure_caption_terminal_dot",
                        value=False,
                        statements=section_statements,
                        source_document=source_document,
                        target="figure_caption",
                        modality="mandatory",
                        confidence=0.64,
                    )
                )

        if "рисун" in normalized and "ссыл" in normalized:
            candidates.append(
                _candidate(
                    parameter="image_after_first_reference",
                    value=True,
                    statements=section_statements,
                    source_document=source_document,
                    target="document",
                    modality="mandatory",
                    confidence=0.62,
                )
            )

        if "таблиц" in normalized:
            if (
                "назван" in normalized
                and ("над таблиц" in normalized or "перед таблиц" in normalized)
            ):
                candidates.append(
                    _candidate(
                        parameter="table_caption_position",
                        value="над таблицей",
                        statements=section_statements,
                        source_document=source_document,
                        target="document",
                        modality="mandatory",
                        confidence=0.68,
                    )
                )

            if "назван" in normalized and "по лев" in normalized:
                candidates.append(
                    _candidate(
                        parameter="table_caption_alignment",
                        value="left",
                        statements=section_statements,
                        source_document=source_document,
                        target="table_caption",
                        modality="mandatory",
                        confidence=0.58,
                    )
                )

            if "таблица" in normalized and "назван" in normalized:
                candidates.append(
                    _candidate(
                        parameter="table_caption_prefix",
                        value="Таблица",
                        statements=section_statements,
                        source_document=source_document,
                        target="table_caption",
                        modality="mandatory",
                        confidence=0.56,
                    )
                )

            if "тире" in normalized and "назван" in normalized:
                candidates.append(
                    _candidate(
                        parameter="table_caption_separator",
                        value="тире после номера",
                        statements=section_statements,
                        source_document=source_document,
                        target="table_caption",
                        modality="mandatory",
                        confidence=0.56,
                    )
                )

            if "назван" in normalized and "точк" in normalized and ("не став" in normalized or "не ставить" in normalized):
                candidates.append(
                    _candidate(
                        parameter="table_caption_terminal_dot",
                        value=False,
                        statements=section_statements,
                        source_document=source_document,
                        target="table_caption",
                        modality="mandatory",
                        confidence=0.6,
                    )
                )

            is_repeat_header_context = "повтор" in normalized or "дублиров" in normalized

            if "головк" in normalized and not is_repeat_header_context:
                candidates.append(
                    _candidate(
                        parameter="table_header_required",
                        value=True,
                        statements=section_statements,
                        source_document=source_document,
                        target="document",
                        modality="mandatory",
                        confidence=0.66,
                    )
                )

            if (
                ("шапк" in normalized or ("строк" in normalized and "заголов" in normalized))
                and not is_repeat_header_context
            ):
                candidates.append(
                    _candidate(
                        parameter="table_header_required",
                        value=True,
                        statements=section_statements,
                        source_document=source_document,
                        target="document",
                        modality="mandatory",
                        confidence=0.62,
                    )
                )

            if "сетк" in normalized or "границ" in normalized:
                candidates.append(
                    _candidate(
                        parameter="table_grid_style",
                        value=True,
                        statements=section_statements,
                        source_document=source_document,
                        target="document",
                        modality="mandatory",
                        confidence=0.62,
                    )
                )

            if (
                ("отрыв" in normalized or "отдел" in normalized or "вместе" in normalized or "одной страниц" in normalized)
                and ("назван" in normalized or "заголов" in normalized)
            ):
                candidates.append(
                    _candidate(
                        parameter="table_title_keep",
                        value=True,
                        statements=section_statements,
                        source_document=source_document,
                        target="document",
                        modality="mandatory",
                        confidence=0.68,
                    )
                )

            if (
                ("повтор" in normalized or "дублиров" in normalized)
                and (
                    "головк" in normalized
                    or "заголов" in normalized
                    or "шапк" in normalized
                    or "строк" in normalized
                )
            ):
                candidates.append(
                    _candidate(
                        parameter="table_repeat_header",
                        value=True,
                        statements=section_statements,
                        source_document=source_document,
                        target="document",
                        modality="mandatory",
                        confidence=0.6,
                    )
                )

            if (
                "текст" in normalized
                and ("одинарн" in normalized or "абзацн" in normalized or "отступ" in normalized)
            ):
                candidates.append(
                    _candidate(
                        parameter="table_text_spacing_indent",
                        value=True,
                        statements=section_statements,
                        source_document=source_document,
                        target="document",
                        modality="mandatory",
                        confidence=0.62,
                    )
                )

        if "автоматическ" in normalized and "нумерац" in normalized and "списк" in normalized:
            candidates.append(
                _candidate(
                    parameter="automatic_list_numbering_required",
                    value=True,
                    statements=section_statements,
                    source_document=source_document,
                    target="list_item",
                    modality="mandatory",
                    confidence=0.5,
                )
            )

        if (
            "после двоеточ" in normalized
            and ("точка с запятой" in normalized or "строчной буквы" in normalized)
            and "спис" in normalized
        ):
            candidates.append(
                _candidate(
                    parameter="list_punctuation_policy",
                    value=True,
                    statements=section_statements,
                    source_document=source_document,
                    target="list_item",
                    modality="mandatory",
                    confidence=0.48,
                )
            )

        if "не использовать" in normalized and (
            "повелительного наклонения" in normalized
            or "оценочной лексики" in normalized
            or "местоимения 1-го" in normalized
            or "местоимения 1" in normalized
        ):
            candidates.append(
                _candidate(
                    parameter="forbidden_phrases",
                    value=FORBIDDEN_PHRASE_VALUES,
                    statements=section_statements,
                    source_document=source_document,
                    target="main_text",
                    modality="recommended",
                    confidence=0.7,
                )
            )

        if (
            "титульн" in normalized
            and "содержание" in normalized
            and "номер" in normalized
            and "не простав" in normalized
            and "введение" in normalized
        ):
            candidates.append(
                _candidate(
                    parameter="front_matter_page_numbers_hidden_until_intro",
                    value=True,
                    statements=section_statements,
                    source_document=source_document,
                    target="document",
                    modality="mandatory",
                    confidence=0.55,
                )
            )

        if "содержание" in normalized and "заголовки" in normalized and "точно повторять" in normalized:
            candidates.append(
                _candidate(
                    parameter="toc_headings_match_text",
                    value=True,
                    statements=section_statements,
                    source_document=source_document,
                    confidence=0.62,
                )
            )

        if "титульн" in normalized and "название" in normalized and "должно соответствовать" in normalized:
            candidates.append(
                _candidate(
                    parameter="title_page_topic_match",
                    value=True,
                    statements=section_statements,
                    source_document=source_document,
                    confidence=0.62,
                )
            )

        if (
            ("на русском языке" in normalized or "русский язык" in normalized)
            and ("вкр" in normalized or "защит" in normalized)
        ):
            candidates.append(
                _candidate(
                    parameter="document_language",
                    value="русский язык",
                    statements=section_statements,
                    source_document=source_document,
                    confidence=0.62,
                )
            )

        if "в конце каждого раздела" in normalized and "вывод" in normalized:
            candidates.append(
                _candidate(
                    parameter="section_conclusions_required",
                    value=True,
                    statements=section_statements,
                    source_document=source_document,
                    confidence=0.62,
                )
            )

        if "первым разделом" in normalized and "обзор" in normalized:
            candidates.append(
                _candidate(
                    parameter="first_main_section_review_required",
                    value=True,
                    statements=section_statements,
                    source_document=source_document,
                    confidence=0.62,
                )
            )

        if "дополнительного раздела" in normalized and "должно быть включено" in normalized:
            candidates.append(
                _candidate(
                    parameter="additional_section_required",
                    value=True,
                    statements=section_statements,
                    source_document=source_document,
                    confidence=0.62,
                )
            )

    return candidates
