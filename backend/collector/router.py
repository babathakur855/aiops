"""
Collector management API — environments, enrollment tokens, collection status, metrics.
"""
from __future__ import annotations

import uuid
from fastapi import APIRouter, Depends, Request, Response
from fastapi.responses import PlainTextResponse
from pydantic import BaseModel

from auth.rbac import require_any, require_admin
from collector.metrics_store import metrics_store
from collector.enrollment import enrollment_registry, generate_enrollment_token, validate_enrollment_token
from collector import scheduler

router = APIRouter(prefix="/api/v1/collector", tags=["collector"])


# ─── Models ───────────────────────────────────────────────────────

class EnrollRequest(BaseModel):
    env_name: str
    platform_type: str = "kubernetes"   # kubernetes | ec2_linux | ecs | windows_vm | cloud_api
    capabilities: list[str] = ["metrics", "logs", "events"]
    expires_in_days: int = 3650


# ─── Installer scripts (no auth — served to new installs) ─────────

@router.get("/install.py", include_in_schema=False)
async def serve_installer():
    """Kubernetes DaemonSet installer — piped into python3."""
    from collector.install_script import INSTALL_SCRIPT
    return PlainTextResponse(INSTALL_SCRIPT, media_type="text/x-python")


@router.get("/install-vm.sh", include_in_schema=False)
async def serve_vm_installer():
    """Linux VM installer — piped into bash."""
    from collector.vm_install_script import VM_INSTALL_SCRIPT
    return PlainTextResponse(VM_INSTALL_SCRIPT, media_type="text/x-sh")


@router.get("/install-vm.ps1", include_in_schema=False)
async def serve_windows_installer():
    """Windows VM installer — piped into PowerShell."""
    from collector.vm_install_script import WINDOWS_INSTALL_SCRIPT
    return PlainTextResponse(WINDOWS_INSTALL_SCRIPT, media_type="text/plain")


# ─── Environment enrollment ───────────────────────────────────────

@router.post("/environments", dependencies=[Depends(require_admin)])
async def create_environment(body: EnrollRequest, request: Request):
    """
    Generate an enrollment token for a new environment.
    Returns platform-specific install commands based on platform_type.
    """
    env_id = str(uuid.uuid4())[:12]
    token_data = generate_enrollment_token(
        env_id=env_id,
        env_name=body.env_name,
        created_by=getattr(getattr(request.state, "user", None), "username", "admin"),
        expires_in_days=body.expires_in_days,
        capabilities=body.capabilities,
    )
    enrollment_registry.register({**token_data, "jti": token_data["token"][-8:]})

    base_url = str(request.base_url).rstrip("/")
    token = token_data["token"]
    name = body.env_name
    pt = body.platform_type

    # ── Platform-specific install commands ────────────────────────
    if pt == "kubernetes":
        install_cmd = (
            f'python3 <(curl -fsSL {base_url}/api/v1/collector/install.py) \\\n'
            f'  --endpoint {base_url} \\\n'
            f'  --token {token} \\\n'
            f'  --env-name "{name}"'
        )
        alt = {
            "download_and_run": (
                f'curl -fsSL {base_url}/api/v1/collector/install.py -o install-collector.py\n'
                f'python3 install-collector.py \\\n'
                f'  --endpoint {base_url} --token {token} --env-name "{name}"'
            ),
            "dry_run": (
                f'python3 install-collector.py \\\n'
                f'  --endpoint {base_url} --token {token} --env-name "{name}" --dry-run'
            ),
            "uninstall": (
                f'python3 install-collector.py \\\n'
                f'  --endpoint {base_url} --token {token} --env-name "{name}" --uninstall'
            ),
        }

    elif pt == "ec2_linux":
        install_cmd = (
            f'curl -fsSL {base_url}/api/v1/collector/install-vm.sh \\\n'
            f'  | sudo bash -s -- \\\n'
            f'      --endpoint {base_url} \\\n'
            f'      --token {token} \\\n'
            f'      --env-name "{name}"'
        )
        alt = {
            "download_and_run": (
                f'curl -fsSL {base_url}/api/v1/collector/install-vm.sh -o install-vm.sh\n'
                f'sudo bash install-vm.sh \\\n'
                f'  --endpoint {base_url} --token {token} --env-name "{name}"'
            ),
            "systemd_check": (
                f'# After installation, verify with:\n'
                f'sudo systemctl status opsbrain-collector\n'
                f'sudo journalctl -u opsbrain-collector -f'
            ),
            "uninstall": (
                f'sudo systemctl stop opsbrain-collector\n'
                f'sudo systemctl disable opsbrain-collector\n'
                f'sudo rm -f /etc/systemd/system/opsbrain-collector.service\n'
                f'sudo rm -rf /opt/opsbrain-collector /etc/opsbrain-collector\n'
                f'sudo systemctl daemon-reload'
            ),
        }

    elif pt == "ecs":
        from collector.vm_install_script import get_ecs_task_snippet
        import json
        ecs_data = get_ecs_task_snippet(base_url, token, name)
        install_cmd = json.dumps(ecs_data["container_definition"], indent=2)
        alt = {
            "ecs_guide": "\n".join(ecs_data["apply_instructions"]),
            "config_override": json.dumps(ecs_data["ecs_config_override"], indent=2),
        }

    elif pt == "windows_vm":
        install_cmd = (
            f'# Run in PowerShell (as Administrator):\n'
            f'$ScriptUrl = "{base_url}/api/v1/collector/install-vm.ps1"\n'
            f'& ([scriptblock]::Create((Invoke-WebRequest -Uri $ScriptUrl).Content)) `\n'
            f'    -Endpoint "{base_url}" `\n'
            f'    -Token "{token}" `\n'
            f'    -EnvName "{name}"'
        )
        alt = {
            "download_and_run": (
                f'Invoke-WebRequest -Uri "{base_url}/api/v1/collector/install-vm.ps1" -OutFile install-vm.ps1\n'
                f'.\\install-vm.ps1 -Endpoint "{base_url}" -Token "{token}" -EnvName "{name}"'
            ),
            "service_check": (
                f'Get-Service OpsBrainCollector\n'
                f'Get-EventLog -LogName Application -Source OpsBrainCollector -Newest 20'
            ),
            "uninstall": (
                f'Stop-Service OpsBrainCollector\n'
                f'& sc.exe delete OpsBrainCollector\n'
                f'Remove-Item -Recurse "C:\\Program Files\\OpsBrainCollector"'
            ),
        }

    else:  # cloud_api — no agent needed
        install_cmd = (
            f'# No agent needed — OpsBrain polls cloud APIs automatically.\n'
            f'# Add your cloud credentials in:\n'
            f'# Connectors → Cloud Providers → Add Data Source\n'
            f'#\n'
            f'# Environment ID for reference: {env_id}'
        )
        alt = {}

    return {
        **token_data,
        "platform_type": pt,
        "install_command": install_cmd,
        "alternative_commands": alt,
    }


