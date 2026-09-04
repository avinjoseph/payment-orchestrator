from prometheus_client import Counter, Gauge, Histogram

PAYMENT_REQUESTS_TOTAL = Counter(
    "payment_requests_total",
    "Total number of payment attempts processed",
    ["gateway", "status"]
)

PAYMENT_LATENCY_SECONDS = Histogram(
    "payment_latency_seconds",  
    "Latency of downstream payment gateway calls in seconds",
    ["gateway"],
    buckets=[0.05, 0.1,0.25, 0.5,0.8, 1.0,1.5, 2.0, 5.0, 10]
)

CIRCUIT_BREAKER_STATE = Gauge(
    "circuit_breaker_state",
    "Current state of the circuit breaker (0=closed, 1=open, 0.5=half-open)",
    ["gateway"]
)

FAILOVER_EVENTS_TOTAL = Counter(
    "failover_events_total",
    "Count of automated failover between gateways",
    ["from_gateway", "to_gateway"]
)