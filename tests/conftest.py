"""Shared fixtures across all tests."""
from __future__ import annotations

from datetime import datetime, timezone

import pytest

from domain.schemas import MetricRecord, ServiceStatuses, ServiceStatus


@pytest.fixture
def sample_record() -> MetricRecord:
    """Nominal record used as a baseline across test suites."""
    return MetricRecord(
        timestamp=datetime.now(tz=timezone.utc),
        cpu_usage=50.0,
        memory_usage=60.0,
        latency_ms=100.0,
        disk_usage=40.0,
        network_in_kbps=1000.0,
        network_out_kbps=500.0,
        io_wait=2.0,
        thread_count=50,
        active_connections=100,
        error_rate=0.01,
        uptime_seconds=3600,
        temperature_celsius=55.0,
        power_consumption_watts=200.0,
        service_status=ServiceStatuses(
            database=ServiceStatus.online,
            api_gateway=ServiceStatus.online,
            cache=ServiceStatus.online,
        ),
    )
