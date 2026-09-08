# Payment Orchestrator

A production-style payment orchestration service built with FastAPI. It routes payment requests across multiple gateways, supports idempotent retries, failover, circuit breaking, webhook processing, and provider health monitoring.

## Overview

This project is designed to orchestrate payments across different providers such as Stripe, Razorpay, PayU, and UPI-style flows. The application centralizes request validation, gateway selection, retry logic, monitoring, and observability while exposing a clean API for merchants and payment clients.

## Core Features

- Multi-gateway payment routing
- Idempotency protection using request keys
- Failover and retry mechanisms
- Circuit breaker pattern for unhealthy providers
- API key authentication and request correlation
- PostgreSQL persistence with Alembic migrations
- Redis-backed rate limiting and queue utilities
- Prometheus metrics and Grafana dashboard support
- Docker Compose setup for local development

## Tech Stack

- Python 3.12
- FastAPI
- SQLAlchemy + PostgreSQL
- Redis
- Alembic
- Prometheus + Grafana
- Docker Compose
- Pytest

---

## Prerequisites

Before starting, ensure you have:

- Python 3.12+
- pip
- Docker and Docker Compose
- Git
- A terminal such as PowerShell, Bash, or zsh

---

## Quick Start with Docker Compose

This is the recommended approach for running the complete project stack.

1. Clone the repository:

```bash
git clone <your-repo-url>
cd payment-orchestrator
```

2. Start all services:

```bash
docker compose up --build
```

This will launch:

- API: http://localhost:8000
- PostgreSQL: localhost:5433
- Redis: localhost:6379
- Prometheus: http://localhost:9090
- Grafana: http://localhost:3000

3. Open the Swagger docs:

```text
http://localhost:8000/docs
```

4. Stop the services:

```bash
docker compose down
```

To remove local data volumes as well:

```bash
docker compose down -v
```

---

## Local Development Setup

If you want to work on the app outside Docker, follow these steps.

1. Create and activate a virtual environment:

```bash
python -m venv .venv
```

Windows PowerShell:

```powershell
.venv\Scripts\Activate.ps1
```

macOS/Linux:

```bash
source .venv/bin/activate
```

2. Install dependencies:

```bash
pip install -r requirements.txt
pip install -r requirements-dev.txt
```

3. Configure environment variables:

```bash
set DATABASE_URL=postgresql+asyncpg://postgres:securepassword@localhost:5433/payment_orchestrator
set REDIS_URL=redis://localhost:6379/0
set ENVIRONMENT=development
set CLIENT_API_KEYS_RAW={"merchant-demo":"demo-secret"}
set CORS_ORIGINS_RAW=["http://localhost:3000"]
```

PowerShell version:

```powershell
$env:DATABASE_URL="postgresql+asyncpg://postgres:securepassword@localhost:5433/payment_orchestrator"
$env:REDIS_URL="redis://localhost:6379/0"
$env:ENVIRONMENT="development"
$env:CLIENT_API_KEYS_RAW='{"merchant-demo":"demo-secret"}'
$env:CORS_ORIGINS_RAW='["http://localhost:3000"]'
```

Optional provider credentials:

```bash
export RAZORPAY_KEY_ID=""
export RAZORPAY_KEY_SECRET=""
export STRIPE_API_KEY=""
export PAYU_MERCHANT_KEY=""
export PAYU_MERCHANT_SALT=""
```

4. Start PostgreSQL and Redis if they are not running:

```bash
docker compose up postgres redis
```

5. Run the app:

```bash
uvicorn app.main:app --host 0.0.0.0 --port 8000 --reload
```

The application will be available at:

```text
http://localhost:8000
```

---

## Environment Configuration

The app uses `pydantic-settings` and reads configuration from environment variables defined in `app/config.py`.

Required values:

- `DATABASE_URL`
- `REDIS_URL`
- `ENVIRONMENT`

Useful optional values:

- `CLIENT_API_KEYS_RAW`
- `CORS_ORIGINS_RAW`
- `RAZORPAY_KEY_ID`
- `RAZORPAY_KEY_SECRET`
- `STRIPE_API_KEY`
- `PAYU_MERCHANT_KEY`
- `PAYU_MERCHANT_SALT`

---

## Database and Migrations

This project uses SQLAlchemy and Alembic.

Apply migrations:

```bash
alembic upgrade head
```

Create a new migration:

```bash
alembic revision --autogenerate -m "your migration name"
```

---

## Running Tests

Run the entire suite:

```bash
pytest -q
```

Run a single test file:

```bash
pytest tests/scenarios/test_failover.py -q
```

---

## API Endpoints

The app exposes the main endpoints below:

- `/health` — service health checks
- `/payments` — payment processing entry point
- `/webhooks/*` — provider webhook ingestion
- `/metrics` — Prometheus metrics endpoint
- `/docs` — Swagger UI (disabled in production)

---

## Project Structure