@router.get("/environments/{env_id}/ecs-snippet", dependencies=[Depends(require_any)])
async def get_ecs_snippet(env_id: str, request: Request):
    """Returns the ECS task definition sidecar snippet for an enrolled environment."""
    env = enrollment_registry.get(env_id)
    if not env:
        from fastapi import HTTPException
        raise HTTPException(404, "Environment not found")
    from collector.vm_install_script import get_ecs_task_snippet
    base_url = str(request.base_url).rstrip("/")
    return get_ecs_task_snippet(base_url, env.get("token", ""), env.get("env_name", env_id))


@router.get("/environments", dependencies=[Depends(require_any)])
async def list_environments():
    """List all enrolled environments with their connection status."""
    envs = enrollment_registry.list_environments()
    # Augment with live metrics summary
    for env in envs:
        env["metrics_summary"] = metrics_store.summary() if envs else {}
        env["services_tracked"] = metrics_store.list_services(env["env_id"])
    return envs


@router.delete("/environments/{env_id}", dependencies=[Depends(require_admin)])
async def revoke_environment(env_id: str):
    """Revoke an environment's enrollment token. Collector stops being trusted."""
    revoked = enrollment_registry.revoke(env_id)
    if not revoked:
        from fastapi import HTTPException
        raise HTTPException(404, "Environment not found")
    return {"status": "revoked", "env_id": env_id}


# ─── Collection control ───────────────────────────────────────────

@router.get("/status", dependencies=[Depends(require_any)])
async def collection_status():
    return {
        "scheduler_running": scheduler.is_running(),
        "metrics_summary": metrics_store.summary(),
        "recent_collections": metrics_store.collection_status(),
        "enrolled_environments": len(enrollment_registry.list_environments()),
    }


@router.post("/run", dependencies=[Depends(require_admin)])
async def trigger_collection():
    """Trigger an immediate cloud API collection cycle."""
    result = await scheduler.run_now()
    return {"triggered": True, "result": result}


# ─── Metrics query ────────────────────────────────────────────────

@router.get("/metrics/{env_id}", dependencies=[Depends(require_any)])
async def get_env_snapshot(env_id: str):
    return {
        "env_id": env_id,
        "services": metrics_store.list_services(env_id),
        "snapshot": metrics_store.snapshot(env_id),
    }


@router.get("/metrics/{env_id}/{service}/{metric}", dependencies=[Depends(require_any)])
async def get_metric_series(env_id: str, service: str, metric: str, last_n: int = 60):
    return {
        "series": metrics_store.get_series(env_id, service, metric, last_n),
    }
