"""
Built-in SOPs and report templates shipped with OpsBrain.
Loaded on first startup via init_defaults().  Users can edit/delete/add their own.

Design principle:
  SOPs tell Claude WHAT to check and HOW to interpret results.
  Report templates show Claude EXACTLY what the output should look like.
  Claude uses both to produce consistent, high-quality reports.
"""
from __future__ import annotations

# ── SOPs ──────────────────────────────────────────────────────────────────────

SOP_INFRA_HEALTH = """\
# Infrastructure Health Checkout — Standard Operating Procedure
**Version:** 1.0  |  **Owner:** Platform SRE  |  **Applies to:** infra_health checkouts

## Purpose
Systematically assess the health of the Kubernetes cluster and connected AWS infrastructure.
This SOP defines exactly what to check, what tools to call, interpretation thresholds,
and escalation rules.

---

## Data Collection Steps (execute in order)

### Step 1 — Pod Health (Tool: get_pod_status)
**Call:** `get_pod_status(namespace="{namespace}")`

**What to record:**
- Count of pods in each state: Running, Pending, CrashLoopBackOff, OOMKilled, Error
- For each non-Running pod: name, status, restart count, node, age

**Interpretation thresholds:**
| Condition | Severity | Action |
|-----------|----------|--------|
| Any CrashLoopBackOff | 🔴 CRITICAL | Immediate — check logs, consider rollback |
| Any OOMKilled | 🔴 CRITICAL | Increase memory limit or fix leak |
| Pending > 5 minutes | ⚠️ WARNING | Check node capacity and taints |
| Restart count > 10 in last hour | ⚠️ WARNING | Investigate root cause |
| Restart count > 50 | 🔴 CRITICAL | Service is unstable |

---

### Step 2 — Node Resource Utilization (Tool: get_resource_usage)
**Call:** `get_resource_usage(namespace="{namespace}", resource_type="nodes")`

**What to record:** CPU%, Memory%, pod count, allocatable pods per node

**Thresholds:**
| Metric | WARNING | CRITICAL |
|--------|---------|----------|
| Memory % | > 80% | > 90% |
| CPU % | > 75% | > 90% |
| Pod count | > 80% of max | > 90% of max |

**Runway calculation:** If memory growing, estimate days to OOM based on trend.

---

### Step 3 — HPA Scaling Status (Tool: get_hpa_status)
**Call:** `get_hpa_status(namespace="{namespace}")`

**What to record:** Current vs desired vs max replicas, CPU target vs actual, scaling events

**Thresholds:**
| Condition | Severity |
|-----------|----------|
| current >= 80% of max | ⚠️ WARNING |
| current = max AND CPU still high | 🔴 CRITICAL — HPA ceiling hit |
| desired > current for > 5 min | ⚠️ WARNING — slow scaling |

---

### Step 4 — Recent Deployment Review (Tool: get_recent_deployments)
**Call:** `get_recent_deployments(namespace="{namespace}", hours=48)`

**What to record:** Deployment name, image version, timestamp, deployed_by, rollout_status

**Interpretation:**
- Failed rollout in the last 6 hours: ⚠️ WARNING (may be root cause of current issues)
- Failed rollout + active CrashLoopBackOff for same service: 🔴 CRITICAL (deployment caused incident)
- Always check if the deploy commit message explains a config change that could cause issues

---

### Step 5 — Active Alerts (Tool: get_active_alerts)
**Call:** `get_active_alerts(severity_filter="all")`

**What to record:** Alert name, severity, service, message, duration (firing_since)

**Thresholds:**
- Any CRITICAL alert firing > 5 minutes: 🔴 CRITICAL
- Any WARNING alert firing > 30 minutes: ⚠️ WARNING
- Alert count > 10: ⚠️ WARNING (alert fatigue risk)

---

### Step 6 — AWS CloudWatch Alarms (via AWS Connector)
**If AWS connector is configured:**
- Fetch all ALARM-state CloudWatch alarms
- Focus on: EKS, RDS, EC2, Lambda, API Gateway alarms
- Cross-reference with K8s alerts for the same service

**If AWS connector not configured:**
- Note in report: "AWS CloudWatch data not available — configure AWS connector for full coverage"

---

## Health Score Calculation
Start at 100. Deduct:
- Each CRITICAL issue: -15 points
- Each WARNING issue: -5 points
- Each alert firing > 1 hour: -3 points
- Cap deductions at 90 (minimum score is 10 if partially functional)

Score bands: 90-100 = Healthy | 70-89 = Degraded | 50-69 = Unhealthy | < 50 = Critical

---

## Status Determination
- **failed**: Any CRITICAL issue OR health score < 60
- **warning**: Any WARNING issue OR health score 60-79
- **passed**: No issues OR health score >= 80

---

## Escalation Rules
- **failed** report: Notify on-call immediately, create ServiceNow P1 ticket
- **warning** report: Post to Slack ops channel, review at next team standup
- **passed** report: Archive and send summary digest

---

## Report Requirements
Produce a report following the Infrastructure Health Report Template.
Use actual numbers — never say "some pods" when you can say "3 pods".
Every finding must include the service name and specific metric value.
"""

