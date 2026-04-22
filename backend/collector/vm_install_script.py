"""
Generates the VM/EC2 installer shell script served at GET /collector/install-vm.sh
Installs OTel Collector as a systemd service on any Linux distribution.
Supports: Amazon Linux 2/2023, Ubuntu 20.04/22.04/24.04, RHEL 8/9, CentOS 7/8,
          Debian 11/12, SUSE, and any systemd-based Linux.
"""

OTEL_VERSION = "0.97.0"

VM_INSTALL_SCRIPT = r'''#!/usr/bin/env bash
# ================================================================
# OpsBrain VM Collector Installer
# Installs the OpsBrain metric agent on any Linux VM or EC2 instance.
#
# Usage:
#   curl -fsSL https://opsbrain.internal:8011/api/v1/collector/install-vm.sh \
#     | bash -s -- \
#         --endpoint https://opsbrain.internal:8011 \
#         --token <enrollment-token> \
#         --env-name "Production EC2 us-east-1"
#
# Supports:
#   AWS EC2 (Amazon Linux 2/2023, Ubuntu, RHEL, CentOS)
#   Azure Virtual Machines (Ubuntu, RHEL, SUSE)
#   GCP Compute Engine (Debian, Ubuntu, CentOS)
#   On-premises Linux VMs (any systemd-based distro)
# ================================================================
set -euo pipefail

OTEL_VERSION="0.97.0"
INSTALL_DIR="/opt/opsbrain-collector"
CONFIG_DIR="/etc/opsbrain-collector"
SERVICE_NAME="opsbrain-collector"

# ── Terminal colours ──────────────────────────────────────────────
R="\033[0m"; G="\033[92m"; RE="\033[91m"; CY="\033[96m"; YE="\033[93m"; B="\033[1m"
ok()   { echo -e "${G}  ✓  $*${R}"; }
err()  { echo -e "${RE}  ✗  $*${R}"; exit 1; }
warn() { echo -e "${YE}  ⚠  $*${R}"; }
info() { echo -e "${CY}  →  $*${R}"; }
step() { echo -e "\n${B}${CY}Step $1: $2${R}\n$(printf '─%.0s' {1..50})"; }

# ── Parse arguments ───────────────────────────────────────────────
ENDPOINT=""
TOKEN=""
ENV_NAME=""
NAMESPACE=""

while [[ $# -gt 0 ]]; do
  case "$1" in
    --endpoint) ENDPOINT="$2"; shift 2 ;;
    --token)    TOKEN="$2";    shift 2 ;;
    --env-name) ENV_NAME="$2"; shift 2 ;;
    *) echo "Unknown argument: $1"; shift ;;
  esac
done

[[ -z "$ENDPOINT" ]] && err "--endpoint is required"
[[ -z "$TOKEN"    ]] && err "--token is required"
[[ -z "$ENV_NAME" ]] && ENV_NAME="$(hostname)"

echo ""
echo -e "${B}${CY}OpsBrain VM Collector Installer${R}"
echo -e "${CY}$(printf '─%.0s' {1..50})${R}"
echo -e "  Environment: ${B}${ENV_NAME}${R}"
echo -e "  Endpoint:    ${B}${ENDPOINT}${R}"
echo ""

# ── Detect platform ───────────────────────────────────────────────
step 1 "Detecting platform"

OS_ID="unknown"
OS_VERSION=""
PKG_MANAGER=""
ARCH=$(uname -m)

if [[ -f /etc/os-release ]]; then
  . /etc/os-release
  OS_ID="${ID:-unknown}"
  OS_VERSION="${VERSION_ID:-}"
fi

case "$OS_ID" in
  amzn)
    PKG_MANAGER="rpm"
    ok "Amazon Linux ${OS_VERSION}"
    PLATFORM="ec2_amazon_linux"
    ;;
  ubuntu|debian)
    PKG_MANAGER="deb"
    ok "Debian/Ubuntu ${OS_VERSION}"
    PLATFORM="linux_debian"
    ;;
  rhel|centos|rocky|almalinux|ol)
    PKG_MANAGER="rpm"
    ok "RHEL/CentOS/Rocky ${OS_VERSION}"
    PLATFORM="linux_rpm"
    ;;
  sles|opensuse*)
    PKG_MANAGER="rpm"
    ok "SUSE Linux ${OS_VERSION}"
    PLATFORM="linux_rpm"
    ;;
  *)
    warn "Unknown OS '${OS_ID}' — using binary install"
    PKG_MANAGER="binary"
    PLATFORM="linux_generic"
    ;;
esac

# Detect cloud provider
CLOUD_PROVIDER="generic"
if curl -sf --max-time 1 http://169.254.169.254/latest/meta-data/ami-id &>/dev/null; then
  CLOUD_PROVIDER="aws"
  AWS_INSTANCE_ID=$(curl -sf http://169.254.169.254/latest/meta-data/instance-id 2>/dev/null || echo "unknown")
  AWS_REGION=$(curl -sf http://169.254.169.254/latest/meta-data/placement/region 2>/dev/null || echo "unknown")
  ok "AWS EC2 detected — instance: ${AWS_INSTANCE_ID}, region: ${AWS_REGION}"
elif curl -sf --max-time 1 -H "Metadata: true" "http://169.254.169.254/metadata/instance?api-version=2021-02-01" &>/dev/null; then
  CLOUD_PROVIDER="azure"
  ok "Azure VM detected"
elif curl -sf --max-time 1 http://metadata.google.internal/computeMetadata/v1/instance/id -H "Metadata-Flavor: Google" &>/dev/null; then
  CLOUD_PROVIDER="gcp"
  GCP_PROJECT=$(curl -sf http://metadata.google.internal/computeMetadata/v1/project/project-id -H "Metadata-Flavor: Google" 2>/dev/null || echo "unknown")
  ok "GCP Compute Engine detected — project: ${GCP_PROJECT}"
fi

# ── Check prerequisites ───────────────────────────────────────────
step 2 "Checking prerequisites"

[[ $EUID -ne 0 ]] && err "Run as root: sudo bash -s -- ... or prefix with sudo"
command -v systemctl &>/dev/null || err "systemd is required (systemctl not found)"
command -v curl &>/dev/null || command -v wget &>/dev/null || err "curl or wget is required"
ok "Prerequisites satisfied"

# ── Download OTel Collector ───────────────────────────────────────
step 3 "Installing OpenTelemetry Collector v${OTEL_VERSION}"

mkdir -p "${INSTALL_DIR}" "${CONFIG_DIR}"
TMP_DIR=$(mktemp -d)
trap "rm -rf ${TMP_DIR}" EXIT

ARCH_SUFFIX="amd64"
[[ "$ARCH" == "aarch64" || "$ARCH" == "arm64" ]] && ARCH_SUFFIX="arm64"

BASE_URL="https://github.com/open-telemetry/opentelemetry-collector-releases/releases/download/v${OTEL_VERSION}"

download_file() {
  local url="$1" dest="$2"
  if command -v curl &>/dev/null; then
    curl -fsSL "$url" -o "$dest"
  else
    wget -q "$url" -O "$dest"
  fi
}

case "$PKG_MANAGER" in
  deb)
    PKG="otelcol-contrib_${OTEL_VERSION}_linux_${ARCH_SUFFIX}.deb"
    info "Downloading ${PKG}…"
    download_file "${BASE_URL}/${PKG}" "${TMP_DIR}/${PKG}"
    dpkg -i "${TMP_DIR}/${PKG}"
    BINARY_PATH="/usr/bin/otelcol-contrib"
    ;;
  rpm)
    PKG="otelcol-contrib_${OTEL_VERSION}_linux_${ARCH_SUFFIX}.rpm"
    info "Downloading ${PKG}…"
    download_file "${BASE_URL}/${PKG}" "${TMP_DIR}/${PKG}"
    rpm -Uvh --force "${TMP_DIR}/${PKG}"
    BINARY_PATH="/usr/bin/otelcol-contrib"
    ;;
  binary|*)
    PKG="otelcol-contrib_${OTEL_VERSION}_linux_${ARCH_SUFFIX}.tar.gz"
    info "Downloading ${PKG}…"
    download_file "${BASE_URL}/${PKG}" "${TMP_DIR}/${PKG}"
    tar -xzf "${TMP_DIR}/${PKG}" -C "${INSTALL_DIR}"
    chmod +x "${INSTALL_DIR}/otelcol-contrib"
    BINARY_PATH="${INSTALL_DIR}/otelcol-contrib"
    ;;
esac

ok "OTel Collector installed"

# ── Write collector config ────────────────────────────────────────
step 4 "Writing collector configuration"

# Determine cloud-specific resource detection
RESOURCE_DETECTORS="[system"
[[ "$CLOUD_PROVIDER" == "aws"   ]] && RESOURCE_DETECTORS="${RESOURCE_DETECTORS}, ec2"
[[ "$CLOUD_PROVIDER" == "azure" ]] && RESOURCE_DETECTORS="${RESOURCE_DETECTORS}, azure"
[[ "$CLOUD_PROVIDER" == "gcp"   ]] && RESOURCE_DETECTORS="${RESOURCE_DETECTORS}, gce"
RESOURCE_DETECTORS="${RESOURCE_DETECTORS}]"

cat > "${CONFIG_DIR}/config.yaml" << OTELCONFIG
receivers:
  # ── IaaS: Host system metrics ─────────────────────────────────
  hostmetrics:
    collection_interval: 60s
    root_path: /host
    scrapers:
      cpu:
        metrics:
          system.cpu.utilization:
            enabled: true
      memory:
        metrics:
          system.memory.utilization:
            enabled: true
      disk: {}
      filesystem:
        exclude_mount_points:
          mount_points: [/proc/*, /sys/*, /dev/*, /run/boot/*]
          match_type: regexp
      network:
        include:
          interfaces: [eth0, ens3, enp0s3, lo]
          match_type: regexp
      load: {}
      paging: {}
      processes: {}
      process:
        include:
          names: [.*]
          match_type: regexp
        mute_process_name_error: true
        metrics:
          process.cpu.utilization:
            enabled: true
          process.memory.utilization:
            enabled: true

processors:
  # Auto-detect cloud metadata (instance ID, region, AZ, etc.)
  resourcedetection:
    detectors: ${RESOURCE_DETECTORS}
    timeout: 10s
    override: false

  # Add environment identity
  resource:
    attributes:
      - {key: opsbrain.env_name, value: "${ENV_NAME}", action: insert}
      - {key: deployment.environment, value: "${ENV_NAME}", action: insert}

  memory_limiter:
    check_interval: 5s
    limit_percentage: 50
    spike_limit_percentage: 20

  batch:
    send_batch_size: 500
    timeout: 60s

exporters:
  otlphttp/opsbrain:
    endpoint: ${ENDPOINT}/v1
    headers:
      X-OpsBrain-Token: "${TOKEN}"
    retry_on_failure:
      enabled: true
      initial_interval: 10s
      max_interval: 300s

service:
  pipelines:
    metrics:
      receivers: [hostmetrics]
      processors: [memory_limiter, resourcedetection, resource, batch]
      exporters: [otlphttp/opsbrain]
OTELCONFIG

ok "Configuration written to ${CONFIG_DIR}/config.yaml"

# ── Write environment file ────────────────────────────────────────
cat > "${CONFIG_DIR}/env" << ENVFILE
OPSBRAIN_TOKEN=${TOKEN}
OPSBRAIN_ENDPOINT=${ENDPOINT}
ENVFILE
chmod 600 "${CONFIG_DIR}/env"

# ── Create systemd service ────────────────────────────────────────
step 5 "Creating systemd service"

cat > "/etc/systemd/system/${SERVICE_NAME}.service" << SYSTEMD
[Unit]
Description=OpsBrain Metric Collector
Documentation=https://github.com/open-telemetry/opentelemetry-collector
After=network-online.target
Wants=network-online.target

[Service]
Type=simple
User=otelcol-contrib
Group=otelcol-contrib
EnvironmentFile=${CONFIG_DIR}/env
ExecStart=${BINARY_PATH} --config=${CONFIG_DIR}/config.yaml
Restart=on-failure
RestartSec=10
TimeoutStopSec=20

# Security hardening
NoNewPrivileges=yes
ProtectSystem=strict
ProtectHome=yes
ReadWritePaths=${CONFIG_DIR} /var/log/opsbrain-collector
PrivateTmp=yes
CapabilityBoundingSet=CAP_NET_BIND_SERVICE
AmbientCapabilities=CAP_NET_BIND_SERVICE
RestrictAddressFamilies=AF_INET AF_INET6 AF_UNIX
RestrictNamespaces=yes
PrivateDevices=yes

[Install]
WantedBy=multi-user.target
SYSTEMD

mkdir -p /var/log/opsbrain-collector

# Create service user if not exists
if ! id otelcol-contrib &>/dev/null 2>&1; then
  useradd --system --no-create-home --shell /sbin/nologin otelcol-contrib 2>/dev/null || true
fi
chown -R otelcol-contrib:otelcol-contrib "${CONFIG_DIR}" /var/log/opsbrain-collector 2>/dev/null || true

systemctl daemon-reload
systemctl enable "${SERVICE_NAME}"
systemctl restart "${SERVICE_NAME}"

ok "systemd service ${SERVICE_NAME} started"

# ── Verify running ────────────────────────────────────────────────
step 6 "Verifying"
sleep 3

if systemctl is-active --quiet "${SERVICE_NAME}"; then
  ok "Collector is running"
else
  warn "Collector may not have started — check: journalctl -u ${SERVICE_NAME} -n 50"
fi

echo ""
echo -e "${G}${B}  ✓  Installation complete!${R}"
echo ""
echo -e "  ${CY}Environment:${R} ${B}${ENV_NAME}${R}"
echo -e "  ${CY}Platform:${R}    ${B}${PLATFORM} / ${CLOUD_PROVIDER}${R}"
echo ""
echo -e "  Useful commands:"
echo -e "    systemctl status ${SERVICE_NAME}"
echo -e "    journalctl -u ${SERVICE_NAME} -f"
echo -e "    systemctl restart ${SERVICE_NAME}"
echo -e "    cat ${CONFIG_DIR}/config.yaml"
echo ""
'''


