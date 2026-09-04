# app/services/failover.py
import asyncio
import time
from typing import NamedTuple
from uuid import UUID

import structlog
from redis.asyncio import Redis

from app.core.metrics import (
    FAILOVER_EVENTS_TOTAL,
    PAYMENT_LATENCY_SECONDS,
    PAYMENT_REQUESTS_TOTAL,
)
from app.core.timeouts import DEFAULT_BUDGET, TimeoutBudget
from app.gateways.base import GatewayResponse, TransientGatewayError
from app.gateways.registry import GatewayRegistry
from app.gateways.registry import registry as default_registry
from app.services.circuit_breaker import CircuitBreaker
from app.services.exceptions import (
    AllGatewaysExhaustedError,
    FailoverBudgetExceededError,
    NoHealthyGatewayError,
)
from app.services.health_monitor import GatewayHealthMonitor
from app.services.router import SmartRouter
from app.services.state_machine import TransactionStateMachine

logger = structlog.get_logger(__name__)

class FailoverResult(NamedTuple):
    gateway_name: str
    response: GatewayResponse
    attempted_gateways: list[str]

class FailoverEngine:
    def __init__(
        self,
        redis: Redis,
        state_machine: TransactionStateMachine,
        registry: GatewayRegistry | None = None,
        budget: TimeoutBudget = DEFAULT_BUDGET
    ):
        self.redis = redis
        self.registry = registry or default_registry
        self.state_machine = state_machine
        self.health_monitor = GatewayHealthMonitor(redis=self.redis)
        self.router = SmartRouter(health_monitor=self.health_monitor, registry=self.registry)
        self.budget = budget

    async def charge_with_failover(
        self,
        transaction_id: UUID,
        amount: int,
        currency: str,
        method: str,
        idempotency_key: str,
        max_attempts: int = 3
    ) -> FailoverResult:
        attempted: list[str] = []
        deadline = time.perf_counter() + self.budget.max_total_failover_sec

        for attempt_idx in range(max_attempts):
            now = time.perf_counter()
            remaining_total = deadline - now
            if remaining_total <= 0.05:
                elapsed_ms = int((self.budget.max_total_failover_sec + (now - deadline)) * 1000)
                raise FailoverBudgetExceededError(elapsed_ms)

            try:
                gateway_name = await self.router.select_gateway(
                    method=method,
                    currency=currency,
                    exclude=attempted
                )
            except NoHealthyGatewayError:
                break

            breaker = CircuitBreaker(gateway=gateway_name, redis=self.redis)
            if not await breaker.is_call_allowed():
                attempted.append(gateway_name)
                continue

            await self.state_machine.transition(
                transaction_id=transaction_id,
                to_status="processing",
                gateway=gateway_name,
                reason=f"Attempt {attempt_idx + 1}: Dispatching charge to {gateway_name}",
            )
            await self.state_machine.db.commit()

            # Cap individual attempt timeout to per-gateway budget or remaining total
            adapter = self.registry.get_adapter(gateway_name)
            attempt_timeout = min(self.budget.gateway_response_timeout_sec, remaining_total)
            call_start = time.perf_counter()

            try:
                resp = await asyncio.wait_for(
                    adapter.charge(
                        amount=amount,
                        currency=currency,
                        method=method,
                        idempotency_key=idempotency_key,
                    ),
                    timeout=attempt_timeout,
                )
                elapsed_sec = time.perf_counter() - call_start
                PAYMENT_LATENCY_SECONDS.labels(gateway=gateway_name).observe(elapsed_sec)
                PAYMENT_REQUESTS_TOTAL.labels(gateway=gateway_name, status=resp.status).inc()
                logger.info(
                    "gateway_charge_completed",
                    gateway=gateway_name,
                    status=resp.status,
                    duration_ms=int(elapsed_sec * 1000),
                )
                return FailoverResult(
                    gateway_name=gateway_name,
                    response=resp,
                    attempted_gateways=attempted + [gateway_name],
                )
            except (TimeoutError, TransientGatewayError, AssertionError) as ex:
                elapsed_sec = time.perf_counter() - call_start
                PAYMENT_LATENCY_SECONDS.labels(gateway=gateway_name).observe(elapsed_sec)
                PAYMENT_REQUESTS_TOTAL.labels(gateway=gateway_name, status="failed").inc()
                logger.warning(
                    "gateway_charge_failed",
                    gateway=gateway_name,
                    error=str(ex),
                    duration_ms=int(elapsed_sec * 1000),
                )
                attempted.append(gateway_name)
                
                next_candidate = await self.router.select_gateway(
                    method=method,
                    currency=currency,
                    exclude=attempted
                )
                
                if next_candidate:
                    FAILOVER_EVENTS_TOTAL.labels(from_gateway=gateway_name, to_gateway=next_candidate).inc()
                    logger.info(
                        "failover_event",
                        from_gateway=gateway_name,
                        to_gateway=next_candidate,
                        attempt=attempt_idx + 1
                    )

        raise AllGatewaysExhaustedError(attempted=attempted)