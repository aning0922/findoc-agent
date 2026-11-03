# C+ 分层验证结果

当前以 [固定24题矩阵](eval/CORE_EXECUTION_MATRIX.md)、[原始机器记录](eval/results/core-execution-matrix-v1.json)和 [EVIDENCE](EVIDENCE.md)为准。旧检查点见 [历史汇总](checkpoints/EVAL_RESULTS-e510876.md)，不能把旧“0新模型成功”沿用到已恢复后的结果。

## 执行与正确性分轴

固定24题精确文本未改。累计13 required-tier executed：E01-01/06/14/15、CP16/17/18/19/20/21/22/23/24。含实际模型、真实公开PDF/OCR、BGE/Milvus、HTTP/Chrome或指定program_contract。这个分母不是正确率：E01-01实际合成研究未找到适用现金流摘录，部分固定题未运行，所有人工语义接受与财务核准仍pending。

CP24最新同图点完整原生9检查（真实page_only回退）；CP21实际3AI返回+1missing PDF UNKNOWN，旧queued3取消仅影响未开始格；E01-14客户端findings/金额refs均422、备注不改变trusted snapshot、旧rev1不可变。原单2025 E01-15与额外双年Interview-B分开记录，不重复计数。

## 真实模型与错误保留

- 旧4次ReadTimeout/UNKNOWN保留，不退款、不自动重放。
- 恢复后实际来源问答、三规则体检、OCR待审说明、年度三主题、模板、单/多Agent和AI批次均有真实返回。
- 同2025固定问题单多Agent11调用；额外双年deep8+synthesis5=13调用，双方同问题/同两份来源/同事实选择且有双年引用。试验窗口余量不足时不启动下一任务；独立新窗口只启动此前未开始的synthesis，全局原5元cap不变。
- 旧cash AI年份金额错配独立文件QA发现，保留原样；新的非数值解释门禁7受控例+原15边界通过，真实再验证仅1SDK、解释成功发布且无数字，仍ai_unreviewed。raw child可审阅，但不是独立报告导出。通过字符门禁不代表语义验证，可能保守拦截“统一/进一步”等普通词。
- 年度首次输入预算拒绝、FTS五来源422、原native selector/30秒GET超时、JS回写0.0→0造成SHA不一致等失败不改为PASS。后续新操作及修复单列。

## 文件、浏览器与命令

实际三宽profile/表格/体检、两个独立浏览器接管旧HTTP401、四模板结构化业务、图表draftrev1、精确版本原生导出均留证。真实四格及故障批次不是fake provider；边界竞态/数字隔离测试则明确synthetic PDF/fake provider。

C+模式前端build必须显式 VITE_FINDOC_DEMO_MODE=1 / VITE_FINDOC_CPLUS_MODE=1 / VITE_FINDOC_SHOWCASE_PREVIEW_CHARTS=0；未开启C+时tree-shaken bundle不能当C+模式构建证据。大chunk/hooks/SWIG警告保留。后端最后选择性命令覆盖 `test_cplus_*.py`、demo、launcher和runtime startup，3个opt-in真实PDF SKIP仍单列；最终PASS分母见STATE/本轮命令结果。

新候选cash文件四格式4/4 SHA，6页PPTX逐页查看，业务图/10候选点/3规则/非数值AI解释；浏览器PDF6页仅查看首末，未做全页布局人审。旧错误文件4/4 SHA未变。CSV Git属性禁止换行改写，确保Gitblob字节与下载一致。

原ledger最终123物理记录/保守预留2.468274元/上限5/UNKNOWN4/账单未知。没有本人财务确认、main合并、公开部署或购买服务。
