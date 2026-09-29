import re
from collections.abc import Iterable
from typing import Any

from app.extraction.models import (
    ExtractedRuleCandidate,
    NormativeFragment,
    NormativeStatement,
)
from app.extraction.patterns import EXTRACTORS, SUPPORTED_PARAMETERS


RANGE_PATTERN = re.compile(
    r"(\d+(?:[.,]\d+)?)\s*[\u2013\u2014-]\s*(\d+(?:[.,]\d+)?)\s*(пт|пункт\w*|см|мм)?",
    re.IGNORECASE,
)
LIST_PATTERN = re.compile(
    r"(\d+(?:[.,]\d+)?)\s+(?:или|;)\s+(\d+(?:[.,]\d+)?)"
    r"|(\d+(?:[.,]\d+)?)\s+,\s+(\d+(?:[.,]\d+)?)",
    re.IGNORECASE,
)
RELATIVE_VALUE_PATTERN = re.compile(
    r"на\s+(\d+(?:[.,]\d+)?)\s*(пт|пункт\w*|см|мм)\s+(меньше|больше)",
    re.IGNORECASE,
)


def _normalize_text(text: str) -> str:
    return " ".join(text.split()).lower()


def _has_keyword(text: str, keywords: list[str]) -> bool:
    normalized = _normalize_text(text)
    return any(keyword.lower() in normalized for keyword in keywords)


PAGE_PARAMETERS = {
    "page_format",
    "page_orientation",
    "top_margin",
    "bottom_margin",
    "left_margin",
    "right_margin",
    "header_distance",
    "footer_distance",
}


def _detect_target(fragment: NormativeFragment, parameter: str | None = None) -> str | None:
    if parameter in PAGE_PARAMETERS:
        return "page"

    if fragment.target_context:
        return fragment.target_context

    normalized = _normalize_text(fragment.text)

    if any(keyword in normalized for keyword in ("заголов", "раздел", "подраздел")):
        return "heading"

    if "таблиц" in normalized:
        return "table_cell"

    if "подпис" in normalized or "рисун" in normalized:
        return "caption"

    if "сноск" in normalized:
        return "footnote"

    if "дополнительн" in normalized and "текст" in normalized:
        return None

    if (
        "основн" in normalized and "текст" in normalized
        or "весь текст" in normalized
        or "по всему тексту" in normalized
        or "текст работы" in normalized
        or "использовать шрифт" in normalized
    ):
        return "main_text"

    if any(keyword in normalized for keyword in ("страниц", "лист", "поле", "формат")):
        return "page"

    return None


def _looks_like_emphasis_statement(text: str) -> bool:
    normalized = _normalize_text(text)
    return any(
        marker in normalized
        for marker in (
            "выделение",
            "выделяются",
            "акцентировать внимание",
            "может использоваться",
            "может быть использован",
        )
    )


def _should_skip_extractor(
    fragment: NormativeFragment,
    extractor: dict[str, Any],
) -> bool:
    parameter = extractor["parameter"]
    text = fragment.text.lower()
    target = _detect_target(fragment, parameter)

    if parameter in {"bold", "italic"}:
        if _looks_like_emphasis_statement(text) and target not in {
            "heading",
            "section_heading",
            "structural_heading",
            "subsection_heading",
            "point_heading",
            "appendix_heading",
        }:
            return True

    if parameter == "italic" and target in {"main_text", None}:
        return True

    if parameter == "bold" and target in {"main_text", "page", None}:
        return True

    return False


def _to_number(value: str) -> float:
    return float(value.replace(",", "."))


def _convert_length_to_cm(value: float, unit: str | None) -> float:
    if unit and unit.lower() == "мм":
        return value / 10

    return value


def _map_value(raw_value: str, value_map: dict[str, Any]) -> Any:
    normalized = _normalize_text(raw_value)

    if normalized.startswith(("черн", "чёрн")):
        return "000000"

    if normalized in value_map:
        return value_map[normalized]

    for key, value in value_map.items():
        if normalized.startswith(key.lower()):
            return value

    if normalized.startswith("полуторн"):
        return 1.5

    if normalized.startswith("одинарн"):
        return 1.0

    if normalized.startswith("центрирован"):
        return "center"

    return raw_value


