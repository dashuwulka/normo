from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any

from app.models.document import ParagraphData, ParagraphType, ParsedDocxDocument
from app.models.profile import Profile, Rule
from app.models.violation import Violation


LINGUISTIC_PARAMETERS = {
    "initial_verb_form",
    "completed_action_form",
    "forbidden_phrases",
}

TASK_INTRO_PATTERN = re.compile(
    r"(задач[аи]|следующие задачи|для достижения.+цели|необходимо решить)",
    re.IGNORECASE,
)
LIST_MARKER_PATTERN = re.compile(
    r"^\s*(?:[—–-]|\d+[).]|[а-яёa-z][).]|[•▪▫‣])\s+",
    re.IGNORECASE,
)
WORD_PATTERN = re.compile(r"[A-Za-zА-Яа-яЁё]+(?:-[A-Za-zА-Яа-яЁё]+)?")
FUTURE_OR_PLAN_PATTERN = re.compile(
    r"\b(будет|будут|планируется|предполагается|предстоит|будущий|будущая|будущее)\b",
    re.IGNORECASE,
)

COMPLETED_ACTION_WORDS = {
    "разработан",
    "разработана",
    "разработано",
    "разработаны",
    "реализован",
    "реализована",
    "реализовано",
    "реализованы",
    "проведен",
    "проведён",
    "проведена",
    "проведено",
    "проведены",
    "определен",
    "определён",
    "определена",
    "определено",
    "определены",
    "выявлен",
    "выявлена",
    "выявлено",
    "выявлены",
    "создан",
    "создана",
    "создано",
    "созданы",
    "предложен",
    "предложена",
    "предложено",
    "предложены",
    "выполнен",
    "выполнена",
    "выполнено",
    "выполнены",
}


@dataclass(frozen=True)
class MorphToken:
    text: str
    lemma: str
    pos: str | None = None
    feats: dict[str, Any] | None = None


class _MorphAnalyzer:
    def __init__(self) -> None:
        self.available = False
        self._segmenter = None
        self._morph_vocab = None
        self._morph_tagger = None
        self._doc_cls = None

        try:
            from natasha import Doc, MorphVocab, NewsEmbedding, NewsMorphTagger, Segmenter
        except ImportError:
            return

        self._segmenter = Segmenter()
        self._morph_vocab = MorphVocab()
        embedding = NewsEmbedding()
        self._morph_tagger = NewsMorphTagger(embedding)
        self._doc_cls = Doc
        self.available = True

    def analyze(self, text: str) -> list[MorphToken]:
        if not self.available:
            return [
                MorphToken(text=word, lemma=_rough_lemma(word))
                for word in WORD_PATTERN.findall(text)
            ]

        doc = self._doc_cls(text)
        doc.segment(self._segmenter)
        doc.tag_morph(self._morph_tagger)

        tokens: list[MorphToken] = []
        for token in doc.tokens:
            token.lemmatize(self._morph_vocab)
            if not WORD_PATTERN.fullmatch(token.text):
                continue
            tokens.append(
                MorphToken(
                    text=token.text,
                    lemma=(token.lemma or token.text).lower(),
                    pos=token.pos,
                    feats=dict(token.feats or {}),
                )
            )
        return tokens


