"""Explicit actions only; candidates do not call this service or persist themselves."""
from app.memory.models import (
    CreateMemoryRequest, DeleteMemoryRequest, MemoryItem, MemoryList, MemoryOperation,
    PatchMemoryRequest,
)
from app.memory.repository import MemoryRepository


class MemoryService:
    def __init__(self, repository: MemoryRepository) -> None:
        self.repository = repository

    def list(self) -> MemoryList:
        return self.repository.list()

    def recall_context(self) -> MemoryList:
        return self.repository.recall_context()

    def excluded_source_turn_ids(self) -> frozenset[str]:
        return self.repository.excluded_source_turn_ids()

    def get(self, memory_id: str) -> MemoryItem:
        return self.repository.get(memory_id)

    def get_operation(self, operation_id: str) -> MemoryOperation:
        return self.repository.get_operation(operation_id)

    def create(self, request: CreateMemoryRequest) -> tuple[MemoryItem, bool]:
        item, replayed = self.repository.mutate("create_memory", request)
        assert isinstance(item, MemoryItem)
        return item, replayed

    def update(self, memory_id: str, request: PatchMemoryRequest) -> MemoryItem:
        item, _ = self.repository.mutate("update_memory", request, memory_id)
        assert isinstance(item, MemoryItem)
        return item

    def delete(self, memory_id: str, request: DeleteMemoryRequest) -> MemoryOperation:
        receipt, _ = self.repository.mutate("delete_memory", request, memory_id)
        assert isinstance(receipt, MemoryOperation)
        return receipt
