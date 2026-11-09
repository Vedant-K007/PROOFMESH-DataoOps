from typing import Any

from pydantic import BaseModel, Field


class InvestigationCreate(BaseModel):
    name: str = Field(min_length=1, max_length=160)
    case_reference: str | None = Field(default=None, max_length=120)
    description: str | None = Field(default=None, max_length=2000)
    category: str = Field(default="general", min_length=1, max_length=80)


class DocumentSummary(BaseModel):
    id: str
    filename: str
    file_type: str
    file_size: int
    sha256: str
    status: str
    created_at: str


class InvestigationRecord(BaseModel):
    id: str
    name: str
    case_reference: str | None
    description: str | None
    category: str
    status: str
    created_at: str
    updated_at: str
    documents: list[DocumentSummary] = Field(default_factory=list)


class DashboardResponse(BaseModel):
    total_investigations: int
    total_documents: int
    pending_investigations: int
    completed_investigations: int
    investigations: list[dict[str, Any]]