SOP_COST_REVIEW = """\
# Cloud Cost Review Checkout — Standard Operating Procedure
**Version:** 1.0  |  **Owner:** FinOps Team  |  **Applies to:** cost_review checkouts

## Purpose
Systematically assess cloud spend, identify waste, detect anomalies, and produce
actionable savings recommendations within a defined review window.

---

## Data Collection Steps (execute in order)

### Step 1 — Current Month Spend vs Previous Month (Tool: get_cloud_cost_breakdown)
**Call:** `get_cloud_cost_breakdown(cloud="all", months=1)`

**What to record:**
- Total MTD spend ($)
- Previous month total ($)
- Month-over-month change (%)
- Top 5 services by cost and their individual trends

**Interpretation:**
| MoM Growth | Severity |
|------------|----------|
| < 5% | ✅ Normal |
| 5–15% | ⚠️ Elevated — investigate cause |
| > 15% | 🔴 High — immediate review required |
| > 30% | 🔴 CRITICAL — likely misconfiguration or runaway resource |

---

### Step 2 — Waste and Underutilized Resources (Tool: get_underutilized_resources)
**Call:** `get_underutilized_resources(resource_type="all", utilization_threshold_pct=20)`

**What to record per resource:**
- Resource ID, type, instance size, avg CPU%, avg connections (RDS), monthly cost, estimated savings

**Interpretation:**
| CPU % (7-day avg) | Action |
|-------------------|--------|
| < 5% | Downsize immediately or delete |
| 5–20% | Downsize one tier — strong savings candidate |
| 20–40% | Monitor — may have peak traffic patterns |

**Priority formula:** Rank by `estimated_savings_usd DESC` — highest savings = highest priority.

---

### Step 3 — Cost Anomaly Detection (Tool: get_cost_anomalies)
**Call:** `get_cost_anomalies(days=30, threshold_pct=20)`

**What to record:** Service, spike date, baseline daily cost, anomaly daily cost, % change, likely cause

**Interpretation:**
- > 50% day-over-day spike: 🔴 CRITICAL — likely misconfiguration (e.g., debug logging, runaway autoscaling)
- 20–50% spike: ⚠️ WARNING — expected traffic event or needs investigation
- Recurring anomalies for same service: systemic issue (e.g., HPA always scaling up on Tuesdays)

---

### Step 4 — Kubernetes Rightsizing (Tool: get_rightsizing_recommendations)
**Call:** `get_rightsizing_recommendations(namespace="{namespace}", min_savings_usd=50)`

**What to record:** Workload, current requests vs actual usage, recommended requests, savings/month

**Priority criteria:**
1. Savings > $500/mo — implement this sprint
2. Savings $100–$500/mo — implement next sprint
3. Savings < $100/mo — batch together quarterly

---

### Step 5 — Real AWS Cost Data (via AWS Connector)
**If AWS connector configured:** Override mock data with real Cost Explorer data.
Note: `source: aws_live` in the data indicates real data is available.

---

## Savings Opportunity Ranking
List all identified savings sorted by:
1. Monthly savings amount (highest first)
2. Implementation effort (prefer low-effort items at top of each tier)
3. Risk (prefer lower-risk items)

---

## Status Determination
- **failed**: MoM growth > 30% OR cost anomaly > $5,000/day unexplained
- **warning**: MoM growth > 15% OR total waste > 20% of spend OR unresolved anomaly
- **passed**: Growth < 15%, waste < 15% of spend, no unexplained anomalies

---

## Report Requirements
- Always show dollar amounts — never percentages alone
- Include a "Total identifiable savings: $X/month" headline
- Rank recommendations by ROI not by category
- Include the exact kubectl or AWS CLI command to fix each rightsizing issue
"""

