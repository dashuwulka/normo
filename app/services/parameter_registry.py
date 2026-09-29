from collections.abc import Callable
from dataclasses import dataclass
from typing import Any

from docx.enum.text import WD_ALIGN_PARAGRAPH

from app.models.document import ParagraphData, ParagraphType, SectionData


ParameterGetter = Callable[[Any], Any]
ParameterApplier = Callable[[Any, Any], None]

ALIGNMENT_TO_WORD = {
    "left": WD_ALIGN_PARAGRAPH.LEFT,
    "center": WD_ALIGN_PARAGRAPH.CENTER,
    "right": WD_ALIGN_PARAGRAPH.RIGHT,
    "justify": WD_ALIGN_PARAGRAPH.JUSTIFY,
}

TARGET_TO_PARAGRAPH_TYPE: dict[str, ParagraphType] = {
    "main_text": ParagraphType.MAIN_TEXT,
    "heading": ParagraphType.HEADING,
    "heading_level_1": ParagraphType.HEADING,
    "heading_level_2": ParagraphType.HEADING,
    "heading_level_3": ParagraphType.HEADING,
    "section_heading": ParagraphType.HEADING,
    "structural_heading": ParagraphType.HEADING,
    "subsection_heading": ParagraphType.HEADING,
    "point_heading": ParagraphType.HEADING,
    "appendix_heading": ParagraphType.HEADING,
    "caption": ParagraphType.CAPTION,
    "list_item": ParagraphType.LIST_ITEM,
    "note": ParagraphType.NOTE,
    "footnote": ParagraphType.FOOTNOTE,
    "table_cell": ParagraphType.TABLE_CELL,
}

TARGET_TO_HEADING_LEVEL: dict[str, int] = {
    "heading_level_1": 1,
    "heading_level_2": 2,
    "heading_level_3": 3,
    "section_heading": 1,
    "subsection_heading": 2,
    "point_heading": 3,
}

ADDITIONAL_TEXT_PARAGRAPH_TYPES: tuple[ParagraphType, ...] = (
    ParagraphType.CAPTION,
    ParagraphType.NOTE,
    ParagraphType.FOOTNOTE,
    ParagraphType.TABLE_CELL,
)


@dataclass(frozen=True)
class ParameterDefinition:
    """Single source of truth for profile parameter metadata."""

    id: str
    label: str
    unit: str | None = None
    target_kind: str = "paragraph"
    getter: ParameterGetter | None = None
    applier: ParameterApplier | None = None
    allowed_operators: tuple[str, ...] = ("equals", "in", "min", "max")


VALUE_LABELS: dict[str, str] = {
    "left": "по левому краю",
    "center": "по центру",
    "right": "по правому краю",
    "justify": "по ширине",
    "portrait": "книжная",
    "landscape": "альбомная",
    "footer": "нижний колонтитул",
    "header": "верхний колонтитул",
    "000000": "чёрный",
}


def _terminal_dot(paragraph: ParagraphData) -> bool:
    return paragraph.text.strip().endswith(".")


def _apply_run_font_name(paragraph: Any, value: Any) -> None:
    for run in paragraph.runs:
        run.font.name = str(value)


def _apply_run_font_size(paragraph: Any, value: Any) -> None:
    from docx.shared import Pt

    for run in paragraph.runs:
        run.font.size = Pt(float(value))


def _apply_run_bold(paragraph: Any, value: Any) -> None:
    for run in paragraph.runs:
        run.font.bold = bool(value)


def _apply_run_italic(paragraph: Any, value: Any) -> None:
    for run in paragraph.runs:
        run.font.italic = bool(value)


def _apply_alignment(paragraph: Any, value: Any) -> None:
    word_alignment = ALIGNMENT_TO_WORD.get(str(value))
    if word_alignment is not None:
        paragraph.alignment = word_alignment


def _apply_cm_paragraph_format(attribute: str) -> ParameterApplier:
    def apply(paragraph: Any, value: Any) -> None:
        from docx.shared import Cm

        setattr(paragraph.paragraph_format, attribute, Cm(float(value)))

    return apply