class LinguisticChecker:
    """Проверяет языковые требования методичек через Natasha, если такие правила есть в профиле."""

    def __init__(self) -> None:
        self._analyzer: _MorphAnalyzer | None = None

    def check(self, document: ParsedDocxDocument, profile: Profile) -> list[Violation]:
        rules = _linguistic_rules(profile)
        if not rules:
            return []

        self._analyzer = _MorphAnalyzer()
        violations: list[Violation] = []

        introduction_rule = rules.get("introduction_tasks_infinitive_required") or rules.get("initial_verb_form")
        if introduction_rule is not None:
            self._check_introduction_tasks(
                document,
                introduction_rule,
                violations,
            )

        conclusion_rule = rules.get("conclusion_completed_results_required") or rules.get("completed_action_form")
        if conclusion_rule is not None:
            self._check_conclusion_results(
                document,
                conclusion_rule,
                violations,
            )

        forbidden_rule = rules.get("first_person_phrases_not_recommended") or rules.get("forbidden_phrases")
        if forbidden_rule is not None:
            self._check_forbidden_phrases(
                document,
                forbidden_rule,
                violations,
            )

        return violations

    def _check_introduction_tasks(
        self,
        document: ParsedDocxDocument,
        rule: Rule,
        violations: list[Violation],
    ) -> None:
        intro_paragraphs = [
            paragraph
            for paragraph in document.paragraphs
            if paragraph.logical_section == "introduction"
            and paragraph.paragraph_type != ParagraphType.TITLE_PAGE
        ]
        task_items = _find_task_items(intro_paragraphs)

        for paragraph in task_items:
            task_text = _strip_list_marker(paragraph.text)
            first_token = _first_meaningful_token(self._analyze(task_text))
            if first_token is None or _is_infinitive(first_token):
                continue

            fragment = _first_words(task_text, limit=4)
            message = (
                "Методические требования: задачи во введении рекомендуется формулировать "
                f"глаголами в неопределённой форме. Абзац {paragraph.index}: найдено начало "
                f"«{fragment}», рекомендуется формулировка с глагола, например "
                "«Проанализировать ...»."
            )
            violations.append(
                _paragraph_violation(
                    rule=rule,
                    paragraph=paragraph,
                    actual=fragment,
                    expected="инфинитив в начале задачи",
                    message=message,
                )
            )

    def _check_conclusion_results(
        self,
        document: ParsedDocxDocument,
        rule: Rule,
        violations: list[Violation],
    ) -> None:
        conclusion_paragraphs = [
            paragraph
            for paragraph in document.paragraphs
            if paragraph.logical_section == "conclusion"
            and paragraph.paragraph_type
            not in {ParagraphType.TITLE_PAGE, ParagraphType.EMPTY, ParagraphType.CAPTION, ParagraphType.TABLE_CELL}
            and paragraph.text.strip()
        ]
        if not conclusion_paragraphs:
            return

        has_completed_result = False
        has_future_issue = False
        for paragraph in conclusion_paragraphs:
            text = paragraph.text.strip()
            tokens = self._analyze(text)
            future_fragment = _first_match(FUTURE_OR_PLAN_PATTERN, text)
            if future_fragment:
                has_future_issue = True
                message = (
                    "Методические требования: в заключении результаты работы должны быть "
                    f"сформулированы как выполненные действия. Абзац {paragraph.index}: "
                    f"обнаружена формулировка будущего времени «{future_fragment}». "
                    "Требуется ручная проверка."
                )
                violations.append(
                    _paragraph_violation(
                        rule=rule,
                        paragraph=paragraph,
                        actual=future_fragment,
                        expected="формулировка выполненного результата",
                        message=message,
                        severity="warning",
                    )
                )
                continue

            if _has_completed_action(tokens, text):
                has_completed_result = True

        if has_completed_result or has_future_issue:
            return

        first = conclusion_paragraphs[0]
        message = (
            "Методические требования: в заключении должны быть явно представлены результаты "
            "выполненной работы. В разделе не найдены устойчивые формулировки завершённых "
            "действий, требуется ручная проверка."
        )
        violations.append(
            _paragraph_violation(
                rule=rule,
                paragraph=first,
                actual="формулировки завершённых действий не найдены",
                expected="разработана/реализован/проведено/определены ...",
                message=message,
                severity="warning",
            )
        )

    def _check_forbidden_phrases(
        self,
        document: ParsedDocxDocument,
        rule: Rule,
        violations: list[Violation],
    ) -> None:
        forbidden_values = rule.value if isinstance(rule.value, list) else []
        if not forbidden_values:
            return

        for paragraph in document.paragraphs:
            if not _should_check_forbidden_phrases(paragraph):
                continue

            text = paragraph.text.strip()
            normalized_text = _normalize_text(text)
            lemma_text = " ".join(token.lemma for token in self._analyze(text))

            for phrase in forbidden_values:
                phrase_text = str(phrase).strip().lower()
                if not phrase_text:
                    continue

                if _contains_forbidden_phrase(normalized_text, lemma_text, phrase_text):
                    found = _find_original_fragment(text, phrase_text) or phrase_text
                    message = (
                        "Методические требования: в научном тексте не рекомендуется использовать "
                        f"личные или разговорные формулировки. Абзац {paragraph.index}: "
                        f"обнаружен фрагмент «{found}». Требуется ручная корректировка."
                    )
                    violations.append(
                        _paragraph_violation(
                            rule=rule,
                            paragraph=paragraph,
                            actual=found,
                            expected="нейтральная научная формулировка",
                            message=message,
                            severity="warning",
                        )
                    )
                    break

    def _analyze(self, text: str) -> list[MorphToken]:
        if self._analyzer is None:
            self._analyzer = _MorphAnalyzer()
        return self._analyzer.analyze(text)


def _linguistic_rules(profile: Profile) -> dict[str, Rule]:
    result: dict[str, Rule] = {}

    for rule in profile.rules:
        if not getattr(rule, "enabled", True):
            continue

        category = getattr(rule.category, "value", rule.category)
        if category != "linguistic" and rule.parameter not in LINGUISTIC_PARAMETERS:
            continue

        result[rule.id] = rule
        result[rule.parameter] = rule

    return result


