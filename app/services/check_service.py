import json
import re
from pathlib import Path
from uuid import uuid4

from app.checkers.format_checker import FormatChecker
from app.models.check_result import CheckServiceResult
from app.models.document import ParagraphType
from app.models.profile import Profile
from app.parsers.docx_parser import DocxParser
from app.reports.html_report import generate_html_report
from app.services.autocorrect_service import autocorrect_docx
from app.services.review_docx_service import create_review_docx
from app.checkers.consistency_checker import ConsistencyChecker
from app.checkers.section_consistency_checker import SectionConsistencyChecker
from app.checkers.typography_checker import TypographyChecker
from app.checkers.linguistic_checker import LinguisticChecker
from app.checkers.structure_checker import StructureChecker


FRONT_MATTER_RULE_IDS = {
    "first_page_no_page_number",
}
FRONT_MATTER_PARAMETERS = {
    "front_matter_page_numbers_hidden_until_intro",
}

SUPPRESSED_PARAMETERS = {
    # These checks are intentionally not reported in the current version:
    # spacing around headings is controlled by explicit heading style rules,
    # and manual/empty paragraph diagnostics were too noisy without layout rendering.
    "empty_paragraph_between_content",
    "empty_paragraph_around_heading",
    "additional_spacing_limit",
    "manual_breaks_forbidden",
}

CONSISTENCY_SOURCE_SECTION = "4.1"


def _load_profile(profile_path: str | Path) -> Profile:
    """Загружает профиль проверки из JSON-файла."""

    profile_path = Path(profile_path)

    if not profile_path.exists():
        raise FileNotFoundError(f"Профиль проверки не найден: {profile_path}")

    for encoding in ("utf-8", "utf-8-sig", "cp1251"):
        try:
            with profile_path.open("r", encoding=encoding) as file:
                return Profile.model_validate(json.load(file))
        except UnicodeDecodeError:
            continue

    raise ValueError(f"Не удалось прочитать JSON-профиль: {profile_path}")


def _make_output_paths(docx_path: Path, output_dir: Path) -> tuple[Path, Path, Path]:
    """Формирует пути для HTML-отчёта и исправленного DOCX-файла."""

    stem = docx_path.stem

    report_path = output_dir / f"report_{stem}.html"
    fixed_docx_path = output_dir / f"fixed_{stem}.docx"
    review_docx_path = output_dir / f"review_{stem}.docx"

    return report_path, fixed_docx_path, review_docx_path


def _make_unique_docx_path(path: Path) -> Path:
    return path.with_name(f"{path.stem}_{uuid4().hex[:8]}{path.suffix}")


def _filter_title_page_violations(parsed_document, violations):
    title_page_indexes = {
        paragraph.index
        for paragraph in parsed_document.paragraphs
        if paragraph.paragraph_type == ParagraphType.TITLE_PAGE
    }
    content_list_indexes = _detect_leading_content_list_indexes(parsed_document)
    front_matter_indexes = _detect_front_matter_indexes(parsed_document)
    front_matter_table_indexes = _detect_front_matter_table_indexes(parsed_document)
    paragraphs_by_index = {
        paragraph.index: paragraph
        for paragraph in parsed_document.paragraphs
    }

    return [
        violation
        for violation in violations
        if _should_keep_violation(
            violation,
            title_page_indexes,
            content_list_indexes,
            front_matter_indexes,
            front_matter_table_indexes,
            paragraphs_by_index,
        )
    ]


def _drop_duplicate_consistency_violations(violations):
    concrete_keys = {
        (violation.paragraph_index, violation.parameter)
        for violation in violations
        if violation.paragraph_index is not None
        and violation.source_section != CONSISTENCY_SOURCE_SECTION
    }

    result = []
    for violation in violations:
        key = (violation.paragraph_index, violation.parameter)
        if (
            violation.source_section == CONSISTENCY_SOURCE_SECTION
            and violation.paragraph_index is not None
            and key in concrete_keys
        ):
            continue
        result.append(violation)

    return result


