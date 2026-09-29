from enum import Enum

from pydantic import BaseModel, Field


class ParagraphType(str, Enum):
    """Тип абзаца после предварительной классификации."""

    EMPTY = "empty"
    TITLE_PAGE = "title_page"
    MAIN_TEXT = "main_text"
    HEADING = "heading"
    CAPTION = "caption"
    LIST_ITEM = "list_item"
    NOTE = "note"
    FOOTNOTE = "footnote"
    TABLE_CELL = "table_cell"
    UNKNOWN = "unknown"


class TextRunData(BaseModel):
    """Данные об одном текстовом фрагменте внутри абзаца DOCX."""

    index: int
    text: str
    style_name: str | None = None

    bold: bool | None = None
    italic: bool | None = None
    underline: bool | None = None
    strike: bool | None = None
    double_strike: bool | None = None
    small_caps: bool | None = None
    all_caps: bool | None = None

    font_size_pt: float | None = None
    font_color: str | None = None
    character_spacing: int | None = None
    subscript: bool = False
    superscript: bool = False
    has_nonbreaking_space: bool = False
    nonbreaking_space_count: int = 0

    has_character_style: bool = False
    has_direct_formatting: bool = False


class ParagraphData(BaseModel):
    """Данные об одном абзаце DOCX-документа."""

    index: int
    text: str
    style_name: str | None = None

    font_family: str | None = None
    font_size_pt: float | None = None
    bold: bool | None = None
    italic: bool | None = None
    runs: list[TextRunData] = Field(default_factory=list)

    alignment: str | None = None
    first_line_indent_cm: float | None = None
    left_indent_cm: float | None = None
    right_indent_cm: float | None = None
    line_spacing: float | None = None
    space_before_pt: float | None = None
    space_after_pt: float | None = None
    keep_with_next: bool | None = None
    keep_together: bool | None = None
    page_break_before: bool | None = None

    has_line_break: bool = False
    has_page_break: bool = False
    has_column_break: bool = False
    has_section_break: bool = False

    has_inline_image: bool = False
    image_count: int = 0

    caption_kind: str | None = None
    caption_number: str | None = None
    caption_prefix: str | None = None
    caption_title: str | None = None

    table_index: int | None = None
    table_row_index: int | None = None
    table_column_index: int | None = None

    list_marker: str | None = None
    list_marker_type: str | None = None
    is_automatic_list: bool = False

    has_equation: bool = False
    equation_count: int = 0
    has_formula_like_image: bool = False
    is_standalone_equation: bool = False
    equation_number: str | None = None

    paragraph_type: ParagraphType = ParagraphType.UNKNOWN
    heading_level: int | None = None
    is_structural_heading: bool = False
    is_numbered_heading: bool = False
    logical_section: str | None = None


class ImageData(BaseModel):
    index: int
    paragraph_index: int | None = None
    width_cm: float | None = None
    height_cm: float | None = None
    width_px: int | None = None
    height_px: int | None = None
    extension: str | None = None
    is_inline: bool = True


class TableData(BaseModel):
    index: int
    rows_count: int
    columns_count: int
    paragraph_before_index: int | None = None
    paragraph_after_index: int | None = None
    title_paragraph_index: int | None = None
    has_header_row: bool = False
    width_cm: float | None = None
    alignment: str | None = None
    has_grid: bool | None = None
    border_color: str | None = None
    border_size: float | None = None
    has_cant_split_rows: bool | None = None
    repeats_header: bool | None = None
    empty_row_indexes: list[int] = Field(default_factory=list)
    enlarged_row_indexes: list[int] = Field(default_factory=list)
    cell_paragraphs: list[ParagraphData] = Field(default_factory=list)


class SectionData(BaseModel):
    """Данные об одной секции DOCX-документа."""

    index: int

    page_width_cm: float | None = None
    page_height_cm: float | None = None
    page_format: str | None = None
    page_orientation: str | None = None

    top_margin_cm: float | None = None
    bottom_margin_cm: float | None = None
    left_margin_cm: float | None = None
    right_margin_cm: float | None = None

    header_distance_cm: float | None = None
    footer_distance_cm: float | None = None
    header_text: str | None = None
    footer_text: str | None = None
    has_header: bool = False
    has_footer: bool = False
    has_page_number: bool = False
    has_footer_page_number: bool = False
    has_first_page_page_number: bool = False
    first_page_has_page_number: bool | None = None
    has_first_page_footer_page_number: bool = False
    page_number_area: str | None = None
    page_number_alignment: str | None = None
    first_page_page_number_area: str | None = None
    page_number_start: int | None = None
    page_number_restart: bool = False
    different_first_page_header_footer: bool = False


class ParsedDocxDocument(BaseModel):
    """Внутреннее представление DOCX-документа после разбора."""

    file_path: str
    paragraphs: list[ParagraphData] = Field(default_factory=list)
    sections: list[SectionData] = Field(default_factory=list)
    images: list[ImageData] = Field(default_factory=list)
    tables: list[TableData] = Field(default_factory=list)
    footnotes: list[ParagraphData] = Field(default_factory=list)
    has_footnotes_part: bool = False
    footnote_number_format: str | None = None
    footnote_number_restart: str | None = None
