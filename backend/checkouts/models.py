from __future__ import annotations
from enum import Enum
from pydantic import BaseModel, Field

class CheckoutFrequency(str, Enum):
    daily       = "daily"
    weekly      = "weekly"
    monthly     = "monthly"
    quarterly   = "quarterly"
    half_yearly = "half-yearly"
    yearly      = "yearly"

WEEKDAYS = ["Monday","Tuesday","Wednesday","Thursday","Friday","Saturday","Sunday"]

class CheckoutType(str, Enum):
    infra_health     = "infra_health"
    cost_review      = "cost_review"
    capacity_review  = "capacity_review"
    slo_review       = "slo_review"
    incident_review  = "incident_review"
    custom           = "custom"

class CheckoutStatus(str, Enum):
    pending = "pending"
    running = "running"
    passed  = "passed"
    warning = "warning"
    failed  = "failed"

class CheckoutCreate(BaseModel):
    name: str
    description: str = ""
    checkout_type: CheckoutType
    frequency: CheckoutFrequency
    # Schedule: hour of day (UTC, 0-23) + weekday (0=Mon) + day of month (1-28)
    scheduled_hour: int = Field(default=9, ge=0, le=23)
    scheduled_weekday: int = Field(default=1, ge=0, le=6)   # for weekly (0=Mon)
    scheduled_day: int = Field(default=1, ge=1, le=28)      # for monthly+
    custom_prompt: str = ""
    audience_emails: list[str] = []
    audience_slack: list[str] = []
    report_format: str = "markdown"
    namespace: str = "production"
    enabled: bool = True

class CheckoutUpdate(BaseModel):
    name: str | None = None
    description: str | None = None
    frequency: CheckoutFrequency | None = None
    scheduled_hour: int | None = None
    scheduled_weekday: int | None = None
    scheduled_day: int | None = None
    custom_prompt: str | None = None
    audience_emails: list[str] | None = None
    audience_slack: list[str] | None = None
    report_format: str | None = None
    namespace: str | None = None
    enabled: bool | None = None

class Checkout(BaseModel):
    id: str
    name: str
    description: str
    checkout_type: CheckoutType
    frequency: CheckoutFrequency
    scheduled_hour: int
    scheduled_weekday: int
    scheduled_day: int
    enabled: bool
    custom_prompt: str
    audience_emails: list[str]
    audience_slack: list[str]
    report_format: str
    namespace: str
    created_at: str
    updated_at: str
    last_run_at: str | None
    next_run_at: str | None
    last_status: CheckoutStatus
    last_summary: str
    run_count: int
    # Knowledge Set assignment
    knowledge_set_id: str | None = None       # explicit set override
    # Compilation
    is_compiled: bool = False
    compiled_at: str | None = None
    execution_plan: dict | None = None        # serialised CheckoutPlan
    tokens_saved_pct: int = 0

class RunHistory(BaseModel):
    id: str
    checkout_id: str
    checkout_name: str
    checkout_type: str
    started_at: str
    completed_at: str | None
    status: CheckoutStatus
    summary: str
    full_report: str
    duration_seconds: float | None
    triggered_by: str
    error: str | None
