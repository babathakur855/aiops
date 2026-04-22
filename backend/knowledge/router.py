from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, UploadFile, File, Form

from auth.rbac import require_any, require_sre
from knowledge import store
from knowledge.models import KnowledgeDocCreate, KnowledgeDocUpdate, DocType
from knowledge import set_store
from knowledge.set_models import KnowledgeSetCreate, KnowledgeSetUpdate

router = APIRouter(prefix="/api/v1/knowledge", tags=["knowledge"])


# ── Document endpoints ────────────────────────────────────────────────────────

@router.get("", dependencies=[Depends(require_any)])
async def list_docs(doc_type: str | None = None, checkout_type: str | None = None):
    return store.list_docs(doc_type=doc_type, checkout_type=checkout_type)


@router.get("/for-checkout/{checkout_type}", dependencies=[Depends(require_any)])
async def docs_for_checkout(checkout_type: str, doc_type: str | None = None):
    return store.get_docs_for_checkout(checkout_type, doc_type=doc_type)


@router.post("", dependencies=[Depends(require_sre)])
async def create_doc(body: KnowledgeDocCreate):
    return store.create_doc(body)


@router.post("/upload", dependencies=[Depends(require_sre)])
async def upload_doc(
    file: UploadFile = File(...),
    name: str = Form(...),
    doc_type: str = Form(...),
    checkout_types: str = Form(default='["*"]'),
    description: str = Form(default=""),
):
    import json as _json
    content_bytes = await file.read()
    if len(content_bytes) > 500_000:
        raise HTTPException(400, "File too large — max 500 KB")
    try:
        content = content_bytes.decode("utf-8")
    except UnicodeDecodeError:
        raise HTTPException(400, "File must be UTF-8 text")
    try:
        ct = _json.loads(checkout_types)
    except Exception:
        ct = [checkout_types]
    doc_data = KnowledgeDocCreate(
        name=name, doc_type=DocType(doc_type),
        checkout_types=ct, description=description, content=content,
    )
    return store.create_doc(doc_data, file_name=file.filename)


@router.get("/{doc_id}", dependencies=[Depends(require_any)])
async def get_doc(doc_id: str):
    doc = store.get_doc(doc_id)
    if not doc:
        raise HTTPException(404, "Document not found")
    return doc


@router.put("/{doc_id}", dependencies=[Depends(require_sre)])
async def update_doc(doc_id: str, body: KnowledgeDocUpdate):
    doc = store.update_doc(doc_id, body)
    if not doc:
        raise HTTPException(404, "Document not found")
    return doc


@router.delete("/{doc_id}", dependencies=[Depends(require_sre)])
async def delete_doc(doc_id: str):
    if not store.delete_doc(doc_id):
        raise HTTPException(404, "Document not found")
    return {"deleted": doc_id}


# ── Knowledge Set endpoints ───────────────────────────────────────────────────

@router.get("/sets/all", dependencies=[Depends(require_any)])
async def list_sets(checkout_type: str | None = None):
    """Return all knowledge sets, optionally filtered by checkout type."""
    return set_store.list_sets(checkout_type=checkout_type)


@router.post("/sets", dependencies=[Depends(require_sre)])
async def create_set(body: KnowledgeSetCreate):
    return set_store.create_set(body)


@router.get("/sets/{set_id}", dependencies=[Depends(require_any)])
async def get_set(set_id: str):
    s = set_store.get_set(set_id)
    if not s:
        raise HTTPException(404, "Set not found")
    return s


@router.put("/sets/{set_id}", dependencies=[Depends(require_sre)])
async def update_set(set_id: str, body: KnowledgeSetUpdate):
    s = set_store.update_set(set_id, body)
    if not s:
        raise HTTPException(404, "Set not found")
    return s


@router.delete("/sets/{set_id}", dependencies=[Depends(require_sre)])
async def delete_set(set_id: str):
    if not set_store.delete_set(set_id):
        raise HTTPException(404, "Set not found")
    return {"deleted": set_id}


@router.post("/sets/{set_id}/assign/{checkout_id}", dependencies=[Depends(require_sre)])
async def assign_set(set_id: str, checkout_id: str):
    """Assign this knowledge set to a specific checkout."""
    if not set_store.get_set(set_id):
        raise HTTPException(404, "Set not found")
    set_store.assign_set_to_checkout(checkout_id, set_id)
    return {"assigned": True, "checkout_id": checkout_id, "set_id": set_id}


@router.delete("/sets/assign/{checkout_id}", dependencies=[Depends(require_sre)])
async def unassign_set(checkout_id: str):
    """Remove the explicit knowledge set assignment from a checkout (falls back to default)."""
    set_store.assign_set_to_checkout(checkout_id, None)
    return {"unassigned": True, "checkout_id": checkout_id}


@router.get("/sets/resolve/{checkout_id}", dependencies=[Depends(require_any)])
async def resolve_set_for_checkout(checkout_id: str):
    """Return the knowledge set that will be used when this checkout runs."""
    from checkouts.store import get_checkout
    co = get_checkout(checkout_id)
    if not co:
        raise HTTPException(404, "Checkout not found")
    ks = set_store.resolve_set(co)
    return {"checkout_id": checkout_id, "set": ks}
