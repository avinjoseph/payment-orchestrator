import uuid

class DomainException(Exception):
    pass

class TransactionNotFoundException(DomainException):
    def __init__(self, transaction_id: uuid.UUID):
        super().__init__(f"Transaction with ID {transaction_id} not found.")
        self.transaction_id = transaction_id
        
class IllegalTransitionError(DomainException):
    def __init__(self, current_status: str, target_status: str, transaction_id: uuid.UUID):
        super().__init__(
            f"Cannot transition transaction {transaction_id} from '{current_status}' to '{target_status}'."
        )
        self.current_status = current_status
        self.target_status = target_status
        self.transaction_id = transaction_id
        
class IdempotencyConflictError(DomainException):
    def __init__(self, idempotency_key:str):
        super().__init__(
            f"A transaction with Idempotency-Key '{idempotency_key}' already exists."
        )
        self.idempotency_key = idempotency_key
        
class AllGatewaysExhaustedError(DomainException):
    def __init__(self, attempted: list[str]):
        super().__init__(f"All eligible gateways were exhausted without success: {attempted}")
        self.attempted = attempted

class FailoverBudgetExceededError(DomainException):
    def __init__(self, elapsed_ms: int):
        super().__init__(f"Failover time budget exceeded ({elapsed_ms}ms).")
        self.elapsed_ms = elapsed_ms
        
class NoHealthyGatewayError(DomainException):
    def __init__(self, method: str, currency: str):
        super().__init__(f"No healthy gateways available for method='{method}' and currency='{currency}'")
