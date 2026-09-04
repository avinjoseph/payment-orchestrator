import hashlib
import hmac
from typing import cast

import httpx

from app.gateways.base import (
    GatewayAdapter,
    GatewayResponse,
        GatewayStatus,
    SettlementRecord,
    TransientGatewayError,
    WebhookEvent,
    WebhookNormalizedStatus,
)

RAZORPAY_STATUS_MAP = {
    "captured": "success",
    "authorized": "success",
    "failed": "declined",
    "created": "pending",
}

class RazorpayAdapter(GatewayAdapter):
    def __init__(self, key_id: str = "rzp_test_key", key_secret: str = "rzp_test_secret", webhook_secret: str = "rzp_webhook_sec" ):
        self.name = "razorpay"
        self.key_id = key_id
        self.key_secret = key_secret
        self.webhook_secret = webhook_secret
        self.base_url = "https://api.razorpay.com/v1"
        
    async def charge(self, amount: int, currency: str, method: str, idempotency_key: str) -> GatewayResponse:
        auth = (self.key_id, self.key_secret)
        payload = {
            "amount": amount,
            "currency": currency,
            "receipt": idempotency_key,
            "notes": {"method": method}
        }
        try:
            async with httpx.AsyncClient(timeout=1.0) as client:
                res = await client.post(f"{self.base_url}/payments", json=payload, auth=auth)
        except (httpx.TimeoutException, httpx.NetworkError) as e:
            raise TransientGatewayError(
                self.name, f"Network timeout/disconnect: {str(e)}"
            ) from e

        if res.status_code >= 500:
            raise TransientGatewayError(self.name, f"5xx Gateway error: {res.text}")

        data = res.json()
        raw_status = data.get("status", "failed")
        mapped_status = RAZORPAY_STATUS_MAP.get(raw_status, "error")

        error_code = None
        if mapped_status == "declined" and "error" in data:
            error_code = data["error"].get("code")

        return GatewayResponse(
            status=cast(GatewayStatus, mapped_status),
            gateway_txn_id=data.get("id"),
            error_code=error_code,
            raw=data,
        )

    async def get_status(self, gateway_txn_id: str) -> GatewayResponse:
        async with httpx.AsyncClient(timeout=1.0) as client:
            res = await client.get(f"{self.base_url}/payments/{gateway_txn_id}", auth=(self.key_id, self.key_secret))
        data = res.json()
        return GatewayResponse(
            status=cast(GatewayStatus, RAZORPAY_STATUS_MAP.get(data.get("status"), "error")),
            gateway_txn_id=data.get("id"),
            raw=data
        )

    async def refund(self, gateway_txn_id: str, amount: int) -> GatewayResponse:
        async with httpx.AsyncClient(timeout=1.0) as client:
            res = await client.post(
                f"{self.base_url}/payments/{gateway_txn_id}/refund",
                json={"amount": amount},
                auth=(self.key_id, self.key_secret)
            )
        data = res.json()
        return GatewayResponse(
            status="success" if res.status_code == 200 else "error",
            gateway_txn_id=data.get("id"),
            raw=data
        )

    def verify_webhook(self, payload: bytes, headers: dict[str, str]) -> bool:
        signature = headers.get("x-razorpay-signature", "")
        expected = hmac.new(self.webhook_secret.encode(), payload, hashlib.sha256).hexdigest()
        return hmac.compare_digest(expected, signature)

    def extract_event_id(self, payload: dict) -> str:
        # Razorpay payload: {"event": "payment.captured", "payload": {"payment": {"entity": {"id": "pay_123"}}}}
        payment_id = (
            payload.get("payload", {})
            .get("payment", {})
            .get("entity", {})
            .get("id", "")
        )
        event = payload.get("event", "event")
        return f"{event}_{payment_id}"
    
    def map_webhook_to_status(self, payload: dict) -> WebhookEvent:
        event = payload.get("event", "")
        payment_entity = (
            payload.get("payload", {})
            .get("payment", {})
            .get("entity", {})
        )
        gateway_txn_id = payment_entity.get("id", "")

        event_map = {
            "payment.captured": "success",
            "payment.authorized": "pending",
            "payment.failed": "declined",
            "refund.processed": "refunded",
        }
        return WebhookEvent(
            gateway_txn_id=gateway_txn_id,
            event_type=event,
            normalized_status=cast(WebhookNormalizedStatus, event_map.get(event, "ignored")),
            raw=payload,
        )

    async def fetch_settlement_report(self) -> list[SettlementRecord]:
        return []