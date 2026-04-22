"""
In-memory circular metrics store.
Holds recent time-series data from all sources (cloud APIs + OTel collectors).
Replace with Prometheus remote-write or TimescaleDB for production persistence.
"""
from __future__ import annotations

from collections import deque
from dataclasses import dataclass, field
from datetime import datetime, timezone
from threading import Lock
from typing import Any


@dataclass
class MetricPoint:
    timestamp: str
    value: float
    labels: dict[str, str] = field(default_factory=dict)


class MetricsStore:
    """
    Keyed as: {environment_id}.{service}.{metric_name}
    Each key holds a deque of the last MAX_POINTS readings.
    """

    MAX_POINTS = 288  # 24h at 5-min intervals

    def __init__(self) -> None:
        self._data: dict[str, deque[MetricPoint]] = {}
        self._lock = Lock()
        self._collection_log: list[dict] = []  # last N collection runs

    # ── Write ──────────────────────────────────────────────────────

    def store(
        self,
        env_id: str,
        service: str,
        metric: str,
        value: float,
        labels: dict[str, str] | None = None,
        timestamp: str | None = None,
    ) -> None:
        key = f"{env_id}.{service}.{metric}"
        point = MetricPoint(
            timestamp=timestamp or datetime.now(timezone.utc).isoformat(),
            value=value,
            labels=labels or {},
        )
        with self._lock:
            if key not in self._data:
                self._data[key] = deque(maxlen=self.MAX_POINTS)
            self._data[key].append(point)

    def store_batch(self, env_id: str, metrics: list[dict]) -> int:
        """Bulk store — used by cloud pollers and OTel receiver."""
        count = 0
        for m in metrics:
            try:
                self.store(
                    env_id=env_id,
                    service=m["service"],
                    metric=m["metric"],
                    value=float(m["value"]),
                    labels=m.get("labels"),
                    timestamp=m.get("timestamp"),
                )
                count += 1
            except (KeyError, ValueError):
                pass
        return count

    def log_collection(self, env_id: str, source: str, count: int, error: str | None = None) -> None:
        self._collection_log.append({
            "env_id": env_id,
            "source": source,
            "count": count,
            "error": error,
            "ts": datetime.now(timezone.utc).isoformat(),
        })
        # Keep last 500 log entries
        if len(self._collection_log) > 500:
            self._collection_log = self._collection_log[-500:]

    # ── Read ───────────────────────────────────────────────────────

    def get_series(
        self, env_id: str, service: str, metric: str, last_n: int = 60
    ) -> list[dict]:
        key = f"{env_id}.{service}.{metric}"
        with self._lock:
            points = list(self._data.get(key, []))[-last_n:]
        return [{"ts": p.timestamp, "value": p.value, "labels": p.labels} for p in points]

    def get_latest(self, env_id: str, service: str, metric: str) -> float | None:
        key = f"{env_id}.{service}.{metric}"
        with self._lock:
            pts = self._data.get(key)
            return pts[-1].value if pts else None

    def list_services(self, env_id: str) -> list[str]:
        prefix = f"{env_id}."
        with self._lock:
            services = {k.split(".")[1] for k in self._data if k.startswith(prefix)}
        return sorted(services)

    def list_metrics(self, env_id: str, service: str) -> list[str]:
        prefix = f"{env_id}.{service}."
        with self._lock:
            metrics = [k.split(".", 2)[2] for k in self._data if k.startswith(prefix)]
        return sorted(metrics)

    def snapshot(self, env_id: str) -> dict[str, Any]:
        """Return the latest value for every metric in an environment."""
        prefix = f"{env_id}."
        result: dict[str, dict] = {}
        with self._lock:
            for key, pts in self._data.items():
                if not key.startswith(prefix) or not pts:
                    continue
                _, service, metric = key.split(".", 2)
                if service not in result:
                    result[service] = {}
                result[service][metric] = pts[-1].value
        return result

    def collection_status(self) -> list[dict]:
        recent = self._collection_log[-100:]
        # Deduplicate by env_id — keep only the most recent per env+source
        seen: dict[str, dict] = {}
        for entry in reversed(recent):
            k = f"{entry['env_id']}.{entry['source']}"
            if k not in seen:
                seen[k] = entry
        return list(seen.values())

    def summary(self) -> dict:
        with self._lock:
            total_series = len(self._data)
            total_points = sum(len(v) for v in self._data.values())
        return {
            "total_series": total_series,
            "total_data_points": total_points,
            "environments_tracked": len({k.split(".")[0] for k in self._data}),
        }


# Singleton
metrics_store = MetricsStore()
