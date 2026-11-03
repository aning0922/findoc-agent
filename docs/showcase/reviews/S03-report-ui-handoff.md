# S03 报告库 UI 交接

导出 `ShowcaseReportsPanel({scopeKey: string})`；主控必须提供来自已验证会话的稳定 scopeKey，包含 workspace 与 lease generation，范围改变后组件重新挂载。sessionStorage 使用精确前缀 `findoc:showcase-report-operation:v1:` 加编码 scopeKey；root 需将此新前缀加入 demoHintBoundary，跨代清除旧线索。组件不负责会话授权。原有报告由 root 分区接入。

GET 列表与指定 revision；四种 findings、来源/转录/解释状态、原 PDF 固定同源路径与物理页、同源 print 链接。POST revision 仅 operation_id/expected_revision/title/notes；UNKNOWN 保存原 UUID，GET operations 查证而不重发。组件按 scope 卸载隔离旧响应；查询序号抑制迟到读取。历史视图修改使用该版本 expected_revision，后端可拒绝旧版本冲突；目前所有错误均进入只读查证，确定性未登记冲突需要后续显式恢复方案。

假 API 测试：frontend 运行 Vite 5198，再运行 `node tests/showcase-reports/smoke.cjs`；1440/1280/390 验证列表、引用链接、仅允许四字段编辑、UNKNOWN 硬刷新查证与范围切换，截图 `/tmp/showcase-reports-{width}.png`，390 目视检查。该测试未模拟延迟响应反序或真实服务授权，未验真实 PDF 下载或真实来源跳转。build/lint 通过（既有告警仍在）。未调用付费模型。scopeKey/gateway 及跨代清理需 root 接线，真实 Agent/报告服务还需端到端验收。