def _find_task_items(paragraphs: list[ParagraphData]) -> list[ParagraphData]:
    task_items: list[ParagraphData] = []
    inside_task_block = False

    for paragraph in paragraphs:
        text = paragraph.text.strip()
        if not text:
            continue

        if TASK_INTRO_PATTERN.search(text):
            inside_task_block = True
            continue

        if not inside_task_block:
            continue

        if paragraph.paragraph_type == ParagraphType.LIST_ITEM or paragraph.list_marker_type:
            task_items.append(paragraph)
            continue

        if task_items:
            break

    return task_items


def _strip_list_marker(text: str) -> str:
    return LIST_MARKER_PATTERN.sub("", text).strip()


def _first_meaningful_token(tokens: list[MorphToken]) -> MorphToken | None:
    for token in tokens:
        if token.lemma not in {"и", "а", "но", "для", "по", "на", "в", "во", "с", "со"}:
            return token
    return None


def _is_infinitive(token: MorphToken) -> bool:
    if token.pos == "VERB" and token.feats and token.feats.get("VerbForm") == "Inf":
        return True

    lemma = token.lemma.lower()
    text = token.text.lower()
    return lemma.endswith(("ть", "ти", "чь")) or text.endswith(("ть", "ти", "чь"))


def _has_completed_action(tokens: list[MorphToken], text: str) -> bool:
    lowered = _normalize_text(text)
    if any(word in lowered for word in COMPLETED_ACTION_WORDS):
        return True

    lemmas = {token.lemma for token in tokens}
    return bool(
        lemmas
        & {
            "разработать",
            "реализовать",
            "провести",
            "определить",
            "выявить",
            "создать",
            "предложить",
            "выполнить",
        }
    )


def _should_check_forbidden_phrases(paragraph: ParagraphData) -> bool:
    if paragraph.paragraph_type in {
        ParagraphType.TITLE_PAGE,
        ParagraphType.EMPTY,
        ParagraphType.CAPTION,
        ParagraphType.TABLE_CELL,
        ParagraphType.FOOTNOTE,
    }:
        return False

    if paragraph.logical_section in {"title_page", "references", "appendix"}:
        return False

    return bool(paragraph.text.strip())


def _paragraph_violation(
    rule: Rule,
    paragraph: ParagraphData,
    actual: str,
    expected: str,
    message: str,
    severity: str | None = None,
) -> Violation:
    resolved_severity = severity or ("warning" if _is_warning(rule) else "error")
    return Violation(
        rule_id=rule.id,
        source_section=rule.source_section,
        target=rule.target,
        parameter=rule.parameter,
        location=f"Абзац {paragraph.index}",
        paragraph_index=paragraph.index,
        expected=expected,
        actual=actual,
        message=message,
        severity=resolved_severity,
        violation_type="linguistic",
    )


def _is_warning(rule: Rule) -> bool:
    return getattr(rule.modality, "value", rule.modality) == "recommended"


def _rough_lemma(word: str) -> str:
    lowered = word.lower().replace("ё", "е")

    if lowered.startswith("счита"):
        return "считать"
    if lowered.startswith("сдела"):
        return "сделать"
    if lowered.startswith("каж"):
        return "казаться"
    if lowered.startswith("планир"):
        return "планироваться"

    return lowered


def _normalize_text(text: str) -> str:
    return " ".join(text.lower().replace("ё", "е").split())


def _contains_forbidden_phrase(
    normalized_text: str,
    lemma_text: str,
    phrase_text: str,
) -> bool:
    normalized_phrase = _normalize_text(phrase_text)
    if not normalized_phrase:
        return False

    # Для коротких местоимений нельзя использовать простое `in`, иначе "вы"
    # сработает внутри слов вроде "вывод". Проверяем границы слов.
    if " " not in normalized_phrase:
        pattern = re.compile(rf"(?<![\w-]){re.escape(normalized_phrase)}(?![\w-])")
        return bool(pattern.search(normalized_text) or pattern.search(lemma_text))

    phrase_pattern = re.compile(
        r"(?<![\w-])" + r"\s+".join(map(re.escape, normalized_phrase.split())) + r"(?![\w-])"
    )
    return bool(phrase_pattern.search(normalized_text) or phrase_pattern.search(lemma_text))


def _first_words(text: str, limit: int = 4) -> str:
    words = WORD_PATTERN.findall(text.strip())
    return " ".join(words[:limit]) if words else text.strip()[:80]


def _first_match(pattern: re.Pattern[str], text: str) -> str | None:
    match = pattern.search(text)
    return match.group(0) if match else None


def _find_original_fragment(text: str, normalized_phrase: str) -> str | None:
    raw_words = normalized_phrase.split()
    if not raw_words:
        return None

    if len(raw_words) == 1:
        pattern = re.compile(re.escape(raw_words[0]), re.IGNORECASE)
    else:
        pattern = re.compile(r"\s+".join(map(re.escape, raw_words)), re.IGNORECASE)

    match = pattern.search(_normalize_text(text))
    if not match:
        return None

    return normalized_phrase