def _should_keep_violation(
    violation,
    title_page_indexes: set[int],
    content_list_indexes: set[int],
    front_matter_indexes: set[int],
    front_matter_table_indexes: set[int],
    paragraphs_by_index,
) -> bool:
    if violation.parameter in SUPPRESSED_PARAMETERS:
        return False

    if (
        violation.rule_id in FRONT_MATTER_RULE_IDS
        or violation.parameter in FRONT_MATTER_PARAMETERS
    ):
        return True

    if violation.paragraph_index in title_page_indexes:
        return False
    if violation.paragraph_index in content_list_indexes:
        return False
    if violation.paragraph_index in front_matter_indexes:
        return False

    table_index = _table_index_for_violation(violation, paragraphs_by_index)
    if table_index in front_matter_table_indexes:
        return False

    return True


def _table_index_for_violation(violation, paragraphs_by_index) -> int | None:
    if violation.paragraph_index is not None:
        paragraph = paragraphs_by_index.get(violation.paragraph_index)
        if paragraph is not None and paragraph.table_index is not None:
            return paragraph.table_index

    text = f"{violation.location or ''} {violation.message or ''}"
    match = re.search(r"(?:Таблица|Table)\s+(\d+)", text, re.IGNORECASE)
    if match is None:
        match = re.search(r"(?:Таблица|Table)\s+(\d+)", text, re.IGNORECASE)
    if match:
        number = int(match.group(1))
        return number - 1 if number > 0 else 0

    return None


def _detect_front_matter_indexes(parsed_document) -> set[int]:
    start_index = _first_content_start_index(parsed_document)
    if start_index is None:
        return set()

    return {
        paragraph.index
        for paragraph in parsed_document.paragraphs
        if paragraph.index < start_index
    }


def _first_content_start_index(parsed_document) -> int | None:
    introduction = next(
        (
            paragraph.index
            for paragraph in parsed_document.paragraphs
            if paragraph.logical_section == "introduction"
            and paragraph.paragraph_type == ParagraphType.HEADING
        ),
        None,
    )
    if introduction is not None:
        return introduction

    for paragraph in parsed_document.paragraphs:
        if (
            paragraph.paragraph_type == ParagraphType.HEADING
            and paragraph.heading_level == 1
            and (
                paragraph.is_numbered_heading
                or paragraph.logical_section in {"main_part", "introduction"}
            )
        ):
            return paragraph.index

    return None


def _detect_front_matter_table_indexes(parsed_document) -> set[int]:
    result: set[int] = set()
    start_index = _first_content_start_index(parsed_document)
    keywords = {
        "министерство",
        "университет",
        "институт",
        "высшая школа",
        "кафедра",
        "направление подготовки",
        "профиль подготовки",
        "руководитель",
        "студент",
        "обучающийся",
        "выпускная квалификационная",
        "задание",
        "наименование института",
        "должность",
    }

    for table in parsed_document.tables:
        if start_index is not None and any(
            paragraph.index < start_index
            for paragraph in table.cell_paragraphs
        ):
            result.add(table.index)
            continue

        text = " ".join(
            paragraph.text.strip().lower()
            for paragraph in table.cell_paragraphs
            if paragraph.text.strip()
        )
        if not text:
            continue
        score = sum(1 for keyword in keywords if keyword in text)
        if score >= 2:
            result.add(table.index)

    return result


