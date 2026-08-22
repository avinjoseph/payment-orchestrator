import uuid

from app.gateways.base import GatewayAdapter, GatewayResponse, TransientGatewayError

class MockGatewayAdapter(GatewayAdapter):
    def __init__(self, name: str = "mock_gateway", forced_status: str | None = None):
        self.name = name
        self.forced_status = forced_status
        
    async def charge(self, amount:int, currency:str, method:str,  idempotency_key:str) -> GatewayResponse:
        
        if self.forced_status == "transient_error":
            raise TransientGatewayError(self.name, "Mock 503 Service Unavailable")
        if self.forced_status == "pending":
            return GatewayResponse(
                status="pending",
                gateway_txn_id=f"mock_pend_{uuid.uuid4().hex[:8]}",
                raw={"gateway": self.name, "flow": "async_polling"}
            )
        if self.forced_status == "declined":
            return GatewayResponse(
                status="declined",
                error_code="CARD_DECLINED",
                raw={"gateway": self.name, "reason": "Insufficient funds"}
            )
        
        txn_id = f"mock_{uuid.uuid4().hex[:12]}"
        return GatewayResponse(
            status="success",
            gateway_txn_id=txn_id,
            raw={"gateway": self.name, "amount": amount, "currency": currency}
        )
        
    async def get_status(self, gateway_txn_id: str) -> GatewayResponse:
        return GatewayResponse(status="success", gateway_txn_id=gateway_txn_id)

    async def refund(self, gateway_txn_id: str, amount: int) -> GatewayResponse:
        return GatewayResponse(status="success", gateway_txn_id=gateway_txn_id)

    def verify_webhook(self, payload: bytes, headers: dict[str, str]) -> bool:
        return True