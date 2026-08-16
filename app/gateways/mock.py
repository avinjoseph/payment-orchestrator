import uuid

from app.gateways.base import GatewayAdapter, GatewayResponse

class MockGatewayAdapter(GatewayAdapter):
    def __init__(self, name: str = "mock_gateway"):
        self.name = name
        
    async def charge(self, amount:int, currency:str, idempotency_key:str) -> GatewayResponse:
        txn_id = f"mock_{uuid.uuid4().hex[:12]}"
        return GatewayResponse(
            success = True,
            gateway_txn_id = txn_id,
            status = "captured",
            raw_payload = {"gateway": self.name,
                           "amount": amount,
                           "currency": currency,
                           "idempotency_key": idempotency_key,
                           "txn_id": txn_id}
        )
        
    async def get_status(self, gateway_txn_id: str) -> GatewayResponse:
        return GatewayResponse(
            success = True,
            gateway_txn_id = gateway_txn_id,
            status = "captured"
        )
        
    async def refund(self, gateway_txn_id: str, amount: int) -> GatewayResponse:
        return GatewayResponse(
            success = True,
            gateway_txn_id = gateway_txn_id,
            status = "refunded"
        )
        
    def verify_webhook(self, payload: bytes, headers: dict) -> bool:
        # In a real implementation, you would verify the webhook signature here
        return True