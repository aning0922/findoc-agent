"""Offline, synthetic-only smoke: HF_HUB_OFFLINE=1 TRANSFORMERS_OFFLINE=1 .venv/bin/python -m tests.real_research_memory_bge"""

import asyncio
from pathlib import Path
from tempfile import TemporaryDirectory
from uuid import uuid4

from app.conversations.repository import ConversationRepository
from app.research_memory.service import ResearchMemoryService
from tests.test_document_sources import Harness


def op():
    return str(uuid4())


async def main():
    from app.rag.embed import embed

    with TemporaryDirectory() as directory:
        h = Harness(Path(directory))
        service = ResearchMemoryService(
            runtime_root=h.root,
            workspace_id="demo",
            sources=h.service,
            conversations=ConversationRepository(h.registry, "demo"),
            embedder=embed,
            embedding_model_version="BAAI/bge-m3@revision-unknown",
        )
        target = await service.mutate(
            kind="create",
            operation_id=op(),
            memory_type="note",
            text="盈利账面很好，关注企业实际回款和偿还供应商款项能力",
            confirmed=True,
        )
        await service.mutate(
            kind="create",
            operation_id=op(),
            memory_type="note",
            text="评估主要商品的竞争格局与营销策略",
            confirmed=True,
        )
        query = "运营现金收支是否充裕？"
        before = await service.list(q=query)
        assert before["items"][0]["memory_id"] == target["memory_id"], "semantic ranking failed"
        await service.mutate(
            kind="delete", operation_id=op(), memory_id=target["memory_id"], expected_revision=1
        )
        after = await service.list(q=query)
        assert all(item["memory_id"] != target["memory_id"] for item in after["items"])
        print(
            "PASS: local BGE semantic ranking and deletion; synthetic notes; model revision unknown; no LLM"
        )


if __name__ == "__main__":
    asyncio.run(main())
