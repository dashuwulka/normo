from typing import Any, Literal
from uuid import uuid4

from pydantic import BaseModel, Field


class NormativeBlock(BaseModel):
    """A normalized block from DOCX/PDF before section segmentation."""

    index: int
    text: str
    source_document: str
    page_number: int | None = None
    block_type: Literal["paragraph", "table_row", "list_item", "toc", "page_number"] = "paragraph"
    x0: float | None = None
    y0: float | None = None
    x1: float | None = None
    y1: float | None = None
    font_size: float | None = None
    bold: bool | None = None
    list_marker: str | None = None


class NormativeSection(BaseModel):
    """One complete section or paragraph from a normative document."""

    number: str | None = None
    text: str
    source_document: str


class NormativeFragment(BaseModel):
    """A classified fragment inside a normative section."""

    section_number: str | None = None
    fragment_type: Literal["requirement", "note", "example"]
    text: str
    target_context: str | None = None
    parent_context: str | None = None
    inherited_modality: str | None = None


class NormativeStatement(BaseModel):
    """One atomic normative statement extracted from a section."""

    text: str
    source_section: str | None = None
    parent_context: str | None = None
    inherited_modality: str | None = None
    statement_type: Literal[
        "requirement",
        "recommendation",
        "permission",
        "prohibition",
        "example",
        "note",
        "condition",
    ] = "requirement"

    @property
    def section_number(self) -> str | None:
        return self.source_section

    @property
    def fragment_type(self) -> Literal["requirement", "note", "example"]:
        if self.statement_type in {"note", "example"}:
            return self.statement_type
        return "requirement"

    @property
    def target_context(self) -> str | None:
        return self.parent_context


class ExtractedRuleCandidate(BaseModel):
    """
    Candidate extracted from a normative text fragment.

    This is not a final profile rule. Only confirmed candidates may be converted
    into app.models.profile.Rule objects.
    """

    id: str = Field(default_factory=lambda: str(uuid4()))
    target: str | None = None
    parameter: str
    operator: Literal["equals", "min", "max", "in"]
    value: Any
    unit: str | None = None
    modality: Literal["mandatory", "recommended", "allowed", "unknown"]
    source_text: str
    source_section: str | None = None
    source_document: str
    confidence: float = Field(ge=0.0, le=1.0)
    status: Literal[
        "extracted",
        "needs_review",
        "unsupported",
        "conflict",
        "rejected",
        "confirmed",
    ]
    explanation: str
    condition: dict[str, Any] | None = None
    relative_to: dict[str, Any] | None = None
