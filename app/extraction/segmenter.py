import re
from collections.abc import Iterable, Sequence
from pathlib import Path
from typing import Pattern

from docx import Document
from docx.oxml.table import CT_Tbl
from docx.oxml.text.paragraph import CT_P
from docx.table import Table
from docx.text.paragraph import Paragraph

from app.extraction.models import NormativeBlock, NormativeFragment, NormativeSection


SECTION_NUMBER_PATTERN = re.compile(r"^\s*(\d+(?:\.\d+)+)\.?\s+\S")
TOP_LEVEL_SECTION_PATTERN = re.compile(r"^\s*(\d+)\.?\s+[А-ЯЁ]")
MARKER_EXAMPLE = re.compile(r"\b(Пример|Примеры|Например)\b[:.]?", re.IGNORECASE)
MARKER_NOTE = re.compile(r"\b(Примечание|Примечания)\b[:.]?", re.IGNORECASE)
LIST_MARKER_CHARS = "-\u2212\u2013\u2014\u2022\u25aa\u25ab\u2023\uf02d\uf076\uf0b7"
LIST_MARKER_PATTERN = re.compile(
    rf"^\s*([{re.escape(LIST_MARKER_CHARS)}]|\d+[).]|[\u0430-\u044f\u0410-\u042f][).])\s+"
)
TOC_DOT_LEADER_PATTERN = re.compile(r"(?:\.|\u2026|\xb7|\u22ef){3,}\s*\d+\s*$")
PAGE_NUMBER_PATTERN = re.compile(r"^\s*\d+\s*$")

DEFAULT_SECTION_PATTERNS: tuple[Pattern[str], ...] = (
    SECTION_NUMBER_PATTERN,
    TOP_LEVEL_SECTION_PATTERN,
)


def _normalize_text(text: str) -> str:
    return " ".join(text.split())


def _block_type_for_text(text: str) -> str:
    if PAGE_NUMBER_PATTERN.match(text):
        return "page_number"

    if TOC_DOT_LEADER_PATTERN.search(text):
        return "toc"

    if LIST_MARKER_PATTERN.match(text):
        return "list_item"

    return "paragraph"


def _list_marker_for_text(text: str) -> str | None:
    match = LIST_MARKER_PATTERN.match(text)
    return match.group(1) if match else None


def _read_docx_blocks(document_path: Path) -> list[NormativeBlock]:
    document = Document(document_path)
    blocks: list[NormativeBlock] = []

    for child in document.element.body.iterchildren():
        if isinstance(child, CT_P):
            paragraph = Paragraph(child, document)
            text = _normalize_text(paragraph.text)
            if text:
                blocks.append(
                    NormativeBlock(
                        index=len(blocks),
                        text=text,
                        source_document=document_path.name,
                        block_type=_block_type_for_text(text),
                        list_marker=_list_marker_for_text(text),
                    )
                )
            continue

        if isinstance(child, CT_Tbl):
            table = Table(child, document)
            for row in table.rows:
                cells = [_normalize_text(cell.text) for cell in row.cells]
                cells = [cell for cell in cells if cell]
                if cells:
                    text = " | ".join(cells)
                    blocks.append(
                        NormativeBlock(
                            index=len(blocks),
                            text=text,
                            source_document=document_path.name,
                            block_type="table_row",
                        )
                    )

    return blocks


def _span_is_bold(span: dict) -> bool | None:
    font_name = str(span.get("font", "")).lower()
    if not font_name:
        return None
    return "bold" in font_name or "semibold" in font_name or "black" in font_name


def _read_pdf_blocks(document_path: Path) -> list[NormativeBlock]:
    import fitz

    blocks: list[NormativeBlock] = []
    with fitz.open(document_path) as pdf_document:
        for page_index, page in enumerate(pdf_document, start=1):
            page_dict = page.get_text("dict")
            for raw_block in page_dict.get("blocks", []):
                if raw_block.get("type") != 0:
                    continue

                for line in raw_block.get("lines", []):
                    parts: list[str] = []
                    font_sizes: list[float] = []
                    bold_values: list[bool] = []

                    for span in line.get("spans", []):
                        span_text = span.get("text", "")
                        if span_text:
                            parts.append(span_text)
                        if span.get("size") is not None:
                            font_sizes.append(float(span["size"]))
                        span_bold = _span_is_bold(span)
                        if span_bold is not None:
                            bold_values.append(span_bold)

                    text = _normalize_text("".join(parts))
                    if not text:
                        continue

                    x0, y0, x1, y1 = line.get("bbox", (None, None, None, None))
                    blocks.append(
                        NormativeBlock(
                            index=len(blocks),
                            text=text,
                            source_document=document_path.name,
                            page_number=page_index,
                            block_type=_block_type_for_text(text),
                            x0=x0,
                            y0=y0,
                            x1=x1,
                            y1=y1,
                            font_size=max(font_sizes) if font_sizes else None,
                            bold=any(bold_values) if bold_values else None,
                            list_marker=_list_marker_for_text(text),
                        )
                    )

    return _drop_pdf_toc_pages(_merge_pdf_continuation_blocks(blocks))


