import re
from collections.abc import Iterable

from app.extraction.models import NormativeFragment, NormativeStatement


SENTENCE_SPLIT_PATTERN = re.compile(r"(?<=[.!?])\s+(?=[А-ЯЁA-Z])")
CLAUSE_SPLIT_PATTERN = re.compile(r";\s+")
TABLE_CELL_SEPARATOR = " | "

MANDATORY_MARKERS = (
    "должен",
    "должна",
    "должно",
    "должны",
    "обязательно",
)
PROHIBITION_MARKERS = (
    "не допускается",
    "недопустимо",
    "запрещается",
    "не должны",
)
RECOMMENDED_MARKERS = (
    "рекомендуется",
    "следует",
    "желательно",
    "предпочтительно",
    "как правило",
)
ALLOWED_MARKERS = (
    "допускается",
    "допустимо",
    "можно",
    "разрешается",
    "может",
)


def _normalize_text(text: str) -> str:
    return " ".join(text.split())


def _statement_type_from_text(
    text: str,
    fragment_type: str,
) -> str:
    if fragment_type in {"note", "example"}:
        return fragment_type

    normalized = text.lower()

    if any(marker in normalized for marker in PROHIBITION_MARKERS):
        return "prohibition"

    if any(marker in normalized for marker in MANDATORY_MARKERS):
        return "requirement"

    if any(marker in normalized for marker in RECOMMENDED_MARKERS):
        return "recommendation"

    if any(marker in normalized for marker in ALLOWED_MARKERS):
        return "permission"

    if normalized.startswith(("если ", "при ", "в случае ")):
        return "condition"

    return "requirement"


def _modality_from_statement_type(
    statement_type: str,
    inherited_modality: str | None,
) -> str | None:
    if statement_type in {"requirement", "prohibition"}:
        return "mandatory"

    if statement_type == "recommendation":
        return "recommended"

    if statement_type == "permission":
        return "allowed"

    return inherited_modality


def _split_table_like_text(text: str) -> list[str]:
    if TABLE_CELL_SEPARATOR not in text:
        return [text]

    cells = [
        _normalize_text(cell).strip(" .")
        for cell in text.split(TABLE_CELL_SEPARATOR)
        if _normalize_text(cell).strip(" .")
    ]

    if len(cells) <= 1:
        return [text]

    context = cells[0]
    return [f"{context}: {cell}" for cell in cells[1:]]


def _split_atomic_text(text: str) -> list[str]:
    parts: list[str] = []

    for line in text.splitlines() or [text]:
        line = _normalize_text(line).strip()
        if not line:
            continue

        for table_part in _split_table_like_text(line):
            for sentence in SENTENCE_SPLIT_PATTERN.split(table_part):
                for clause in CLAUSE_SPLIT_PATTERN.split(sentence):
                    clause = _normalize_text(clause).strip(" .")
                    if clause:
                        parts.append(clause)

    return parts


def build_statements(
    fragments: Iterable[NormativeFragment],
) -> list[NormativeStatement]:
    statements: list[NormativeStatement] = []

    for fragment in fragments:
        for text in _split_atomic_text(fragment.text):
            statement_type = _statement_type_from_text(text, fragment.fragment_type)
            inherited_modality = _modality_from_statement_type(
                statement_type,
                fragment.inherited_modality,
            )
            statements.append(
                NormativeStatement(
                    text=text,
                    source_section=fragment.section_number,
                    parent_context=fragment.target_context or fragment.parent_context,
                    inherited_modality=inherited_modality,
                    statement_type=statement_type,
                )
            )

    return statements