SOP_CAPACITY_REVIEW = """\
# Capacity Planning Checkout — Standard Operating Procedure
**Version:** 1.0  |  **Owner:** Infrastructure Team  |  **Applies to:** capacity_review checkouts

## Purpose
Forecast infrastructure capacity requirements, identify resource runways, and ensure
the platform has sufficient headroom for the next review period.

---

## Data Collection Steps (execute in order)

### Step 1 — Node Resource Utilization (Tool: get_resource_usage)
**Call:** `get_resource_usage(namespace="{namespace}", resource_type="nodes")`

For each node record: CPU%, Memory%, current pod count, max pod capacity.
Calculate cluster-level averages.

**Runway estimation formula:**
If Memory% growing ~X% per day → Days until 95% full = (95 - current%) / X
Apply to each node individually and report the shortest runway.

---

### Step 2 — Pod Resource Usage vs Requests (Tool: get_resource_usage)
**Call:** `get_resource_usage(namespace="{namespace}", resource_type="pods")`

For each pod: actual CPU (millicores), actual memory (Mi), vs requests/limits.
Identify pods where actual << requested (over-provisioned waste).
Identify pods where actual ≈ limit (at risk of OOM or throttling).

**Efficiency score per pod:**
- Actual CPU / CPU limit < 30%: Over-provisioned
- Actual memory / memory limit > 85%: At OOM risk

---

### Step 3 — HPA Headroom Analysis (Tool: get_hpa_status)
**Call:** `get_hpa_status(namespace="{namespace}")`

For each HPA:
- Current replicas / Max replicas = headroom%
- If headroom < 30%: WARNING — may hit ceiling under load
- If headroom < 10%: CRITICAL — will hit ceiling imminently

Also check: Is cluster autoscaler enabled? If HPA hits max but cluster can't add nodes, we have a hard ceiling.

---

### Step 4 — Service Metric Trends (Tool: query_metrics per service)
**For each service in ["order-service", "payment-service", "auth-service", "notification-svc"]:**
**Call:** `query_metrics(service="{svc}", metric="cpu_usage", window_minutes=1440)`
**Call:** `query_metrics(service="{svc}", metric="memory_usage", window_minutes=1440)`

Plot trend: is resource usage growing, stable, or declining?
Extrapolate: at current growth rate, when does it hit 80% of limit?

---

## Capacity Planning Output

### Runway Table (required in report)
| Resource | Current % | Growth Rate | Days to 80% | Days to 95% |
|----------|-----------|-------------|-------------|-------------|
| node-1 CPU | 71% | +2%/day | 4d | 12d |
| node-2 Memory | 92% | +1%/day | 0d (already at 92%) | Immediate |

### HPA Ceiling Risk Table (required in report)
| Service | Current | Max | Headroom | Risk |
|---------|---------|-----|----------|------|
| payment-service | 7/10 | 10 | 30% | MEDIUM |

---

## Status Determination
- **failed**: Any resource with < 7 days runway OR any HPA with headroom < 10%
- **warning**: Any resource with 7–30 days runway OR any HPA with headroom < 30%
- **passed**: All resources > 30 days runway AND all HPAs > 30% headroom

---

## Required Decisions
The report MUST answer:
1. Do we need to add nodes in the next 30 days? (Yes/No + by when)
2. Which workloads need rightsizing this sprint?
3. What is the estimated monthly cost of adding required capacity?
"""

