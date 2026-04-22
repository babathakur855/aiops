from __future__ import annotations
from pydantic import BaseModel


class KnowledgeSet(BaseModel):
    id: str
    name: str
    description: str
    checkout_types: list[str]   # which checkout types this set is designed for
    sop_doc_id: str | None      # exactly one SOP
    sop_doc_name: str | None    # denormalised for display
    template_doc_id: str | None # exactly one report template
    template_doc_name: str | None
    context_doc_ids: list[str]  # zero or more context docs
    context_doc_names: list[str]
    created_at: str
    updated_at: str
    is_default: bool            # auto-selected when no explicit set is assigned


class KnowledgeSetCreate(BaseModel):
    name: str
    description: str = ""
    checkout_types: list[str]
    sop_doc_id: str | None = None
    template_doc_id: str | None = None
    context_doc_ids: list[str] = []
    is_default: bool = False


class KnowledgeSetUpdate(BaseModel):
    name: str | None = None
    description: str | None = None
    checkout_types: list[str] | None = None
    sop_doc_id: str | None = None
    template_doc_id: str | None = None
    context_doc_ids: list[str] | None = None
    is_default: bool | None = None
