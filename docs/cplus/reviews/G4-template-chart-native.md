# 模板与图表草稿的真实导出闭环

在 root `448417d` 之后的本地 14540 演示运行时，以真实格力 2025 公告来源、零模型调用和零人工财务确认进行；未使用 14542。测试入口 `frontend/e2e/cplus-template-chart-native.mjs`。原始 [结果和截图哈希](/Users/aipuli/.codex/worktrees/findoc-showcase-cplus-integration/findoc-agent/data/cplus-template-chart-native/result.json)保存在 root ignored data，不提交凭据或二进制。

- 明确运行 overview、`generate_explanation=false`，保存五个真实候选财务点，provider outcome 为 not_requested。
- 报告中心通过真实 GET `export-snapshots?domain=template_run_v1&identifier=…&revision=1` 返回唯一 current 版本，页面预选同一 payload SHA。CSV、XLSX、PPTX 均实际生成并下载，下载 SHA 与 manifest 一致。
- 企业 360 明确选取 2025 年报全年/年末五点，生成候选趋势并点击复制图表到报告草稿；读取已保存草稿时 record_refs 与原回执一致，trend ID 与所选趋势相同、financial_authority=false。图表草稿报告中心精确过滤与 SHA 预选通过，CSV 生成下载 SHA 与 manifest 一致。
- 模板与图表报告中心在 1440 和 390 宽度通过全局横向溢出检查，截图路径与哈希、接口状态和耗时见结果 JSON。
- 登出 HTTP 200，旧会话 HTTP 401；初次状态为 resetting，随后只读轮询确认 ready。未停止 launcher。

本次验证候选和文件完整性，不构成模型解释、财务核准或全部导出内容人工审阅。HTML 控件和报告来源本身来自真实服务；未插入模拟数据。图表草稿只验证 CSV，模板验证三种格式。原始结果先记录 resetting，随后追加 ready 观察；脚本已加入同样的有界 ready 等待供下次运行。
