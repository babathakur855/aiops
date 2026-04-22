from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Request

from auth.rbac import require_any, require_sre
from checkouts import store
from checkouts.models import CheckoutCreate, CheckoutUpdate
from checkouts.compiler import compile_checkout
from checkouts.plan import CheckoutPlan

router = APIRouter(prefix="/api/v1/checkouts", tags=["checkouts"])


@router.get("", dependencies=[Depends(require_any)])
async def list_checkouts():
    return store.list_checkouts()


@router.get("/stats", dependencies=[Depends(require_any)])
async def checkout_stats():
    return store.get_stats()


@router.get("/runs/recent", dependencies=[Depends(require_any)])
async def recent_runs(limit: int = 50):
    return store.list_recent_runs(limit)


@router.post("", dependencies=[Depends(require_sre)])
async def create_checkout(body: CheckoutCreate):
    return store.create_checkout(body)


@router.get("/{checkout_id}", dependencies=[Depends(require_any)])
async def get_checkout(checkout_id: str):
    c = store.get_checkout(checkout_id)
    if not c:
        raise HTTPException(404, "Checkout not found")
    return c


@router.put("/{checkout_id}", dependencies=[Depends(require_sre)])
async def update_checkout(checkout_id: str, body: CheckoutUpdate):
    patch = body.model_dump(exclude_none=True)
    c = store.update_checkout(checkout_id, patch)
    if not c:
        raise HTTPException(404, "Checkout not found")
    return c


@router.delete("/{checkout_id}", dependencies=[Depends(require_sre)])
async def delete_checkout(checkout_id: str):
    if not store.delete_checkout(checkout_id):
        raise HTTPException(404, "Checkout not found")
    return {"deleted": checkout_id}


@router.post("/{checkout_id}/run", dependencies=[Depends(require_sre)])
async def run_now(checkout_id: str, request: Request):
    c = store.get_checkout(checkout_id)
    if not c:
        raise HTTPException(404, "Checkout not found")
    from checkouts.runner import run_checkout
    run = await run_checkout(c, request.app.state.llm, triggered_by="manual")
    return run


@router.post("/{checkout_id}/compile", dependencies=[Depends(require_sre)])
async def compile_now(checkout_id: str, request: Request):
    """
    One-time compilation: Claude reads the SOP + templates from the Knowledge Base
    and generates a reusable execution plan.  Future runs use the plan instead of
    reloading the SOP — saving ~78% of tokens per run.
    """
    c = store.get_checkout(checkout_id)
    if not c:
        raise HTTPException(404, "Checkout not found")
    try:
        plan = await compile_checkout(c, request.app.state.llm)
        plan_dict = plan.to_dict()
        store.save_plan(checkout_id, plan_dict, plan.estimated_tokens_saved_pct)
        updated = store.get_checkout(checkout_id)
        return {
            "compiled": True,
            "checkout": updated,
            "plan_summary": {
                "tool_steps": len(plan.tool_steps),
                "thresholds_critical": len(plan.thresholds.get("critical", [])),
                "thresholds_warning": len(plan.thresholds.get("warning", [])),
                "narrative_prompt_words": len(plan.narrative_prompt.split()),
                "tokens_saved_pct": plan.estimated_tokens_saved_pct,
                "compiled_from": plan.compiled_from,
            },
        }
    except Exception as e:
        raise HTTPException(500, f"Compilation failed: {e}")


@router.delete("/{checkout_id}/compile", dependencies=[Depends(require_sre)])
async def reset_plan(checkout_id: str):
    """Remove the compiled plan — next run will re-read SOPs and recompile."""
    if not store.get_checkout(checkout_id):
        raise HTTPException(404, "Checkout not found")
    store.clear_plan(checkout_id)
    return {"reset": True, "message": "Plan cleared — next run will recompile from SOPs"}


@router.get("/{checkout_id}/runs", dependencies=[Depends(require_any)])
async def get_runs(checkout_id: str, limit: int = 20):
    return store.list_runs(checkout_id, limit)