def _coerce_value(match: re.Match[str], extractor: dict[str, Any]) -> Any:
    value_type = extractor["value_type"]

    if value_type == "constant":
        return extractor["value"]

    if value_type == "number":
        return _to_number(match.group(1))

    if value_type == "string":
        return match.group(1)

    if value_type == "length_cm":
        value = _to_number(match.group(1))
        unit = match.group(2) if match.lastindex and match.lastindex >= 2 else None
        return _convert_length_to_cm(value, unit)

    if value_type in {"mapped_number", "mapped_string"}:
        raw_value = match.group(1)
        value_map = extractor.get("value_map", {})
        mapped = _map_value(raw_value, value_map)
        if value_type == "mapped_number" and isinstance(mapped, str):
            return _to_number(mapped)
        return mapped

    return match.group(1)


def _candidate_status(
    parameter: str,
    target: str | None,
) -> tuple[str, float, str]:
    if parameter not in SUPPORTED_PARAMETERS:
        return (
            "unsupported",
            0.35,
            "параметр пока не поддерживается автоматической проверкой",
        )

    if target is None:
        return (
            "needs_review",
            0.5,
            "не удалось определить, к чему относится правило",
        )

    return "extracted", 0.8, "кандидат извлечён автоматически"


def _make_candidate(
    fragment: NormativeFragment,
    source_document: str,
    extractor: dict[str, Any],
    operator: str,
    value: Any,
    status: str | None = None,
    confidence: float | None = None,
    explanation: str | None = None,
    target: str | None = None,
    relative_to: dict[str, Any] | None = None,
) -> ExtractedRuleCandidate:
    parameter = extractor["parameter"]
    target = target or _detect_target(fragment, parameter)
    default_status, default_confidence, default_explanation = _candidate_status(
        parameter,
        target,
    )

    if default_status == "unsupported":
        status = default_status
        confidence = default_confidence
        explanation = default_explanation

    return ExtractedRuleCandidate(
        target=target,
        parameter=parameter,
        operator=operator,
        value=value,
        unit=extractor.get("unit"),
        modality=fragment.inherited_modality or "unknown",
        source_text=fragment.text,
        source_section=fragment.section_number,
        source_document=source_document,
        confidence=confidence if confidence is not None else default_confidence,
        status=status or default_status,
        explanation=explanation or default_explanation,
        relative_to=relative_to,
    )


def _make_direct_candidate(
    fragment: NormativeFragment,
    source_document: str,
    parameter: str,
    operator: str,
    value: Any,
    unit: str | None = None,
    target: str | None = None,
    status: str | None = None,
    confidence: float | None = None,
    explanation: str | None = None,
) -> ExtractedRuleCandidate:
    extractor = {"parameter": parameter, "unit": unit}
    return _make_candidate(
        fragment,
        source_document,
        extractor,
        operator,
        value,
        target=target,
        status=status,
        confidence=confidence,
        explanation=explanation,
    )


def _number_from_match(match: re.Match[str], group: int = 1, default_unit: str = "см") -> float:
    value = _to_number(match.group(group))
    unit = match.group(group + 1) if match.lastindex and match.lastindex >= group + 1 else default_unit
    return _convert_length_to_cm(value, unit or default_unit)


