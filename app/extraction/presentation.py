from collections import defaultdict
from typing import Any

from app.extraction.models import ExtractedRuleCandidate
from app.services.parameter_registry import format_value, get_parameter_label


TARGET_LABELS = {
    "page": "страница",
    "document": "документ",
    "main_text": "основной текст",
    "additional_text": "дополнительный текст",
    "heading": "все заголовки",
    "heading_level_1": "заголовок первого уровня",
    "heading_level_2": "заголовок второго уровня",
    "heading_level_3": "заголовок третьего уровня",
    "section_heading": "заголовок раздела",
    "structural_heading": "ненумерованный раздел: введение, заключение, содержание",
    "subsection_heading": "заголовок подраздела",
    "point_heading": "заголовок пункта",
    "appendix_heading": "заголовок приложения",
    "caption": "подписи и названия",
    "figure_caption": "подпись рисунка",
    "table_caption": "название таблицы",
    "table": "таблица",
    "table_cell": "текст таблицы",
    "footnote": "сноски",
    "note": "примечания",
    "list_item": "элемент списка",
    "introduction_tasks": "задачи во введении",
    "conclusion": "заключение",
}

TARGET_GROUP_LABELS = {
    "page": "Оформление страницы",
    "document": "Структура документа",
    "main_text": "Основной текст",
    "additional_text": "Дополнительный текст",
    "heading": "Заголовки",
    "heading_level_1": "Заголовки",
    "heading_level_2": "Заголовки",
    "heading_level_3": "Заголовки",
    "section_heading": "Заголовки",
    "structural_heading": "Заголовки",
    "subsection_heading": "Заголовки",
    "point_heading": "Заголовки",
    "appendix_heading": "Заголовки",
    "caption": "Рисунки, таблицы и подписи",
    "figure_caption": "Рисунки, таблицы и подписи",
    "table_caption": "Рисунки, таблицы и подписи",
    "table": "Таблицы",
    "table_cell": "Таблицы",
    "footnote": "Сноски",
    "note": "Примечания",
    "list_item": "Списки",
}

EXTRA_PARAMETER_LABELS = {
    "required_document_structure": "состав работы",
    "recommended_work_volume": "рекомендуемый объём работы",
    "introduction_required_content": "содержание введения",
    "conclusion_required_content": "содержание заключения",
    "toc_headings_match_text": "соответствие содержания заголовкам",
    "title_page_topic_match": "соответствие названия утверждённой теме",
    "document_language": "язык работы",
    "section_conclusions_required": "выводы в конце разделов",
    "first_main_section_review_required": "обзор источников в первом разделе",
    "additional_section_required": "дополнительный раздел",
    "references_min_count": "минимальное количество источников",
    "initial_verb_form": "форма задач во введении",
    "forbidden_phrases": "нежелательные слова и формулировки",
    "completed_action_form": "формулировки результатов в заключении",
    "heading_english_not_allowed": "заголовки на английском языке",
    "list_marker_dash_required": "маркер списка — длинное тире",
    "list_marker_consistency": "единый тип маркера в списке",
    "front_matter_page_numbers_hidden_until_intro": "скрытая нумерация до введения",
    "automatic_list_numbering_required": "автоматическая нумерация списков",
    "list_punctuation_policy": "оформление пунктов списка",
    "dash_spacing": "оформление длинного тире",
    "hyphen_instead_of_dash": "дефис вместо тире",
    "numeric_range_dash": "тире в числовых диапазонах",
    "number_sign_symbol": "знак номера",
    "russian_quotes": "русские кавычки",
    "no_dot_after_udc_keywords_table_title": "точка там, где её не ставят",
    "image_keep_with_next": "рисунок не отрывать от подписи",
    "figure_caption_position": "подпись под рисунком",
    "figure_caption_alignment": "выравнивание подписи рисунка",
    "figure_caption_prefix": "слово в начале подписи рисунка",
    "figure_caption_separator": "разделитель после номера рисунка",
    "figure_caption_terminal_dot": "точка в конце подписи рисунка",
    "figure_reference_required": "ссылка на рисунок в тексте",
    "figure_after_reference": "рисунок после первого упоминания",
    "table_caption_position": "название над таблицей",
    "table_caption_alignment": "выравнивание названия таблицы",
    "table_caption_prefix": "слово в начале названия таблицы",
    "table_caption_separator": "разделитель после номера таблицы",
    "table_caption_terminal_dot": "точка в конце названия таблицы",
    "table_text_font_size": "размер шрифта в таблице",
    "table_text_line_spacing": "межстрочный интервал в таблице",
    "table_header_required": "строка заголовков таблицы",
    "table_grid_style": "сетка таблицы",
    "table_title_keep": "название таблицы не отрывать от таблицы",
    "table_repeat_header": "повтор строки заголовков таблицы",
}

