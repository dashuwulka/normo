from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
import re
from xml.etree import ElementTree as ET
from zipfile import ZIP_DEFLATED, ZipFile

from app.models.violation import Violation


W_NS = "http://schemas.openxmlformats.org/wordprocessingml/2006/main"
R_NS = "http://schemas.openxmlformats.org/officeDocument/2006/relationships"
REL_NS = "http://schemas.openxmlformats.org/package/2006/relationships"
CT_NS = "http://schemas.openxmlformats.org/package/2006/content-types"
COMMENTS_REL_TYPE = (
    "http://schemas.openxmlformats.org/officeDocument/2006/relationships/comments"
)
COMMENTS_CONTENT_TYPE = (
    "application/vnd.openxmlformats-officedocument.wordprocessingml.comments+xml"
)


ET.register_namespace("w", W_NS)
ET.register_namespace("r", R_NS)


def _qn(namespace: str, tag: str) -> str:
    return f"{{{namespace}}}{tag}"


def _read_xml(zip_file: ZipFile, name: str) -> ET.Element:
    return ET.fromstring(zip_file.read(name))


def _xml_bytes(root: ET.Element) -> bytes:
    return ET.tostring(root, encoding="utf-8", xml_declaration=True)


def _get_or_create_comments_root(zip_file: ZipFile) -> tuple[ET.Element, int]:
    if "word/comments.xml" not in zip_file.namelist():
        root = ET.Element(_qn(W_NS, "comments"))
        return root, 0

    root = _read_xml(zip_file, "word/comments.xml")
    max_id = -1
    for comment in root.findall(_qn(W_NS, "comment")):
        value = comment.get(_qn(W_NS, "id"))
        if value is not None and value.isdigit():
            max_id = max(max_id, int(value))

    return root, max_id + 1


def _ensure_comments_relationship(rels_root: ET.Element) -> None:
    for relationship in rels_root.findall(_qn(REL_NS, "Relationship")):
        if relationship.get("Type") == COMMENTS_REL_TYPE:
            return

    used_ids = []
    for relationship in rels_root.findall(_qn(REL_NS, "Relationship")):
        rel_id = relationship.get("Id", "")
        if rel_id.startswith("rId") and rel_id[3:].isdigit():
            used_ids.append(int(rel_id[3:]))

    next_id = max(used_ids, default=0) + 1
    ET.SubElement(
        rels_root,
        _qn(REL_NS, "Relationship"),
        {
            "Id": f"rId{next_id}",
            "Type": COMMENTS_REL_TYPE,
            "Target": "comments.xml",
        },
    )


def _ensure_comments_content_type(content_types_root: ET.Element) -> None:
    for override in content_types_root.findall(_qn(CT_NS, "Override")):
        if override.get("PartName") == "/word/comments.xml":
            return

    ET.SubElement(
        content_types_root,
        _qn(CT_NS, "Override"),
        {
            "PartName": "/word/comments.xml",
            "ContentType": COMMENTS_CONTENT_TYPE,
        },
    )


_TECHNICAL_TOKENS = (
    "line_spacing",
    "first_line_indent",
    "left_indent",
    "right_indent",
    "keep_with_next",
    "keep_together",
    "tblHeader",
    "not set",
)

_READABLE_REPLACEMENTS = {
    "line_spacing": "межстрочный интервал",
    "first_line_indent": "абзацный отступ",
    "left_indent": "левый отступ",
    "right_indent": "правый отступ",
    "keep_with_next": "не отрывать от следующего",
    "keep_together": "не разрывать абзац",
    "tblHeader": "повторять строку с названиями столбцов",
    "center": "по центру",
    "justify": "по ширине",
    "left": "по левому краю",
    "right": "по правому краю",
    "000000": "чёрный",
    "True": "да",
    "False": "нет",
    "None": "не задано",
    "not set": "не задано",
}


def _is_technical_value(value: str | None) -> bool:
    if not value:
        return False
    text = value.lower()
    return any(token in text for token in _TECHNICAL_TOKENS)


