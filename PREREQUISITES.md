# OpsBrain — Prerequisites

## 1. Core Runtime (always required)

| Requirement | Version | Notes |
|---|---|---|
| Python | 3.11+ | Backend runtime |
| Node.js | 18+ | Frontend runtime |
| npm | 9+ | Bundled with Node.js |
| Anthropic API key | — | Get one at console.anthropic.com — all AI features run through Claude |

The Anthropic API key goes in `.env` at the project root:
```
ANTHROPIC_API_KEY=sk-ant-...
```

---

## 2. Running Locally (without Docker)

Install Python dependencies from inside the `backend/` directory:
```bash
cd backend
pip install -r requirements.txt
```

Install frontend dependencies:
```bash
cd frontend
npm install
```

Start both:
```bash
# terminal 1 — from backend/
uvicorn main:app --port 8011 --reload

# terminal 2 — from frontend/
npm run dev
```

---

## 3. Running with Docker

| Requirement | Version |
|---|---|
| Docker | 24+ |
| Docker Compose | v2+ (bundled with Docker Desktop) |

```bash
docker-compose up
```

---

## 4. AWS Prerequisites

### 4.1 Always required

- An AWS account
- IAM user or role with the permissions listed in section 4.3
- Access Key + Secret Key (local/dev) **or** an IAM role attached to the compute where OpsBrain runs (production)

### 4.2 Per-feature requirements

| Feature | What must exist in your account |
|---|---|
| Connection test | Nothing extra — just valid credentials |
| CloudWatch alarms | At least one CloudWatch alarm created |
| Cost breakdown | Cost Explorer enabled (free — activate once in Billing console) |
| EC2 metrics (CPU, network) | At least one running EC2 instance with basic monitoring (default, free) |
| EC2 memory + disk metrics | **CloudWatch Agent** installed and running on each EC2 instance |
| RDS metrics | At least one RDS instance |
| Lambda metrics | At least one Lambda function that has been invoked |
| SQS metrics | At least one SQS queue with traffic |
| ALB metrics | At least one Application Load Balancer |
| EKS node/pod metrics | EKS cluster + **Container Insights enabled** on the cluster |
| CloudWatch Logs | At least one log group with log events |

### 4.3 Required IAM permissions

Attach this policy to your IAM user or role:

```json
{
  "Version": "2012-10-17",
  "Statement": [
    {
      "Sid": "OpsBrainReadAccess",
      "Effect": "Allow",
      "Action": [
        "sts:GetCallerIdentity",
        "ce:GetCostAndUsage",
        "ce:GetDimensionValues",
        "ce:GetRecommendations",
        "ec2:Describe*",
        "eks:Describe*",
        "eks:List*",
        "cloudwatch:GetMetricData",
        "cloudwatch:GetMetricStatistics",
        "cloudwatch:DescribeAlarms",
        "cloudwatch:ListMetrics",
        "logs:FilterLogEvents",
        "logs:GetLogEvents",
        "logs:DescribeLogGroups",
        "logs:DescribeLogStreams",
        "s3:ListBucket",
        "s3:GetObject"
      ],
      "Resource": "*"
    }
  ]
}
```

### 4.4 CloudWatch Agent (EC2 memory + disk)

Basic CloudWatch monitoring gives you CPU and network for free. Memory usage and disk utilization are **OS-level metrics** — AWS does not publish them unless the CloudWatch Agent is installed on each EC2 instance.

**Install on Amazon Linux 2 / AL2023:**
```bash
sudo yum install -y amazon-cloudwatch-agent
sudo /opt/aws/amazon-cloudwatch-agent/bin/amazon-cloudwatch-agent-config-wizard
sudo systemctl enable amazon-cloudwatch-agent
sudo systemctl start amazon-cloudwatch-agent
```

**Install on Ubuntu:**
```bash
wget https://s3.amazonaws.com/amazoncloudwatch-agent/ubuntu/amd64/latest/amazon-cloudwatch-agent.deb
sudo dpkg -i amazon-cloudwatch-agent.deb
sudo /opt/aws/amazon-cloudwatch-agent/bin/amazon-cloudwatch-agent-config-wizard
sudo systemctl enable amazon-cloudwatch-agent
sudo systemctl start amazon-cloudwatch-agent
```

