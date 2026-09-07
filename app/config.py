import json

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    PROJECT_NAME: str = "Payment Orchestration Platform"
    ENVIRONMENT: str = "production"
    VERSION: str = "1.0.0"
    DATABASE_URL: str 
    REDIS_URL: str = "redis://localhost:6379/0"
    
    CLIENT_API_KEYS_RAW: str = "{}"

    # Allowed CORS origins
    CORS_ORIGINS_RAW: str = '["https://merchant.example.com"]'

    # Gateway Credentials
    RAZORPAY_KEY_ID: str = ""
    RAZORPAY_KEY_SECRET: str = ""
    RAZORPAY_WEBHOOK_SECRET: str = ""

    STRIPE_API_KEY: str = ""
    STRIPE_WEBHOOK_SECRET: str = ""

    PAYU_MERCHANT_KEY: str = ""
    PAYU_MERCHANT_SALT: str = ""
    
    @property
    def CLIENT_API_KEYS(self) -> dict[str, str]:
        try:
            return json.loads(self.CLIENT_API_KEYS_RAW)
        except Exception:
            return {}
        
    @property
    def CORS_ORIGINS(self) -> list[str]:
        try:
            return json.loads(self.CORS_ORIGINS_RAW)
        except Exception:
            return []
        
    model_config = SettingsConfigDict(
        case_sensitive=True,
    )

settings = Settings()  # type: ignore[call-arg]