def _extract_margin_candidates(
    fragment: NormativeFragment,
    source_document: str,
) -> list[ExtractedRuleCandidate]:
    text = fragment.text.lower()
    if "отступ" in text and "пол" not in text and fragment.target_context != "page":
        return []

    if (
        "пол" not in text
        and "части страницы" not in text
        and not re.search(r"\b(?:сверху|снизу|слева|справа)\b[^0-9]{0,80}[—–-]\s*\d", text)
        and fragment.target_context != "page"
    ):
        return []

    candidates: list[ExtractedRuleCandidate] = []
    paired_before = re.search(
        r"(\d+(?:[.,]\d+)?)\s*(см|мм)?\s*[—–-]\s*в\s+верхн\w+\s+и\s+нижн\w+\s+част[иья]\s+страниц",
        text,
        re.IGNORECASE,
    )
    if paired_before:
        value = _number_from_match(paired_before)
        candidates.append(_make_direct_candidate(fragment, source_document, "top_margin", "equals", value, "cm", target="page"))
        candidates.append(_make_direct_candidate(fragment, source_document, "bottom_margin", "equals", value, "cm", target="page"))

    value_before_side_patterns = {
        "left_margin": r"(\d+(?:[.,]\d+)?)\s*(см|мм)?\s*[—–-]\s*в\s+лев\w+\s+част[иья]\s+страниц",
        "right_margin": r"(\d+(?:[.,]\d+)?)\s*(см|мм)?\s*[—–-]\s*в\s+прав\w+\s+част[иья]\s+страниц",
        "top_margin": r"(\d+(?:[.,]\d+)?)\s*(см|мм)?\s*[—–-]\s*в\s+верхн\w+\s+част[иья]\s+страниц",
        "bottom_margin": r"(\d+(?:[.,]\d+)?)\s*(см|мм)?\s*[—–-]\s*в\s+нижн\w+\s+част[иья]\s+страниц",
    }
    for parameter, pattern in value_before_side_patterns.items():
        match = re.search(pattern, text, re.IGNORECASE)
        if match:
            candidates.append(
                _make_direct_candidate(
                    fragment,
                    source_document,
                    parameter,
                    "equals",
                    _number_from_match(match),
                    "cm",
                    target="page",
                )
            )

    top_bottom = re.search(
        r"сверху\s*,\s*снизу\s*[—–-]\s*(\d+(?:[.,]\d+)?)\s*(см|мм)?",
        text,
        re.IGNORECASE,
    )
    if top_bottom:
        value = _number_from_match(top_bottom)
        candidates.append(_make_direct_candidate(fragment, source_document, "top_margin", "equals", value, "cm", target="page"))
        candidates.append(_make_direct_candidate(fragment, source_document, "bottom_margin", "equals", value, "cm", target="page"))

    side_patterns = {
        "left_margin": r"\bслева[^—–-]*[—–-]\s*(\d+(?:[.,]\d+)?)\s*(см|мм)?",
        "right_margin": r"\bсправа[^—–-]*[—–-]\s*(\d+(?:[.,]\d+)?)\s*(см|мм)?",
        "top_margin": r"(?:сверху|верхн\w*)[^—–-]*[—–-]\s*(\d+(?:[.,]\d+)?)\s*(см|мм)?",
        "bottom_margin": r"(?:снизу|нижн\w*)[^—–-]*[—–-]\s*(\d+(?:[.,]\d+)?)\s*(см|мм)?",
    }
    for parameter, pattern in side_patterns.items():
        match = re.search(pattern, text, re.IGNORECASE)
        if match:
            candidates.append(
                _make_direct_candidate(
                    fragment,
                    source_document,
                    parameter,
                    "equals",
                    _number_from_match(match),
                    "cm",
                    target="page",
                )
            )

    return _deduplicate_candidates(candidates)


def _extract_spacing_candidates(
    fragment: NormativeFragment,
    source_document: str,
) -> list[ExtractedRuleCandidate]:
    text = fragment.text.lower()
    if "интервал" not in text:
        return []

    candidates: list[ExtractedRuleCandidate] = []
    if "межстроч" in text or "междустроч" in text or "интерлиньяж" in text:
        if re.search(r"\bполуторн\w*", text):
            candidates.append(_make_direct_candidate(fragment, source_document, "line_spacing", "equals", 1.5))
        elif re.search(r"\bодинарн\w*", text):
            candidates.append(_make_direct_candidate(fragment, source_document, "line_spacing", "equals", 1.0))

    before_after = re.search(r"перед\s+и\s+после\s*[—–-]\s*(\d+(?:[.,]\d+)?)", text)
    if before_after:
        value = _to_number(before_after.group(1))
        candidates.append(_make_direct_candidate(fragment, source_document, "space_before", "equals", value, "pt"))
        candidates.append(_make_direct_candidate(fragment, source_document, "space_after", "equals", value, "pt"))

    before = re.search(r"перед\s*[—–-]\s*(\d+(?:[.,]\d+)?)", text)
    after = re.search(r"после\s*[—–-]\s*(\d+(?:[.,]\d+)?)", text)
    if before:
        candidates.append(_make_direct_candidate(fragment, source_document, "space_before", "equals", _to_number(before.group(1)), "pt"))
    if after:
        candidates.append(_make_direct_candidate(fragment, source_document, "space_after", "equals", _to_number(after.group(1)), "pt"))

    return _deduplicate_candidates(candidates)


