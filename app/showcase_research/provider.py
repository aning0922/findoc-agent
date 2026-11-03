"""Bounded SDK proxy reuses legacy single-attempt adapters without modifying them."""
import asyncio
import json
import time

from app.conversations.context import tokens
from app.showcase_research.models import ResearchError


class BoundedSDK:
    def __init__(self, client, limit, tool_choice=None):
        self.client, self.limit, self.tool_choice = client, limit, tool_choice
        self.chat = self.completions = self

    def with_options(self, **options):
        return BoundedSDK(self.client.with_options(**options), self.limit, self.tool_choice)

    def create(self, **kwargs):
        kwargs["max_tokens"] = self.limit
        if self.tool_choice is not None and kwargs.get("tools"):
            kwargs["tool_choice"] = self.tool_choice
        return self.client.chat.completions.create(**kwargs)


class Provider:
    def __init__(self, store, llm_client=None):
        self.store, self.llm = store, llm_client

    @property
    def configured(self):
        return self.llm is not None

    async def json(self, run_id, agent_id, prompt, *, tools=None, tool_choice=None):
        if self.llm is None:
            raise ResearchError("provider_unconfigured", 503)
        count = tokens(prompt)
        if len(prompt) > 28000 or count > 6000:
            raise ResearchError("provider_input_too_large")
        attempt = self.store.reserve_call(run_id, agent_id, input_tokens=count)
        deadline = self.store.usage(run_id)["deadline"]
        remaining = min(45, deadline - time.time())
        if remaining <= 0:
            raise ResearchError("budget_deadline_exhausted")
        llm = self.llm
        if hasattr(llm, "client"):
            from app.rag.openai_compatible_llm import OpenAICompatibleLLMClient
            bounded = BoundedSDK(llm.client.with_options(max_retries=0, timeout=remaining), 1024, tool_choice)
            llm = OpenAICompatibleLLMClient(llm.model, bounded)
        async def invoke():
            if tools is None:
                return await asyncio.to_thread(llm.generate_once, prompt)
            response = await asyncio.to_thread(llm.complete, [{"role": "user", "content": prompt}], tools)
            return response.message
        # Timeout may leave a provider thread alive; UNKNOWN stays charged and is never retried.
        result = await asyncio.wait_for(invoke(), timeout=remaining)
        self.store.returned(attempt)
        if time.time() > deadline:
            raise ResearchError("budget_deadline_exhausted")
        if tools is not None:
            encoded = json.dumps(result, ensure_ascii=False)
            if len(encoded) > 12000 or tokens(encoded) > 2048:
                raise ResearchError("provider_output_too_large")
            return result
        if not isinstance(result, str) or len(result) > 12000 or tokens(result) > 2048:
            raise ResearchError("provider_output_too_large")
        try:
            return json.loads(result)
        except (ValueError, TypeError):
            raise ResearchError("provider_protocol_error") from None