SOP_SLO_REVIEW = """\
# SLO & Reliability Review Checkout — Standard Operating Procedure
**Version:** 1.0  |  **Owner:** Reliability Engineering  |  **Applies to:** slo_review checkouts

## Purpose
Evaluate per-service SLO compliance, identify reliability trends, and maintain
a traffic-light reliability scorecard.

## SLO Definitions (baseline — override in custom_prompt if different)
| Service | Error Rate SLO | p99 Latency SLO | Availability SLO |
|---------|---------------|-----------------|------------------|
| api-gateway | < 0.1% | < 50ms | 99.99% |
| auth-service | < 0.5% | < 200ms | 99.95% |
| payment-service | < 0.5% | < 500ms | 99.9% |
| order-service | < 1.0% | < 1000ms | 99.5% |
| notification-svc | < 2.0% | < 2000ms | 99.0% |

---

## Data Collection Steps

### Step 1 — Error Rate per Service (Tool: query_metrics)
**For each service:**
**Call:** `query_metrics(service="{svc}", metric="error_rate", window_minutes=1440)`

Record: current value, avg over window, peak value, SLO threshold.
Calculate: Is current value within SLO? How much headroom?

**Traffic light logic:**
- 🟢 GREEN: current < SLO threshold AND avg < SLO
- 🟡 YELLOW: current < SLO but avg within 50% of threshold, OR trending toward breach
- 🔴 RED: current >= SLO threshold (SLO breached)

---

### Step 2 — Latency p99 per Service (Tool: query_metrics)
**Call:** `query_metrics(service="{svc}", metric="latency_p99", window_minutes=1440)`

Record: current p99, avg p99, max p99, SLO threshold.

---

### Step 3 — Throughput (RPS) per Service (Tool: query_metrics)
**Call:** `query_metrics(service="{svc}", metric="rps", window_minutes=1440)`

Note significant drops in RPS (may indicate service is returning errors causing clients to stop retrying).

---

### Step 4 — Active Alerts (Tool: get_active_alerts)
**Call:** `get_active_alerts(severity_filter="all")`

Record: total count, breakdown by severity, duration of longest-firing alert.
Alert noise score = (total alerts) / (number of actionable alerts).
If noise score > 3: flag as alert fatigue.

---

### Step 5 — Pod Availability (Tool: get_pod_status)
**Call:** `get_pod_status(namespace="{namespace}")`

For services with non-Running pods: note availability impact.

---

## SLO Burn Rate Calculation
For each service:
- Error budget consumed = (error_rate_actual - 0) / (SLO_threshold - 0) × 100%
- If > 100%: SLO breached
- If 80–100%: at risk (WARNING)
- If < 80%: healthy

---

## Status Determination
- **failed**: Any service with SLO breach (error rate > threshold OR latency > threshold)
- **warning**: Any service within 20% of SLO threshold OR alert noise > 3
- **passed**: All services within SLO with > 20% headroom

---

## Report Requirements
The report MUST include:
1. SLO Scorecard table — one row per service with traffic light
2. Error budget remaining per service (% and hours)
3. Top 3 reliability risks for the next period
4. Recommended SLO adjustments if any service consistently passes/fails
"""

