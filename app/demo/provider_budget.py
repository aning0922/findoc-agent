"""Session-wide conservative CNY reservations for the explicitly configured DeepSeek smoke.

The ledger lives outside generations: demo reset cannot replenish this allowance.
Peak cache-miss rates verified against official pricing on 2026-11-03. No prompts,
responses, credentials or account balance are persisted here.
"""
from contextlib import closing
from decimal import Decimal
import hashlib
import json
from pathlib import Path
import sqlite3
from types import SimpleNamespace
from uuid import uuid4

from app.rag.openai_compatible_llm import OpenAICompatibleLLMClient

INPUT_PER_MILLION = Decimal('2')
OUTPUT_PER_MILLION = Decimal('8')
PRICE_SOURCE = 'https://api-docs.deepseek.com/zh-cn/quick_start/pricing/'


class ProviderBudgetError(RuntimeError):
    pass


class ProviderBudget:
    def __init__(self, path: Path, cap_cny: str = '5'):
        cap = Decimal(cap_cny)
        if not path.is_absolute() or not cap.is_finite() or not 0 < cap <= 5:
            raise ValueError('Invalid isolated provider budget')
        self.path, self.cap = path.resolve(), cap
        self.path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
        with closing(self.connect()) as db, db:
            db.execute('CREATE TABLE IF NOT EXISTS config (id INTEGER PRIMARY KEY CHECK(id=1), cap TEXT NOT NULL)')
            db.execute('INSERT OR IGNORE INTO config VALUES (1,?)', (str(cap),))
            if Decimal(db.execute('SELECT cap FROM config WHERE id=1').fetchone()[0]) != cap:
                raise ValueError('Existing allowance cannot be silently changed')
            db.execute('CREATE TABLE IF NOT EXISTS calls (id TEXT PRIMARY KEY, digest TEXT NOT NULL, '
                       'reserved TEXT NOT NULL, state TEXT NOT NULL, input_tokens INTEGER, output_tokens INTEGER)')
        self.path.chmod(0o600)

    def connect(self):
        return sqlite3.connect(self.path, timeout=5)

    def reserve(self, body: bytes, maximum_output: int):
        # UTF-8 byte count plus bounded message/schema framing is deliberately
        # more conservative than a tokenizer estimate. No images/native web tools.
        amount = (Decimal(len(body) + 2048) * INPUT_PER_MILLION
                  + Decimal(maximum_output) * OUTPUT_PER_MILLION) / 1_000_000
        call_id = str(uuid4())
        with closing(self.connect()) as db, db:
            db.execute('BEGIN IMMEDIATE')
            used = sum((Decimal(row[0]) for row in db.execute('SELECT reserved FROM calls')), Decimal(0))
            if used + amount > self.cap:
                raise ProviderBudgetError('provider_budget_exhausted')
            db.execute('INSERT INTO calls VALUES (?,?,?,\'unknown\',NULL,NULL)',
                       (call_id, hashlib.sha256(body).hexdigest(), str(amount)))
        return call_id

    def returned(self, call_id, response):
        usage = getattr(response, 'usage', None)
        prompt = getattr(usage, 'prompt_tokens', None)
        completion = getattr(usage, 'completion_tokens', None)
        if type(prompt) is not int or type(completion) is not int or min(prompt, completion) < 0:
            return  # Missing usage retains the complete worst-case reservation.
        with closing(self.connect()) as db, db:
            prior = Decimal(db.execute('SELECT reserved FROM calls WHERE id=?', (call_id,)).fetchone()[0])
            upper = (Decimal(prompt) * INPUT_PER_MILLION + Decimal(completion) * OUTPUT_PER_MILLION) / 1_000_000
            db.execute('UPDATE calls SET state=?,input_tokens=?,output_tokens=?,reserved=? WHERE id=?',
                       ('returned' if upper <= prior else 'usage_bound_exceeded', prompt, completion,
                        str(max(prior, upper)), call_id))

    def summary(self):
        with closing(self.connect()) as db:
            rows = db.execute('SELECT reserved,state,input_tokens,output_tokens FROM calls').fetchall()
        return dict(cap_cny=str(self.cap), calls=len(rows),
                    conservative_reserved_cny=str(sum((Decimal(r[0]) for r in rows), Decimal(0))),
                    usage_reported_calls=sum(r[2] is not None for r in rows),
                    input_tokens=sum(r[2] or 0 for r in rows), output_tokens=sum(r[3] or 0 for r in rows),
                    unknown_calls=sum(r[1] == 'unknown' for r in rows), price_source=PRICE_SOURCE,
                    actual_billed_cny='not_observed')


class BudgetedSDKClient:
    """Keep the existing adapter contract, including chained with_options()."""
    def __init__(self, client, budget: ProviderBudget):
        self._client, self.budget = client, budget
        self.chat = SimpleNamespace(completions=SimpleNamespace(create=self.create))

    def with_options(self, **kwargs):
        kwargs['max_retries'] = 0
        return type(self)(self._client.with_options(**kwargs), self.budget)

    def create(self, **kwargs):
        if kwargs.get('model') != 'deepseek-flash' or kwargs.get('stream', False):
            raise ProviderBudgetError('unsupported_budgeted_provider_request')
        if len(kwargs.get('messages', [])) > 80 or any(t.get('type') != 'function' for t in (kwargs.get('tools') or [])):
            raise ProviderBudgetError('unsupported_budgeted_provider_tools')
        maximum = kwargs.get('max_tokens', 2048)
        if type(maximum) is not int or maximum < 1:
            raise ProviderBudgetError('invalid_output_budget')
        kwargs['max_tokens'] = min(maximum, 4096)
        if set(kwargs.get('extra_body') or {}) - {'thinking'}:
            raise ProviderBudgetError('unsupported_provider_body_override')
        kwargs['extra_body'] = {'thinking': {'type': 'disabled'}}
        body = json.dumps(kwargs, ensure_ascii=False, allow_nan=False, separators=(',', ':')).encode()
        if len(body) > 65536:
            raise ProviderBudgetError('provider_input_budget_exceeded')
        call_id = self.budget.reserve(body, kwargs['max_tokens'])
        response = self._client.with_options(max_retries=0).chat.completions.create(**kwargs)
        self.budget.returned(call_id, response)
        return response


def budgeted_client(client: OpenAICompatibleLLMClient, path: Path, cap_cny='5'):
    from urllib.parse import urlsplit

    if urlsplit(str(client.client.base_url)).hostname != 'api.deepseek.com' or client.model != 'deepseek-flash':
        raise ProviderBudgetError('provider_price_not_verified')
    return type(client)(client.model, BudgetedSDKClient(client.client, ProviderBudget(path, cap_cny)))