def _strip_duplicate_section_prefix(message: str, section: str | None) -> str:
    if not message:
        return message
    if section and message.lstrip().lower().startswith(f"раздел {section.lower()}:"):
        message = message.lstrip()[len(f"Раздел {section}:"):].lstrip()
    # В старых сообщениях чекеров мог оставаться номер раздела встроенного ГОСТа
    # ("Раздел 11.3: ..."). В review показываем источник из профиля, поэтому
    # второй номер внутри текста только путает пользователя.
    message = re.sub(r"^\s*Раздел\s+[\d.]+:\s*", "", message, flags=re.IGNORECASE)
    for technical, readable in _READABLE_REPLACEMENTS.items():
        message = message.replace(technical, readable)
    return message


def _normalize_review_message(message: str, section: str | None) -> str:
    if not message:
        return message

    stripped = message.lstrip()
    if section and stripped.lower().startswith(f"раздел {section.lower()}:"):
        stripped = stripped[len(f"Раздел {section}:"):].lstrip()

    stripped = re.sub(r"^\s*(?:Раздел|Р Р°Р·РґРµР»)\s+[\d.]+:\s*", "", stripped, flags=re.IGNORECASE)
    for technical, readable in _READABLE_REPLACEMENTS.items():
        stripped = stripped.replace(technical, readable)
    return stripped


def _comment_line(violation: Violation) -> str:
    section = violation.source_section
    severity = "Предупреждение" if violation.severity == "warning" else "Ошибка"
    message = _normalize_review_message(violation.message or "", section)

    prefix = f"{severity}. §{section}: " if section else f"{severity}. "
    return f"{prefix}{message}"


def _table_comment_message(violation: Violation) -> str:
    message = _normalize_review_message(violation.message or "", violation.source_section)
    message = re.sub(
        r"(?:Таблица|Table)\s+\d+(?:,\s*строка\s+\d+,\s*ячейка\s+\d+)?\s*:\s*",
        "",
        message,
        flags=re.IGNORECASE,
    )
    message = re.sub(
        r"(?:Таблица|Table)\s+\d+(?:,\s*строка\s+\d+,\s*ячейка\s+\d+)?\s*:\s*",
        "",
        message,
        flags=re.IGNORECASE,
    )
    message = re.sub(r"\bв\s+\d+\s+ячейках\b", "", message, flags=re.IGNORECASE)
    message = re.sub(r"\bячейк[аеиоуы]?\b", "", message, flags=re.IGNORECASE)
    message = re.sub(r"\bстрока\s+\d+\b", "", message, flags=re.IGNORECASE)
    message = re.sub(r"\s{2,}", " ", message).strip(" .,:;")
    message = re.sub(r"\s{2,}", " ", message).strip()
    return message


def _table_comment_text(violations: list[Violation]) -> str:
    grouped: dict[tuple[str | None, str, str], dict[str, object]] = {}

    for violation in violations:
        severity = "Предупреждение" if violation.severity == "warning" else "Ошибка"
        section = violation.source_section
        key = (section, severity, violation.rule_id)
        entry = grouped.setdefault(
            key,
            {
                "message": _table_comment_message(violation),
                "count": 0,
            },
        )
        entry["count"] = int(entry["count"]) + 1

    lines: list[str] = []
    for (section, severity, _rule_id), entry in grouped.items():
        message = str(entry["message"]).rstrip(".")
        count = int(entry["count"])
        if count > 1:
            message = re.split(r"(?<=\.)\s+", message, maxsplit=1)[0].rstrip(".")
            message = f"{message}. Найдено {count} нарушений такого типа в таблице"
        prefix = f"{severity}. В§{section}: " if section else f"{severity}. "
        lines.append(f"{prefix}{message}.")

    return "\n".join(lines)


def _comment_text(violations: list[Violation]) -> str:
    table_indexes = {_table_index_from_violation(violation) for violation in violations}
    if violations and None not in table_indexes:
        return _table_comment_text(violations)
    return "\n".join(_comment_line(violation) for violation in violations)


