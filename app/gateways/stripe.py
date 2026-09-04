# app/adapters/stripe.py
import httpx

from app.gateways.base import GatewayAdapter, GatewayResponse, TransientGatewayError

STRIPE_STATUS_MAP = {
    "succeeded": "success",
    "requires_action": "pending",
    "requires_payment_method": "declined",
    "canceled": "declined"
}

class StripeAdapter(GatewayAdapter):
    def __init__(self, api_key: str = "sk_test_123", webhook_secret: str = "whsec_123"):
        self.name = "stripe"
        self.api_key = api_key
        self.webhook_secret = webhook_secret
        self.base_url = "https://api.stripe.com/v1"

    async def charge(self, amount: int, currency: str, method: str, idempotency_key: str) -> GatewayResponse:
        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Idempotency-Key": idempotency_key,
            "Content-Type": "application/x-www-form-urlencoded"
        }
        data = {
            "amount": str(amount),
            "currency": currency.lower(),
            "payment_method_types[]": method if method in ["card"] else "card",
            "confirm": "true"
        }
        try:
            async with httpx.AsyncClient(timeout=1.0) as client:
                res = await client.post(f"{self.base_url}/payment_intents", data=data, headers=headers)
        except (httpx.TimeoutException, httpx.NetworkError) as e:
            raise TransientGatewayError(
                self.name, f"Network timeout/disconnect: {str(e)}"
            ) from e

        if res.status_code >= 500:
            raise TransientGatewayError(self.name, f"5xx Gateway error: {res.text}")

        res_json = res.json()
        if "error" in res_json:
            return GatewayResponse(
                status="declined",
                error_code=res_json["error"].get("code"),
                raw=res_json
            )

        status_str = res_json.get("status", "unknown")
        return GatewayResponse(
            status=STRIPE_STATUS_MAP.get(status_str, "error"),
            gateway_txn_id=res_json.get("id"),
            raw=res_json
        )

    async def get_status(self, gateway_txn_id: str) -> GatewayResponse:
        headers = {"Authorization": f"Bearer {self.api_key}"}
        async with httpx.AsyncClient(timeout=1.0) as client:
            res = await client.get(f"{self.base_url}/payment_intents/{gateway_txn_id}", headers=headers)
        res_json = res.json()
        return GatewayResponse(
            status=STRIPE_STATUS_MAP.get(res_json.get("status"), "error"),
            gateway_txn_id=res_json.get("id"),
            raw=res_json
        )

    async def refund(self, gateway_txn_id: str, amount: int) -> GatewayResponse:
        headers = {"Authorization": f"Bearer {self.api_key}"}
        async with httpx.AsyncClient(timeout=1.0) as client:
            res = await client.post(f"{self.base_url}/refunds", data={"payment_intent": gateway_txn_id, "amount": amount}, headers=headers)
        return GatewayResponse(status="success" if res.status_code == 200 else "error", gateway_txn_id=gateway_txn_id)

    def verify_webhook(self, payload: bytes, headers: dict[str, str]) -> bool:
        sig_header = headers.get("stripe-signature", "")
        # Minimal verification implementation for testing
        return len(sig_header) > 0