The agent publishes metrics under the `CWAgent` namespace. The IAM role attached to the EC2 instance also needs `cloudwatch:PutMetricData` and `logs:CreateLogGroup` permissions.

### 4.5 EKS Container Insights (pod/node metrics)

Container Insights must be enabled on each EKS cluster for OpsBrain to collect pod-level CPU, memory, and filesystem metrics.

```bash
# Replace with your cluster name and region
aws eks update-cluster-config \
  --name <cluster-name> \
  --region <region> \
  --logging '{"clusterLogging":[{"types":["api","audit","authenticator","controllerManager","scheduler"],"enabled":true}]}'

# Install the CloudWatch Observability add-on
aws eks create-addon \
  --cluster-name <cluster-name> \
  --addon-name amazon-cloudwatch-observability \
  --region <region>
```

The EC2 node group role also needs the `CloudWatchAgentServerPolicy` IAM policy attached.

### 4.6 Cost Explorer activation

Cost Explorer is not enabled by default on new accounts. Activate it once (free):

AWS Console → Billing → Cost Explorer → Enable Cost Explorer

Data appears with up to **24 hours** delay after first activation.

---

## 5. Kubernetes Prerequisites (optional)

Required only if you use the K8s agent (`/api/v1/k8s/*` endpoints).

| Requirement | Notes |
|---|---|
| `kubectl` installed locally | Only if OpsBrain runs on the same machine as your kubeconfig |
| Valid `~/.kube/config` | Pointing at your target cluster |
| Cluster RBAC permissions | The service account needs `get`, `list`, `watch` on pods, deployments, nodes, and events |

Without a real cluster, the K8s agent falls back to mock data automatically.

---

## 6. Azure Prerequisites (optional)

Required only if connecting an Azure subscription as a data source.

| Requirement | Notes |
|---|---|
| Azure subscription | With at least Reader role |
| Service Principal | Client ID + secret, or use Managed Identity if running on AKS |
| Azure Monitor enabled | Metrics are enabled by default on most resource types |
| Log Analytics Workspace | Only if querying Azure logs |

---

## 7. GCP Prerequisites (optional)

Required only if connecting a GCP project as a data source.

| Requirement | Notes |
|---|---|
| GCP project | With billing enabled |
| Service Account JSON | With `roles/monitoring.viewer` and `roles/logging.viewer` |
| Cloud Monitoring API enabled | Enable in GCP Console → APIs & Services |
| Cloud Logging API enabled | Enable in GCP Console → APIs & Services |

---

## 8. Optional Integrations

All of these are optional. OpsBrain works without any of them — add only what you use.

| Integration | What you need |
|---|---|
| ServiceNow | Instance URL, username + password (or OAuth client ID + secret) |
| Confluence | Base URL, username, API token |
| Dynatrace | Environment URL, API token with `Read problems` + `Read metrics` scopes |
| Elasticsearch / OpenSearch | URL, API key or username + password |
| Slack | Bot token (`xoxb-...`) with `chat:write` scope, or incoming webhook URL |
| Microsoft Teams | Incoming webhook URL |
| Email (SMTP) | SMTP host, port, username, password, from address |

---

## 9. Region Note

OpsBrain polls **only the single AWS region** you configure per data source. If your resources span multiple regions, add a separate data source entry per region.

Cost Explorer data is always fetched from `us-east-1` regardless of your configured region — this is an AWS constraint (Cost Explorer has a single global endpoint).

---

## 10. Summary Checklist

**Minimum to run the tool at all:**
- [ ] Python 3.11+
- [ ] Node.js 18+
- [ ] Anthropic API key in `.env`

**Minimum to get live AWS data:**
- [ ] AWS account with IAM access key + secret
- [ ] IAM policy from section 4.3 attached
- [ ] Cost Explorer activated in Billing console

**To get EC2 memory and disk metrics:**
- [ ] CloudWatch Agent installed and running on each EC2 instance
- [ ] `CloudWatchAgentServerPolicy` attached to the EC2 instance role

**To get EKS pod/node metrics:**
- [ ] `amazon-cloudwatch-observability` add-on installed on the cluster
- [ ] `CloudWatchAgentServerPolicy` attached to the node group role
