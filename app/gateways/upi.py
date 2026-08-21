# app/adapters/upi.py
import uuid

import httpx
from app.gateways.base import GatewayAdapter, GatewayResponse, TransientGatewayError


class UPIAdapter(GatewayAdapter):
    def __init__(self, psp_id: str = "npci_psp_01"):
        self.name = "upi"
        self.psp_id = psp_id

    async def charge(self, amount: int, currency: str, method: str, idempotency_key: str) -> GatewayResponse:
        # UPI collect request: always initiates in asynchronous "pending" state
        collect_txn_id = f"upi_req_{uuid.uuid4().hex[:10]}"
        return GatewayResponse(
            status="pending",
            gateway_txn_id=collect_txn_id,
            raw={"vpa": "customer@upi", "approval_timeout_sec": 300}
        )

    async def get_status(self, gateway_txn_id: str) -> GatewayResponse:
        return GatewayResponse(status="pending", gateway_txn_id=gateway_txn_id)

    async def refund(self, gateway_txn_id: str, amount: int) -> GatewayResponse:
        return GatewayResponse(status="success", gateway_txn_id=gateway_txn_id)

    def verify_webhook(self, payload: bytes, headers: dict[str, str]) -> bool:
        return True