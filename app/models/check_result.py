from pathlib import Path

from pydantic import BaseModel

from app.models.violation import Violation
from app.services.violation_grouping import (
    count_by_severity,
    group_violations_by_section,
)


class CheckServiceResult(BaseModel):
    """Результат работы сервиса проверки документа."""

    source_docx_path: Path
    report_path: Path
    fixed_docx_path: Path | None = None
    review_docx_path: Path | None = None
    violations: list[Violation]

    @property
    def has_violations(self) -> bool:
        """Есть ли найденные нарушения."""
        return len(self.violations) > 0

    @property
    def violations_count(self) -> int:
        """Количество найденных нарушений."""
        return len(self.violations)

    @property
    def errors_count(self) -> int:
        """Количество обязательных ошибок."""
        return count_by_severity(self.violations)["error"]

    @property
    def warnings_count(self) -> int:
        """Количество предупреждений и рекомендаций."""
        return count_by_severity(self.violations)["warning"]

    @property
    def grouped_violations(self):
        """Нарушения, сгруппированные по разделам ГОСТа и rule_id."""
        return group_violations_by_section(self.violations)
