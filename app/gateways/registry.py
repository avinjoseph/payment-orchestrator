from dataclasses import dataclass
from app.gateways.base import GatewayAdapter
from app.gateways.mock import MockGatewayAdapter
from app.gateways.razorpay import RazorpayAdapter
from app.gateways.stripe import StripeAdapter
from app.gateways.payu import PayUAdapter
from app.gateways.upi import UPIAdapter

@dataclass(frozen=True)
class GatewayConfig:
    adapter: GatewayAdapter
    supported_currencies: set[str]
    supported_methods: set[set]
    
class GatewayRegistry:
    def __init__(self):
        self._registry: dict[str, GatewayConfig] = {}
        
    def register(self, name:str, adapter: GatewayAdapter, currencies: set[str], methods: set[str]) -> None:
        self._registry[name] = GatewayConfig(
            adapter=adapter,
            supported_currencies=currencies,
            supported_methods=methods
        )
        
    def get_adapter(self, name: str) -> GatewayAdapter:
        if name not in self._registry:
            raise KeyError(f"Gateway '{name}' is not registered.")
        return self._registry[name].adapter
    
    def get_eligible_gateways(self, method: str, currency: str) -> list[str]:
        return [
            name for name, cfg in self._registry.items()
            if method in cfg.supported_methods and currency in cfg.supported_currencies
        ]

    def list_gateways(self) -> list[str]:
        return list(self._registry.keys())
    
registry = GatewayRegistry()
registry.register(
    name="mock",
    adapter=MockGatewayAdapter(name="mock"),
    currencies={"INR", "USD", "EUR"},
    methods={"card", "upi", "netbanking"}
)
registry.register("razorpay", RazorpayAdapter(), currencies={"INR", "USD"}, methods={"card", "upi", "netbanking"})
registry.register("stripe", StripeAdapter(), currencies={"USD", "EUR", "GBP", "INR"}, methods={"card"})
registry.register("payu", PayUAdapter(), currencies={"INR"}, methods={"card", "netbanking"})
registry.register("upi", UPIAdapter(), currencies={"INR"}, methods={"upi"})