def _append_comment(comments_root: ET.Element, comment_id: int, violations: list[Violation]) -> None:
    comment = ET.SubElement(
        comments_root,
        _qn(W_NS, "comment"),
        {
            _qn(W_NS, "id"): str(comment_id),
            _qn(W_NS, "author"): "NormControl",
            _qn(W_NS, "initials"): "NC",
            _qn(W_NS, "date"): datetime.now(timezone.utc).isoformat(),
        },
    )
    paragraph = ET.SubElement(comment, _qn(W_NS, "p"))
    for index, line in enumerate(_comment_text(violations).splitlines()):
        if index:
            break_run = ET.SubElement(paragraph, _qn(W_NS, "r"))
            ET.SubElement(break_run, _qn(W_NS, "br"))
        run = ET.SubElement(paragraph, _qn(W_NS, "r"))
        text = ET.SubElement(run, _qn(W_NS, "t"))
        text.text = line


def _insert_comment_reference(paragraph: ET.Element, comment_id: int) -> None:
    start = ET.Element(_qn(W_NS, "commentRangeStart"), {_qn(W_NS, "id"): str(comment_id)})
    end = ET.Element(_qn(W_NS, "commentRangeEnd"), {_qn(W_NS, "id"): str(comment_id)})
    reference_run = ET.Element(_qn(W_NS, "r"))
    reference = ET.SubElement(
        reference_run,
        _qn(W_NS, "commentReference"),
        {_qn(W_NS, "id"): str(comment_id)},
    )

    insert_index = 0
    if len(paragraph) and paragraph[0].tag == _qn(W_NS, "pPr"):
        insert_index = 1

    paragraph.insert(insert_index, start)
    paragraph.append(end)
    paragraph.append(reference_run)


def _paragraph_for_violation(
    paragraphs: list[ET.Element],
    violation: Violation,
    table_anchors: dict[int, ET.Element],
) -> ET.Element | None:
    if not paragraphs:
        return None

    table_index = _table_index_from_violation(violation)
    if table_index is not None and table_index in table_anchors:
        return table_anchors[table_index]
    if table_index is not None and table_index - 1 in table_anchors:
        return table_anchors[table_index - 1]

    if (
        violation.paragraph_index is not None
        and 0 <= violation.paragraph_index < len(paragraphs)
    ):
        return paragraphs[violation.paragraph_index]

    return paragraphs[0]


def _table_index_from_violation(violation: Violation) -> int | None:
    if (
        violation.target == "table_cell"
        or violation.target == "table"
        or violation.parameter.startswith("table_")
        or violation.rule_id.startswith("table_")
    ):
        search_text = f"{violation.location} {violation.message}"
        match = re.search(r"(?:Таблица|Table)\s+(\d+)", search_text)
        if match is None:
            match = re.search(r"(?:Таблица|Table)\s+(\d+)", search_text)
        if match:
            number = int(match.group(1))
            return number - 1 if number > 0 else 0

    return None


def _table_anchor_paragraphs(body: ET.Element | None) -> dict[int, ET.Element]:
    if body is None:
        return {}

    children = list(body)
    anchors: dict[int, ET.Element] = {}
    table_index = 0
    previous_paragraph: ET.Element | None = None
    previous_table_caption: ET.Element | None = None

    def paragraph_text(paragraph: ET.Element) -> str:
        return "".join(text.text or "" for text in paragraph.iter(_qn(W_NS, "t"))).strip()

    for child_index, child in enumerate(children):
        if child.tag == _qn(W_NS, "p"):
            previous_paragraph = child
            if re.match(r"^(?:Табл\.|Таблица)\s+\d+(?:\.\d+)*\b", paragraph_text(child), re.IGNORECASE):
                previous_table_caption = child
            continue

        if child.tag != _qn(W_NS, "tbl"):
            continue

        anchor = previous_table_caption or previous_paragraph
        if anchor is None:
            for next_child in children[child_index + 1:]:
                if next_child.tag == _qn(W_NS, "p"):
                    anchor = next_child
                    break

        if anchor is not None:
            anchors[table_index] = anchor

        previous_table_caption = None
        table_index += 1

    return anchors


