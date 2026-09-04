# app/services/health_monitor.py
import time

from redis.asyncio import Redis


class GatewayHealthMonitor:
    def __init__(self, redis: Redis, window_minutes: int = 5, latency_ceiling_ms: float = 2000.0):
        self.redis = redis
        self.window_minutes = window_minutes
        self.latency_ceiling_ms = latency_ceiling_ms

    def _get_minute_bucket(self, offset_minutes: int = 0) -> int:
        return int(time.time() // 60) - offset_minutes

    async def record_outcome(self, gateway: str, success: bool, latency_ms: int) -> None:
        bucket = self._get_minute_bucket()
        stats_key = f"stats:{gateway}:{bucket}"
        lat_key = f"latencies:{gateway}:{bucket}"

        async with self.redis.pipeline(transaction=True) as pipe:
            field = "success" if success else "failure"
            pipe.hincrby(stats_key, field, 1)
            pipe.expire(stats_key, (self.window_minutes + 2) * 60)
            pipe.rpush(lat_key, latency_ms)
            pipe.expire(lat_key, (self.window_minutes + 2) * 60)
            await pipe.execute()

    async def compute_health_score(self, gateway: str) -> float:
        total_success = 0
        total_failure = 0
        all_latencies: list[int] = []

        for i in range(self.window_minutes):
            bucket = self._get_minute_bucket(offset_minutes=i)
            stats = await self.redis.hgetall(f"stats:{gateway}:{bucket}")
            if stats:
                total_success += int(stats.get("success", 0))
                total_failure += int(stats.get("failure", 0))

            lats = await self.redis.lrange(f"latencies:{gateway}:{bucket}", 0, -1)
            if lats:
                all_latencies.extend([int(lat) for lat in lats])

        total_requests = total_success + total_failure
        if total_requests == 0:
            return 0.5

        success_rate = total_success / total_requests

        if all_latencies:
            all_latencies.sort()
            idx = int(0.95 * (len(all_latencies) - 1))
            p95_lat = all_latencies[idx]
        else:
            p95_lat = 200.0

        latency_penalty = min(p95_lat / self.latency_ceiling_ms, 1.0)
        latency_score = 1.0 - latency_penalty

        # Health Formula: 70% success rate + 30% latency performance
        score = (0.7 * success_rate) + (0.3 * latency_score)
        return round(score, 4)

    async def has_recent_observations(self, gateway: str) -> bool:
        bucket = self._get_minute_bucket()
        return bool(await self.redis.exists(f"stats:{gateway}:{bucket}"))

    async def refresh_scores(self, gateways: list[str]) -> None:
        for gw in gateways:
            score = await self.compute_health_score(gw)
            await self.redis.set(f"health:{gw}", str(score), ex=300)

    async def get_cached_score(self, gateway: str) -> float:
        cached = await self.redis.get(f"health:{gateway}")
        if cached is not None:
            return float(cached)
        return 1.0