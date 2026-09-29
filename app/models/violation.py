from pydantic import BaseModel


class Violation(BaseModel):
    """Одно найденное нарушение."""

    rule_id: str
    source_section: str | None = None

    target: str
    parameter: str

    location: str
    paragraph_index: int | None = None
    section_index: int | None = None

    expected: str
    actual: str | None

    message: str

    severity: str = "error"
    violation_type: str = "formatting"
