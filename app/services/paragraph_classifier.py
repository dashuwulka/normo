import re

from app.models.document import ParagraphData, ParagraphType


HEADING_NUMBER_PATTERN = re.compile(r"^(\d+(?:\.\d+)*)(?:\.\s*|\s+)(.+)$")
APPENDIX_HEADING_PATTERN = re.compile(
    r"^приложение\s+[а-яёa-z](?:\.|\s|$)",
    re.IGNORECASE,
)
CAPTION_PATTERN = re.compile(
    r"^(?P<prefix>Рис\.|Рисунок|Табл\.|Таблица)\s+"
    r"(?P<number>\d+(?:\.\d+)*)"
    r"(?P<separator>[.\u2014-])?\s*"
    r"(?P<title>.*)$",
    re.IGNORECASE,
)

LIST_STYLE_KEYWORDS = (
    "list",
    "список",
    "перечень",
    "bullet",
    "numbered",
)

STRUCTURAL_HEADING_ALIASES = {
    "содержание",
    "оглавление",
    "введение",
    "заключение",
    "вывод",
    "выводы",
    "список литературы",
    "список источников",
    "список использованной литературы",
    "список использованных источников",
    "библиографический список",
    "библиография",
    "приложение",
    "приложения"
}


def _normalize_text(text: str) -> str:
    """Нормализует текст для сравнения заголовков."""
    return " ".join(text.strip().lower().split())


def _get_heading_level_from_style(style_name: str | None) -> int | None:
    """
    Определяет уровень заголовка по имени стиля Word.

    Например:
    Heading 1 -> 1
    Heading 2 -> 2
    Заголовок 1 -> 1
    """
    if not style_name:
        return None

    normalized_style_name = style_name.strip().lower()

    english_match = re.search(r"heading\s+(\d+)", normalized_style_name)
    if english_match:
        return int(english_match.group(1))

    russian_match = re.search(r"заголовок\s+(\d+)", normalized_style_name)
    if russian_match:
        return int(russian_match.group(1))

    role_levels = {
        "structural heading": 1,
        "subsection heading": 2,
        "point heading": 3,
        "appendix heading": 1,
        "section heading": 1,
    }
    for marker, level in role_levels.items():
        if marker in normalized_style_name:
            return level

    return None


def _get_heading_level_from_number(text: str) -> int | None:
    """
    Определяет уровень заголовка по номеру в начале строки.

    2 -> уровень 1
    2.1 -> уровень 2
    2.1.3 -> уровень 3
    """
    match = HEADING_NUMBER_PATTERN.match(text.strip())
    if not match:
        return None

    number = match.group(1)
    return number.count(".") + 1


def _is_structural_heading(text: str) -> bool:
    """
    Проверяет, является ли строка ненумерованным структурным заголовком.

    Например: Введение, Заключение, Содержание, Список литературы.
    """
    normalized = _normalize_text(text)

    # Убираем точку на конце только для распознавания.
    # Саму ошибку точки потом должна найти проверка.
    normalized_without_dot = normalized.rstrip(".")

    return (
        normalized_without_dot in STRUCTURAL_HEADING_ALIASES
        or APPENDIX_HEADING_PATTERN.match(normalized_without_dot) is not None
    )


def _is_list_style(style_name: str | None) -> bool:
    """
    Проверяет, является ли стиль абзаца стилем списка.

    Например, ListParagraph, List Bullet, Список, Маркированный список и т.п.
    """
    if not style_name:
        return False

    normalized = style_name.strip().lower()
    return any(keyword in normalized for keyword in LIST_STYLE_KEYWORDS)


def _apply_caption_data(paragraph: ParagraphData, text: str) -> bool:
    match = CAPTION_PATTERN.match(text.strip())
    if not match:
        return False

    prefix = match.group("prefix")
    normalized_prefix = prefix.lower()
    paragraph.paragraph_type = ParagraphType.CAPTION
    paragraph.heading_level = None
    paragraph.caption_prefix = prefix
    paragraph.caption_number = match.group("number")
    paragraph.caption_title = (match.group("title") or "").strip()
    paragraph.caption_kind = (
        "figure"
        if normalized_prefix.startswith("рис")
        else "table"
    )
    return True


