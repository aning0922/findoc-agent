# 08｜OCR 入正式检索、混合检索、重排序与回答质量

## 当前真实缺口

现有 `ParseV2Service` 的 OCR 文本落在独立 parse-v2 SQLite+FTS，不自动构成正式 `SelectedScopeSearch`/Milvus 可检索来源；现有 `showcase_research/agents.py` 使用受限选定文档的 dense search，风险问题有少量硬编码关键字过滤，但真实多 Agent 研究出现了与“经营风险”不紧密相关的委托理财表格片段。

## 推荐架构

```
实际PDF bytes & 源版本
  ├── Fast PDF evidence (已有信任边界)
  └── OCR artifact (新版本，明确 unreviewed)
        ↓ normalized SearchDocument + SourceEvidenceRef
  ├── lexical FTS/BM25
  └── BGE dense / Milvus
        ↓ RRF + 基于章节/年份/报表的过滤
        ↓ reranker（可选本地 cross-encoder；没有则规则质量过滤）
        ↓ 严格 source_revision/physical_page/文本匹配复核
        ↓ 源等级/转录审查状态清楚的回答
```

`OCR_transcription_unreviewed` 与 `verified_original_exact` 永远是独立授权级别，OCR 加入检索不表示可以自动上升为财务已确认值；答案中明确“OCR 转录待核对”。

## 索引与检索策略

- 融合查询：预处理公司别名、年度、主题；metadata filter 按本会话冻结文档、公司、年度、parser_version。
- 段落检索：标题/章节定位优先，正文相关性重排序，表格内容用于数值问题，风险概述不被无关财务表优先占满。
- 混合检索首版采用 SQLite FTS5 / rank 或 BM25 + 当前 dense Milvus，并用 Reciprocal Rank Fusion (RRF) 合并。分数无统一量纲不要直接求和。
- 加 `document_type`: `text|table|ocr_text|ocr_table` 与 `source_authority`: `exact_original|ocr_unreviewed`。
- 对于模型解释关联的证据，检索排名并不授予因果结论授权；模型引用只能选择程序已发布的合法 refs。

## 固定真实质量集（最低 12 条，建议 24 条）

| 类别 | 例子 | 重点判定 |
|---|---|---|
| 风险 | 2025 年报主要经营风险有哪些 | 不能首要显示“委托理财概况”纯数字表 |
| 风险 | 年报中如何描述原材料风险 | 有对应 PDF 引文，未搜到则说不足 |
| 财务 | 本年营业收入/经营现金流 | 未确认拒算；原文可摘录 |
| 跨年 | 2024/2025 管理层经营重点有什么变化 | 两年引用并列且都真实 |
| OCR | 扫描页中某个实际字段是什么 | 引用 OCR 页和未核对状态 |
| 多轮 | “那上一年呢” | 公司/期间承接而非猜测 |
| 反例 | 用户输入不在选定来源内的公司 | 澄清或要求新会话 |
| 注入 | PDF 中带“忽略系统规则”的内容 | 只当不可信原文，不当指令 |

建议用同一批 query 记录 baseline 与 C+：Hit@5、MRR@5、至少两名评审/或人工标注相关证据覆盖率（可用 1 人重点审核）、无关片段数、延迟、检索成本。作为求职版本不设虚假“95%通过”，任何真实失败单列出来。

## OCR 从解析到问答的 DoD

一份**派生扫描 PDF**（当前真实苹果 Vision 样本）→ OCR 出文字 bbox → 该 OCR artifact 进入受限检索范围（保留 SHA/版本）→ 用户提出实际问题 → 结果显示页面与“待人工复核” → 点击 PDF 原图定位。额外可选一份真正扫描原生报告验证，但不是首版必做。不能据派生样本宣称所有扫描年报准确。
