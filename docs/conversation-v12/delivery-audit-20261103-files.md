# 相对 origin/main 的完整改动清单

审计基线：`origin/main@1f0a3d4131480ac0ea742772127afac3c892fc7c`。产品快照：`77a2e18ff42173d7e555a594a092439c51b116ac`。初始共91文件、10655行新增/17行删除，17个提交，分支未落后main。

| 类别 | 文件数 | 新增行 | 删除行 |
| --- | ---: | ---: | ---: |
| CI | 1 | 2 | 0 |
| 文档与交接材料 | 32 | 2285 | 3 |
| 后端会话/偏好与runtime接线 | 21 | 2752 | 0 |
| 只读真实案例 | 3 | 623 | 0 |
| 测试与验证脚本 | 18 | 3881 | 2 |
| 依赖 | 2 | 5 | 5 |
| 前端应用 | 14 | 1107 | 7 |

## 全部产品快照文件

| 状态 | 文件 | 新增行 | 删除行 |
| --- | --- | ---: | ---: |
| M | [.github/workflows/quality.yml](../../.github/workflows/quality.yml) | 2 | 0 |
| M | [README.md](../../README.md) | 14 | 3 |
| M | [app/api/research_history_app.py](../../app/api/research_history_app.py) | 12 | 0 |
| M | [app/api/runtime_factory.py](../../app/api/runtime_factory.py) | 24 | 0 |
| M | [app/companies/migrations.py](../../app/companies/migrations.py) | 6 | 0 |
| A | [app/conversations/__init__.py](../../app/conversations/__init__.py) | 1 | 0 |
| A | [app/conversations/api.py](../../app/conversations/api.py) | 110 | 0 |
| A | [app/conversations/context.py](../../app/conversations/context.py) | 250 | 0 |
| A | [app/conversations/context_schema.py](../../app/conversations/context_schema.py) | 17 | 0 |
| A | [app/conversations/graph.py](../../app/conversations/graph.py) | 110 | 0 |
| A | [app/conversations/models.py](../../app/conversations/models.py) | 388 | 0 |
| A | [app/conversations/repository.py](../../app/conversations/repository.py) | 669 | 0 |
| A | [app/conversations/schema.py](../../app/conversations/schema.py) | 103 | 0 |
| A | [app/conversations/service.py](../../app/conversations/service.py) | 108 | 0 |
| A | [app/conversations/summaries.py](../../app/conversations/summaries.py) | 124 | 0 |
| A | [app/conversations/tools.py](../../app/conversations/tools.py) | 233 | 0 |
| A | [app/memory/__init__.py](../../app/memory/__init__.py) | 1 | 0 |
| A | [app/memory/api.py](../../app/memory/api.py) | 86 | 0 |
| A | [app/memory/candidates.py](../../app/memory/candidates.py) | 27 | 0 |
| A | [app/memory/models.py](../../app/memory/models.py) | 142 | 0 |
| A | [app/memory/repository.py](../../app/memory/repository.py) | 247 | 0 |
| A | [app/memory/schema.py](../../app/memory/schema.py) | 53 | 0 |
| A | [app/memory/service.py](../../app/memory/service.py) | 41 | 0 |
| A | [demo/conversation-v12/README.md](../../demo/conversation-v12/README.md) | 49 | 0 |
| A | [demo/conversation-v12/index.html](../../demo/conversation-v12/index.html) | 76 | 0 |
| A | [demo/conversation-v12/real-model-history.json](../../demo/conversation-v12/real-model-history.json) | 498 | 0 |
| A | [docs/conversation-v12/api-contract.md](../../docs/conversation-v12/api-contract.md) | 12 | 0 |
| A | [docs/conversation-v12/architecture.md](../../docs/conversation-v12/architecture.md) | 40 | 0 |
| A | [docs/conversation-v12/backend-a0.md](../../docs/conversation-v12/backend-a0.md) | 384 | 0 |
| A | [docs/conversation-v12/baseline.md](../../docs/conversation-v12/baseline.md) | 19 | 0 |
| A | [docs/conversation-v12/contracts.md](../../docs/conversation-v12/contracts.md) | 32 | 0 |
| A | [docs/conversation-v12/design.md](../../docs/conversation-v12/design.md) | 22 | 0 |
| A | [docs/conversation-v12/frontend-a0.md](../../docs/conversation-v12/frontend-a0.md) | 190 | 0 |
| A | [docs/conversation-v12/handoff/01_PRODUCT_UX.md](../../docs/conversation-v12/handoff/01_PRODUCT_UX.md) | 48 | 0 |
| A | [docs/conversation-v12/handoff/02_TECH_DESIGN.md](../../docs/conversation-v12/handoff/02_TECH_DESIGN.md) | 117 | 0 |
| A | [docs/conversation-v12/handoff/03_PHASES_ACCEPTANCE.md](../../docs/conversation-v12/handoff/03_PHASES_ACCEPTANCE.md) | 90 | 0 |
| A | [docs/conversation-v12/handoff/04_CODEX_KICKOFF.md](../../docs/conversation-v12/handoff/04_CODEX_KICKOFF.md) | 43 | 0 |
| A | [docs/conversation-v12/handoff/README.md](../../docs/conversation-v12/handoff/README.md) | 52 | 0 |
| A | [docs/conversation-v12/human-review.md](../../docs/conversation-v12/human-review.md) | 27 | 0 |
| A | [docs/conversation-v12/journey.md](../../docs/conversation-v12/journey.md) | 11 | 0 |
| A | [docs/conversation-v12/memory-b1.md](../../docs/conversation-v12/memory-b1.md) | 72 | 0 |
| A | [docs/conversation-v12/migration-plan.md](../../docs/conversation-v12/migration-plan.md) | 15 | 0 |
| A | [docs/conversation-v12/migration.md](../../docs/conversation-v12/migration.md) | 11 | 0 |
| A | [docs/conversation-v12/orchestration.md](../../docs/conversation-v12/orchestration.md) | 73 | 0 |
| A | [docs/conversation-v12/pr-description.md](../../docs/conversation-v12/pr-description.md) | 9 | 0 |
| A | [docs/conversation-v12/release-notes.md](../../docs/conversation-v12/release-notes.md) | 32 | 0 |
| A | [docs/conversation-v12/requirements.md](../../docs/conversation-v12/requirements.md) | 15 | 0 |
| A | [docs/conversation-v12/reviews/a0-architecture.md](../../docs/conversation-v12/reviews/a0-architecture.md) | 180 | 0 |
| A | [docs/conversation-v12/reviews/a1-persistence.md](../../docs/conversation-v12/reviews/a1-persistence.md) | 75 | 0 |
| A | [docs/conversation-v12/reviews/a3-foundation.md](../../docs/conversation-v12/reviews/a3-foundation.md) | 26 | 0 |
| A | [docs/conversation-v12/reviews/g-final-audit.md](../../docs/conversation-v12/reviews/g-final-audit.md) | 117 | 0 |
| A | [docs/conversation-v12/risk-register.md](../../docs/conversation-v12/risk-register.md) | 18 | 0 |
| A | [docs/conversation-v12/status.md](../../docs/conversation-v12/status.md) | 17 | 0 |
| A | [docs/conversation-v12/tests.md](../../docs/conversation-v12/tests.md) | 78 | 0 |
| A | [docs/conversation-v12/user-guide.md](../../docs/conversation-v12/user-guide.md) | 45 | 0 |
| A | [docs/conversation-v12/validation-a0.md](../../docs/conversation-v12/validation-a0.md) | 154 | 0 |
| A | [docs/conversation-v12/validation-a4-preparation.md](../../docs/conversation-v12/validation-a4-preparation.md) | 247 | 0 |
| A | [frontend/e2e/conversation-api.spec.ts](../../frontend/e2e/conversation-api.spec.ts) | 234 | 0 |
| A | [frontend/e2e/conversation-browser.spec.ts](../../frontend/e2e/conversation-browser.spec.ts) | 240 | 0 |
| A | [frontend/e2e/conversation-helpers.ts](../../frontend/e2e/conversation-helpers.ts) | 76 | 0 |
| A | [frontend/e2e/conversation-memory.spec.ts](../../frontend/e2e/conversation-memory.spec.ts) | 185 | 0 |
| A | [frontend/e2e/conversation-recovery.spec.ts](../../frontend/e2e/conversation-recovery.spec.ts) | 175 | 0 |
| M | [frontend/package-lock.json](../../frontend/package-lock.json) | 4 | 4 |
| M | [frontend/package.json](../../frontend/package.json) | 1 | 1 |
| A | [frontend/playwright.conversations.config.ts](../../frontend/playwright.conversations.config.ts) | 27 | 0 |
| M | [frontend/src/product/AppShell.tsx](../../frontend/src/product/AppShell.tsx) | 2 | 2 |
| A | [frontend/src/product/Conversations.module.css](../../frontend/src/product/Conversations.module.css) | 102 | 0 |
| A | [frontend/src/product/Conversations.tsx](../../frontend/src/product/Conversations.tsx) | 345 | 0 |
| M | [frontend/src/product/FinancialProduct.tsx](../../frontend/src/product/FinancialProduct.tsx) | 5 | 0 |
| M | [frontend/src/product/QADialog.tsx](../../frontend/src/product/QADialog.tsx) | 2 | 2 |
| A | [frontend/src/product/ResearchPreferences.tsx](../../frontend/src/product/ResearchPreferences.tsx) | 110 | 0 |
| A | [frontend/src/product/conversationApi.ts](../../frontend/src/product/conversationApi.ts) | 187 | 0 |
| A | [frontend/src/product/conversationFacts.ts](../../frontend/src/product/conversationFacts.ts) | 16 | 0 |
| A | [frontend/src/product/conversationPdf.ts](../../frontend/src/product/conversationPdf.ts) | 43 | 0 |
| A | [frontend/src/product/conversationSources.ts](../../frontend/src/product/conversationSources.ts) | 39 | 0 |
| A | [frontend/src/product/conversationState.ts](../../frontend/src/product/conversationState.ts) | 50 | 0 |
| A | [frontend/src/product/conversationTypes.ts](../../frontend/src/product/conversationTypes.ts) | 142 | 0 |
| A | [frontend/src/product/memoryApi.ts](../../frontend/src/product/memoryApi.ts) | 57 | 0 |
| M | [frontend/src/product/productRoutes.ts](../../frontend/src/product/productRoutes.ts) | 7 | 3 |
| A | [frontend/tests/conversationApi.test.ts](../../frontend/tests/conversationApi.test.ts) | 170 | 0 |
| A | [frontend/tests/conversationAuditRecovery.test.ts](../../frontend/tests/conversationAuditRecovery.test.ts) | 131 | 0 |
| A | [frontend/tests/conversationFoundation.test.ts](../../frontend/tests/conversationFoundation.test.ts) | 59 | 0 |
| A | [frontend/tests/conversationPdf.test.ts](../../frontend/tests/conversationPdf.test.ts) | 52 | 0 |
| A | [scripts/run_conversation_v12_e2e.py](../../scripts/run_conversation_v12_e2e.py) | 252 | 0 |
| A | [scripts/validate_conversation_v12_live.py](../../scripts/validate_conversation_v12_live.py) | 295 | 0 |
| A | [tests/support/conversation_app.py](../../tests/support/conversation_app.py) | 199 | 0 |
| A | [tests/test_conversation_a1.py](../../tests/test_conversation_a1.py) | 674 | 0 |
| A | [tests/test_conversation_context.py](../../tests/test_conversation_context.py) | 161 | 0 |
| A | [tests/test_conversation_graph.py](../../tests/test_conversation_graph.py) | 533 | 0 |
| M | [tests/test_d23_migrations.py](../../tests/test_d23_migrations.py) | 8 | 2 |
| A | [tests/test_memory_b1.py](../../tests/test_memory_b1.py) | 410 | 0 |