SOP_INCIDENT_REVIEW = """\
# Incident Retrospective Checkout — Standard Operating Procedure
**Version:** 1.0  |  **Owner:** On-Call Engineering  |  **Applies to:** incident_review checkouts

## Purpose
Review the incident landscape for the period, identify patterns, assess response quality,
and surface systemic improvements.

---

## Data Collection Steps

### Step 1 — Active & Recent Alerts (Tool: get_active_alerts)
**Call:** `get_active_alerts(severity_filter="all")`

Record: all currently firing alerts with severity, service, duration.
Any alert firing > 1 hour = outstanding incident requiring attention.

---

### Step 2 — Pod Status for Incident Evidence (Tool: get_pod_status)
**Call:** `get_pod_status(namespace="{namespace}")`

Correlate unhealthy pods with alerts: is there a CrashLoopBackOff that
corresponds to an active alert?

---

### Step 3 — Recent Deployments (Tool: get_recent_deployments)
**Call:** `get_recent_deployments(namespace="{namespace}", hours=72)`

For the review window, identify:
- How many deployments were made?
- Which deployments failed?
- Did any failed deployment correlate with an incident?
- Deployment-to-incident ratio (if > 30% of deploys cause incidents: process risk)

---

### Step 4 — Error Log Analysis per Service (Tool: query_logs)
**For each of ["order-service", "payment-service", "auth-service"]:**
**Call:** `query_logs(service="{svc}", query="ERROR|FATAL|panic|exception", severity="ERROR", window_minutes=4320)`

Record: total error count, most frequent error pattern, latest error.
High error count with low alert count = possible missed alerting gap.

---

## Incident Pattern Analysis (Claude's job after data collection)

**Recurring incident detection:**
If the same alert fires 3+ times in the review window = recurring incident.
Root cause has NOT been fixed. Escalate.

**Deployment causation:**
If a deployment precedes an incident by < 30 minutes = deployment likely caused incident.
Track deployment-caused incidents as % of total.

**MTTR assessment:**
From alert firing time → pod/service recovery.
Target MTTR: P0 < 15min, P1 < 1h, P2 < 4h.

**Alert quality score:**
= (actionable alerts) / (total alerts) × 100
- > 80%: Good alert hygiene
- 50–80%: Needs review — some noise
- < 50%: Alert fatigue — engineers ignoring alerts (dangerous)

---

## Status Determination
- **failed**: Any active incident (alert firing > 30min) OR recurring incident (3+ same alert)
- **warning**: Any alert > 1h without resolution OR alert quality < 60% OR deployment-caused incidents > 20%
- **passed**: No active incidents, alert quality > 80%, no recurring patterns

---

## Required Report Sections
1. Incident Summary — total count, severity breakdown, MTTR for each
2. Deployment Analysis — # deploys, # failures, causation analysis
3. Recurring Patterns — any systemic issues
4. Alert Quality Score — with top 3 alerts to tune or remove
5. Top 3 Systemic Improvements with estimated incident reduction %
"""

# ── Report Templates ──────────────────────────────────────────────────────────

TEMPLATE_INFRA_HEALTH = """\
# Infrastructure Health Report
**Date:** {{date}} UTC  |  **Namespace:** {{namespace}}  |  **Schedule:** {{frequency}}
**Generated by:** OpsBrain AI  |  **Data sources:** {{sources}}

---

## Overall Status: {{STATUS_EMOJI}} {{STATUS}} — Health Score: {{SCORE}}/100

> {{EXECUTIVE_SUMMARY}}

---

## Component Health Summary

| Component | Status | Key Metric | Action Required |
|-----------|--------|-----------|-----------------|
| Pods | 🔴 CRITICAL | 1 CrashLoopBackOff (order-service, 23 restarts) | Rollback order-service:v2.4.1 |
| Nodes | ⚠️ WARNING | node-2 at 92% memory | Add node within 3 days |
| HPA | ⚠️ WARNING | payment-service at 7/10 replicas | Monitor — ceiling risk |
| Deployments | ⚠️ WARNING | 1 failed rollout (9 min ago) | Rollback completed ✓ |
| Alerts | ⚠️ WARNING | 2 critical, 2 warning | See alerts section |
| AWS CloudWatch | ✅ HEALTHY | 0 alarms firing | — |

---

## Pod Status

| Pod | Status | Restarts | Node | Issue |
|-----|--------|----------|------|-------|
| order-service-8f9g0h-def34 | 🔴 CrashLoopBackOff | 23 | node-2 | DB connection pool exhausted |
| payment-service-7d9f8b-bv3r1 | ⚠️ Running | 14 | node-3 | High restart count — memory pressure |
| notification-svc-2b3c4d-ghi56 | ⚠️ Pending | 0 | — | Insufficient memory on available nodes |
| auth-service-5c6d7e-abc12 | ✅ Running | 0 | node-1 | Healthy |

---

## Node Utilization

| Node | CPU | Memory | Pod Slots | Status |
|------|-----|--------|-----------|--------|
| node-1 | 71% | 83% | 18/30 | ⚠️ WARNING (memory) |
| node-2 | 45% | **92%** | 22/30 | 🔴 CRITICAL (memory — 3d runway) |
| node-3 | 12% | 34% | 9/30 | ✅ HEALTHY |
| **Cluster avg** | **43%** | **70%** | **49/90** | |

---

## Active Alerts ({{ALERT_COUNT}} firing)

| Severity | Alert | Service | Firing Since | Duration |
|----------|-------|---------|-------------|----------|
| 🔴 CRITICAL | PodCrashLoopBackOff | order-service | 14:52 UTC | 8 min |
| 🔴 CRITICAL | HighErrorRate | order-service | 14:53 UTC | 7 min |
| ⚠️ WARNING | HPAMaxReplicas | payment-service | 14:56 UTC | 4 min |
| ⚠️ WARNING | NodeMemoryPressure | node-2 | 14:45 UTC | 15 min |

---

## Recent Deployments (last 48h)

| Service | Version | Deployed By | Time | Status |
|---------|---------|-------------|------|--------|
| order-service | :v2.4.0 → :v2.4.1 | ci-pipeline | 14:52 UTC (-9m) | 🔴 FAILED |
| payment-service | :v1.9.5 → :v1.9.6 | alice@company.com | 12:00 UTC (-2h) | ✅ SUCCESS |

---

## AWS Infrastructure

| Service | Status | Details |
|---------|--------|---------|
| EKS Cluster prod-cluster | ✅ ACTIVE | v1.28, endpoint healthy |
| CloudWatch Alarms | ✅ 0 firing | Last checked: {{date}} |

---

## Analysis

{{ANALYSIS_NARRATIVE}}

---

## Recommendations

| Priority | Action | Expected Impact | Effort | Owner |
|----------|--------|-----------------|--------|-------|
| P0 | Rollback order-service to v2.4.0 | Restore 4,200 user orders immediately | Low (2 min) | On-call SRE |
| P0 | Add 1 node to ng-general-purpose | Prevent node-2 OOM in 3 days | Medium (30 min) | Infra team |
| P1 | Fix DB connection pool config in v2.4.2 | Prevent recurrence | Medium | order-service team |
| P1 | Enable cluster autoscaler scale-down | Save ~$640/mo, prevent ceiling issues | Medium | Infra |
| P2 | Investigate payment-service memory leak | Prevent future OOM | High | payment-service team |
"""

