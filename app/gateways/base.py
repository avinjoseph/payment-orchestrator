from typing import NamedTuple, Protocol, Literal
from dataclasses import dataclass
from app.services.exceptions import DomainException

GatewayStatus = Literal["success", "declined", "timeout", "error", "pending"]

class TransientGatewayError(DomainException):
    def __init__(self, gateway:str ,message: str, raw_payload: dict | None=None):
        super().__init__(f"Transient faliure on {gateway} : {message}")
        self.gateway  = gateway
        self.message = message
        self.raw_payload = raw_payload
        
@dataclass(frozen=True)        
class GatewayResponse:
    status: GatewayStatus
    gateway_txn_id: str | None
    error_message: str | None = None
    raw: dict | None = None
    
class GatewayAdapter(Protocol):
    name :str
    
    async def charge(self, amount:int, currency:str, idempotency_key: str) -> GatewayResponse: ...
    async def get_status(self, gateway_txn_id: str) -> GatewayResponse: ...
    async def refund(self, gateway_txn_id: str, amount: int ) -> GatewayResponse: ...
    def verify_hook(self,payload:bytes, headers:dict) -> bool: ...