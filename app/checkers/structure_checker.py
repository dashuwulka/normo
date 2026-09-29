import re

from app.models.document import ParsedDocxDocument, ParagraphData, ParagraphType
from app.models.profile import Profile, Rule
from app.models.violation import Violation


STRUCTURE_PARAMETERS = {
    "required_document_structure",
    "references_min_count",
    "heading_english_not_allowed",
    "front_matter_page_numbers_hidden_until_intro",
    "toc_headings_match_text",
    "introduction_required_content",
    "conclusion_required_content",
}


def _is_recommended(rule: Rule) -> bool:
    return getattr(rule.modality, "value", rule.modality) == "recommended"


def _normalize_text(text: str) -> str:
    return " ".join(text.lower().replace("ё", "е").split())


def _is_introduction_paragraph(paragraph: ParagraphData) -> bool:
    text = paragraph.text.strip().lower().replace("ё", "е")
    text = re.sub(r"^\d+(?:\.\d+)*\.?\s+", "", text)
    return paragraph.logical_section == "introduction" or text == "введение"


def _section_text(document: ParsedDocxDocument, logical_section: str) -> str:
    return "\n".join(
        paragraph.text
        for paragraph in document.paragraphs
        if paragraph.logical_section == logical_section
    )


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
                violation_type="structure",
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
                violation_type="structure",
            )
        )

    return violations


def _check_required_document_structure_rule(
    rule: Rule,
    document: ParsedDocxDocument,
) -> list[Violation]:
    expected_items = rule.value if isinstance(rule.value, list) else []
    if not expected_items:
        return []

    full_text = _normalize_text("\n".join(p.text for p in document.paragraphs))
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
        item = _normalize_text(str(raw_item).strip(" .;:"))
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
        if paragraph.paragraph_type != ParagraphType.HEADING:
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
                violation_type="structure",
            )
        )
    return violations


def _check_toc_headings_match_text_rule(
    rule: Rule,
    document: ParsedDocxDocument,
) -> list[Violation]:
    toc_paragraphs = [
        paragraph for paragraph in document.paragraphs
        if paragraph.logical_section == "toc" and paragraph.text.strip()
    ]
    if not toc_paragraphs:
        return []

    heading_texts = {
        _normalize_text(re.sub(r"\s+\d+\s*$", "", paragraph.text))
        for paragraph in document.paragraphs
        if paragraph.paragraph_type == ParagraphType.HEADING
    }
    missing = []
    for paragraph in toc_paragraphs:
        item = _normalize_text(re.sub(r"\s+\d+\s*$", "", paragraph.text))
        if item and item not in heading_texts:
            missing.append(paragraph.text.strip())

    if not missing:
        return []

    return [
        Violation(
            rule_id=rule.id,
            source_section=rule.source_section,
            target=rule.target,
            parameter=rule.parameter,
            location="Содержание",
            expected="пункты содержания совпадают с заголовками в тексте",
            actual=f"не совпадают: {', '.join(missing[:5])}",
            message=(
                "Содержание должно повторять заголовки документа. "
                f"Найдены строки содержания без совпадающего заголовка: {', '.join(missing[:5])}."
            ),
            severity="warning" if _is_recommended(rule) else "error",
            violation_type="structure",
        )
    ]


def _check_intro_content_rule(rule: Rule, document: ParsedDocxDocument) -> list[Violation]:
    expected_items = rule.value if isinstance(rule.value, list) else []
    intro_text = _normalize_text(_section_text(document, "introduction"))
    if not expected_items or not intro_text:
        return []

    missing = [
        str(item)
        for item in expected_items
        if not all(word in intro_text for word in _normalize_text(str(item)).split()[:2])
    ]
    if not missing:
        return []

    return [
        Violation(
            rule_id=rule.id,
            source_section=rule.source_section,
            target=rule.target,
            parameter=rule.parameter,
            location="Введение",
            expected=", ".join(str(item) for item in expected_items),
            actual=f"не найдено: {', '.join(missing)}",
            message=(
                "Во введении не найдены все элементы, требуемые профилем: "
                f"{', '.join(missing)}."
            ),
            severity="warning" if _is_recommended(rule) else "error",
            violation_type="structure",
        )
    ]


def _check_conclusion_content_rule(rule: Rule, document: ParsedDocxDocument) -> list[Violation]:
    conclusion_text = _normalize_text(_section_text(document, "conclusion"))
    if conclusion_text:
        return []

    return [
        Violation(
            rule_id=rule.id,
            source_section=rule.source_section,
            target=rule.target,
            parameter=rule.parameter,
            location="Заключение",
            expected="заключение содержит основные результаты и выводы",
            actual="текст заключения не найден",
            message="В документе не найден текст заключения для проверки содержания.",
            severity="warning" if _is_recommended(rule) else "error",
            violation_type="structure",
        )
    ]


class StructureChecker:
    """Проверяет структуру и содержательные элементы документа."""

    def check(self, document: ParsedDocxDocument, profile: Profile) -> list[Violation]:
        violations: list[Violation] = []

        for rule in profile.rules:
            if rule.parameter not in STRUCTURE_PARAMETERS:
                continue

            if rule.parameter == "front_matter_page_numbers_hidden_until_intro":
                violations.extend(_check_front_matter_page_numbers_hidden_until_intro_rule(rule, document))
            elif rule.parameter == "required_document_structure":
                violations.extend(_check_required_document_structure_rule(rule, document))
            elif rule.parameter == "references_min_count":
                violations.extend(_check_references_min_count_rule(rule, document))
            elif rule.parameter == "heading_english_not_allowed":
                violations.extend(_check_heading_english_not_allowed_rule(rule, document))
            elif rule.parameter == "toc_headings_match_text":
                violations.extend(_check_toc_headings_match_text_rule(rule, document))
            elif rule.parameter == "introduction_required_content":
                violations.extend(_check_intro_content_rule(rule, document))
            elif rule.parameter == "conclusion_required_content":
                violations.extend(_check_conclusion_content_rule(rule, document))

        return violations