TEMPLATE_COST_REVIEW = """\
# Cloud Cost Review Report
**Date:** {{date}} UTC  |  **Review Period:** {{window}}  |  **Schedule:** {{frequency}}
**Generated by:** OpsBrain AI  |  **Data source:** {{source}}

---

## Overall Status: {{STATUS_EMOJI}} {{STATUS}}

> {{EXECUTIVE_SUMMARY}}

---

## Spend Summary

| Metric | This Period | Last Period | Change |
|--------|------------|------------|--------|
| Total Spend | $34,820 | $31,450 | **+$3,370 (+10.7%)** ⚠️ |
| Identified Waste | $7,240/mo | $6,100/mo | +18.7% |
| Waste as % of Spend | 20.8% | 19.4% | +1.4pp |
| **Estimated Savings Available** | **$7,240/mo** | | |

---

## Spend by Service

| Service | Monthly Cost | % of Total | MoM Trend | Status |
|---------|-------------|-----------|-----------|--------|
| EC2 (compute) | $12,400 | 35.6% | +8% | ⚠️ Growing |
| RDS (databases) | $8,200 | 23.6% | +2% | ✅ Stable |
| EKS clusters | $6,800 | 19.5% | **+22%** | 🔴 High growth |
| Data Transfer | $3,100 | 8.9% | +5% | ✅ Acceptable |
| S3 Storage | $2,400 | 6.9% | +1% | ✅ Stable |
| CloudWatch/Logging | $1,920 | 5.5% | **+45%** | 🔴 Anomaly |

---

## Waste & Savings Opportunities (ranked by savings)

| # | Resource | Type | Monthly Cost | Avg CPU | Est. Savings | Action | Effort |
|---|----------|------|-------------|---------|-------------|--------|--------|
| 1 | prod-reporting-db | RDS db.r6g.2xlarge | $1,840 | 3.2% | **$1,520/mo** | Migrate to Aurora Serverless v2 | Medium |
| 2 | ng-general-purpose | EKS node group (6 nodes) | $2,880 | 22% | **$960/mo** | Enable cluster autoscaler, scale to 4 nodes | Medium |
| 3 | CloudWatch logging | Log ingestion | $1,920 | — | **$820/mo** | Set LOG_LEVEL=INFO in production | **Low (2 min)** |
| 4 | analytics-worker-01 | EC2 m5.4xlarge | $560 | 8.1% | **$480/mo** | Downsize to m5.large | Low |
| 5 | elasticsearch-data-pvc | PVC 2TB → 250GB | $200 | — | **$182/mo** | Resize PVC | Low |
| | **TOTAL** | | **$7,400** | | **$3,962/mo** | | |

---

## Cost Anomalies

| Service | Date | Baseline/day | Spike/day | Change | Root Cause |
|---------|------|-------------|-----------|--------|-----------|
| CloudWatch/Logging | Apr 18 | $45 | $210 | **+366%** 🔴 | Debug logging enabled in production |
| EKS clusters | Apr 15 | $185 | $312 | +68.6% ⚠️ | HPA scale-out not scaled back down |

---

## Quick Wins (implement this week, < 4 hours total)

```bash
# 1. Fix debug logging — saves $820/mo immediately (2 min)
kubectl set env deployment/order-service LOG_LEVEL=INFO -n production

# 2. Resize elasticsearch PVC — saves $182/mo (30 min)
kubectl patch pvc elasticsearch-data-pvc -p '{"spec":{"resources":{"requests":{"storage":"300Gi"}}}}'

# 3. Downsize analytics-worker-01 — saves $480/mo (1h)
aws ec2 modify-instance-attribute --instance-id i-0a1b2c3d4e5f --instance-type m5.large
```

---

## Analysis

{{ANALYSIS_NARRATIVE}}

---

## Recommendations

| Priority | Action | Savings/mo | Effort | Risk | Owner |
|----------|--------|-----------|--------|------|-------|
| P0 — This week | Fix CloudWatch debug logging | $820 | Low | None | order-service team |
| P0 — This week | Downsize analytics-worker-01 | $480 | Low | Low | Infra |
| P1 — This sprint | Migrate prod-reporting-db to Aurora Serverless | $1,520 | Medium | Low | Data team |
| P1 — This sprint | Enable cluster autoscaler on ng-general-purpose | $960 | Medium | Low | Infra |
| P2 — Next quarter | Resize elasticsearch PVC | $182 | Low | Low | Storage team |
"""