def _table_anchor_indexes(
    paragraphs: list[ET.Element],
    table_anchors: dict[int, ET.Element],
) -> dict[int, int]:
    result: dict[int, int] = {}
    for table_index, anchor in table_anchors.items():
        try:
            result[paragraphs.index(anchor)] = table_index
        except ValueError:
            continue
    return result


def _group_violations_for_comments(
    violations: list[Violation],
    table_anchor_indexes: dict[int, int] | None = None,
) -> list[list[Violation]]:
    grouped: dict[tuple[str, int | None, int | None], list[Violation]] = {}
    table_anchor_indexes = table_anchor_indexes or {}
    for violation in violations:
        table_index = _table_index_from_violation(violation)
        if table_index is None and violation.paragraph_index in table_anchor_indexes:
            table_index = table_anchor_indexes[violation.paragraph_index]

        if table_index is not None:
            key = ("table", table_index, None)
        elif violation.paragraph_index is not None:
            key = ("paragraph", violation.paragraph_index, None)
        elif violation.section_index is not None:
            # Нарушения секции относятся к странице/полям/колонтитулам, а не к
            # конкретному абзацу. Если ставить их в первый абзац, Word визуально
            # помечает титульный лист, что выглядит как ложная ошибка титула.
            continue
        else:
            continue
        grouped.setdefault(key, []).append(violation)

    return list(grouped.values())


def create_review_docx(
    input_path: str | Path,
    output_path: str | Path,
    violations: list[Violation],
) -> Path:
    """
    Создаёт отдельную DOCX-копию с комментариями Word по найденным нарушениям.

    Исходный документ не изменяется. Комментарии записываются напрямую в XML DOCX,
    потому что python-docx не поддерживает создание comments API.
    """

    input_path = Path(input_path)
    output_path = Path(output_path)
    output_path.parent.mkdir(parents=True, exist_ok=True)

    with ZipFile(input_path, "r") as source:
        document_root = _read_xml(source, "word/document.xml")
        rels_root = _read_xml(source, "word/_rels/document.xml.rels")
        content_types_root = _read_xml(source, "[Content_Types].xml")
        comments_root, next_comment_id = _get_or_create_comments_root(source)

        body = document_root.find(_qn(W_NS, "body"))
        paragraphs = body.findall(_qn(W_NS, "p")) if body is not None else []
        table_anchors = _table_anchor_paragraphs(body)
        anchor_indexes = _table_anchor_indexes(paragraphs, table_anchors)

        for violation_group in _group_violations_for_comments(violations, anchor_indexes):
            paragraph = _paragraph_for_violation(
                paragraphs,
                violation_group[0],
                table_anchors,
            )
            if paragraph is None:
                continue

            comment_id = next_comment_id
            next_comment_id += 1
            _append_comment(comments_root, comment_id, violation_group)
            _insert_comment_reference(paragraph, comment_id)

        _ensure_comments_relationship(rels_root)
        _ensure_comments_content_type(content_types_root)

        replaced = {
            "word/document.xml",
            "word/_rels/document.xml.rels",
            "[Content_Types].xml",
            "word/comments.xml",
        }

        with ZipFile(output_path, "w", compression=ZIP_DEFLATED) as target:
            for item in source.infolist():
                if item.filename in replaced:
                    continue
                target.writestr(item, source.read(item.filename))

            target.writestr("word/document.xml", _xml_bytes(document_root))
            target.writestr("word/_rels/document.xml.rels", _xml_bytes(rels_root))
            target.writestr("[Content_Types].xml", _xml_bytes(content_types_root))
            target.writestr("word/comments.xml", _xml_bytes(comments_root))

    return output_path
