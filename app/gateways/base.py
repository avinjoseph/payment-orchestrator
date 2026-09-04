from dataclasses import dataclass
from typing import Any, Literal, Protocol

from app.services.exceptions import DomainException

GatewayStatus = Literal["success", "declined", "timeout", "error", "pending"]
WebhookNormalizedStatus = Literal["success", "declined", "refunded", "pending", "ignored"]
class TransientGatewayError(DomainException):
    def __init__(self, gateway:str ,message: str, raw_payload: dict[str, Any] | None=None):
        super().__init__(f"Transient faliure on {gateway} : {message}")
        self.gateway  = gateway
        self.message = message
        self.raw_payload = raw_payload
        
@dataclass(frozen=True)        
class GatewayResponse:
    status: GatewayStatus
    gateway_txn_id: str | None = None
    error_code: str | None = None
    # error_message: str | None = None
    raw: dict[str, Any] | None = None
    
@dataclass(frozen=True)
class WebhookEvent:
    gateway_txn_id: str
    event_type: str
    normalized_status: WebhookNormalizedStatus
    raw: dict[str, Any]
    
@dataclass(frozen=True)
class SettlementRecord:
    gateway_txn_id: str
    status: str
    amount: int
    currency: str
    raw: dict[str, Any] | None = None
    
class GatewayAdapter(Protocol):
    name :str
    
    async def charge(self, amount: int, currency: str, method: str, idempotency_key: str) -> GatewayResponse: ...
    async def get_status(self, gateway_txn_id: str) -> GatewayResponse: ...
    async def refund(self, gateway_txn_id: str, amount: int ) -> GatewayResponse: ...
    def verify_webhook(self,payload:bytes, headers:dict[str, str]) -> bool: ...
    def extract_event_id(self, payload: dict[str, Any]) -> str: ...
    def map_webhook_to_status(self, payload: dict[str, Any]) -> WebhookEvent: ...
    async def fetch_settlement_report(self) -> list[SettlementRecord]: ...
    