def _looks_like_numbered_heading(text: str, style_name: str | None = None) -> bool:
    """
    Проверяет, похож ли абзац на нумерованный заголовок.

    Заголовок обычно:
    - начинается с номера;
    - не слишком длинный;
    - не выглядит как обычный длинный абзац или элемент списка.
    """

    # Стиль списка надёжно говорит о том, что это не заголовок,
    # даже если текст совпадает по форме с нумерованным заголовком.
    if _is_list_style(style_name):
        return False

    text = text.strip()

    match = HEADING_NUMBER_PATTERN.match(text)
    if not match:
        return False

    title_part = match.group(2).strip()

    if not title_part:
        return False

    is_short_enough = len(text) <= 160

    # Точки внутри заголовка считаем только те, которые завершают предложение
    # (а не находятся внутри сокращений вроде «т.д.», «и.т.п.»).
    # Простая эвристика: убираем точки, окружённые буквами с обеих сторон.
    sentence_text = re.sub(r"(?<=\w)\.(?=\w)", "", title_part)
    has_only_one_sentence = sentence_text.count(".") <= 1

    return is_short_enough and has_only_one_sentence


def _looks_like_styled_heading(text: str) -> bool:
    """
    Проверяет, похож ли абзац со стилем Heading на настоящий заголовок.

    В реальных DOCX иногда обычный текст случайно набран стилем Heading.
    Поэтому длинное законченное предложение с точкой не считаем заголовком
    только из-за имени стиля.
    """

    stripped = text.strip()
    if not stripped:
        return False

    if len(stripped) > 160:
        return False

    words_count = len(stripped.split())
    if words_count > 5 and stripped.endswith((".", "!", "?", "…")):
        return False

    return True


def classify_paragraph(paragraph: ParagraphData) -> ParagraphData:
    """
    Определяет предварительный тип абзаца.

    Приоритет:
    1. Пустой абзац.
    2. Ненумерованные структурные заголовки.
    3. Заголовок по стилю Word.
    4. Нумерованный заголовок по началу строки.
    5. Основной текст.
    """

    text = paragraph.text.strip()

    if not text:
        paragraph.paragraph_type = ParagraphType.EMPTY
        paragraph.heading_level = None
        paragraph.is_structural_heading = False
        paragraph.is_numbered_heading = False
        return paragraph

    if _apply_caption_data(paragraph, text):
        paragraph.is_structural_heading = False
        paragraph.is_numbered_heading = False
        return paragraph

    if _is_list_style(paragraph.style_name) or paragraph.is_automatic_list:
        paragraph.paragraph_type = ParagraphType.LIST_ITEM
        paragraph.heading_level = None
        paragraph.is_structural_heading = False
        paragraph.is_numbered_heading = False
        return paragraph

    if paragraph.list_marker_type is not None:
        paragraph.paragraph_type = ParagraphType.LIST_ITEM
        paragraph.heading_level = None
        paragraph.is_structural_heading = False
        paragraph.is_numbered_heading = False
        return paragraph

    if _is_structural_heading(text):
        paragraph.paragraph_type = ParagraphType.HEADING
        paragraph.heading_level = 1
        paragraph.is_structural_heading = True
        paragraph.is_numbered_heading = False
        return paragraph

    style_heading_level = _get_heading_level_from_style(paragraph.style_name)
    number_heading_level = _get_heading_level_from_number(text)

    if style_heading_level is not None and (
        number_heading_level is not None
        or _looks_like_styled_heading(text)
    ):
        paragraph.paragraph_type = ParagraphType.HEADING
        paragraph.heading_level = number_heading_level or style_heading_level
        paragraph.is_structural_heading = False
        paragraph.is_numbered_heading = number_heading_level is not None
        return paragraph

    if _looks_like_numbered_heading(text, paragraph.style_name):
        paragraph.paragraph_type = ParagraphType.HEADING
        paragraph.heading_level = number_heading_level
        paragraph.is_structural_heading = False
        paragraph.is_numbered_heading = True
        return paragraph

    paragraph.paragraph_type = ParagraphType.MAIN_TEXT
    paragraph.heading_level = None
    paragraph.is_structural_heading = False
    paragraph.is_numbered_heading = False
    return paragraph