def _drop_pdf_toc_pages(blocks: list[NormativeBlock]) -> list[NormativeBlock]:
    toc_pages = {
        block.page_number
        for block in blocks
        if block.page_number is not None
        and _normalize_text(block.text).lower() in {"оглавление", "содержание"}
    }
    if not toc_pages:
        return blocks

    result: list[NormativeBlock] = []
    for block in blocks:
        if block.page_number in toc_pages:
            continue
        block.index = len(result)
        result.append(block)
    return result


def _merge_pdf_continuation_blocks(blocks: list[NormativeBlock]) -> list[NormativeBlock]:
    merged: list[NormativeBlock] = []

    for block in blocks:
        if block.block_type in {"toc", "page_number"}:
            merged.append(block)
            continue

        if (
            merged
            and merged[-1].block_type == "paragraph"
            and block.block_type == "paragraph"
            and merged[-1].page_number == block.page_number
            and not _match_section_number(block.text, DEFAULT_SECTION_PATTERNS)
            and not merged[-1].text.endswith((".", ":", ";", "!", "?"))
        ):
            previous = merged[-1]
            separator = "" if previous.text.endswith("-") else " "
            previous.text = f"{previous.text.rstrip('-')}{separator}{block.text}"
            previous.y1 = block.y1
            continue

        block.index = len(merged)
        merged.append(block)

    return merged


def _read_document_blocks(document_path: Path) -> list[NormativeBlock]:
    suffix = document_path.suffix.lower()

    if suffix == ".docx":
        return _read_docx_blocks(document_path)

    if suffix == ".pdf":
        return _read_pdf_blocks(document_path)

    raise ValueError("Сегментация поддерживает только DOCX и PDF")


def _is_reference_or_footnote_block(block: NormativeBlock) -> bool:
    if block.font_size is None or block.font_size > 12.5:
        return False

    normalized = _normalize_text(block.text).lower()
    return bool(
        re.match(r"^\d+\s+", normalized)
        or normalized.startswith(("url", "http", "– url", "- url"))
        or "федер. агентство" in normalized
        or "регулированию и метрологии" in normalized
    )


def _read_docx_lines(document_path: Path) -> list[str]:
    return [
        block.text
        for block in _read_docx_blocks(document_path)
        if block.block_type not in {"toc", "page_number"}
    ]


def _read_pdf_lines(document_path: Path) -> list[str]:
    return [
        block.text
        for block in _read_pdf_blocks(document_path)
        if block.block_type not in {"toc", "page_number"}
    ]


def _read_document_lines(document_path: Path) -> list[str]:
    return [
        block.text
        for block in _read_document_blocks(document_path)
        if block.block_type not in {"toc", "page_number"}
    ]


def _match_section_number(
    text: str,
    section_patterns: Sequence[Pattern[str]],
) -> str | None:
    for pattern in section_patterns:
        match = pattern.match(text)
        if match:
            return match.group(1)

    return None


def _coerce_patterns(
    section_patterns: Iterable[str | Pattern[str]] | None,
) -> tuple[Pattern[str], ...]:
    if section_patterns is None:
        return DEFAULT_SECTION_PATTERNS

    return tuple(
        re.compile(pattern) if isinstance(pattern, str) else pattern
        for pattern in section_patterns
    )


def segment(
    document_path: str,
    section_patterns: Iterable[str | Pattern[str]] | None = None,
) -> list[NormativeSection]:
    """Split a normative DOCX or PDF document into numbered sections."""

    path = Path(document_path)
    patterns = _coerce_patterns(section_patterns)
    blocks = [
        block
        for block in _read_document_blocks(path)
        if block.block_type not in {"toc", "page_number"}
        and not _is_reference_or_footnote_block(block)
    ]

    sections: list[NormativeSection] = []
    current_number: str | None = None
    current_lines: list[str] = []

    for block in blocks:
        section_number = _match_section_number(block.text, patterns)

        if section_number is not None:
            if current_number is not None and current_lines:
                sections.append(
                    NormativeSection(
                        number=current_number,
                        text="\n".join(current_lines),
                        source_document=path.name,
                    )
                )

            current_number = section_number
            current_lines = [block.text]
            continue

        if current_number is None:
            continue

        current_lines.append(block.text)

    if current_number is not None and current_lines:
        sections.append(
            NormativeSection(
                number=current_number,
                text="\n".join(current_lines),
                source_document=path.name,
            )
        )

    return sections


