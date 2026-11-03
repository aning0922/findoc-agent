# D03 官方年报目录 UI 交接

基线 `89230aadbf53900d756f7bbcb280fe167fdd714f`，分支 `codex/showcase-d03`。组件 `frontend/src/product/disclosures/DisclosurePanel.tsx` 导出 `DisclosurePanel({company, companies, onImported?})`；由主控在 DocumentLibrary 现有手动上传表单上方挂载。`onImported` 仅在服务端返回 completed 后通知主控刷新目录；completed 表示上传/绑定结束，解析状态必须从旧目录另行读取，不代表财务确认。

使用 D02 的 GET search、POST import、GET imports/{operation_id}。目录文案明确限定美的/格力 2024/2025，日期与更正状态空值显示未知；来源链接仅呈现允许的 HTTPS 官方主机，不提供任意 URL 下载。候选代码需与当前绑定企业代码一致，服务端仍独立核验企业名称、交易所等。空态和失败均提示使用既有手动上传。

提交前在 sessionStorage 保存 `findoc:disclosure-import:<company_id>` 的公司与原 operation UUID；UNKNOWN、网络中断、无法核验的返回均保留，硬刷新后只允许 GET 原操作，不自动重 POST 或更换 UUID。存储不可写时不提交；存储提示损坏/不可读时阻止新导入并提示核对目录。该前缀已追加 demoHintBoundary allowlist，与同租约硬刷新保留、跨代清理规则一致。企业切换/unmount abort 并递增 epoch，迟到结果不更新新企业 UI；原企业未完成操作身份仍留在对应 key。

验证：Node 24 `npm run build` 与 `npm run lint` PASS（既有 warning 及本组件 effect warning）；本机 Vite + Chrome headless 拦截的 UI_MOCK，在 1440/1280/390 宽度通过目录查询、完成导入与回调、UNKNOWN 后硬刷新只读查证（无重复 POST）、切企业丢弃迟到响应，检查无横向溢出及页面异常；390 截图已人工查看。DemoGate 存储窄集包括新增前缀，首激活/同代刷新/跨代/异常检查 PASS。未运行真实 D02 接口/网络下载、实际资料解析或财务确认；主控接线后需做真实 HTTP 联调，mock 不能作为后端或正式验收证据。

复跑：先在 frontend 启动 `npm run dev -- --host 127.0.0.1 --port 5180`；再运行 `CHROME_PATH='/Applications/Google Chrome.app/Contents/MacOS/Google Chrome' node e2e/showcase-live-disclosure.mjs`。截图目录 `/Users/aipuli/.codex/visualizations/2026/11/03/01a19f9d-a871-7520-aed9-dd6d22774d1a/d03/`：`d03-{1440,1280,390}.png`、`success-{...}.png`、`unknown-{...}.png`、`switch-{...}.png`。测试数据与官方地址均为 UI_MOCK。
