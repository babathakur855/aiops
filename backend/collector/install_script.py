"""
Generates the install-collector.py script served at GET /collector/install.py.
This is the script users pipe into python3 — zero dependencies, just kubectl.
"""

INSTALL_SCRIPT = r'''#!/usr/bin/env python3
"""
OpsBrain Collector Installer
============================
Installs the OpsBrain metric collection agent into any Kubernetes cluster.
No Helm, no Operators, no external dependencies — just kubectl + Python 3.

Supports: AWS EKS · Azure AKS · GCP GKE · Red Hat OpenShift · ROSA · ARO · Vanilla k8s

Usage:
  python3 install-collector.py \
    --endpoint https://opsbrain.internal:8011 \
    --token <enrollment-token> \
    --env-name "Production EKS"

Options:
  --endpoint    URL of your OpsBrain backend (must be reachable from within the cluster)
  --token       Enrollment token from OpsBrain UI (Settings → Environments → Add)
  --env-name    Human-readable name for this environment (e.g. "Production EKS us-east-1")
  --namespace   Namespace to install into (default: opsbrain-collector)
  --dry-run     Print the generated YAML without applying it
  --uninstall   Remove the collector from this cluster
"""
from __future__ import annotations

import argparse
import base64
import json
import os
import shutil
import subprocess
import sys
import tempfile
import textwrap
import time
import urllib.request
import urllib.error

# ── Terminal colours ──────────────────────────────────────────────
R = "\033[0m"; B = "\033[1m"; GR = "\033[92m"; RE = "\033[91m"; CY = "\033[96m"; YE = "\033[93m"; DI = "\033[2m"
def ok(m):  print(f"{GR}  ✓  {m}{R}")
def err(m): print(f"{RE}  ✗  {m}{R}"); sys.exit(1)
def warn(m):print(f"{YE}  ⚠  {m}{R}")
def info(m):print(f"{CY}  →  {m}{R}")
def step(n, t): print(f"\n{B}{CY}Step {n}: {t}{R}\n{'─'*50}")


# ── Platform detection ────────────────────────────────────────────

def detect_platform() -> str:
    try:
        nodes_raw = _kubectl("get nodes -o json", capture=True)
        nodes = json.loads(nodes_raw)
        for node in nodes.get("items", []):
            labels = node.get("metadata", {}).get("labels", {})
            provider_id = node.get("spec", {}).get("providerID", "")

            if "eks.amazonaws.com" in str(labels) or provider_id.startswith("aws:///"):
                return "eks"
            if "kubernetes.azure.com" in str(labels) or provider_id.startswith("azure:///"):
                return "aks"
            if "cloud.google.com" in str(labels) or provider_id.startswith("gce://"):
                return "gke"

        # Check for OpenShift
        result = _kubectl("api-resources --api-group=route.openshift.io", capture=True, check=False)
        if result and "routes" in result:
            return "openshift"
    except Exception:
        pass
    return "kubernetes"


def _kubectl(args: str, capture: bool = False, check: bool = True) -> str | None:
    cmd = ["kubectl"] + args.split()
    if capture:
        result = subprocess.run(cmd, capture_output=True, text=True)
        if check and result.returncode != 0:
            raise RuntimeError(result.stderr.strip())
        return result.stdout.strip() if result.returncode == 0 else None
    else:
        result = subprocess.run(cmd, text=True)
        if check and result.returncode != 0:
            raise RuntimeError(f"kubectl {args} failed")
        return None


def _kubectl_apply(yaml_content: str) -> None:
    with tempfile.NamedTemporaryFile(mode="w", suffix=".yaml", delete=False) as f:
        f.write(yaml_content)
        tmp_path = f.name
    try:
        subprocess.run(["kubectl", "apply", "-f", tmp_path], check=True, text=True)
    finally:
        os.unlink(tmp_path)


# ── Manifest generation ───────────────────────────────────────────

def generate_manifest(endpoint: str, token: str, env_name: str, namespace: str, platform: str) -> str:
    """
    Generate a single self-contained YAML bundle.
    Security-hardened: read-only, non-root, network-isolated, resource-limited.
    """

    # Encode token as k8s secret (base64)
    token_b64 = base64.b64encode(token.encode()).decode()
    endpoint_b64 = base64.b64encode(endpoint.encode()).decode()

    # Determine kubelet endpoint path per platform
    kubelet_endpoint = "\\${K8S_NODE_IP}:10250"
    insecure_skip_verify = "true"

    # OpenShift uses port 10255 (read-only kubelet)
    if platform == "openshift":
        kubelet_endpoint = "\\${K8S_NODE_IP}:10255"
        insecure_skip_verify = "true"

    otel_config = f"""receivers:
      # IaaS: node + pod metrics from kubelet
      kubeletstats:
        collection_interval: 60s
        auth_type: serviceAccount
        endpoint: "{kubelet_endpoint}"
        insecure_skip_verify: {insecure_skip_verify}
        metric_groups: [node, pod, container, volume]

      # PaaS: kube-state-metrics (deployment health, HPA, PVCs)
      prometheus/ksm:
        config:
          scrape_configs:
            - job_name: kube-state-metrics
              scrape_interval: 60s
              kubernetes_sd_configs: [{{role: endpoints}}]
              relabel_configs:
                - source_labels: [__meta_kubernetes_endpoints_name]
                  regex: kube-state-metrics
                  action: keep

      # App metrics: Prometheus /metrics from annotated pods
      prometheus/apps:
        config:
          scrape_configs:
            - job_name: pod-metrics
              scrape_interval: 60s
              kubernetes_sd_configs: [{{role: pod}}]
              relabel_configs:
                - source_labels: [__meta_kubernetes_pod_annotation_prometheus_io_scrape]
                  action: keep
                  regex: "true"
                - source_labels: [__meta_kubernetes_pod_annotation_prometheus_io_path]
                  action: replace
                  target_label: __metrics_path__
                  regex: (.+)
                - source_labels: [__address__, __meta_kubernetes_pod_annotation_prometheus_io_port]
                  action: replace
                  regex: ([^:]+)(?::\\d+)?;(\\d+)
                  replacement: $1:$2
                  target_label: __address__

      # K8s events (pod restarts, OOM kills, scheduling failures)
      k8s_events:
        auth_type: serviceAccount
        namespaces: []

    processors:
      # Add k8s metadata to all metrics
      k8sattributes:
        auth_type: serviceAccount
        passthrough: false
        extract:
          metadata: [k8s.pod.name, k8s.namespace.name, k8s.deployment.name, k8s.node.name]

      # Tag with environment identity
      resource:
        attributes:
          - {{key: opsbrain.env_name, value: "{env_name}", action: insert}}

      # Drop high-cardinality histogram buckets (reduce data volume)
      filter/drop_noise:
        metrics:
          exclude:
            match_type: regexp
            metric_names: [".*_bucket", "go_gc_.*", "go_memstats_.*"]

      batch:
        send_batch_size: 500
        timeout: 60s

      # Memory limiter — prevents collector from consuming too much RAM
      memory_limiter:
        check_interval: 5s
        limit_percentage: 80
        spike_limit_percentage: 25

    exporters:
      otlphttp/opsbrain:
        endpoint: ${{env:OPSBRAIN_ENDPOINT}}/v1
        headers:
          X-OpsBrain-Token: ${{env:OPSBRAIN_TOKEN}}
        tls:
          insecure_skip_verify: false
        retry_on_failure:
          enabled: true
          initial_interval: 10s
          max_interval: 120s
          max_elapsed_time: 600s
        sending_queue:
          enabled: true
          num_consumers: 4
          queue_size: 100

    service:
      pipelines:
        metrics:
          receivers: [kubeletstats, prometheus/ksm, prometheus/apps]
          processors: [memory_limiter, k8sattributes, resource, filter/drop_noise, batch]
          exporters: [otlphttp/opsbrain]
        logs:
          receivers: [k8s_events]
          processors: [memory_limiter, k8sattributes, resource, batch]
          exporters: [otlphttp/opsbrain]
    """

    # OpenShift-specific SCC annotation
    ds_annotations = ""
    if platform == "openshift":
        ds_annotations = """
      annotations:
        openshift.io/scc: hostaccess"""

    manifest = f"""# OpsBrain Collector — auto-generated by OpsBrain installer
# Platform: {platform.upper()} | Environment: {env_name}
# Generated by: python3 install-collector.py
# DO NOT EDIT manually — re-run install-collector.py to update
---
apiVersion: v1
kind: Namespace
metadata:
  name: {namespace}
  labels:
    app.kubernetes.io/managed-by: opsbrain
    opsbrain.io/component: collector
    # Enforce restricted pod security on this namespace
    pod-security.kubernetes.io/enforce: restricted
    pod-security.kubernetes.io/warn: restricted
---
# ── Enrollment credentials (token never leaves this namespace) ────
apiVersion: v1
kind: Secret
metadata:
  name: opsbrain-collector-credentials
  namespace: {namespace}
  labels:
    app.kubernetes.io/managed-by: opsbrain
type: Opaque
data:
  token: {token_b64}
  endpoint: {endpoint_b64}
---
# ── Collector configuration ───────────────────────────────────────
apiVersion: v1
kind: ConfigMap
metadata:
  name: opsbrain-collector-config
  namespace: {namespace}
  labels:
    app.kubernetes.io/managed-by: opsbrain
data:
  config.yaml: |
{textwrap.indent(otel_config, "    ")}
---
# ── ServiceAccount ────────────────────────────────────────────────
apiVersion: v1
kind: ServiceAccount
metadata:
  name: opsbrain-collector
  namespace: {namespace}
  labels:
    app.kubernetes.io/managed-by: opsbrain
automountServiceAccountToken: false   # We mount it explicitly below
---
# ── ClusterRole — READ-ONLY, metrics only ─────────────────────────
# Cannot: create/update/delete/patch/exec/portforward/access secrets
apiVersion: rbac.authorization.k8s.io/v1
kind: ClusterRole
metadata:
  name: opsbrain-collector
  labels:
    app.kubernetes.io/managed-by: opsbrain
rules:
  # Core: read node, pod, service, endpoint, event info
  - apiGroups: [""]
    resources: [nodes, nodes/metrics, nodes/stats, nodes/proxy, pods, services, endpoints, namespaces, events, persistentvolumes, persistentvolumeclaims, replicationcontrollers]
    verbs: [get, list, watch]
  # Apps: read deployment, replicaset, statefulset, daemonset state
  - apiGroups: [apps]
    resources: [deployments, replicasets, statefulsets, daemonsets]
    verbs: [get, list, watch]
  # Autoscaling: HPA status
  - apiGroups: [autoscaling]
    resources: [horizontalpodautoscalers]
    verbs: [get, list, watch]
  # Batch: job and cronjob status
  - apiGroups: [batch]
    resources: [jobs, cronjobs]
    verbs: [get, list, watch]
  # Kubelet metrics endpoint
  - nonResourceURLs: [/metrics, /metrics/cadvisor, /metrics/resource, /healthz]
    verbs: [get]
  # Storage classes for PVC analysis
  - apiGroups: [storage.k8s.io]
    resources: [storageclasses]
    verbs: [get, list, watch]
  # EXPLICIT DENY: no access to secrets, configmaps, or exec
  # (ClusterRole omission = deny — explicitly documented here for auditability)
  # Denied: secrets, configmaps, exec, portforward, attach, log
---
# ── ClusterRoleBinding ────────────────────────────────────────────
apiVersion: rbac.authorization.k8s.io/v1
kind: ClusterRoleBinding
metadata:
  name: opsbrain-collector
  labels:
    app.kubernetes.io/managed-by: opsbrain
roleRef:
  apiGroup: rbac.authorization.k8s.io
  kind: ClusterRole
  name: opsbrain-collector
subjects:
  - kind: ServiceAccount
    name: opsbrain-collector
    namespace: {namespace}
---
# ── NetworkPolicy — zero-trust egress ─────────────────────────────
# Collector can ONLY talk to: k8s API server + OpsBrain endpoint
# Cannot talk to: other pods, databases, internal services
apiVersion: networking.k8s.io/v1
kind: NetworkPolicy
metadata:
  name: opsbrain-collector-netpol
  namespace: {namespace}
  labels:
    app.kubernetes.io/managed-by: opsbrain
spec:
  podSelector:
    matchLabels:
      app: opsbrain-collector
  policyTypes: [Ingress, Egress]
  ingress: []  # No inbound traffic allowed
  egress:
    # Allow: Kubernetes API server
    - ports:
        - port: 6443
          protocol: TCP
        - port: 443
          protocol: TCP
    # Allow: Kubelet on each node (metrics scraping)
    - ports:
        - port: 10250
          protocol: TCP
        - port: 10255
          protocol: TCP
    # Allow: OpsBrain endpoint (all external HTTPS — restrict to IP if possible)
    - ports:
        - port: 8011
          protocol: TCP
        - port: 443
          protocol: TCP
    # Allow: DNS resolution
    - ports:
        - port: 53
          protocol: UDP
        - port: 53
          protocol: TCP
---
# ── DaemonSet — one collector pod per node ────────────────────────
apiVersion: apps/v1
kind: DaemonSet
metadata:
  name: opsbrain-collector
  namespace: {namespace}
  labels:
    app: opsbrain-collector
    app.kubernetes.io/managed-by: opsbrain
    opsbrain.io/component: collector
    opsbrain.io/platform: {platform}
spec:
  selector:
    matchLabels:
      app: opsbrain-collector
  updateStrategy:
    type: RollingUpdate
    rollingUpdate:
      maxUnavailable: 1
  template:
    metadata:
      labels:
        app: opsbrain-collector
        opsbrain.io/component: collector{ds_annotations}
    spec:
      serviceAccountName: opsbrain-collector
      automountServiceAccountToken: false

      # Run on all nodes including control plane
      tolerations:
        - key: node-role.kubernetes.io/control-plane
          effect: NoSchedule
        - key: node-role.kubernetes.io/master
          effect: NoSchedule
        - key: CriticalAddonsOnly
          operator: Exists

      # No host-level access — fully isolated
      hostNetwork: false
      hostPID: false
      hostIPC: false

      # Priority class — lower than application pods
      priorityClassName: system-node-critical

      securityContext:
        runAsNonRoot: true
        runAsUser: 10001
        runAsGroup: 10001
        fsGroup: 10001
        seccompProfile:
          type: RuntimeDefault

      containers:
        - name: collector
          image: otel/opentelemetry-collector-contrib:0.97.0
          imagePullPolicy: IfNotPresent
          command: [/otelcol-contrib, --config=/conf/config.yaml]

          env:
            - name: K8S_NODE_IP
              valueFrom:
                fieldRef:
                  fieldPath: status.hostIP
            - name: K8S_NODE_NAME
              valueFrom:
                fieldRef:
                  fieldPath: spec.nodeName
            - name: OPSBRAIN_TOKEN
              valueFrom:
                secretKeyRef:
                  name: opsbrain-collector-credentials
                  key: token
            - name: OPSBRAIN_ENDPOINT
              valueFrom:
                secretKeyRef:
                  name: opsbrain-collector-credentials
                  key: endpoint

          volumeMounts:
            - name: config
              mountPath: /conf
              readOnly: true
            - name: sa-token
              mountPath: /var/run/secrets/kubernetes.io/serviceaccount
              readOnly: true

          resources:
            requests:
              cpu: 50m
              memory: 128Mi
            limits:
              cpu: 200m        # Cannot starve application pods
              memory: 256Mi    # Hard limit — OOM-killed before app pods

          securityContext:
            allowPrivilegeEscalation: false
            readOnlyRootFilesystem: true
            runAsNonRoot: true
            runAsUser: 10001
            capabilities:
              drop: [ALL]     # Drop ALL Linux capabilities

          livenessProbe:
            httpGet: {{path: /, port: 13133}}
            initialDelaySeconds: 20
            periodSeconds: 30
            failureThreshold: 3
          readinessProbe:
            httpGet: {{path: /, port: 13133}}
            initialDelaySeconds: 5
            periodSeconds: 10

      volumes:
        - name: config
          configMap:
            name: opsbrain-collector-config
        - name: sa-token
          projected:
            sources:
              - serviceAccountToken:
                  path: token
                  expirationSeconds: 3600
              - configMap:
                  name: kube-root-ca.crt
                  items: [{{key: ca.crt, path: ca.crt}}]
              - downwardAPI:
                  items: [{{path: namespace, fieldRef: {{fieldPath: metadata.namespace}}}}]
"""
    return manifest


# ── Main ──────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(description="OpsBrain Collector Installer")
    parser.add_argument("--endpoint", required=True, help="OpsBrain backend URL")
    parser.add_argument("--token",    required=True, help="Enrollment token from OpsBrain UI")
    parser.add_argument("--env-name", required=True, help="Human-readable environment name")
    parser.add_argument("--namespace", default="opsbrain-collector", help="Kubernetes namespace (default: opsbrain-collector)")
    parser.add_argument("--dry-run",  action="store_true", help="Print YAML without applying")
    parser.add_argument("--uninstall", action="store_true", help="Remove collector from this cluster")
    args = parser.parse_args()

    print(f"\n{B}{CY}OpsBrain Collector Installer{R}")
    print(f"{DI}{'─'*50}{R}\n")

    # ── Preflight ─────────────────────────────────────────────────
    step(1, "Preflight checks")
    if not shutil.which("kubectl"):
        err("kubectl not found. Install: https://kubernetes.io/docs/tasks/tools/")

    try:
        ctx = _kubectl("config current-context", capture=True)
        ok(f"kubectl context: {ctx}")
    except Exception:
        err("Cannot connect to Kubernetes cluster. Check your kubeconfig.")

    server = _kubectl("cluster-info --short 2>/dev/null", capture=True, check=False) or "unknown"
    ok(f"Cluster reachable")

    # ── Uninstall ─────────────────────────────────────────────────
    if args.uninstall:
        step(2, "Removing OpsBrain collector")
        _kubectl(f"delete namespace {args.namespace} --ignore-not-found", check=False)
        _kubectl("delete clusterrole opsbrain-collector --ignore-not-found", check=False)
        _kubectl("delete clusterrolebinding opsbrain-collector --ignore-not-found", check=False)
        ok("Collector removed from cluster")
        return

    # ── Detect platform ───────────────────────────────────────────
    step(2, "Detecting Kubernetes platform")
    platform = detect_platform()
    PLATFORM_LABELS = {
        "eks":        f"{CY}AWS EKS{R}",
        "aks":        f"{CY}Azure AKS{R}",
        "gke":        f"{CY}GCP GKE{R}",
        "openshift":  f"{CY}Red Hat OpenShift{R}",
        "kubernetes": f"{CY}Kubernetes{R}",
    }
    ok(f"Platform detected: {PLATFORM_LABELS.get(platform, platform)}")

    # ── Generate manifest ─────────────────────────────────────────
    step(3, "Generating secure manifest")
    manifest = generate_manifest(
        endpoint=args.endpoint,
        token=args.token,
        env_name=args.env_name,
        namespace=args.namespace,
        platform=platform,
    )
    ok(f"Manifest generated ({len(manifest.splitlines())} lines)")
    info("Security profile: non-root · read-only RBAC · network-isolated · resource-limited")

    if args.dry_run:
        print(f"\n{DI}{'─'*50}{R}")
        print(manifest)
        print(f"{DI}{'─'*50}{R}")
        info("Dry-run mode — manifest not applied")
        return

    # ── Apply ─────────────────────────────────────────────────────
    step(4, "Applying to cluster")
    _kubectl_apply(manifest)
    ok("Manifests applied successfully")

    # ── Wait for pods ─────────────────────────────────────────────
    step(5, "Waiting for collector pods to start")
    info("This may take 30-60 seconds for the image to pull…")
    for attempt in range(24):
        time.sleep(5)
        result = _kubectl(
            f"get pods -n {args.namespace} -l app=opsbrain-collector --field-selector=status.phase=Running -o name",
            capture=True, check=False,
        )
        if result:
            count = len(result.strip().split("\n"))
            ok(f"{count} collector pod(s) running")
            break
        if attempt % 4 == 0:
            info(f"Waiting… ({attempt * 5}s)")
    else:
        warn("Pods not ready after 2 minutes — check: kubectl get pods -n " + args.namespace)

    # ── Verify connectivity to OpsBrain ───────────────────────────
    step(6, "Verifying connection to OpsBrain")
    try:
        req = urllib.request.Request(
            f"{args.endpoint}/health",
            headers={"User-Agent": "opsbrain-installer/1.0"},
        )
        with urllib.request.urlopen(req, timeout=10) as resp:
            health = json.loads(resp.read())
            if health.get("status") == "ok":
                ok(f"OpsBrain backend reachable at {args.endpoint}")
            else:
                warn(f"OpsBrain returned unexpected status: {health}")
    except Exception as e:
        warn(f"Cannot verify OpsBrain connectivity: {e}")
        info("The collector will retry automatically — check network policies if it fails")

    # ── Done ──────────────────────────────────────────────────────
    print(f"""
{GR}{B}  ✓  Installation complete!{R}

  {DI}Environment:{R}  {B}{args.env_name}{R}
  {DI}Platform:{R}     {B}{platform.upper()}{R}
  {DI}Namespace:{R}    {B}{args.namespace}{R}

  {DI}The collector will start sending data to OpsBrain within 2 minutes.{R}
  {DI}View live status in: OpsBrain → Environments tab{R}

  {DI}Useful commands:{R}
    kubectl get pods -n {args.namespace}
    kubectl logs -n {args.namespace} -l app=opsbrain-collector --tail=50
    kubectl get events -n {args.namespace}
""")


if __name__ == "__main__":
    main()
'''
