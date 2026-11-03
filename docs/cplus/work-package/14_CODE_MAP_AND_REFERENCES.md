# 14｜现有代码映射、审查清单和外部资料

## 代码入口（核验于 C 集成 SHA 45d55d75662f...）

| 功能 | 原代码 | 应用方式 |
|---|---|---|
| 企业/年报目录 | `app/disclosures/service.py`, `catalog.json`, `api.py` | 替换固定目录查询为 provider adapter，兼容原静态 fallback |
| 安全下载 | `app/disclosures/download.py` | 复用/扩展有受限下载器，改体积策略必须统一上下游 |
| PDF 上传/去重 | `app/documents/service.py`, `source_service.py`, `local_object_store.py` | 继续走 upload；保留 SHA/版本/封面校验 |
| 解析/向量索引 | `app/documents/processor.py`, `app/api/runtime_factory.py` | PyMuPDF/pdfplumber/BGE/Milvus；扩展索引合同时审查 source revision |
| OCR/解析质量 | `app/parsing/service.py`, `vision.py` | 独立 OCR artifact → read-only search adapter → 来源引用；不混财务核准 |
| 财务旧合同 | `app/research/template_contracts.py`, `app/agent/revenue_confirmation.py` | 3x2 基础不动，人工签核不由 Agent 自动执行 |
| 财务扩展 v2 | `app/finance_v2/models.py`, `extraction.py`, `service.py` | 仅资产负债 instant，v3 新领域容纳期间指标 |
| 首页与可视化 | `frontend/src/product/showcase/ShowcaseDashboard.tsx`, `app/dashboard/service.py` | 复用 Navigation/KPI，增量企业 360 与真实分析图 |
| 当前会话 | `app/conversations/*`, `frontend/src/product/Conversations.tsx` | 复用 scope/turn/memory，图表预填必须显式用户发送 |
| 多 Agent | `app/showcase_research/agents.py`, `jobs.py`, `findings.py` | 复用 bounded tools/routing/存储；新增比较/批次属于业务域 |
| 语义记忆 | `app/research_memory/service.py` | 收藏/变更/删除继续使用原版本与权限 |
| 报告 | `app/showcase_reports/service.py`, `printing.py`; `app/reports/` | 只读扩展导出，不改已有 revision |
| 演示隔离 | `app/demo/controller.py`, `process.py`, `gateway.py`, `seed.py` | cache 独立；generation/fence 必须保留 |
| UI 路由 | `frontend/src/product/productRoutes.ts`, `AppShell.tsx` | 主控统一接线，不删除旧深链 |
| 现有状态 | `docs/showcase/STATE.md`, `KNOWN_ISSUES.md`, `task-board.csv`, `EVIDENCE.md` | 保留真实与模拟分级、不要擦除 FAIL |
| 测试入口 | `.github/workflows/quality.yml`, `frontend/e2e/showcase-*` | 增量 CI 专项 smoke，绿色 Quality 不等于全部真实 E2E |

## 外部官方资源（检索日期 2026-11-03）

- 巨潮公司列表： https://www.cninfo.com.cn/new/snapshot/companyListCn （页面显示“代码、简称或拼音缩写”搜索框）。
- 巨潮信息披露： https://www.cninfo.com.cn/new/commonUrl?url=disclosure%2Flist%2Fnotice （有代码/简称/拼音、公告标题、年报分类、日期筛选）。
- 巨潮首页： https://www.cninfo.com.cn/ 。
- 深圳证券交易所公告： https://www.szse.cn/disclosure/notice/company/index.html 。
- 第三方代码示例中提及 `hisAnnouncement/query`，但这是非官方接口资料，不得视为稳定或官方开放 API；M0 需实际预检 HTTPS/条款及 fallback。
- 工具参考：`https://github.com/aning0922/findoc-agent/pull/2`（当前 C 候选草稿）、`https://github.com/aning0922/findoc-agent/tree/codex/findoc-showcase-c-integration`。

## 首个 Codex 技术走查动作

```
git fetch origin
git rev-parse origin/codex/findoc-showcase-c-integration
# SHA 匹配则创建 C+ 新集成工作树；不从 main/旧v12直接复用
# 读取 docs/showcase/STATE.md 和 KNOWN_ISSUES.md
# 先导出路由与模块结构，生成 M0 架构决策，再启动 worker
```

本工作包不包含 API 凭据、受版权保护的年报原件或私有 seed，已有 Git 忽略的本地证据与原开发数据保持不变。