## 原17个提交（保留全部历史）

```text
4d88756 docs(conversations): freeze v1.2 contracts and orchestration plan
3957f04 fix(frontend): pin Vite 8.2.4 security patch
71468aa feat(memory): add confirmed local preferences and operation receipts
b5208c0 feat(conversations): add persistent research chat and preference interface
e458389 feat(conversations): persist idempotent turns and read-only recovery
a699464 fix(memory): support the requested cash-flow preference phrase
80fe451 fix(conversations): recover rejected turns without replaying requests
8b160b1 test(conversations): prepare isolated browser and live validation harnesses
847b19c feat(conversations): connect bounded graph to verified read-only tools
f4eee49 ci: run conversation and memory contract checks
8638b05 feat(conversations): persist bounded structural summaries for long chats
c103ab3 fix(conversations): preserve complete questions and normalize source races
337916f fix(conversations): resolve rejected writes and deleted preference receipts
5e9fb1b test(conversations): cover final recovery and source invalidation cases
10339fd fix(conversations): improve table reading and observe physical vector search
ad12570 test(conversations): verify explicit preference journey and robust fixtures
77a2e18 docs(conversations): deliver validated v1.2 candidate and real-model history
```

## 本次仅文档审计变更

本轮不改应用、测试、验证脚本、依赖或CI；新增本清单、同目录`delivery-audit-20261103.md`与`delivery-validation-20261103.json`，更新当前路径/交付状态与验证索引，清理交接README末尾一个空行。最终完整差异以GitHub的main…开发分支比较为准，文件清单可由`git diff --name-status origin/main...HEAD`重新取得。

[查看GitHub全部差异](https://github.com/aning0922/findoc-agent/compare/main...codex/conversation-memory-v12-20261102)
