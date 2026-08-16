from typing import NamedTuple, Protocol


class GatewayResponse(NamedTuple):
    success: bool
    gateway_txn_id: str | None
    status: str | None
    error_message: str | None = None
    raw_payload: dict | None = None
    
class GatewayAdapter(Protocol):
    async def charge(self, amount:int, currency:str, idempotency_key: str) -> GatewayResponse: ...
    async def get_status(self, gateway_txn_id: str) -> GatewayResponse: ...
    async def refund(self, gateway_txn_id: str, amount: int ) -> GatewayResponse: ...
    def verify_hook(self,payload:bytes, headers:dict) -> bool: ...