def _extract_indent_candidates(
    fragment: NormativeFragment,
    source_document: str,
) -> list[ExtractedRuleCandidate]:
    text = fragment.text.lower()
    if "отступ" not in text:
        return []

    candidates: list[ExtractedRuleCandidate] = []
    target = _detect_target(fragment)
    if target == "table_cell" and re.search(r"(?:без|нет)\s+\w*\s*отступ", text):
        candidates.append(_make_direct_candidate(fragment, source_document, "first_line_indent", "equals", 0, "cm", target="table_cell"))
        candidates.append(_make_direct_candidate(fragment, source_document, "left_indent", "equals", 0, "cm", target="table_cell"))
        candidates.append(_make_direct_candidate(fragment, source_document, "right_indent", "equals", 0, "cm", target="table_cell"))

    first_none = re.search(r"отступ\s+первой\s+строки\s*[—–-]\s*(нет|0)", text)
    if first_none:
        candidates.append(_make_direct_candidate(fragment, source_document, "first_line_indent", "equals", 0, "cm"))

    left = re.search(r"отступ\s+слева\s*[—–-]\s*(\d+(?:[.,]\d+)?)\s*(см|мм)?", text)
    if left:
        candidates.append(
            _make_direct_candidate(
                fragment,
                source_document,
                "left_indent",
                "equals",
                _number_from_match(left),
                "cm",
            )
        )

    return candidates


def _extract_contextual_font_size_candidates(
    fragment: NormativeFragment,
    source_document: str,
) -> list[ExtractedRuleCandidate]:
    text = fragment.text.lower()
    if not (
        "кегль" in text
        or "размер шрифта" in text
        or "размером" in text
        or "шрифта" in text
    ):
        return []

    target = _detect_target(fragment, "font_size")
    list_match = re.search(
        r"(?:кегль|размер шрифта|шрифт)[^0-9]{0,40}(\d+(?:[.,]\d+)?)\s*(?:пт|пункт\w*)?\s*(?:или|/|,)\s*(\d+(?:[.,]\d+)?)\s*(?:пт|пункт\w*)?",
        text,
    )
    if list_match:
        return [
            _make_direct_candidate(
                fragment,
                source_document,
                "font_size",
                "in",
                [_to_number(list_match.group(1)), _to_number(list_match.group(2))],
                "pt",
                target=target,
            )
        ]

    match = re.search(r"[—–-]\s*(\d+(?:[.,]\d+)?)\s*(?:пт|пункт\w*)?\s*$", text)
    if not match:
        match = re.search(r"(?:кегль|размер шрифта)[^0-9]{0,40}(\d+(?:[.,]\d+)?)", text)
    if not match:
        return []

    return [
        _make_direct_candidate(
            fragment,
            source_document,
            "font_size",
            "equals",
            _to_number(match.group(1)),
            "pt",
            target=target,
        )
    ]


def _extract_boolean_candidates(
    fragment: NormativeFragment,
    source_document: str,
) -> list[ExtractedRuleCandidate]:
    text = fragment.text.lower()
    candidates: list[ExtractedRuleCandidate] = []
    if "не отрывать от следующего" in text:
        target = _detect_target(fragment, "keep_with_next")
        if target is None and (
            "заголов" in text
            or fragment.target_context in {
                "heading",
                "structural_heading",
                "section_heading",
                "subsection_heading",
                "point_heading",
                "appendix_heading",
            }
            or fragment.parent_context in {
                "heading",
                "structural_heading",
                "section_heading",
                "subsection_heading",
                "point_heading",
                "appendix_heading",
            }
        ):
            target = "heading"
        candidates.append(_make_direct_candidate(fragment, source_document, "keep_with_next", "equals", True, target=target))
    if "не разрывать" in text:
        candidates.append(_make_direct_candidate(fragment, source_document, "keep_together", "equals", True))
    if "начинать с новой страницы" in text or "начинать с новой страницы" in text:
        target = _detect_target(fragment, "page_break_before")
        if target != "heading":
            candidates.append(_make_direct_candidate(fragment, source_document, "page_break_before", "equals", True))
    return candidates


def _deduplicate_candidates(candidates: list[ExtractedRuleCandidate]) -> list[ExtractedRuleCandidate]:
    seen: set[tuple[str | None, str, str, str]] = set()
    result: list[ExtractedRuleCandidate] = []
    for candidate in candidates:
        key = (candidate.target, candidate.parameter, candidate.operator, str(candidate.value))
        if key in seen:
            continue
        seen.add(key)
        result.append(candidate)
    return result