VALUE_LABELS = {
    "000000": "чёрный",
    "black": "чёрный",
    "true": "да",
    "false": "нет",
    "justify": "по ширине",
    "center": "по центру",
    "left": "по левому краю",
    "right": "по правому краю",
    "dash": "тире после номера",
    "hyphen": "дефис",
    "dot": "точка после номера",
    "no_dot": "без точки в конце",
    "below": "под объектом",
    "above": "над объектом",
    "after_reference": "после первого упоминания",
    "infinitive": "глагол в неопределённой форме",
    "automatic": "автоматически",
    "visible": "видимая",
    "hidden": "скрытая",
    "russian": "русский язык",
    "русский язык": "русский язык",
}

OPERATOR_LABELS = {
    "equals": "должно быть",
    "min": "не меньше",
    "max": "не больше",
    "in": "одно из значений",
}

MODALITY_LABELS = {
    "mandatory": "обязательное требование",
    "recommended": "рекомендация",
    "allowed": "допускается",
    "unknown": "требует уточнения",
}

STATUS_LABELS = {
    "extracted": "можно принять",
    "needs_review": "нужно проверить",
    "unsupported": "не добавляется в профиль",
    "conflict": "есть конфликт",
    "rejected": "пропущено",
    "confirmed": "принято",
}

STATUS_HINTS = {
    "extracted": "Правило распознано достаточно уверенно. Его можно сохранить в профиль.",
    "needs_review": "Система нашла требование, но его лучше проверить вручную перед сохранением.",
    "unsupported": "Такое требование найдено, но сейчас программа его не проверяет, поэтому оно не будет добавлено в профиль.",
    "conflict": "В документе найдены разные значения для одного требования. Нужно выбрать правильное.",
    "rejected": "Правило не попадёт в итоговый профиль.",
    "confirmed": "Правило будет сохранено в JSON-профиль.",
}

BOOLEAN_RULE_TEXTS = {
    "hyphen_instead_of_dash": "не использовать дефис вместо тире",
    "dash_spacing": "оформлять длинное тире с пробелами",
    "numeric_range_dash": "использовать тире в числовых диапазонах",
    "number_sign_symbol": "использовать знак № для обозначения номера",
    "russian_quotes": "использовать русские кавычки «ёлочки»",
    "list_marker_dash_required": "использовать длинное тире как маркер списка",
    "automatic_list_numbering_required": "оформлять нумерованные списки средствами Word",
    "list_punctuation_policy": "оформлять пункты списка по правилам методички",
    "front_matter_page_numbers_hidden_until_intro": "скрывать номера страниц до введения",
    "heading_english_not_allowed": "не использовать заголовки на английском языке",
    "table_header_required": "в таблице должна быть строка с названиями столбцов",
    "table_grid_style": "таблица должна иметь видимую сетку",
    "table_title_keep": "название таблицы должно оставаться вместе с таблицей",
    "table_repeat_header": "повторять строку с названиями столбцов на следующей странице",
    "table_text_spacing_indent": "оформлять текст таблицы без абзацного отступа и с нужным интервалом",
    "figure_caption_position": "подпись должна стоять под рисунком",
    "figure_caption_alignment": "подпись рисунка должна быть выровнена по центру",
    "image_keep_with_next": "рисунок должен оставаться вместе с подписью",
    "figure_after_reference": "рисунок должен располагаться после первого упоминания",
    "image_after_first_reference": "рисунок должен располагаться после первого упоминания",
    "figure_reference_required": "на рисунок должна быть ссылка в тексте",
    "no_dot_after_udc_keywords_table_title": "не ставить точку там, где методичка её запрещает",
}


