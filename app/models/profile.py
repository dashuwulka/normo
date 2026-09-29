from enum import Enum
from typing import Any

from pydantic import BaseModel, Field


class RuleCategory(str, Enum):
    """Крупная группа, к которой относится правило."""
    FORMATTING = "formatting"
    STRUCTURE = "structure"
    TEXT = "text"
    CONSISTENCY = "consistency"
    LINGUISTIC = "linguistic"


class RuleModality(str, Enum):
    """Степень обязательности требования."""
    MANDATORY = "mandatory"
    RECOMMENDED = "recommended"
    ALLOWED = "allowed"


class RuleOrigin(str, Enum):
    """Откуда появилось правило."""
    MANUAL = "manual"
    EXTRACTED = "extracted"


class RuleOperator(str, Enum):
    """Как проверяется значение."""
    EQUALS = "equals"
    MIN = "min"
    MAX = "max"
    IN = "in"
    CONSISTENT = "consistent"
    CONTAINS = "contains"
    MATCHES = "matches"
    REQUIRED = "required"
    NOT_CONTAINS = "not_contains"


class Rule(BaseModel):
    """
    Одно правило проверки.

    """
    id: str = Field(..., description="Уникальный идентификатор правила")
    category: RuleCategory
    target: str = Field(..., description="К чему относится правило")
    parameter: str = Field(..., description="Какой параметр проверяется")
    operator: RuleOperator
    value: Any = Field(..., description="Требуемое значение")
    unit: str | None = Field(default=None, description="Единица измерения, если нужна")

    modality: RuleModality = RuleModality.MANDATORY
    origin: RuleOrigin = RuleOrigin.MANUAL

    description: str = Field(..., description="Человеко-понятное описание правила")
    source_text: str | None = Field(
        default=None,
        description="Фрагмент нормативного документа, из которого взято правило",
    )
    source_section: str | None = Field(
        default=None,
        description="Пункт или раздел нормативного документа",
    )
    consistency_strategy: dict[str, Any] | None = Field(
        default=None,
        description="Настройки выбора единого значения для проверки единообразия",
    )
    condition: dict[str, Any] | None = Field(
        default=None,
        description="Условие применения правила, если оно задано в нормативном документе",
    )
    relative_to: dict[str, Any] | None = Field(
        default=None,
        description="Описание относительного значения, если правило зависит от другого параметра",
    )


class Profile(BaseModel):
    """
    Профиль проверки — набор правил для конкретного ГОСТа или методички.
    """
    id: str = Field(..., description="Уникальный идентификатор профиля")
    name: str = Field(..., description="Название профиля")
    source_name: str = Field(..., description="Название нормативного документа")
    version: str | None = Field(default=None, description="Версия профиля")
    description: str | None = None
    rules: list[Rule] = Field(default_factory=list)
