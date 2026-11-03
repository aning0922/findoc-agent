# M1 UI 组件交接

基线 d6ccca07（包含 8c2c8a7），分支 codex/showcase-h02。H02 初稿 171ab87，修订 f14e105；后续提交包含 L04 与本记录。组件未接现有入口，主控负责装配。

- `ShowcaseDashboard` 接收 `{companies, company, access?}`；自身读取 overview/charts。失败显示错误，不回退数字；独立示意状态有水印。建议问题只接收同源 `/conversations?question=...` 预填链接，搜索选择后提供相同路线的 CTA。默认 revenue，图表表格保留 Decimal 原字符串和来源。柱图是同指标各期对比：H01 当前 comparison 为 `[]`，尚未实现多企业比较；来源清单和 limitations 由 DTO 展示。overview/chart 的 runtime schema 目前未校验；不得把本草稿视作已审计。
- `DemoGate` 显式 `enabled`；false 原样渲染 children，true 先检查 status/session，再挂载业务 children。Cookie 请求、pending poll、claim 使用独立 UUID、占用/owner 接管、owner 授权、logout、session 定期核验均为 UI 实现；不存密码或 token 到 localStorage，不自动执行财务步骤。挂载：`<DemoGate enabled={明确的演示开关}><App /></DemoGate>`。开关来源、后端网关强制权限、控制器状态均由主控负责。
- 验证：Node 24 build/lint PASS；存在组件 effect lint warning 和既有 fast-refresh/build chunk warning。Vite + Chrome headless 的 `frontend/e2e/showcase-live-mock.mjs` 在 1440/1280/390 通过模拟 pending→claim→dashboard→logout，断言 claim UUID 不同于 attempt、无横向溢出。截图目录 `/Users/aipuli/.codex/visualizations/2026/11/03/01a19f9d-a871-7520-aed9-dd6d22774d1a/m1-mock/`；内容均为拦截假数据。先运行 `npm run dev -- --host 127.0.0.1 --port 5180`，再运行 `CHROME_PATH='/Applications/Google Chrome.app/Contents/MacOS/Google Chrome' node e2e/showcase-live-mock.mjs`。
- 真实 HTTP、双浏览器、失效/接管并发、owner 权限、cookie 丢失、真实种子与业务回归均 SKIP；与并行后端集成后必须执行。默认 npm build 仅编译类型，组件未被产品入口引用，不能声称正式页面已接入。