def _find_fragment_markers(text: str) -> list[tuple[int, int, str]]:
    markers: list[tuple[int, int, str]] = []

    for match in MARKER_EXAMPLE.finditer(text):
        markers.append((match.start(), match.end(), "example"))

    for match in MARKER_NOTE.finditer(text):
        markers.append((match.start(), match.end(), "note"))

    return sorted(markers, key=lambda marker: marker[0])


def _strip_list_marker(text: str) -> str:
    return LIST_MARKER_PATTERN.sub("", text, count=1).strip()


def _context_from_text(text: str, current_context: str | None = None) -> str | None:
    normalized = text.lower()

    if "основн" in normalized and "текст" in normalized:
        return "main_text"
    if any(
        marker in normalized
        for marker in (
            "содержание",
            "введение",
            "заключение",
            "список источников",
            "список использованных источников",
            "приложения",
        )
    ) and "заголов" in normalized:
        return "structural_heading"
    if "структурн" in normalized and ("раздел" in normalized or "элемент" in normalized):
        return "structural_heading"
    if "формат страниц" in normalized or "поля" in normalized or "поле" in normalized:
        return "page"
    if "стил" in normalized and "заголов" in normalized:
        return "heading"
    if "заголов" in normalized and ("1-го" in normalized or "1 уровня" in normalized):
        return "section_heading"
    if "параграф" in normalized or ("заголов" in normalized and ("2-го" in normalized or "2 уровня" in normalized)):
        return "subsection_heading"
    if "пункт" in normalized or ("заголов" in normalized and ("3-го" in normalized or "3 уровня" in normalized)):
        return "point_heading"
    if "рисунк" in normalized or "подпис" in normalized:
        return "caption"
    if "таблиц" in normalized:
        return "table_cell"
    if "сноск" in normalized or "снос" in normalized:
        return "footnote"

    return current_context


def _modality_from_text(text: str, current_modality: str | None = None) -> str | None:
    normalized = text.lower()

    if any(marker in normalized for marker in ("должен", "должна", "должно", "должны", "не допускается", "недопустимо", "запрещается")):
        return "mandatory"
    if any(marker in normalized for marker in ("рекомендуется", "следует", "желательно", "предпочтительно")):
        return "recommended"
    if any(marker in normalized for marker in ("допускается", "можно", "разрешается", "допустимо")):
        return "allowed"

    return current_modality


def _split_requirement_text(
    text: str,
    section_number: str | None,
) -> list[NormativeFragment]:
    fragments: list[NormativeFragment] = []
    context: str | None = None
    context_prefix: str | None = None
    modality: str | None = None

    for raw_line in text.splitlines():
        has_list_marker = LIST_MARKER_PATTERN.match(raw_line) is not None
        line = _strip_list_marker(raw_line)
        if not line:
            continue

        line_context = _context_from_text(line, None)
        modality = _modality_from_text(line, modality)
        is_context_line = line.endswith(":") or line.endswith("):")
        if is_context_line:
            if line_context is not None:
                context = line_context
            context_prefix = line
            continue

        fragment_context = line_context or (context if has_list_marker else None)

        parts = [
            part.strip(" .")
            for part in re.split(r";(?=\s*[а-яА-ЯA-Z]|$)", line)
            if part.strip(" .")
        ]

        for part in parts:
            if part.lower().startswith(("неправильно", "правильно")):
                continue
            fragment_text = (
                f"{context_prefix}: {part}"
                if context_prefix and has_list_marker
                else part
            )
            fragments.append(
                NormativeFragment(
                    section_number=section_number,
                    fragment_type="requirement",
                    text=fragment_text,
                    target_context=fragment_context,
                    parent_context=fragment_context,
                    inherited_modality=modality,
                )
            )

    return fragments


def split_into_fragments(section: NormativeSection) -> list[NormativeFragment]:
    """Split one normative section into requirement, example, and note fragments."""

    text = section.text.strip()
    if not text:
        return []

    markers = _find_fragment_markers(text)
    fragments: list[NormativeFragment] = []

    if not markers:
        return _split_requirement_text(text, section.number)

    first_marker_start = markers[0][0]
    requirement_text = text[:first_marker_start].strip()
    if requirement_text:
        fragments.extend(_split_requirement_text(requirement_text, section.number))

    for index, (_start, marker_end, fragment_type) in enumerate(markers):
        next_start = markers[index + 1][0] if index + 1 < len(markers) else len(text)
        fragment_text = text[marker_end:next_start].strip()

        if not fragment_text:
            continue

        fragments.append(
            NormativeFragment(
                section_number=section.number,
                fragment_type=fragment_type,
                text=fragment_text,
            )
        )

    return fragments