def _apply_pt_paragraph_format(attribute: str) -> ParameterApplier:
    def apply(paragraph: Any, value: Any) -> None:
        from docx.shared import Pt

        setattr(paragraph.paragraph_format, attribute, Pt(float(value)))

    return apply


def _apply_paragraph_format(attribute: str) -> ParameterApplier:
    def apply(paragraph: Any, value: Any) -> None:
        setattr(paragraph.paragraph_format, attribute, value)

    return apply


PARAMETER_REGISTRY: dict[str, ParameterDefinition] = {
    "font_family": ParameterDefinition(
        id="font_family",
        label="шрифт",
        getter=lambda p: p.font_family,
        applier=_apply_run_font_name,
    ),
    "font_size": ParameterDefinition(
        id="font_size",
        label="размер шрифта",
        unit="pt",
        getter=lambda p: p.font_size_pt,
        applier=_apply_run_font_size,
    ),
    "bold": ParameterDefinition(
        id="bold",
        label="полужирное начертание",
        getter=lambda p: p.bold,
        applier=_apply_run_bold,
    ),
    "italic": ParameterDefinition(
        id="italic",
        label="курсивное начертание",
        getter=lambda p: p.italic,
        applier=_apply_run_italic,
    ),
    "alignment": ParameterDefinition(
        id="alignment",
        label="выравнивание",
        getter=lambda p: p.alignment,
        applier=_apply_alignment,
    ),
    "first_line_indent": ParameterDefinition(
        id="first_line_indent",
        label="абзацный отступ",
        unit="cm",
        getter=lambda p: p.first_line_indent_cm or 0.0,
        applier=_apply_cm_paragraph_format("first_line_indent"),
    ),
    "left_indent": ParameterDefinition(
        id="left_indent",
        label="левый отступ абзаца",
        unit="cm",
        getter=lambda p: p.left_indent_cm or 0.0,
        applier=_apply_cm_paragraph_format("left_indent"),
    ),
    "right_indent": ParameterDefinition(
        id="right_indent",
        label="правый отступ абзаца",
        unit="cm",
        getter=lambda p: p.right_indent_cm or 0.0,
        applier=_apply_cm_paragraph_format("right_indent"),
    ),
    "line_spacing": ParameterDefinition(
        id="line_spacing",
        label="межстрочный интервал",
        getter=lambda p: p.line_spacing,
        applier=_apply_paragraph_format("line_spacing"),
    ),
    "space_before": ParameterDefinition(
        id="space_before",
        label="интервал перед абзацем",
        unit="pt",
        getter=lambda p: p.space_before_pt or 0.0,
        applier=_apply_pt_paragraph_format("space_before"),
    ),
    "space_after": ParameterDefinition(
        id="space_after",
        label="интервал после абзаца",
        unit="pt",
        getter=lambda p: p.space_after_pt or 0.0,
        applier=_apply_pt_paragraph_format("space_after"),
    ),
    "keep_with_next": ParameterDefinition(
        id="keep_with_next",
        label="не отрывать от следующего абзаца",
        getter=lambda p: bool(p.keep_with_next),
        applier=_apply_paragraph_format("keep_with_next"),
    ),
    "keep_together": ParameterDefinition(
        id="keep_together",
        label="не разрывать абзац",
        getter=lambda p: bool(p.keep_together),
        applier=_apply_paragraph_format("keep_together"),
    ),
    "page_break_before": ParameterDefinition(
        id="page_break_before",
        label="с новой страницы",
        getter=lambda p: bool(p.page_break_before),
        applier=_apply_paragraph_format("page_break_before"),
    ),
    "terminal_dot": ParameterDefinition(
        id="terminal_dot",
        label="точка в конце заголовка",
        getter=_terminal_dot,
    ),
    "numbering_terminal_dot": ParameterDefinition(
        id="numbering_terminal_dot",
        label="точка после нумерационной части заголовка",
    ),
    "starts_with_capital": ParameterDefinition(
        id="starts_with_capital",
        label="прописная буква в начале заголовка",
    ),
    "empty_paragraph_around_heading": ParameterDefinition(
        id="empty_paragraph_around_heading",
        label="пустая строка вокруг заголовка",
        target_kind="document",
    ),
    "heading_indent_policy": ParameterDefinition(
        id="heading_indent_policy",
        label="отступы заголовка",
        target_kind="document",
    ),
    "page_format": ParameterDefinition(
        id="page_format",
        label="формат страницы",
        target_kind="section",
        getter=lambda s: s.page_format,
    ),
    "page_orientation": ParameterDefinition(
        id="page_orientation",
        label="ориентация страницы",
        target_kind="section",
        getter=lambda s: s.page_orientation,
    ),
    "top_margin": ParameterDefinition(
        id="top_margin",
        label="верхнее поле",
        unit="cm",
        target_kind="section",
        getter=lambda s: s.top_margin_cm,
    ),
    "bottom_margin": ParameterDefinition(
        id="bottom_margin",
        label="нижнее поле",
        unit="cm",
        target_kind="section",
        getter=lambda s: s.bottom_margin_cm,
    ),
    "left_margin": ParameterDefinition(
        id="left_margin",
        label="левое поле",
        unit="cm",
        target_kind="section",
        getter=lambda s: s.left_margin_cm,
    ),
    "right_margin": ParameterDefinition(
        id="right_margin",
        label="правое поле",
        unit="cm",
        target_kind="section",
        getter=lambda s: s.right_margin_cm,
    ),
    "header_distance": ParameterDefinition(
        id="header_distance",
        label="расстояние до верхнего колонтитула",
        unit="cm",
        target_kind="section",
        getter=lambda s: s.header_distance_cm,
    ),
    "footer_distance": ParameterDefinition(
        id="footer_distance",
        label="расстояние до нижнего колонтитула",
        unit="cm",
        target_kind="section",
        getter=lambda s: s.footer_distance_cm,
    ),
    "page_number_area": ParameterDefinition(
        id="page_number_area",
        label="расположение колонцифры",
        target_kind="section",
        getter=lambda s: s.page_number_area,
    ),
    "page_number_alignment": ParameterDefinition(
        id="page_number_alignment",
        label="выравнивание колонцифры",
        target_kind="section",
        getter=lambda s: s.page_number_alignment,
    ),
    "header_short_title": ParameterDefinition(
        id="header_short_title",
        label="верхний колонтитул",
        target_kind="section",
        getter=lambda s: s.header_text,
    ),
    "first_page_no_page_number": ParameterDefinition(
        id="first_page_no_page_number",
        label="номер на титульной странице",
        target_kind="document",
    ),
    "continuous_page_numbering": ParameterDefinition(
        id="continuous_page_numbering",
        label="непрерывная нумерация страниц",
        target_kind="section",
    ),
    "font_color": ParameterDefinition(id="font_color", label="цвет шрифта"),
    "underline": ParameterDefinition(id="underline", label="подчёркивание"),
    "strike": ParameterDefinition(id="strike", label="зачёркивание"),
    "double_strike": ParameterDefinition(
        id="double_strike",
        label="двойное зачёркивание",
    ),
    "small_caps": ParameterDefinition(id="small_caps", label="капитель"),
    "all_caps": ParameterDefinition(id="all_caps", label="прописные буквы"),
    "character_spacing": ParameterDefinition(
        id="character_spacing",
        label="разрядка",
    ),
    "emphasis_character_style": ParameterDefinition(
        id="emphasis_character_style",
        label="символьный стиль выделения",
    ),
    "emphasis_methods_consistency": ParameterDefinition(
        id="emphasis_methods_consistency",
        label="единообразие способов выделения",
        target_kind="document",
    ),
    "uppercase_emphasis": ParameterDefinition(
        id="uppercase_emphasis",
        label="выделение прописными буквами",
    ),
    "empty_paragraph_between_content": ParameterDefinition(
        id="empty_paragraph_between_content",
        label="пустой абзац между содержательными абзацами",
        target_kind="document",
    ),
    "heading_font_size_hierarchy": ParameterDefinition(
        id="heading_font_size_hierarchy",
        label="соподчинённость кеглей заголовков",
        unit="pt",
        target_kind="document",
    ),
    "heading_line_spacing_max_main": ParameterDefinition(
        id="heading_line_spacing_max_main",
        label="интерлиньяж заголовка",
        target_kind="document",
    ),
    "heading_spacing_order": ParameterDefinition(
        id="heading_spacing_order",
        label="интервалы вокруг заголовка",
        target_kind="document",
    ),
    "heading_space_after_min_single": ParameterDefinition(
        id="heading_space_after_min_single",
        label="интервал после заголовка",
        target_kind="document",
    ),
    "heading_all_caps": ParameterDefinition(
        id="heading_all_caps",
        label="заголовок прописными буквами",
        target_kind="document",
    ),
    "heading_color_only": ParameterDefinition(
        id="heading_color_only",
        label="выделение заголовка только цветом",
        target_kind="document",
    ),
    "additional_text_font_size_relative": ParameterDefinition(
        id="additional_text_font_size_relative",
        label="кегль дополнительного текста",
        unit="pt",
        target_kind="document",
    ),
    "additional_spacing_limit": ParameterDefinition(
        id="additional_spacing_limit",
        label="дополнительный интервал между частями текста",
        unit="pt",
        target_kind="document",
    ),
    "centered_text_no_indents": ParameterDefinition(
        id="centered_text_no_indents",
        label="центрированный текст без втяжек",
        target_kind="document",
    ),
    "repeated_spaces": ParameterDefinition(id="repeated_spaces", label="повторяющиеся пробелы", target_kind="document"),
    "paragraph_edge_spaces": ParameterDefinition(id="paragraph_edge_spaces", label="пробелы в начале или конце абзаца", target_kind="document"),
    "spaces_near_punctuation": ParameterDefinition(id="spaces_near_punctuation", label="пробелы около знаков препинания", target_kind="document"),
    "repeated_tabs": ParameterDefinition(id="repeated_tabs", label="повторяющиеся табуляции", target_kind="document"),
    "spaces_inside_brackets_quotes": ParameterDefinition(id="spaces_inside_brackets_quotes", label="пробелы внутри скобок и кавычек", target_kind="document"),
    "number_letter_no_space": ParameterDefinition(id="number_letter_no_space", label="число с буквой без пробела", target_kind="document"),
    "nbsp_after_abbreviations": ParameterDefinition(id="nbsp_after_abbreviations", label="неразрывный пробел после сокращений", target_kind="document"),
    "nbsp_between_initials": ParameterDefinition(id="nbsp_between_initials", label="неразрывный пробел между инициалами", target_kind="document"),
    "nbsp_after_number_sign": ParameterDefinition(id="nbsp_after_number_sign", label="неразрывный пробел после знака номера", target_kind="document"),
    "nbsp_after_paragraph_sign": ParameterDefinition(id="nbsp_after_paragraph_sign", label="неразрывный пробел после знака параграфа", target_kind="document"),
    "nbsp_after_figure_table_reference": ParameterDefinition(id="nbsp_after_figure_table_reference", label="неразрывный пробел после ссылки на рисунок или таблицу", target_kind="document"),
    "nbsp_between_number_and_unit": ParameterDefinition(id="nbsp_between_number_and_unit", label="неразрывный пробел между числом и единицей", target_kind="document"),
    "image_format": ParameterDefinition(id="image_format", label="формат изображения", target_kind="document"),
    "image_max_px": ParameterDefinition(id="image_max_px", label="размер изображения в пикселях", target_kind="document"),
    "image_after_first_reference": ParameterDefinition(id="image_after_first_reference", label="рисунок после первого упоминания", target_kind="document"),
    "image_paragraph_centered": ParameterDefinition(id="image_paragraph_centered", label="абзац с изображением по центру", target_kind="document"),
    "image_keep_with_next": ParameterDefinition(id="image_keep_with_next", label="изображение не отрывать от подписи", target_kind="document"),
    "image_no_space_after_if_caption": ParameterDefinition(id="image_no_space_after_if_caption", label="интервал после изображения перед подписью", target_kind="document"),
    "image_size_consistency": ParameterDefinition(id="image_size_consistency", label="единообразие размеров изображений", target_kind="document"),
    "figure_caption_position": ParameterDefinition(id="figure_caption_position", label="расположение подписи рисунка", target_kind="document"),
    "figure_caption_alignment": ParameterDefinition(id="figure_caption_alignment", label="выравнивание подписи рисунка", target_kind="document"),
    "figure_caption_prefix": ParameterDefinition(id="figure_caption_prefix", label="слово в начале подписи рисунка", target_kind="document"),
    "figure_caption_separator": ParameterDefinition(id="figure_caption_separator", label="разделитель после номера рисунка", target_kind="document"),
    "figure_caption_terminal_dot": ParameterDefinition(id="figure_caption_terminal_dot", label="точка в конце подписи рисунка", target_kind="document"),
    "figure_reference_required": ParameterDefinition(id="figure_reference_required", label="ссылка на рисунок в тексте", target_kind="document"),
    "figure_after_reference": ParameterDefinition(id="figure_after_reference", label="рисунок после первого упоминания", target_kind="document"),
    "figure_caption_prefix_consistency": ParameterDefinition(id="figure_caption_prefix_consistency", label="единообразие начала подписей рисунков", target_kind="document"),
    "figure_caption_dot_after_number": ParameterDefinition(id="figure_caption_dot_after_number", label="точка после номера рисунка", target_kind="document"),
    "figure_caption_title_format": ParameterDefinition(id="figure_caption_title_format", label="оформление названия рисунка", target_kind="document"),
    "figure_caption_font_size": ParameterDefinition(id="figure_caption_font_size", label="кегль подписи рисунка", unit="pt", target_kind="document"),
    "figure_caption_spacing": ParameterDefinition(id="figure_caption_spacing", label="интервалы подписи рисунка", unit="pt", target_kind="document"),
    "table_after_first_reference": ParameterDefinition(id="table_after_first_reference", label="таблица после первого упоминания", target_kind="document"),
    "table_grid_style": ParameterDefinition(id="table_grid_style", label="простая сетка таблицы", target_kind="document"),
    "table_caption_position": ParameterDefinition(id="table_caption_position", label="название над таблицей", target_kind="document"),
    "table_caption_alignment": ParameterDefinition(id="table_caption_alignment", label="выравнивание названия таблицы", target_kind="document"),
    "table_caption_prefix": ParameterDefinition(id="table_caption_prefix", label="слово в начале названия таблицы", target_kind="document"),
    "table_caption_separator": ParameterDefinition(id="table_caption_separator", label="разделитель после номера таблицы", target_kind="document"),
    "table_caption_terminal_dot": ParameterDefinition(id="table_caption_terminal_dot", label="точка в конце названия таблицы", target_kind="document"),
    "table_text_font_size": ParameterDefinition(id="table_text_font_size", label="размер шрифта в таблице", unit="pt", target_kind="document"),
    "table_text_line_spacing": ParameterDefinition(id="table_text_line_spacing", label="межстрочный интервал в таблице", target_kind="document"),
    "table_title_position": ParameterDefinition(id="table_title_position", label="заголовок таблицы над таблицей", target_kind="document"),
    "table_title_format": ParameterDefinition(id="table_title_format", label="формат заголовка таблицы", target_kind="document"),
    "table_title_font_size": ParameterDefinition(id="table_title_font_size", label="кегль заголовка таблицы", unit="pt", target_kind="document"),
    "table_title_keep": ParameterDefinition(id="table_title_keep", label="не отрывать заголовок таблицы", target_kind="document"),
    "table_header_required": ParameterDefinition(id="table_header_required", label="строка с названиями столбцов", target_kind="document"),
    "table_text_spacing_indent": ParameterDefinition(id="table_text_spacing_indent", label="интервал и отступы текста таблицы", target_kind="document"),
    "table_font_size": ParameterDefinition(id="table_font_size", label="кегль текста таблиц", unit="pt", target_kind="document"),
    "table_font_size_consistency": ParameterDefinition(id="table_font_size_consistency", label="единообразие кегля таблиц", unit="pt", target_kind="document"),
    "table_column_alignment_consistency": ParameterDefinition(id="table_column_alignment_consistency", label="выравнивание в колонках таблиц", target_kind="document"),
    "table_width_within_text_area": ParameterDefinition(id="table_width_within_text_area", label="ширина таблицы в полосе набора", target_kind="document"),
    "table_no_empty_rows": ParameterDefinition(id="table_no_empty_rows", label="пустые строки таблицы", target_kind="document"),
    "table_allow_row_break": ParameterDefinition(id="table_allow_row_break", label="перенос строк таблицы", target_kind="document"),
    "table_repeat_header": ParameterDefinition(id="table_repeat_header", label="повтор строки с названиями столбцов", target_kind="document"),
    "no_continuation_table_titles": ParameterDefinition(id="no_continuation_table_titles", label="без надписей Продолжение таблицы", target_kind="document"),
    "list_marker_allowed": ParameterDefinition(id="list_marker_allowed", label="маркер перечисления", target_kind="document"),
    "list_marker_dash_required": ParameterDefinition(id="list_marker_dash_required", label="маркер списка — длинное тире", target_kind="document"),
    "hyphen_list_marker_not_recommended": ParameterDefinition(id="hyphen_list_marker_not_recommended", label="дефис как маркер списка", target_kind="document"),
    "list_marker_consistency": ParameterDefinition(id="list_marker_consistency", label="единый тип маркера в списке", target_kind="document"),
    "references_min_count": ParameterDefinition(id="references_min_count", label="минимальное количество источников", target_kind="document"),
    "required_document_structure": ParameterDefinition(id="required_document_structure", label="состав работы", target_kind="document"),
    "heading_english_not_allowed": ParameterDefinition(id="heading_english_not_allowed", label="заголовки на английском языке", target_kind="document"),
    "front_matter_page_numbers_hidden_until_intro": ParameterDefinition(id="front_matter_page_numbers_hidden_until_intro", label="скрытая нумерация до введения", target_kind="document"),
    "automatic_list_numbering_required": ParameterDefinition(id="automatic_list_numbering_required", label="автоматическая нумерация списков", target_kind="document"),
    "list_punctuation_policy": ParameterDefinition(id="list_punctuation_policy", label="оформление пунктов списка", target_kind="document"),
    "initial_verb_form": ParameterDefinition(id="initial_verb_form", label="форма задач во введении", target_kind="document"),
    "completed_action_form": ParameterDefinition(id="completed_action_form", label="формулировки результатов в заключении", target_kind="document"),
    "forbidden_phrases": ParameterDefinition(id="forbidden_phrases", label="нежелательные слова и формулировки", target_kind="document"),
    "equations_editable": ParameterDefinition(id="equations_editable", label="редактируемые формулы", target_kind="document"),
    "long_equation_standalone": ParameterDefinition(id="long_equation_standalone", label="формула отдельной строкой", target_kind="document"),
    "equation_alignment_left": ParameterDefinition(id="equation_alignment_left", label="выравнивание уравнения", target_kind="document"),
    "equation_number_right": ParameterDefinition(id="equation_number_right", label="номер уравнения", target_kind="document"),
    "numbered_equation_has_reference": ParameterDefinition(id="numbered_equation_has_reference", label="ссылка на нумерованную формулу", target_kind="document"),
    "math_operator_nbsp": ParameterDefinition(id="math_operator_nbsp", label="неразрывные пробелы вокруг математических операций", target_kind="document"),
    "slash_without_spaces": ParameterDefinition(id="slash_without_spaces", label="косая черта без пробелов", target_kind="document"),
    "wrong_multiplication_symbols": ParameterDefinition(id="wrong_multiplication_symbols", label="недопустимый знак умножения", target_kind="document"),
    "hyphen_instead_of_minus": ParameterDefinition(id="hyphen_instead_of_minus", label="дефис вместо минуса", target_kind="document"),
    "multiplication_sign_consistency": ParameterDefinition(id="multiplication_sign_consistency", label="единообразие знака умножения", target_kind="document"),
    "equation_line_break_rule": ParameterDefinition(id="equation_line_break_rule", label="перенос формулы", target_kind="document"),
    "decimal_separator_comma": ParameterDefinition(id="decimal_separator_comma", label="десятичная запятая", target_kind="document"),
    "degree_symbol": ParameterDefinition(id="degree_symbol", label="знак градуса", target_kind="document"),
    "multiplication_symbol": ParameterDefinition(id="multiplication_symbol", label="символ умножения", target_kind="document"),
    "minus_symbol": ParameterDefinition(id="minus_symbol", label="символ минуса", target_kind="document"),
    "variable_italic": ParameterDefinition(id="variable_italic", label="курсив переменных", target_kind="document"),
    "function_and_chemical_regular": ParameterDefinition(id="function_and_chemical_regular", label="прямое начертание функций и химических формул", target_kind="document"),
    "numeric_range_dash": ParameterDefinition(id="numeric_range_dash", label="тире в числовом диапазоне", target_kind="document"),
    "unit_nbsp": ParameterDefinition(id="unit_nbsp", label="неразрывный пробел между числом и единицей", target_kind="document"),
    "temperature_nbsp": ParameterDefinition(id="temperature_nbsp", label="температура и знак градуса", target_kind="document"),
    "percent_nbsp": ParameterDefinition(id="percent_nbsp", label="процент и промилле", target_kind="document"),
    "dimension_operator_spacing": ParameterDefinition(id="dimension_operator_spacing", label="пробелы в размерностях", target_kind="document"),
    "dimension_consistency": ParameterDefinition(id="dimension_consistency", label="единообразие размерностей", target_kind="document"),
    "no_dot_after_units": ParameterDefinition(id="no_dot_after_units", label="точка после единиц измерения", target_kind="document"),
    "variable_unit_comma": ParameterDefinition(id="variable_unit_comma", label="размерность переменной через запятую", target_kind="document"),
    "unit_only_after_last_number": ParameterDefinition(id="unit_only_after_last_number", label="размерность только у последнего числа", target_kind="document"),
    "index_language_consistency": ParameterDefinition(id="index_language_consistency", label="индексы", target_kind="document"),
    "scientific_notation_consistency": ParameterDefinition(id="scientific_notation_consistency", label="единообразие научной записи", target_kind="document"),
    "digit_grouping_nbsp": ParameterDefinition(id="digit_grouping_nbsp", label="группировка разрядов", target_kind="document"),
    "footnotes_processor_required": ParameterDefinition(id="footnotes_processor_required", label="автоматические сноски", target_kind="document"),
    "footnotes_format_consistency": ParameterDefinition(id="footnotes_format_consistency", label="единообразие сносок", target_kind="document"),
    "footnotes_continuous_decimal_numbering": ParameterDefinition(id="footnotes_continuous_decimal_numbering", label="сквозная нумерация сносок", target_kind="document"),
    "footnote_font_family_and_size": ParameterDefinition(id="footnote_font_family_and_size", label="гарнитура и кегль сносок", target_kind="document"),
    "hyphen_spacing": ParameterDefinition(id="hyphen_spacing", label="пробелы вокруг дефиса", target_kind="document"),
    "manual_hyphenation_forbidden": ParameterDefinition(id="manual_hyphenation_forbidden", label="ручной перенос дефисом", target_kind="document"),
    "dash_spacing": ParameterDefinition(id="dash_spacing", label="пробелы вокруг тире", target_kind="document"),
    "hyphen_instead_of_dash": ParameterDefinition(id="hyphen_instead_of_dash", label="дефис вместо тире", target_kind="document"),
    "russian_quotes": ParameterDefinition(id="russian_quotes", label="русские кавычки", target_kind="document"),
    "nested_quotes": ParameterDefinition(id="nested_quotes", label="вложенность кавычек", target_kind="document"),
    "number_sign_symbol": ParameterDefinition(id="number_sign_symbol", label="символ номера", target_kind="document"),
    "number_sign_nbsp": ParameterDefinition(id="number_sign_nbsp", label="неразрывный пробел после №", target_kind="document"),
    "parentheses_not_slash": ParameterDefinition(id="parentheses_not_slash", label="скобки вместо косых линий", target_kind="document"),
    "square_brackets_usage": ParameterDefinition(id="square_brackets_usage", label="употребление квадратных скобок", target_kind="document"),
    "citation_omission_format": ParameterDefinition(id="citation_omission_format", label="пропуск в цитате", target_kind="document"),
    "dot_after_footnote_or_note": ParameterDefinition(id="dot_after_footnote_or_note", label="точка после сноски или примечания", target_kind="document"),
    "no_dot_after_udc_keywords_table_title": ParameterDefinition(id="no_dot_after_udc_keywords_table_title", label="где точка не ставится", target_kind="document"),
    "music_terms_typography": ParameterDefinition(id="music_terms_typography", label="музыкальные обозначения", target_kind="document"),
    "phone_number_format": ParameterDefinition(id="phone_number_format", label="формат телефонного номера", target_kind="document"),
    "phone_country_code_consistency": ParameterDefinition(id="phone_country_code_consistency", label="единообразие кода страны", target_kind="document"),
}