def _detect_leading_content_list_indexes(parsed_document) -> set[int]:
    first_main_text_position: int | None = None
    for position, paragraph in enumerate(parsed_document.paragraphs):
        if (
            paragraph.paragraph_type == ParagraphType.MAIN_TEXT
            and paragraph.text.strip()
        ):
            first_main_text_position = position
            break

    if first_main_text_position is None:
        return set()

    real_start_index: int | None = None
    for paragraph in reversed(parsed_document.paragraphs[:first_main_text_position]):
        if paragraph.text.strip():
            real_start_index = paragraph.index
            break

    if real_start_index is None:
        return set()

    leading_headings = [
        paragraph
        for paragraph in parsed_document.paragraphs
        if paragraph.index < real_start_index
        and paragraph.text.strip()
        and paragraph.paragraph_type == ParagraphType.HEADING
    ]
    leading_non_headings = [
        paragraph
        for paragraph in parsed_document.paragraphs
        if paragraph.index < real_start_index
        and paragraph.text.strip()
        and paragraph.paragraph_type not in {ParagraphType.HEADING, ParagraphType.TITLE_PAGE}
    ]

    if len(leading_headings) >= 3 and not leading_non_headings:
        return {paragraph.index for paragraph in leading_headings}

    return set()


def check_docx_document(
    docx_path: str | Path,
    profile_path: str | Path,
    output_dir: str | Path = "outputs",
    autocorrect: bool = True,
    create_review: bool = True,
) -> CheckServiceResult:
    """
    Выполняет полный цикл проверки DOCX-документа.

    Этапы:
    1. загрузка профиля;
    2. разбор DOCX;
    3. проверка форматирования;
    4. создание HTML-отчёта;
    5. создание исправленного DOCX-файла, если включено автоисправление.
    """

    docx_path = Path(docx_path)
    output_dir = Path(output_dir)

    if not docx_path.exists():
        raise FileNotFoundError(f"DOCX-файл не найден: {docx_path}")

    if docx_path.suffix.lower() != ".docx":
        raise ValueError("Сервис проверки DOCX поддерживает только файлы .docx")

    output_dir.mkdir(parents=True, exist_ok=True)

    profile = _load_profile(profile_path)
    report_path, fixed_docx_path, review_docx_path = _make_output_paths(docx_path, output_dir)

    parsed_document = DocxParser().parse(docx_path)
    format_violations = FormatChecker().check(parsed_document, profile)
    structure_violations = StructureChecker().check(parsed_document, profile)
    consistency_violations = ConsistencyChecker().check(parsed_document, profile)
    section_consistency_violations = SectionConsistencyChecker().check(
        parsed_document,
        profile,
    )
    typography_violations = TypographyChecker().check(parsed_document, profile)
    linguistic_violations = LinguisticChecker().check(parsed_document, profile)

    violations = (
        format_violations
        + structure_violations
        + consistency_violations
        + section_consistency_violations
        + typography_violations
        + linguistic_violations
    )
    violations = _filter_title_page_violations(parsed_document, violations)
    violations = _drop_duplicate_consistency_violations(violations)
    
    generate_html_report(
        violations=violations,
        document_name=docx_path.name,
        output_path=report_path,
    )

    created_fixed_docx_path: Path | None = None
    created_review_docx_path: Path | None = None

    if create_review and violations:
        try:
            create_review_docx(
                input_path=docx_path,
                output_path=review_docx_path,
                violations=violations,
            )
            created_review_docx_path = review_docx_path
        except PermissionError:
            fallback_review_docx_path = _make_unique_docx_path(review_docx_path)
            create_review_docx(
                input_path=docx_path,
                output_path=fallback_review_docx_path,
                violations=violations,
            )
            created_review_docx_path = fallback_review_docx_path

    if autocorrect and violations:
        try:
            autocorrect_docx(
                input_path=docx_path,
                output_path=fixed_docx_path,
                profile=profile,
                parsed_document=parsed_document,
            )
            created_fixed_docx_path = fixed_docx_path
        except PermissionError:
            fallback_fixed_docx_path = _make_unique_docx_path(fixed_docx_path)
            autocorrect_docx(
                input_path=docx_path,
                output_path=fallback_fixed_docx_path,
                profile=profile,
                parsed_document=parsed_document,
            )
            created_fixed_docx_path = fallback_fixed_docx_path

    return CheckServiceResult(
        source_docx_path=docx_path,
        report_path=report_path,
        fixed_docx_path=created_fixed_docx_path,
        review_docx_path=created_review_docx_path,
        violations=violations,
    )