def target_label(target: str | None) -> str:
    if target is None:
        return "нужно уточнить объект проверки"
    return TARGET_LABELS.get(target, target.replace("_", " "))


def group_label(target: str | None) -> str:
    if target is None:
        return "Требуют уточнения"
    return TARGET_GROUP_LABELS.get(target, target_label(target).capitalize())


def operator_label(operator: str) -> str:
    return OPERATOR_LABELS.get(operator, operator)


def modality_label(modality: str) -> str:
    return MODALITY_LABELS.get(modality, modality)


def status_label(status: str) -> str:
    return STATUS_LABELS.get(status, status)


def status_hint(candidate: ExtractedRuleCandidate) -> str:
    if candidate.explanation and candidate.status not in STATUS_HINTS:
        return candidate.explanation
    return STATUS_HINTS.get(candidate.status, candidate.explanation)


def parameter_label(parameter: str) -> str:
    return EXTRA_PARAMETER_LABELS.get(parameter, get_parameter_label(parameter))


def candidate_value_text(candidate: ExtractedRuleCandidate) -> str:
    return _friendly_value(candidate.value, candidate.unit)


def _friendly_value(value: Any, unit: str | None = None) -> str:
    if isinstance(value, list):
        return ", ".join(_friendly_value(item, None) for item in value)

    text = format_value(value, unit)
    lookup = text.strip().lower()
    if lookup in VALUE_LABELS:
        return VALUE_LABELS[lookup]

    if unit and text.endswith(f" {unit}"):
        raw_text = text[: -(len(unit) + 1)]
        raw_lookup = raw_text.strip().lower()
        if raw_lookup in VALUE_LABELS:
            unit_labels = {"cm": "см", "pt": "пт"}
            return f"{VALUE_LABELS[raw_lookup]} {unit_labels.get(unit, unit)}"

    return text


def candidate_rule_text(candidate: ExtractedRuleCandidate) -> str:
    target = target_label(candidate.target)
    parameter = parameter_label(candidate.parameter)
    value = candidate_value_text(candidate)
    operator = operator_label(candidate.operator)

    if candidate.operator == "equals" and candidate.value is True:
        text = BOOLEAN_RULE_TEXTS.get(candidate.parameter)
        if text:
            return f"{target}: {text}"

    if candidate.operator == "equals":
        return f"{target}: {parameter} — {value}"

    return f"{target}: {parameter} {operator} {value}"


def candidate_can_be_accepted(candidate: ExtractedRuleCandidate) -> bool:
    return (
        candidate.status != "unsupported"
        and candidate.target is not None
        and candidate.modality != "unknown"
    )


def candidate_view(candidate: ExtractedRuleCandidate) -> dict[str, Any]:
    can_accept = candidate_can_be_accepted(candidate)
    return {
        "id": candidate.id,
        "rule_text": candidate_rule_text(candidate),
        "target": target_label(candidate.target),
        "parameter": parameter_label(candidate.parameter),
        "value": candidate_value_text(candidate),
        "modality": modality_label(candidate.modality),
        "status": status_label(candidate.status),
        "status_hint": status_hint(candidate),
        "source_section": candidate.source_section or "без номера",
        "source_text": candidate.source_text,
        "confidence": round(candidate.confidence * 100),
        "can_accept": can_accept,
        "checked": candidate.status == "extracted" and can_accept,
        "raw_status": candidate.status,
    }


def grouped_candidate_views(
    candidates: list[ExtractedRuleCandidate],
) -> list[dict[str, Any]]:
    grouped: dict[str, list[dict[str, Any]]] = defaultdict(list)

    for candidate in candidates:
        grouped[group_label(candidate.target)].append(candidate_view(candidate))

    return [
        {
            "label": label,
            "count": len(items),
            "rules": items,
        }
        for label, items in grouped.items()
    ]
