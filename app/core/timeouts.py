# app/core/timeouts.py
from dataclasses import dataclass


@dataclass(frozen=True)
class TimeoutBudget:
    connect_timeout_sec: float = 0.3
    gateway_response_timeout_sec: float = 0.8  # Max per-gateway attempt budget
    max_total_failover_sec: float = 2.0         # Hard ceiling for complete flow

DEFAULT_BUDGET = TimeoutBudget()