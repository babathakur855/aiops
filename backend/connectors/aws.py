"""
AWS Connector — IAM, Bedrock, Cost Explorer, EKS, CloudWatch.
Supports: Access Keys, IAM Role Assumption (cross-account), Instance Profile.
"""
from __future__ import annotations

import asyncio
import json
from typing import Any

from connectors.base import BaseConnector, ConnectorConfig


# ── Required IAM policy (least-privilege read + Bedrock) ────────────
AWS_REQUIRED_POLICY = {
    "Version": "2012-10-17",
    "Statement": [
        {
            "Sid": "OpsBrainReadAccess",
            "Effect": "Allow",
            "Action": [
                "sts:GetCallerIdentity",
                "bedrock:InvokeModel",
                "bedrock:InvokeModelWithResponseStream",
                "bedrock:ListFoundationModels",
                "ce:GetCostAndUsage",
                "ce:GetDimensionValues",
                "ce:GetRecommendations",
                "ec2:Describe*",
                "eks:Describe*",
                "eks:List*",
                "cloudwatch:GetMetricData",
                "cloudwatch:DescribeAlarms",
                "cloudwatch:ListMetrics",
                "logs:FilterLogEvents",
                "logs:GetLogEvents",
                "logs:DescribeLogGroups",
                "logs:DescribeLogStreams",
                "s3:ListBucket",
                "s3:GetObject",
            ],
            "Resource": "*",
        }
    ],
}

AWS_DEPLOY_POLICY = {
    "Version": "2012-10-17",
    "Statement": [
        {
            "Sid": "OpsBrainDeployAccess",
            "Effect": "Allow",
            "Action": [
                "eks:UpdateNodegroupScalingConfig",
                "eks:UpdateClusterConfig",
                "ec2:StartInstances",
                "ec2:StopInstances",
                "cloudformation:CreateStack",
                "cloudformation:UpdateStack",
                "cloudformation:DeleteStack",
                "cloudformation:Describe*",
            ],
            "Resource": "*",
        }
    ],
}

TRUST_POLICY_TEMPLATE = {
    "Version": "2012-10-17",
    "Statement": [
        {
            "Effect": "Allow",
            "Principal": {"AWS": "arn:aws:iam::<OPSBRAIN_ACCOUNT_ID>:role/OpsBrain"},
            "Action": "sts:AssumeRole",
            "Condition": {"StringEquals": {"sts:ExternalId": "<EXTERNAL_ID>"}},
        }
    ],
}


