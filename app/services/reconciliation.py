from dataclasses import dataclass

import structlog
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import ReconciliationMismatch, Transactions
from app.gateways.base import SettlementRecord
from app.gateways.registry import GatewayRegistry
from app.gateways.registry import registry as default_registry

logger = structlog.get_logger(__name__)

@dataclass(frozen=True)
class MismatchItem:
    kind: str
    gateway_txn_id: str
    local_status: str | None
    remote_status: str
    
class ReconiliationService:
    def __init__(self, db: AsyncSession, registry: GatewayRegistry | None = None):
        self.db = db
        self.registry = registry or default_registry
        
    def normalize_remote_status(self, remote_status: str) -> str:
        mapping = {
            "captured": "captured",
            "succeeded": "captured",
            "success": "captured",
            "failed": "failed",
            "refunded": "refunded",
        }
        return mapping.get(remote_status.lower(), "processing")
    
    async def reconcile_gateway(self, gateway: str) -> list[MismatchItem]:
        adapter = self.registry.get_adapter(gateway)
        remote_records: list[SettlementRecord] = await adapter.fetch_settlement_report()
        mismatches: list[MismatchItem] = []

        for remote in remote_records:
            stmt = select(Transactions).where(Transactions.gateway_txn_id == remote.gateway_txn_id)
            res = await self.db.execute(stmt)
            local_txn = res.scalar_one_or_none()

            normalized_remote = self.normalize_remote_status(remote.status)

            if not local_txn:
                mismatch = MismatchItem(
                    kind="missing_locally",
                    gateway_txn_id=remote.gateway_txn_id,
                    local_status=None,
                    remote_status=normalized_remote,
                )
                mismatches.append(mismatch)
                self.db.add(
                    ReconciliationMismatch(
                        gateway=gateway,
                        gateway_txn_id=remote.gateway_txn_id,
                        mismatch_type="missing_locally",
                        local_status=None,
                        remote_status=normalized_remote,
                        remote_payload=remote.raw,
                    )
                )
            elif local_txn.status != normalized_remote:
                mismatch = MismatchItem(
                    kind="status_mismatch",
                    gateway_txn_id=remote.gateway_txn_id,
                    local_status=local_txn.status,
                    remote_status=normalized_remote,
                )
                mismatches.append(mismatch)
                self.db.add(
                    ReconciliationMismatch(
                        gateway=gateway,
                        gateway_txn_id=remote.gateway_txn_id,
                        mismatch_type="status_mismatch",
                        local_status=local_txn.status,
                        remote_status=normalized_remote,
                        remote_payload=remote.raw,
                    )
                )

        if mismatches:
            await self.db.commit()
            logger.warning("reconciliation_mismatches_flagged", gateway=gateway, count=len(mismatches))

        return mismatches