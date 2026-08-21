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
        
        