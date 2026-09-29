import re
from collections.abc import Iterable

from app.extraction.models import ExtractedRuleCandidate, NormativeFragment, NormativeStatement


MANDATORY_MARKERS = [
    "должен",
    "должна",
    "должно",
    "должны",
    "обязательно",
    "не допускается",
    "недопустимо",
    "не должны",
    "запрещается",
]
RECOMMENDED_MARKERS = [
    "рекомендуется",
    "как правило",
    "предпочтительно",
    "желательно",
    "следует",
]
ALLOWED_MARKERS = [
    "допускается",
    "можно",
    "разрешается",
    "может",
    "допустимо",
]


def _split_sentences(text: str) -> list[str]:
    sentences = re.split(r"(?<=[.!?])\s+", text.strip())
    return [sentence.strip() for sentence in sentences if sentence.strip()]


def _normalize(text: str) -> str:
    return " ".join(text.lower().split())


def _value_tokens(value) -> list[str]:
    if isinstance(value, list):
        return [str(item).replace(".", ",").lower() for item in value] + [
            str(item).lower() for item in value
        ]

    return [str(value).replace(".", ",").lower(), str(value).lower()]


def _sentence_contains_candidate_value(
    sentence: str,
    candidate: ExtractedRuleCandidate,
) -> bool:
    normalized_sentence = _normalize(sentence)

    for token in _value_tokens(candidate.value):
        token = _normalize(token)
        if token and token in normalized_sentence:
            return True

    if candidate.parameter in normalized_sentence:
        return True

    return False


def _find_candidate_sentence(candidate: ExtractedRuleCandidate) -> str:
    sentences = _split_sentences(candidate.source_text)

    for sentence in sentences:
        if _sentence_contains_candidate_value(sentence, candidate):
            return sentence

    return candidate.source_text


def _contains_marker(text: str, markers: list[str]) -> bool:
    normalized = _normalize(text)
    return any(marker in normalized for marker in markers)


def _detect_sentence_modality(sentence: str) -> str | None:
    has_mandatory = _contains_marker(sentence, MANDATORY_MARKERS)
    has_recommended = _contains_marker(sentence, RECOMMENDED_MARKERS)
    has_allowed = _contains_marker(sentence, ALLOWED_MARKERS)

    detected = [
        modality
        for modality, present in (
            ("mandatory", has_mandatory),
            ("recommended", has_recommended),
            ("allowed", has_allowed),
        )
        if present
    ]

    if len(detected) != 1:
        return None

    return detected[0]


def detect_modality(
    candidates: Iterable[ExtractedRuleCandidate],
    fragments: Iterable[NormativeFragment | NormativeStatement],
) -> list[ExtractedRuleCandidate]:
    """Detect rule modality for extracted candidates from their source sentence."""

    _ = fragments
    updated_candidates: list[ExtractedRuleCandidate] = []

    for candidate in candidates:
        if candidate.modality != "unknown":
            updated_candidates.append(candidate)
            continue

        sentence = _find_candidate_sentence(candidate)
        modality = _detect_sentence_modality(sentence)

        if modality is None:
            updated_candidates.append(
                candidate.model_copy(
                    update={
                        "modality": "unknown",
                        "status": "needs_review",
                        "explanation": (
                            "не удалось однозначно определить модальность требования"
                        ),
                    }
                )
            )
            continue

        updated_candidates.append(candidate.model_copy(update={"modality": modality}))

    return updated_candidates