WINDOWS_INSTALL_SCRIPT = r'''# ================================================================
# OpsBrain VM Collector Installer — Windows
# Installs OTel Collector as a Windows Service on any Windows Server or VM.
#
# Usage (run in PowerShell as Administrator):
#   & ([scriptblock]::Create((Invoke-WebRequest -Uri "https://opsbrain.internal:8011/api/v1/collector/install-vm.ps1").Content)) `
#       -Endpoint "https://opsbrain.internal:8011" `
#       -Token "<enrollment-token>" `
#       -EnvName "Production Windows Server"
# ================================================================
param(
  [Parameter(Mandatory=$true)]  [string]$Endpoint,
  [Parameter(Mandatory=$true)]  [string]$Token,
  [Parameter(Mandatory=$false)] [string]$EnvName = $env:COMPUTERNAME,
  [string]$InstallDir = "C:\Program Files\OpsBrainCollector"
)

$ErrorActionPreference = "Stop"
$OtelVersion = "0.97.0"
$ServiceName = "OpsBrainCollector"

Write-Host ""
Write-Host "OpsBrain VM Collector Installer (Windows)" -ForegroundColor Cyan
Write-Host ("-" * 50) -ForegroundColor DarkGray
Write-Host "  Environment: $EnvName" -ForegroundColor White
Write-Host "  Endpoint:    $Endpoint" -ForegroundColor White
Write-Host ""

# ── Check admin ───────────────────────────────────────────────────
if (-not ([Security.Principal.WindowsPrincipal] [Security.Principal.WindowsIdentity]::GetCurrent()).IsInRole([Security.Principal.WindowsBuiltInRole]::Administrator)) {
    Write-Host "  X  Run as Administrator" -ForegroundColor Red; exit 1
}
Write-Host "  √  Running as Administrator" -ForegroundColor Green

# ── Detect cloud provider ─────────────────────────────────────────
$CloudProvider = "generic"
try {
    $awsCheck = Invoke-WebRequest -Uri "http://169.254.169.254/latest/meta-data/ami-id" -TimeoutSec 1 -ErrorAction Stop
    $CloudProvider = "aws"
    Write-Host "  √  AWS EC2 detected" -ForegroundColor Green
} catch {}

try {
    $azureCheck = Invoke-WebRequest -Uri "http://169.254.169.254/metadata/instance?api-version=2021-02-01" -Headers @{"Metadata"="true"} -TimeoutSec 1 -ErrorAction Stop
    $CloudProvider = "azure"
    Write-Host "  √  Azure VM detected" -ForegroundColor Green
} catch {}

# ── Download OTel Collector ───────────────────────────────────────
Write-Host "`nStep 1: Downloading OTel Collector v$OtelVersion..." -ForegroundColor Cyan
New-Item -ItemType Directory -Force -Path $InstallDir | Out-Null
$Url = "https://github.com/open-telemetry/opentelemetry-collector-releases/releases/download/v$OtelVersion/otelcol-contrib_${OtelVersion}_windows_amd64.tar.gz"
$TarFile = "$env:TEMP\otelcol.tar.gz"
Invoke-WebRequest -Uri $Url -OutFile $TarFile
tar -xzf $TarFile -C $InstallDir
Write-Host "  √  Downloaded and extracted" -ForegroundColor Green

# ── Write config ──────────────────────────────────────────────────
Write-Host "`nStep 2: Writing configuration..." -ForegroundColor Cyan
$ConfigDir = "$InstallDir\config"
New-Item -ItemType Directory -Force -Path $ConfigDir | Out-Null

$ResourceDetectors = "system"
if ($CloudProvider -eq "aws")   { $ResourceDetectors = "system, ec2" }
if ($CloudProvider -eq "azure") { $ResourceDetectors = "system, azure" }

$Config = @"
receivers:
  hostmetrics:
    collection_interval: 60s
    scrapers:
      cpu:
        metrics:
          system.cpu.utilization:
            enabled: true
      memory:
        metrics:
          system.memory.utilization:
            enabled: true
      disk: {}
      filesystem: {}
      network: {}
      load: {}
      paging: {}
      process:
        mute_process_name_error: true

processors:
  resourcedetection:
    detectors: [$ResourceDetectors]
    timeout: 10s
  resource:
    attributes:
      - {key: opsbrain.env_name, value: "$EnvName", action: insert}
  memory_limiter:
    check_interval: 5s
    limit_percentage: 50
  batch:
    send_batch_size: 500
    timeout: 60s

exporters:
  otlphttp/opsbrain:
    endpoint: $Endpoint/v1
    headers:
      X-OpsBrain-Token: "$Token"
    retry_on_failure:
      enabled: true

service:
  pipelines:
    metrics:
      receivers: [hostmetrics]
      processors: [memory_limiter, resourcedetection, resource, batch]
      exporters: [otlphttp/opsbrain]
"@

$Config | Set-Content -Path "$ConfigDir\config.yaml" -Encoding UTF8
Write-Host "  √  Config written to $ConfigDir\config.yaml" -ForegroundColor Green

# ── Register Windows Service ──────────────────────────────────────
Write-Host "`nStep 3: Registering Windows Service..." -ForegroundColor Cyan
$BinaryPath = "$InstallDir\otelcol-contrib.exe"
$ServiceArgs = "--config `"$ConfigDir\config.yaml`""

if (Get-Service -Name $ServiceName -ErrorAction SilentlyContinue) {
    Stop-Service -Name $ServiceName -Force -ErrorAction SilentlyContinue
    & sc.exe delete $ServiceName | Out-Null
    Start-Sleep -Seconds 2
}

New-Service -Name $ServiceName `
    -DisplayName "OpsBrain Metric Collector" `
    -Description "Collects system and application metrics for OpsBrain AIOps" `
    -BinaryPathName "`"$BinaryPath`" $ServiceArgs" `
    -StartupType Automatic | Out-Null

Start-Service -Name $ServiceName
Write-Host "  √  Windows Service '$ServiceName' started" -ForegroundColor Green

# ── Done ──────────────────────────────────────────────────────────
Write-Host ""
Write-Host "  √  Installation complete!" -ForegroundColor Green
Write-Host ""
Write-Host "  Useful commands:" -ForegroundColor DarkGray
Write-Host "    Get-Service $ServiceName"
Write-Host "    Restart-Service $ServiceName"
Write-Host "    Get-EventLog -LogName Application -Source $ServiceName -Newest 20"
Write-Host ""
'''