def _extract_relative_candidate(
    fragment: NormativeFragment,
    source_document: str,
    extractor: dict[str, Any],
) -> ExtractedRuleCandidate | None:
    match = RELATIVE_VALUE_PATTERN.search(fragment.text)
    if not match:
        return None

    return _make_candidate(
        fragment=fragment,
        source_document=source_document,
        extractor=extractor,
        operator="equals",
        value=match.group(0),
        status="unsupported",
        confidence=0.45,
        explanation=(
            "относительное значение найдено, но пока не превращается "
            "в автоматически проверяемое правило"
        ),
        relative_to={
            "target": "main_text",
            "parameter": extractor["parameter"],
            "delta": -_to_number(match.group(1)) if match.group(3).lower().startswith("меньше") else _to_number(match.group(1)),
            "unit": match.group(2),
        },
    )


def _extract_range_candidates(
    fragment: NormativeFragment,
    source_document: str,
    extractor: dict[str, Any],
) -> list[ExtractedRuleCandidate]:
    if extractor["value_type"] not in {"number", "length_cm"}:
        return []
    if extractor["parameter"] == "font_size" and "уровн" in fragment.text.lower():
        return []

    match = RANGE_PATTERN.search(fragment.text)
    if not match:
        return []

    first = _to_number(match.group(1))
    second = _to_number(match.group(2))
    unit = match.group(3)

    if extractor["value_type"] == "length_cm":
        first = _convert_length_to_cm(first, unit)
        second = _convert_length_to_cm(second, unit)

    minimum, maximum = sorted((first, second))

    return [
        _make_candidate(fragment, source_document, extractor, "min", minimum),
        _make_candidate(fragment, source_document, extractor, "max", maximum),
    ]


def _extract_list_candidate(
    fragment: NormativeFragment,
    source_document: str,
    extractor: dict[str, Any],
) -> ExtractedRuleCandidate | None:
    if extractor["value_type"] not in {"number", "mapped_number"}:
        return None

    match = LIST_PATTERN.search(fragment.text)
    if not match:
        return None

    first = match.group(1) or match.group(3)
    second = match.group(2) or match.group(4)
    values = [_to_number(first), _to_number(second)]

    if extractor["parameter"] == "line_spacing" and any(value > 3 for value in values):
        return None

    return _make_candidate(fragment, source_document, extractor, "in", values)


def extract_candidates(
    fragments: Iterable[NormativeFragment | NormativeStatement],
    source_document: str,
) -> list[ExtractedRuleCandidate]:
    candidates: list[ExtractedRuleCandidate] = []

    for fragment in fragments:
        if fragment.fragment_type != "requirement":
            continue

        candidates.extend(_extract_margin_candidates(fragment, source_document))
        candidates.extend(_extract_spacing_candidates(fragment, source_document))
        candidates.extend(_extract_indent_candidates(fragment, source_document))
        candidates.extend(_extract_boolean_candidates(fragment, source_document))
        candidates.extend(_extract_contextual_font_size_candidates(fragment, source_document))

        for extractor in EXTRACTORS:
            if _should_skip_extractor(fragment, extractor):
                continue
            if extractor["parameter"] == "font_size" and "уровн" in fragment.text.lower():
                continue

            if not _has_keyword(fragment.text, extractor["keywords"]):
                continue

            if (
                extractor["parameter"] == "line_spacing"
                and ("перед" in fragment.text.lower() or "после" in fragment.text.lower())
                and "межстроч" not in fragment.text.lower()
                and "интерлиньяж" not in fragment.text.lower()
            ):
                continue

            if (
                extractor["parameter"] == "first_line_indent"
                and "отступ первой строки" in fragment.text.lower()
                and "нет" in fragment.text.lower()
            ):
                continue

            relative_candidate = _extract_relative_candidate(
                fragment,
                source_document,
                extractor,
            )
            if relative_candidate is not None:
                candidates.append(relative_candidate)
                continue

            range_candidates = _extract_range_candidates(
                fragment,
                source_document,
                extractor,
            )
            if range_candidates:
                candidates.extend(range_candidates)
                continue

            list_candidate = _extract_list_candidate(
                fragment,
                source_document,
                extractor,
            )
            if list_candidate is not None:
                candidates.append(list_candidate)
                continue

            value_pattern = re.compile(extractor["value_pattern"], re.IGNORECASE)
            match = value_pattern.search(fragment.text)
            if not match:
                continue

            value = _coerce_value(match, extractor)
            candidates.append(
                _make_candidate(
                    fragment=fragment,
                    source_document=source_document,
                    extractor=extractor,
                    operator=extractor["operator"],
                    value=value,
                )
            )

    return _deduplicate_candidates(candidates)