```text
payment-orchestrator/
├── alembic/                     # Alembic migration scripts and config
├── app/                         # Main FastAPI application package
│   ├── api/                     # HTTP layer: routes, middleware, dependencies, handlers
│   │   ├── dependencies.py      # Reusable dependency injection setup
│   │   ├── error_handlers.py    # Exception-to-HTTP response mapping
│   │   ├── middleware.py        # Correlation ID and security middleware
│   │   └── routes/              # Route modules for health, payments, and webhooks
│   ├── core/                    # Shared infrastructure and operational utilities
│   │   ├── auth.py              # Client API key validation
│   │   ├── logging.py           # Structured logging configuration
│   │   ├── metrics.py           # Prometheus metric definitions/helpers
│   │   ├── queue_client.py      # Queue abstraction utilities
│   │   ├── rate_limiter.py      # Rate limiter behavior
│   │   ├── redis_client.py      # Redis connection setup
│   │   └── timeouts.py          # Timeout configuration helpers
│   ├── db/                      # Database models and session management
│   │   ├── models.py            # SQLAlchemy models
│   │   └── session.py           # Async DB engine/session factory
│   ├── gateways/                # External payment provider adapters
│   │   ├── base.py              # Base gateway contract
│   │   ├── mock.py              # Mock gateway for testing/dev flows
│   │   ├── payu.py              # PayU integration logic
│   │   ├── razorpay.py          # Razorpay integration logic
│   │   ├── registry.py          # Gateway registry/lookup
│   │   ├── stripe.py            # Stripe integration logic
│   │   └── upi.py               # UPI integration logic
│   ├── models/                  # Domain schemas and payload models
│   ├── services/                # Business logic for orchestration
│   │   ├── circuit_breaker.py   # Circuit breaker logic
│   │   ├── failover.py          # Provider failover logic
│   │   ├── health_monitor.py    # Provider health checks
│   │   ├── idempotency.py       # Idempotency enforcement
│   │   ├── payment_services.py  # Core payment processing orchestration
│   │   ├── reconciliation.py    # Reconciliation logic
│   │   ├── router.py            # Routing decisions to target gateways
│   │   ├── state_machine.py     # Payment lifecycle state machine
│   │   └── exceptions.py        # Domain-specific exceptions
│   ├── workers/                 # Background worker processes
│   │   └── webhook_consumer.py  # Webhook processing worker
│   ├── __init__.py
│   ├── config.py                # App configuration and environment settings
│   └── main.py                  # FastAPI app initialization and startup lifecycle
├── observability/               # Prometheus and Grafana monitoring config
│   ├── deploy/                  # Deployment-specific config, such as proxy files
│   ├── grafana/                 # Grafana provisioning and dashboards
│   ├── prometheus.yml           # Prometheus configuration
│   └── rules.yml                # Alerting rules
├── tests/                       # Automated test suite and scenarios
│   ├── scenarios/               # End-to-end failure and resilience scenarios
│   ├── conftest.py              # Shared pytest fixtures
│   ├── test_phase2.py           # Phase 2 feature tests
│   ├── test_phase3.py           # Phase 3 feature tests
│   ├── test_phase4.py           # Phase 4 feature tests
│   ├── test_phase5.py           # Phase 5 feature tests
│   ├── test_phase6.py           # Phase 6 feature tests
│   └── test_phase8.py           # Phase 8 feature tests
├── .dockerignore                # Files excluded from Docker builds
├── Dockerfile                   # Application container definition
├── alembic.ini                  # Alembic config file
├── docker-compose.yml           # Local development infrastructure setup
├── pyproject.toml               # Python tooling configuration
├── pytest.ini                   # Pytest configuration
├── requirements.txt             # Runtime dependencies
├── requirements-dev.txt         # Development/test dependencies
├── README.md                    # Project documentation
└── .gitignore                   # Git ignore rules
```

### Folder-by-folder guide

- `app/` — Main application code
- `app/api/` — API contracts, routes, security checks, middleware
- `app/core/` — Cross-cutting infrastructure such as logging, auth, Redis, and metrics
- `app/db/` — Database models and SQLAlchemy session setup
- `app/gateways/` — Payment provider integrations and gateway abstraction
- `app/services/` — Payment orchestration logic, routing, retries, and monitoring
- `app/workers/` — Async or background workers
- `alembic/` — DB migration scripts
- `observability/` — Monitoring and dashboards
- `tests/` — Pytest suite and scenario coverage

---

## Useful Commands Summary

```bash
# Start everything
docker compose up --build

# Start only dependencies
docker compose up postgres redis

# Run the app locally
uvicorn app.main:app --host 0.0.0.0 --port 8000 --reload

# Run tests
pytest -q

# Apply DB migrations
alembic upgrade head
```

---

## Notes

- The app reads configuration from environment variables rather than storing secrets in source control.
- `docker-compose.yml` is already configured for local infrastructure and service wiring.
- New gateways can be added under `app/gateways/` and plugged into the registry for routing.
- Monitoring and Grafana dashboards are bundled under `observability/`.

This project is ready to run from a fresh checkout using either Docker Compose or a local virtual environment setup.
