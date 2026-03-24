from __future__ import annotations

from enum import Enum
from typing import Any

from pydantic import BaseModel, ConfigDict, Field, model_validator


class Status(str, Enum):
    success = "success"
    needs_review = "needs_review"
    error = "error"


class DocumentType(str, Enum):
    lab_result = "lab_result"
    academic_document = "academic_document"
    medical_document = "medical_document"
    support_document = "support_document"
    other = "other"
    unknown = "unknown"


class ToolTraceItem(BaseModel):
    model_config = ConfigDict(extra="forbid")

    tool: str
    reason: str
    success: bool


class AnalyzeResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    status: Status
    document_type: DocumentType
    summary: str
    extracted_data: dict[str, Any] = Field(default_factory=dict)
    warnings: list[str] = Field(default_factory=list)
    needs_clarification: bool = False
    clarifying_questions: list[str] = Field(default_factory=list)
    tool_trace: list[ToolTraceItem] = Field(default_factory=list)

    @model_validator(mode="after")
    def validate_clarifications(self) -> "AnalyzeResponse":
        if self.needs_clarification and len(self.clarifying_questions) < 2:
            raise ValueError("clarifying_questions must have at least 2 items when needs_clarification=true")
        if not self.needs_clarification and self.clarifying_questions:
            raise ValueError("clarifying_questions must be [] when needs_clarification=false")
        return self


class LabTestItem(BaseModel):
    model_config = ConfigDict(extra="forbid")

    exam_name: str
    value: str
    unit: str | None = None
    reference_range: str | None = None
    interpretation: str | None = None


class LLMLabExtraction(BaseModel):
    """Structured intermediate output expected from the LLM."""

    model_config = ConfigDict(extra="forbid")

    patient_name: str | None = None
    collection_date: str | None = None
    laboratory_name: str | None = None
    observations: list[str] = Field(default_factory=list)
    tests: list[LabTestItem] = Field(default_factory=list)
    confidence_notes: list[str] = Field(default_factory=list)
