# app/adapters/payu.py
import hmac
import hashlib
import httpx
from app.gateways.base import GatewayAdapter, GatewayResponse, TransientGatewayError

class PayUAdapter(GatewayAdapter):
    def __init__(self, merchant_key: str = "payu_key", merchant_salt: str = "payu_salt"):
        self.name = "payu"
        self.merchant_key = merchant_key
        self.merchant_salt = merchant_salt
        self.base_url = "https://test.payu.in/merchant/postservice?form=2"

    async def charge(self, amount: int, currency: str, method: str, idempotency_key: str) -> GatewayResponse:
        txnid = f"payu_{idempotency_key[:12]}"
        hash_seq = f"{self.merchant_key}|{txnid}|{amount}|product|cust|test@test.com|||||||||||{self.merchant_salt}"
        calc_hash = hashlib.sha512(hash_seq.encode()).hexdigest()

        payload = {
            "key": self.merchant_key,
            "txnid": txnid,
            "amount": str(amount),
            "productinfo": "product",
            "firstname": "cust",
            "email": "test@test.com",
            "hash": calc_hash
        }
        try:
            async with httpx.AsyncClient(timeout=1.0) as client:
                res = await client.post(self.base_url, data=payload)
        except (httpx.TimeoutException, httpx.NetworkError) as e:
            raise TransientGatewayError(self.name, f"Network timeout/disconnect: {str(e)}")

        if res.status_code >= 500:
            raise TransientGatewayError(self.name, f"PayU 5xx Server error: {res.text}")

        # PayU redirects/pending flow
        return GatewayResponse(status="pending", gateway_txn_id=txnid, raw={"response": res.text})

    async def get_status(self, gateway_txn_id: str) -> GatewayResponse:
        return GatewayResponse(status="success", gateway_txn_id=gateway_txn_id)

    async def refund(self, gateway_txn_id: str, amount: int) -> GatewayResponse:
        return GatewayResponse(status="success", gateway_txn_id=gateway_txn_id)

    def verify_webhook(self, payload: bytes, headers: dict[str, str]) -> bool:
        return True