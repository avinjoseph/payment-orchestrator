# app/services/router.py
from app.gateways.registry import GatewayRegistry
from app.gateways.registry import registry as default_registry
from app.services.circuit_breaker import CircuitBreaker
from app.services.exceptions import DomainException, NoHealthyGatewayError
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
            score = await self.health_monitor.get_cached_score(gateway)
            scored.append((gateway, score))

        scored.sort(key=lambda item: item[1], reverse=True)
        return scored[0][0]