class AWSConnector(BaseConnector):
    def __init__(self, config: ConnectorConfig) -> None:
        super().__init__(config)
        cfg = config.config
        self.auth_method = cfg.get("auth_method", "access_key")
        self.region = cfg.get("region", "us-east-1")
        self.role_arn = cfg.get("role_arn", "")
        self.external_id = cfg.get("external_id", "")
        self.access_key_id = cfg.get("access_key_id", "")
        self.secret_access_key = cfg.get("secret_access_key", "")
        self.bedrock_model_id = cfg.get("bedrock_model_id", "anthropic.claude-3-5-sonnet-20241022-v2:0")
        self._session: Any = None

    def _make_session(self) -> Any:
        try:
            import boto3
        except ImportError:
            raise ImportError("Install boto3: pip install boto3")

        if self.auth_method == "access_key":
            return boto3.Session(
                aws_access_key_id=self.access_key_id,
                aws_secret_access_key=self.secret_access_key,
                region_name=self.region,
            )

        if self.auth_method == "iam_role":
            base = boto3.Session(region_name=self.region)
            sts = base.client("sts")
            kwargs: dict = {"RoleArn": self.role_arn, "RoleSessionName": "OpsBrain"}
            if self.external_id:
                kwargs["ExternalId"] = self.external_id
            creds = sts.assume_role(**kwargs)["Credentials"]
            return boto3.Session(
                aws_access_key_id=creds["AccessKeyId"],
                aws_secret_access_key=creds["SecretAccessKey"],
                aws_session_token=creds["SessionToken"],
                region_name=self.region,
            )

        # instance_profile / IRSA — boto3 finds credentials automatically
        return boto3.Session(region_name=self.region)

    def _session_or_new(self) -> Any:
        if self._session is None:
            self._session = self._make_session()
        return self._session

    # ── BaseConnector interface ──────────────────────────────────────

    async def test_connection(self) -> dict:
        def _test():
            session = self._make_session()
            sts = session.client("sts")
            identity = sts.get_caller_identity()
            return {
                "healthy": True,
                "account_id": identity["Account"],
                "caller_arn": identity["Arn"],
                "region": self.region,
                "auth_method": self.auth_method,
            }
        try:
            return await asyncio.to_thread(_test)
        except Exception as e:
            return {"healthy": False, "error": str(e)}

    async def fetch_alerts(self, severity: str = "all") -> list[dict]:
        def _fetch():
            session = self._session_or_new()
            cw = session.client("cloudwatch")
            states = ["ALARM"] if severity != "all" else ["ALARM", "INSUFFICIENT_DATA"]
            alarms = cw.describe_alarms(StateValue=states[0])["MetricAlarms"]
            return [
                {
                    "name": a["AlarmName"],
                    "severity": "critical" if a["StateValue"] == "ALARM" else "warning",
                    "service": a.get("Namespace", "").replace("AWS/", "").lower(),
                    "message": a.get("StateReason", ""),
                    "metric": a.get("MetricName", ""),
                    "firing_since": str(a.get("StateUpdatedTimestamp", "")),
                    "source": "cloudwatch",
                }
                for a in alarms
            ]
        try:
            return await asyncio.to_thread(_fetch)
        except Exception:
            return []

    async def fetch_logs(self, query: str, window_minutes: int = 15) -> list[dict]:
        def _fetch():
            from datetime import datetime, timedelta, timezone
            session = self._session_or_new()
            logs = session.client("logs")
            groups = logs.describe_log_groups(limit=5)["logGroups"]
            results = []
            since = int((datetime.now(timezone.utc) - timedelta(minutes=window_minutes)).timestamp() * 1000)
            for g in groups[:3]:
                events = logs.filter_log_events(
                    logGroupName=g["logGroupName"],
                    filterPattern=query,
                    startTime=since,
                    limit=20,
                ).get("events", [])
                results.extend([{"group": g["logGroupName"], "message": e["message"], "timestamp": e["timestamp"]} for e in events])
            return results
        try:
            return await asyncio.to_thread(_fetch)
        except Exception:
            return []

    # ── AWS-specific methods ─────────────────────────────────────────

    async def get_cost_breakdown(self, months: int = 1) -> dict:
        def _fetch():
            from datetime import datetime, timedelta
            session = self._session_or_new()
            ce = session.client("ce", region_name="us-east-1")
            end = datetime.utcnow().strftime("%Y-%m-%d")
            start = (datetime.utcnow() - timedelta(days=30 * months)).strftime("%Y-%m-%d")
            result = ce.get_cost_and_usage(
                TimePeriod={"Start": start, "End": end},
                Granularity="MONTHLY",
                Metrics=["UnblendedCost"],
                GroupBy=[{"Type": "DIMENSION", "Key": "SERVICE"}],
            )
            items = result["ResultsByTime"][0]["Groups"] if result["ResultsByTime"] else []
            return [
                {"service": i["Keys"][0], "cost_usd": round(float(i["Metrics"]["UnblendedCost"]["Amount"]), 2)}
                for i in sorted(items, key=lambda x: float(x["Metrics"]["UnblendedCost"]["Amount"]), reverse=True)
            ]
        try:
            return {"breakdown": await asyncio.to_thread(_fetch)}
        except Exception as e:
            return {"error": str(e)}

    async def list_eks_clusters(self) -> list[dict]:
        def _fetch():
            session = self._session_or_new()
            eks = session.client("eks")
            cluster_names = eks.list_clusters()["clusters"]
            clusters = []
            for name in cluster_names:
                info = eks.describe_cluster(name=name)["cluster"]
                clusters.append({
                    "name": name,
                    "status": info["status"],
                    "version": info["version"],
                    "endpoint": info.get("endpoint", ""),
                    "region": self.region,
                })
            return clusters
        try:
            return await asyncio.to_thread(_fetch)
        except Exception:
            return []

    async def invoke_bedrock(self, prompt: str, system: str = "") -> str:
        def _invoke():
            session = self._session_or_new()
            bedrock = session.client("bedrock-runtime")
            body = {
                "anthropic_version": "bedrock-2023-05-31",
                "max_tokens": 4096,
                "messages": [{"role": "user", "content": prompt}],
            }
            if system:
                body["system"] = system
            response = bedrock.invoke_model(
                modelId=self.bedrock_model_id,
                body=json.dumps(body),
                contentType="application/json",
            )
            result = json.loads(response["body"].read())
            return result["content"][0]["text"]
        try:
            return await asyncio.to_thread(_invoke)
        except Exception as e:
            return f"Bedrock error: {e}"

    @staticmethod
    def get_required_iam_policy() -> dict:
        return AWS_REQUIRED_POLICY

    @staticmethod
    def get_deploy_iam_policy() -> dict:
        return AWS_DEPLOY_POLICY

    @staticmethod
    def get_trust_policy_template() -> dict:
        return TRUST_POLICY_TEMPLATE
