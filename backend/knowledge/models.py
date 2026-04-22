from __future__ import annotations
from enum import Enum
from pydantic import BaseModel

class DocType(str, Enum):
    sop             = "sop"              # Standard Operating Procedure — steps + thresholds
    report_template = "report_template"  # Sample output the checkout should produce
    context         = "context"          # Background: architecture, SLOs, contacts, glossary

class KnowledgeDoc(BaseModel):
    id: str
    name: str
    doc_type: DocType
    checkout_types: list[str]   # e.g. ["infra_health","cost_review"] or ["*"] for all
    description: str
    content: str                # full text content (markdown)
    file_name: str | None
    file_size: int
    created_at: str
    updated_at: str
    is_default: bool            # built-in docs shipped with OpsBrain

class KnowledgeDocCreate(BaseModel):
    name: str
    doc_type: DocType
    checkout_types: list[str] = ["*"]
    description: str = ""
    content: str

class KnowledgeDocUpdate(BaseModel):
    name: str | None = None
    doc_type: DocType | None = None
    checkout_types: list[str] | None = None
    description: str | None = None
    content: str | None = None
