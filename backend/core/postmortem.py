"""
Auto Post-Mortem Generator — blameless, structured post-mortems from incident data.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime

from core.claude_client import ClaudeClient


@dataclass
class IncidentData:
    title: str
    service: str
    severity: str
    started_at: str
    resolved_at: str
    detected_by: str
    resolved_by: str
    affected_users: int
    error_rate_peak_pct: float
    timeline_events: list[dict] = field(default_factory=list)
    root_cause_notes: str = ""
    actions_taken: list[str] = field(default_factory=list)


class PostMortemGenerator:
    def __init__(self, claude: ClaudeClient) -> None:
        self.claude = claude

    async def generate(self, incident: IncidentData) -> dict:
        """Generate a complete blameless post-mortem document."""
        timeline_str = "\n".join(
            f"  - {e.get('time', '')}: {e.get('event', '')}" for e in incident.timeline_events
        )
        actions_str = "\n".join(f"  - {a}" for a in incident.actions_taken)

        prompt = f"""
Generate a complete blameless post-mortem for this incident:

INCIDENT DETAILS:
Title: {incident.title}
Service: {incident.service}
Severity: {incident.severity}
Start: {incident.started_at}
Resolved: {incident.resolved_at}
Detected by: {incident.detected_by}
Resolved by: {incident.resolved_by}
Affected users: {incident.affected_users:,}
Peak error rate: {incident.error_rate_peak_pct}%

TIMELINE:
{timeline_str if timeline_str else '  - No timeline provided'}

ROOT CAUSE NOTES:
{incident.root_cause_notes or 'No notes provided — infer from available data'}

ACTIONS TAKEN DURING INCIDENT:
{actions_str if actions_str else '  - No actions recorded'}

Generate the full post-mortem document. Include:
1. Duration and exact MTTR
2. Complete 5-whys root cause analysis
3. Quantified business impact (estimate revenue impact if not provided)
4. Concrete action items with: owner placeholder, priority (P0/P1/P2), effort (S/M/L), and due date (relative: 1 week / 2 weeks / 1 month)
5. Detection gap analysis: could this have been caught earlier?
6. A "what we're proud of" section highlighting the response that worked well
"""
        result = await self.claude.analyze(agent_type="postmortem", user_message=prompt)
        return {
            "incident_title": incident.title,
            "service": incident.service,
            "severity": incident.severity,
            "document": result["text"],
            "generated_at": datetime.utcnow().isoformat() + "Z",
            "usage": result.get("usage", {}),
        }

    async def generate_action_items(self, postmortem_text: str) -> dict:
        """Extract structured action items from a post-mortem document."""
        prompt = f"""
Extract all action items from this post-mortem and return them as a structured JSON list.

POST-MORTEM:
{postmortem_text}

Return a JSON array where each item has:
- title: short description
- category: one of [detection, prevention, process, monitoring, documentation]
- priority: P0/P1/P2
- effort: S/M/L (Small <1 day, Medium 1-3 days, Large 1+ week)
- due_in_days: number of days until due (7, 14, or 30)

Respond with ONLY the JSON array, no other text.
"""
        result = await self.claude.analyze(agent_type="postmortem", user_message=prompt)
        return {"action_items_raw": result["text"]}