TEMPLATE_SLO_REVIEW = """\
# SLO & Reliability Scorecard
**Date:** {{date}} UTC  |  **Review Period:** {{window}}  |  **Schedule:** {{frequency}}
**Generated by:** OpsBrain AI

---

## Overall Status: {{STATUS_EMOJI}} {{STATUS}}

> {{EXECUTIVE_SUMMARY}}

---

## SLO Scorecard

| Service | Status | Error Rate | SLO | Headroom | p99 Latency | SLO | Headroom |
|---------|--------|-----------|-----|---------|------------|-----|---------|
| api-gateway | 🟢 | 0.1% | 0.1% | At limit | 12ms | 50ms | 76% |
| auth-service | 🟢 | 0.2% | 0.5% | 60% | 43ms | 200ms | 78% |
| payment-service | 🟢 | 0.3% | 0.5% | 40% | 46ms | 500ms | 91% |
| order-service | 🔴 | **97.8%** | 1.0% | **BREACHED** | N/A (crashing) | 1000ms | N/A |
| notification-svc | 🟡 | 3.8% | 2.0% | **BREACHED** | 112ms | 2000ms | 94% |

---

## Error Budget Remaining

| Service | Error Budget (30d) | Consumed | Remaining | Burn Rate |
|---------|-------------------|---------|-----------|-----------|
| order-service | 720 min | **720 min** | **0 min** | 🔴 Exhausted |
| notification-svc | 1,440 min | 2,736 min | **-1,296 min** | 🔴 Exhausted |
| payment-service | 2,160 min | 1,296 min | 864 min | 🟡 Caution |
| auth-service | 2,160 min | 864 min | 1,296 min | 🟢 Healthy |
| api-gateway | 432 min | 432 min | 0 min | 🟡 At limit |

---

## Alert Volume

| Metric | Value | Status |
|--------|-------|--------|
| Total alerts fired (period) | 47 | |
| Actionable alerts | 38 | |
| Noise / false positives | 9 | |
| Alert quality score | **80.9%** | ✅ Good |
| Longest-firing alert | NodeMemoryPressure (15 min) | |

---

## Reliability Risks for Next Period

1. **order-service** — zero error budget remaining; any future incident will immediately breach SLO
2. **notification-svc** — consistently above SLO threshold; upstream dependency on order-service causing cascading errors
3. **api-gateway** — error budget exactly consumed; one bad deploy could breach SLO

---

## Analysis

{{ANALYSIS_NARRATIVE}}

---

## Recommendations

| Priority | Service | Action | Expected Improvement |
|----------|---------|--------|---------------------|
| P0 | order-service | Resolve active CrashLoopBackOff, implement error budget policy | Restore from SLO breach |
| P1 | notification-svc | Circuit-break order-service dependency during incidents | Reduce cascading failures |
| P1 | api-gateway | Tighten SLO from 0.1% → 0.05% after fixing root causes | Better early warning |
| P2 | All | Review 9 noisy alerts — tune or remove | Reduce alert fatigue |
"""

