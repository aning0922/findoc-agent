# F03 扩展财务面板交接

基线 `32f4f6d0ee6ee50dc685b0f9412e30dc41453e2e`，分支 codex/showcase-f03。新增 `ExtendedFinancePanel({company: Company})` 与 scoped CSS；主控在公司分析页接线，没有改 FinancialProduct、旧六事实或财务服务。读取 F01 交接及实际 api/models/contracts/service 后实现。

先 GET 目录+metadata 筛选当前企业 ready 资料，用户明确选择文档，GET source 并校验精确来源，再显式 POST collect（只含 operation/company/document/revision）。表格分开显示 report_year 与 as_of_date、原始 Decimal、合并口径、候选/unsupported 与原 PDF 物理页证据链接；不补值、不选最新披露版本。候选不会入图。

明确选择同文档/来源修订/时点的资产与负债两项后，POST extended-reviews 创建待核对快照。逐项 checkbox、GET demo/session 验证有效 active/can_review/grant 时间后才开放真人确认；确认前再 GET 重新验证，并由后端最终鉴权。v2 独立回执不替代旧 ACCEPT/SAVE/RESUME。撤销同样先查 owner 并显式操作，授权失败撤下图；不绕过 owner 或写 simulated_test 至真实服务。

图只读 GET extended-metrics 重新核验的 confirmed + current_valid + local_operator 原始指标；Decimal 仅转 Number 作坐标/单位格式化，原值 tooltip 保留字符串。没有真实核准时图保持空。两已核准 ID 明确提交 extended-analyses，前端不计算比率/金额；结果仅显示为服务端保存快照。每15秒及窗口 focus GET 重验，来源失效响应或失败立即撤图；没有跨端实时 push 信号，不能声称浏览器收到服务端变化前就即时识别。用户可显式只读核验。

新存储提示 `findoc:finance-v2-operation:<company_id>` 只保存原 UUID/action，已纳入 Demo exact prefix allowlist；UNKNOWN 硬 reload 后只 GET operations。历史响应只提供历史说明，不恢复 review/授权或确认状态；随后 GET metrics 才可展示当前有效图。企业/来源切换 abort+epoch，GET 用序列隔离旧响应。存储线索异常关闭新写入。已知 POST 拒绝也保守保留为待查证，用户可 GET 得到 failed；不自动换 ID 重发。

D03 按主控要求只补 `.disclosure-panel.disclosure-panel button` specificity，覆盖全局按钮重置；未动其业务逻辑。

## 验证层级

Node 24 build/lint PASS（保留 effect/ref/deps、fast-refresh 与 chunk 提示）。独立 Playwright Chrome UI_MOCK：1440/1280/390 候选空图、明确来源/两项快照、无owner/逐项勾选时禁用接受、**假接口**的模拟确认、confirmed 折/柱、服务端比率请求无金额、owner 失效无写并撤图、来源失效撤图、UNKNOWN 硬 reload 只读恢复且不复放确认/金额。Demo 存储窄集含新前缀 PASS。同样本只测代表性路径，不宣称所有 DTO 与竞态穷举。

真实 financial confirmation 数 **0**。测试所有 `/api` 均被拦截，不触真实库、不产真实 local_operator 回执、不调用模型。真实 F02 HTTP/源解析/人工确认由主控后续联调；组件默认 build 只做类型检查，主控接线后才会进入正式产品 bundle。

复跑：frontend 下 Vite `npm run dev -- --host 127.0.0.1 --port 5180`，再 `CHROME_PATH='/Applications/Google Chrome.app/Contents/MacOS/Google Chrome' node e2e/showcase-live-finance-v2.mjs`。截图 `/Users/aipuli/.codex/visualizations/2026/11/03/01a19f9d-a871-7520-aed9-dd6d22774d1a/f03/`，`candidate-*.png`、`confirmed-*.png`、`unknown-*.png`；390 confirmed 已 view_image 检查，修正大额坐标截断后重拍。所有数据为显著 UI_MOCK。