def get_parameter_definition(parameter: str) -> ParameterDefinition | None:
    return PARAMETER_REGISTRY.get(parameter)


def get_parameter_label(parameter: str) -> str:
    definition = get_parameter_definition(parameter)
    return definition.label if definition is not None else parameter


def get_parameter_unit(parameter: str) -> str | None:
    definition = get_parameter_definition(parameter)
    return definition.unit if definition is not None else None


def get_value_label(value: Any) -> str:
    return VALUE_LABELS.get(str(value), str(value))


def get_paragraph_value(paragraph: ParagraphData, parameter: str) -> Any:
    definition = get_parameter_definition(parameter)
    if definition is None or definition.getter is None:
        return None

    if definition.target_kind != "paragraph":
        return None

    return definition.getter(paragraph)


def get_section_value(section: SectionData, parameter: str) -> Any:
    definition = get_parameter_definition(parameter)
    if definition is None or definition.getter is None:
        return None

    if definition.target_kind != "section":
        return None

    return definition.getter(section)


def apply_paragraph_value(paragraph: Any, parameter: str, value: Any) -> bool:
    definition = get_parameter_definition(parameter)
    if definition is None or definition.applier is None:
        return False

    if definition.target_kind != "paragraph":
        return False

    definition.applier(paragraph, value)
    return True


def format_value(value: Any, unit: str | None = None) -> str:
    if value is None:
        return "не определено"

    if isinstance(value, bool):
        value_text = "да" if value else "нет"
    elif isinstance(value, list):
        value_text = ", ".join(format_value(item, unit=None) for item in value)
    elif isinstance(value, float):
        value_text = f"{value:.2f}".rstrip("0").rstrip(".")
    else:
        value_text = str(value)

    value_text = VALUE_LABELS.get(value_text, value_text)

    unit_labels = {
        "cm": "см",
        "pt": "пт",
    }

    if unit and not isinstance(value, list):
        return f"{value_text} {unit_labels.get(unit, unit)}"

    return value_text