# ── Default doc manifest ───────────────────────────────────────────────────────

DEFAULT_DOCS = [
    # SOPs
    {
        "name": "Infrastructure Health SOP",
        "doc_type": "sop",
        "checkout_types": ["infra_health"],
        "description": "Step-by-step procedure for Kubernetes + AWS infrastructure health checks. Defines what tools to call, thresholds, and escalation rules.",
        "content": SOP_INFRA_HEALTH,
    },
    {
        "name": "Cost Review SOP",
        "doc_type": "sop",
        "checkout_types": ["cost_review"],
        "description": "Procedure for cloud spend analysis — Cost Explorer, waste identification, anomaly detection, and rightsizing.",
        "content": SOP_COST_REVIEW,
    },
    {
        "name": "Capacity Planning SOP",
        "doc_type": "sop",
        "checkout_types": ["capacity_review"],
        "description": "Resource runway calculation, HPA headroom analysis, and capacity provisioning decisions.",
        "content": SOP_CAPACITY_REVIEW,
    },
    {
        "name": "SLO Review SOP",
        "doc_type": "sop",
        "checkout_types": ["slo_review"],
        "description": "SLO compliance checking, error budget tracking, and reliability scoring per service.",
        "content": SOP_SLO_REVIEW,
    },
    {
        "name": "Incident Retrospective SOP",
        "doc_type": "sop",
        "checkout_types": ["incident_review"],
        "description": "Incident pattern analysis, MTTR assessment, alert quality scoring, and systemic improvement identification.",
        "content": SOP_INCIDENT_REVIEW,
    },
    # Report templates
    {
        "name": "Infrastructure Health Report Template",
        "doc_type": "report_template",
        "checkout_types": ["infra_health"],
        "description": "Sample report showing exact format, tables, and sections expected in an infra health checkout output.",
        "content": TEMPLATE_INFRA_HEALTH,
    },
    {
        "name": "Cost Review Report Template",
        "doc_type": "report_template",
        "checkout_types": ["cost_review"],
        "description": "Sample cost review report with spend tables, waste ranking, quick wins, and recommendations.",
        "content": TEMPLATE_COST_REVIEW,
    },
    {
        "name": "SLO Scorecard Report Template",
        "doc_type": "report_template",
        "checkout_types": ["slo_review"],
        "description": "Sample SLO report with traffic-light scorecard, error budget, alert quality score.",
        "content": TEMPLATE_SLO_REVIEW,
    },
]


def init_defaults() -> None:
    """Load built-in docs on first startup — skip if they already exist."""
    from knowledge.store import create_doc, doc_exists_by_name
    from knowledge.models import KnowledgeDocCreate, DocType

    for d in DEFAULT_DOCS:
        if not doc_exists_by_name(d["name"]):
            create_doc(
                KnowledgeDocCreate(
                    name=d["name"],
                    doc_type=DocType(d["doc_type"]),
                    checkout_types=d["checkout_types"],
                    description=d["description"],
                    content=d["content"],
                ),
                is_default=True,
            )
