# app/services/router.py
from app.gateways.registry import GatewayRegistry
from app.gateways.registry import registry as default_registry
from app.services.circuit_breaker import CircuitBreaker
from app.services.exceptions import NoHealthyGatewayError
from app.services.health_monitor import GatewayHealthMonitor


class SmartRouter:
    def __init__(self, health_monitor: GatewayHealthMonitor, registry: GatewayRegistry | None = None):
        self.health_monitor = health_monitor
        self.registry = registry or default_registry

    async def select_gateway(self, method: str, currency: str, exclude: list[str] | None = None) -> str:
        excluded = set(exclude or [])
        candidates = self.registry.get_eligible_gateways(method=method, currency=currency)
        candidates = [g for g in candidates if g not in excluded]

        healthy_candidates: list[str] = []
        for g in candidates:
            cb = CircuitBreaker(gateway=g, redis=self.health_monitor.redis)
            state = await cb.get_state()
            if state != "OPEN":
                healthy_candidates.append(g)

        if not healthy_candidates:
            raise NoHealthyGatewayError(method=method, currency=currency)

        scored: list[tuple[str, float]] = []
        for gateway in healthy_candidates:
            if await self.health_monitor.has_recent_observations(gateway):
                score = await self.health_monitor.compute_health_score(gateway)
            else:
                score = 0.5
            scored.append((gateway, score))

        priority = {"stripe": 3, "razorpay": 2, "payu": 1, "upi": 1, "mock": 0}
        scored.sort(key=lambda item: (item[1], priority.get(item[0], 0)), reverse=True)
        return scored[0][0]