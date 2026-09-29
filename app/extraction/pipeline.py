from collections.abc import Iterable
from typing import Any

from app.extraction.models import ExtractedRuleCandidate, NormativeFragment, NormativeStatement
from app.extraction.modality_detector import detect_modality
from app.extraction.parameter_extractor import extract_candidates
from app.extraction.presentation import candidate_rule_text
from app.extraction.segmenter import segment, split_into_fragments
from app.extraction.statement_builder import build_statements
from app.extraction.structure_extractor import extract_structure_candidates
from app.extraction.verifier import verify
from app.models.profile import Profile, Rule, RuleOrigin


def run_extraction(
    document_path: str,
    source_name: str,
) -> list[ExtractedRuleCandidate]:
    sections = segment(document_path)
    fragments: list[NormativeFragment] = []

    for section in sections:
        fragments.extend(split_into_fragments(section))

    statements: list[NormativeStatement] = build_statements(fragments)
    candidates = [
        *extract_candidates(statements, source_name),
        *extract_structure_candidates(statements, source_name),
    ]
    candidates = detect_modality(candidates, statements)
    candidates = verify(candidates)
    return candidates


def _rule_category_for_candidate(candidate: ExtractedRuleCandidate) -> str:
    if candidate.parameter in {
        "initial_verb_form",
        "completed_action_form",
        "forbidden_phrases",
    }:
        return "linguistic"

    if candidate.parameter in {
        "required_document_structure",
        "references_min_count",
        "introduction_required_content",
        "conclusion_required_content",
        "toc_headings_match_text",
        "heading_english_not_allowed",
        "front_matter_page_numbers_hidden_until_intro",
        "automatic_list_numbering_required",
        "list_punctuation_policy",
    }:
        return "structure"

    if candidate.parameter in {
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
    }:
        return "formatting" if (
            candidate.parameter.startswith("figure_caption_")
            or candidate.parameter.startswith("image_")
            or candidate.parameter.startswith("table_")
        ) else "text"

    if candidate.parameter in {
        "font_size",
        "font_family",
        "font_color",
        "bold",
        "italic",
        "alignment",
        "line_spacing",
        "first_line_indent",
        "left_indent",
        "right_indent",
        "space_before",
        "space_after",
        "keep_with_next",
        "keep_together",
        "page_break_before",
    }:
        return "formatting"

    if candidate.parameter in {
        "page_format",
        "page_orientation",
        "top_margin",
        "bottom_margin",
        "left_margin",
        "right_margin",
        "header_distance",
        "footer_distance",
    }:
        return "formatting"

    return "text"


def _rule_id_for_candidate(candidate: ExtractedRuleCandidate) -> str:
    parts = [
        "extracted",
        candidate.source_section or "unknown",
        candidate.target or "unknown",
        candidate.parameter,
        candidate.operator,
    ]
    return "_".join(
        str(part)
        .lower()
        .replace(".", "_")
        .replace(" ", "_")
        .replace("-", "_")
        for part in parts
    )


def _description_for_candidate(candidate: ExtractedRuleCandidate) -> str:
    return f"Извлечённое из методички правило: {candidate_rule_text(candidate)}"


def build_profile_from_confirmed(
    candidates: Iterable[ExtractedRuleCandidate],
    profile_meta: dict[str, Any],
) -> Profile:
    confirmed_candidates = [
        candidate
        for candidate in candidates
        if candidate.status == "confirmed"
        and candidate.target is not None
        and candidate.modality != "unknown"
    ]

    rules: list[Rule] = []
    for candidate in confirmed_candidates:
        rules.append(
            Rule(
                id=_rule_id_for_candidate(candidate),
                category=_rule_category_for_candidate(candidate),
                target=candidate.target,
                parameter=candidate.parameter,
                operator=candidate.operator,
                value=candidate.value,
                unit=candidate.unit,
                modality=candidate.modality,
                origin=RuleOrigin.EXTRACTED,
                description=_description_for_candidate(candidate),
                source_text=candidate.source_text,
                source_section=candidate.source_section,
                condition=candidate.condition,
                relative_to=candidate.relative_to,
            )
        )

    return Profile(
        id=profile_meta["id"],
        name=profile_meta["name"],
        source_name=profile_meta["source_name"],
        version=profile_meta.get("version"),
        description=profile_meta.get("description"),
        rules=rules,
    )
