import uuid
from datetime import datetime

from sqlalchemy import BigInteger, DateTime, ForeignKey, Integer, String, Text, func, UniqueConstraint
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship
from app.db.session import Base

class Transactions(Base):
    __tablename__ = "transactions"
    
    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    idempotency_key: Mapped[str] = mapped_column(String(255), unique=True, nullable=False, index=True)
    amount: Mapped[int] = mapped_column(BigInteger, nullable= False)
    currency: Mapped[str] = mapped_column(String(3), nullable= False)
    status: Mapped[str] = mapped_column(String(50), nullable=False, default="created", index=True)
    gateway: Mapped[str | None] = mapped_column(String(50), nullable=True)
    gateway_txn_id: Mapped[str | None] = mapped_column(String(255), nullable=True)
    attempt_count: Mapped[int] = mapped_column(Integer, default=0)
    customer_ref: Mapped[str | None] = mapped_column(String(255), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False)
    
    events: Mapped[list["TransactionEvents"]] = relationship("TransactionEvents", back_populates="transaction", cascade="all, delete-orphan")
    
class TransactionEvents(Base):
    __tablename__ = "transaction_events"
    
    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    transaction_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("transactions.id", ondelete="CASCADE"), nullable=False, index=True)
    from_status: Mapped[str | None] = mapped_column(String(50), nullable=True)
    to_status: Mapped[str] = mapped_column(String(50), nullable=False)
    gateway: Mapped[str | None] = mapped_column(String(50), nullable=True)
    reason: Mapped[str | None] = mapped_column(Text, nullable=True)
    payload: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    
    transaction: Mapped["Transactions"] = relationship("Transactions", back_populates="events")
    

class InboundWebhook(Base):
    __tablename__ = "inbound_webhooks"
    
    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    gateway: Mapped[str] = mapped_column(String(50), nullable=False, index=True)
    gateway_event_id: Mapped[str] = mapped_column(String(255), nullable=False)
    payload: Mapped[dict] = mapped_column(JSONB, nullable=False)
    received_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(),nullable=False)
    
    __table_args__ = (
        UniqueConstraint("gateway", "gateway_event_id", name="uq_gateway_event_id"),
    )
    
class ReconciliationMismatch(Base):
    __tablename__ = "reconciliation_mismatches"
    
    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    gateway: Mapped[str] = mapped_column(String(50), nullable=False)
    gateway_txn_id: Mapped[str] = mapped_column(String(255), nullable=False)
    mismatch_type: Mapped[str] = mapped_column(String(50), nullable=False)
    local_status: Mapped[str | None] = mapped_column(String(50), nullable=True)
    remote_status: Mapped[str] = mapped_column(String(50), nullable=False)
    remote_payload: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
    resolved: Mapped[bool] = mapped_column(default=False, nullable=False)
    detected_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)