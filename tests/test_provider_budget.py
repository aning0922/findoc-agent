from types import SimpleNamespace

import pytest

from app.demo.provider_budget import BudgetedSDKClient, ProviderBudget, ProviderBudgetError


class SDK:
    def __init__(self):
        self.calls, self.fail = [], False
        self.chat = SimpleNamespace(completions=SimpleNamespace(create=self.create))

    def with_options(self, **kwargs):
        assert kwargs['max_retries'] == 0
        return self

    def create(self, **kwargs):
        self.calls.append(kwargs)
        if self.fail:
            raise TimeoutError('outcome unknown')
        return SimpleNamespace(usage=SimpleNamespace(prompt_tokens=12, completion_tokens=2))


def request():
    return dict(model='deepseek-flash', messages=[{'role': 'user', 'content': 'fixture'}], max_tokens=32)


def test_unknown_reservation_survives_restart_and_cannot_reset_allowance(tmp_path):
    sdk = SDK()
    sdk.fail = True
    budget = ProviderBudget(tmp_path / 'outside-generation.db', '0.006')
    client = BudgetedSDKClient(sdk, budget)
    with pytest.raises(TimeoutError):
        client.create(**request())
    assert len(sdk.calls) == 1
    reopened = ProviderBudget(budget.path, '0.006')
    with pytest.raises(ProviderBudgetError, match='exhausted'):
        BudgetedSDKClient(sdk, reopened).create(**request())
    assert len(sdk.calls) == 1 and reopened.summary()['unknown_calls'] == 1
    with pytest.raises(ValueError):
        ProviderBudget(budget.path, '5')


def test_sdk_options_token_caps_and_native_tools_do_not_bypass_ledger(tmp_path):
    sdk = SDK()
    budget = ProviderBudget(tmp_path / 'cost.db')
    client = BudgetedSDKClient(sdk, budget).with_options(max_retries=2)
    client.create(**{**request(), 'max_tokens': 99999})
    assert sdk.calls[-1]['max_tokens'] == 4096
    assert sdk.calls[-1]['extra_body'] == {'thinking': {'type': 'disabled'}}
    for override in ({'tools': [{'type': 'web_search'}]}, {'messages': [{'role': 'user', 'content': 'x' * 70000}]},
                     {'extra_body': {'max_tokens': 100000}}, {'max_tokens': 0}):
        with pytest.raises(ProviderBudgetError):
            client.create(**{**request(), **override})
    assert len(sdk.calls) == 1
    summary = budget.summary()
    assert summary['calls'] == 1 and summary['usage_reported_calls'] == 1
    assert summary['actual_billed_cny'] == 'not_observed'
