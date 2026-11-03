# M5 已知模板问题限定复核

日期：2026-11-03。独立复核基线：`267c5e937b440c4e67fc7336d6d44ff6bc2987ca`，包含 `a1920c0` 非数值解释政策及 `267c5e9` 来源类型提示/可读打印规则。复核分支只提交本文与渲染图片；没有修改业务代码、调用真实模型、访问私有 ledger 或重放旧请求。

## 结论与范围

此前现金模板 AI 文本把年份与金额顺序错配，以及浏览器 PDF 原始规则 JSON 右溢，这两项在本次新模板输出中可关闭。修复采用 `non_numeric_review_v1`：AI 解释不再承载年份/金额配对；含数字的解释隔离，保存的 child 原回答仍保留。新真实输出是 **returned + ai_unreviewed 的非数值解释**，并非本次解释被 withheld。该结论不构成财务语义正确性或人工财务验收。

## 源码与受控测试

- `explanation_question` 保留用户主题并限制 child 问题长度；原完整问题仍保存。明确禁止金额、比例、年份、中文/Unicode 数词与年份金额排序配对。
- `has_numeric_characters` 使用 `isnumeric()` 加显式中文数词集。命中后父解释为空、结果为 `numeric_claim_requires_review`；不修改 child 已保存回答，不重试 provider。普通“统一”等可能保守误拦截，属于已声明限制，不宣称任意自然语言数字语义检测完整。
- 非数字解释仍为 `ai_unreviewed`、不授予 financial authority。选中财务点、receipt、source、memory 与 precommit 检查未放宽。
- fast-only 来源提示明确为 verified PDF fast text；含 OCR 来源才提示 OCR。提示语不构成语义质量证明。
- 打印把 `saved_checkup_rule` 从原始证据摘录排除，单独渲染可读规则、期间、观察与来源链接；结构化 JSON 提供 CSV/XLSX 指引，保留 HTML escaping 和断行 CSS。

独立运行 `tests/test_cplus_template_numeric_gate.py` 与 `tests/test_cplus_print_business_view.py`：**8 passed，5 个既有 SWIG warnings，9.34s**。覆盖原错误数字文本、中文/全角/正式数词、保守误拦截、非数值放行、长问题保存、child 原文保留及同 operation 不重调、打印转义及可读规则。不宣称独立复跑全部项目测试。

另按 root 请求复核其当时未提交的 `app/cplus/exports.py` child 读边界：以 `children` JOIN 父 `operations` 的 owner、`explanation-once`、completed、result_ref 定位内部回答，共用 resolver 拒绝其独立报告导出，因此列表也会过滤。原 answer GET 保留；后续原 source/owner/receipt resolve 未放宽。未发现可复现 P1。

新增 `tests/test_cplus_template_child_report_boundary.py` 初次独立运行 **1 failed**：fixture 缺少 `showcase_report_service`，列表在属性读取处返回 409，尚未验证目标断言。root 随后补入空报告表/服务装配；独立重跑 **1 passed，5 warnings，1.92s**。验证原 child GET 可读、独立列表为空、直接导出 409 `template_child_is_not_report`、父模板可列出，以及 fake provider 仅一次。此次未再调用真实 provider。初次失败保留在本记录，不能用后续通过抹除。

## 新真实文件及独立视觉检查

实际文件目录：`data/cplus-final-business-native-corrected-v1`（root integration checkout）。保存 run：`3f941792-2b7e-41f3-aaec-f6e4ccf775d5`。该目录 `result.json` 记录 PASS / 18 checks；这是 root 原生验证证据，独立检查范围如下。

- 四个实际文件 SHA 与 root receipt 一致（下表）。
- PPTX 重开为 6 slides / 1 chart；使用 LibreOffice 实际渲染为 PDF，再逐页查看全部 6 页。10 个财务点、3 条体检规则、趋势图和完整已保存解释均可见，未见裁切。
- 第 3 页按原期间显示：2024 归母净利润 32184570372.28、经营现金流 29369250570.66；2025 分别为 29003103411.66、46383114754.02。数值继续标为候选待核对。
- 第 5 页完整非数值解释以“所给 fast 文本仅含主要会计数据中的经营现金流与归母净利润摘录”起始，以“证据不足，不作财务核准，以上为 AI 待审草稿”结束；未重复旧年份金额错配，且未误称 OCR。
- 浏览器实际 PDF 共 6 页，已查看首尾页；首面规则使用可读业务文字与来源链接，末面段落在页宽内换行，未见原 JSON 右溢。全文文本扫描无 `input_refs`。**未宣称逐页视觉查看浏览器 PDF 中间四页。**

| 文件 | SHA-256 |
| --- | --- |
| cash-template.csv | `0da8c0b7096989db51916f9d51b871a076305a0799f84399365abac2268b5e22` |
| cash-template.xlsx | `0b4c3e6f8ca98bd3c9a6a4d95dcff8c523504ab3a296564d3b1b47d38057f475` |
| cash-template.pptx | `14c555a70e62355ba03aabbd60a0f5d4444961393c9994a6d17102dc03afdb81` |
| cash-template.pdf | `09a6029fe865d154af4f670edb323a6b7628686171ac1b084f3c23054301a1d9` |

视觉证据在 [template-policy-corrected-qa](template-policy-corrected-qa/)：`slide-1.png` 至 `slide-6.png`，`browser-first.png`、`browser-last.png`。

root 的 `docs/cplus/eval/results/template-numeric-policy-real-v1/result.json` 当前记录 `PASS_REAL_PROVIDER_NATIVE_NON_NUMERIC_POLICY_HUMAN_PENDING`、`interpretation_published=true`、1 个新 guard row、`old_unknown_state_changes={}`、logout 200 / old session 401。这是读取 root 已写证明，未独立读取私有账本或重验运行会话。

## 旧证据保留

`data/cplus-final-business-native-v1` 的原四文件均与此前 SHA 相同，4/4 未变化：

| 原文件 | SHA-256 |
| --- | --- |
| cash-template.csv | `dc53b9486d34d0a9fa16ab983ec5b72224aac1642a094982057ee0149ddb4bec` |
| cash-template.xlsx | `6b9a316cd22affdc07c80d2d3bb407477d77058d9df7efda2440600e2e7d0a88` |
| cash-template.pptx | `089d9dcb350e9a0ed3c17564b0385a1e5a95a3c71f8ae2b8333f16788a56c583` |
| cash-template.pdf | `ee9c2f3f434e63ce802f1bbca082dbfc870cca315c8fe5247d7a18772a9fdb22` |

原错误回答、原文件和失败记录继续作为负例；本次新文件通过不会追溯修正旧文件，也不将旧错误样本转成正例。复核仅关闭已知两项输出问题，未增加验收门槛，未批准其他财务推断。