def get_ecs_task_snippet(endpoint: str, token: str, env_name: str) -> dict:
    """
    Returns an ECS sidecar container definition to add to any ECS task definition.
    Supports both EC2 and Fargate launch types.
    """
    return {
        "guide": (
            "Add the 'opsbrain-collector' container to your ECS task definition. "
            "It collects container metrics and sends them to OpsBrain. "
            "No changes to your application containers are needed."
        ),
        "container_definition": {
            "name": "opsbrain-collector",
            "image": "otel/opentelemetry-collector-contrib:0.97.0",
            "essential": False,
            "command": ["--config=/etc/otelcol/config.yaml"],
            "environment": [
                {"name": "OPSBRAIN_TOKEN", "value": token},
                {"name": "OPSBRAIN_ENDPOINT", "value": endpoint},
                {"name": "OPSBRAIN_ENV_NAME", "value": env_name},
            ],
            "mountPoints": [],
            "portMappings": [],
            "logConfiguration": {
                "logDriver": "awslogs",
                "options": {
                    "awslogs-group": f"/ecs/opsbrain-collector",
                    "awslogs-region": "us-east-1",
                    "awslogs-stream-prefix": "opsbrain",
                    "awslogs-create-group": "true",
                },
            },
            "resourceRequirements": [
                {"type": "CPU", "value": "128"},
                {"type": "MEMORY", "value": "256"},
            ],
            "secrets": [],
            "dockerLabels": {
                "opsbrain.env_name": env_name,
                "opsbrain.component": "collector",
            },
            "healthCheck": {
                "command": ["CMD", "/otelcol-contrib", "--version"],
                "interval": 30,
                "timeout": 5,
                "retries": 3,
                "startPeriod": 10,
            },
        },
        "ecs_config_override": {
            "name": "opsbrain-collector-config",
            "image": "otel/opentelemetry-collector-contrib:0.97.0",
            "command": [
                "--config=env:OTEL_CONFIG"
            ],
            "environment": [
                {"name": "OPSBRAIN_TOKEN", "value": token},
                {"name": "OPSBRAIN_ENDPOINT", "value": endpoint},
                {"name": "OTEL_CONFIG", "value": f"""
receivers:
  awsecscontainermetrics: {{}}
  otlp:
    protocols:
      grpc:
        endpoint: 0.0.0.0:4317
      http:
        endpoint: 0.0.0.0:4318

processors:
  resource:
    attributes:
      - {{key: opsbrain.env_name, value: "{env_name}", action: insert}}
  batch:
    send_batch_size: 500
    timeout: 60s

exporters:
  otlphttp/opsbrain:
    endpoint: {endpoint}/v1
    headers:
      X-OpsBrain-Token: "{token}"
    retry_on_failure:
      enabled: true

service:
  pipelines:
    metrics:
      receivers: [awsecscontainermetrics]
      processors: [resource, batch]
      exporters: [otlphttp/opsbrain]
"""},
            ],
        },
        "apply_instructions": [
            "1. Copy the 'container_definition' JSON above",
            "2. Add it to your ECS task definition's 'containerDefinitions' array",
            "3. Create a new task definition revision",
            "4. Update your ECS service to use the new revision",
            "Tip: The collector is 'essential: false' — if it crashes, your app keeps running",
        ],
    }
