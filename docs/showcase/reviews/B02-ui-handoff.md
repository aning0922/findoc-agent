# B02｜独立 React 界面原型交接

- 基线：`92f7fa13a8b1905f3810ef66bc1c5713b4724947`，独立分支 `codex/showcase-b02-ui`。
- 定位：`UI_MOCK`。全部企业、数字、会话及状态都是界面示意；没有认证、独占租约、重置、数据持久化、真实财报、真实模型或财务确认。输入任意值只触发本地转场。刷新会重置状态。
- 入口：`cd frontend && PATH=/Users/aipuli/.nvm/versions/node/v24.19.0/bin:$PATH npm run dev -- --host 127.0.0.1`，打开 `http://127.0.0.1:5173/showcase.html`。独立入口仅供 Vite 开发预览；现有默认 `npm run build` 不包含此 HTML。已用 Vite API 单独构建此入口到 `/tmp/findoc-b02-build`，未改变业务构建配置。
- 首页包括搜索预填、四个指标、三种图及表格替代、近期研究、推荐问题和五导航。侧栏会话可切换，名称和模型标签按会话独立保存在当前 React 状态。研究、资料、任务和报告是可导航预览，不是业务接线。
- 登录、占用、等待、二次确认、重置、到期、被接管和空态均为本地模拟；不会操作共享环境。等待按钮返回浏览，并不轮询。
- 推荐主控优先考虑 Navy / Blue：侧栏与金融研究场景相符，主色在 KPI、按钮和图表之间有稳定层次；Ink / Teal 提供更温和的替代方案。两者共用结构，可右上角切换；最终选择由主控决定。候选主色分别为 `#4878d4`、`#218c88`，深色侧栏分别为 `#111f39`、`#132b30`。

## 验证记录

- PASS：Node 24.19.0，`npm run build` 和 `npm run lint`；lint 有既有测试文件一条 warning，本入口两条 React fast-refresh warning；build 有现有大 chunk 提示。默认 build 只构建原业务入口，单独 Vite API 构建 showcase 也 PASS（Recharts bundle 大小提示）。
- PASS：本机 Vite + Google Chrome（Playwright Chromium，headless），1440、1280、390 宽度，两配色完整页面截图，`document.documentElement.scrollWidth <= innerWidth`，无页面 JS 异常。截图捕获前关闭图表动画。截图由自动化捕获；390 和 1440 Navy 已人工检查。
- PASS：搜索预填、会话名称/模型切换并返回保持；登录→占用→二次确认→重置→到期→被接管；空态切换、报告与任务预览跳转。首轮脚本存在定位器不匹配，修正后上述流程重跑 PASS。
- SKIP：真实双浏览器租约、后端/API、真实财务数据、生产部署、全量测试。原型未实现上述能力，不能据此宣称已验收。
- 截图目录：`/Users/aipuli/.codex/visualizations/2026/11/03/01a19f9d-a871-7520-aed9-dd6d22774d1a/b02/`；文件为 `navy-1440.png`、`navy-1280.png`、`navy-390.png`、`ink-1440.png`、`ink-1280.png`、`ink-390.png`。
- 已知限制：配色状态、会话修改和输入仅存内存；移动端会话位于菜单抽屉；表格替代展示静态示意值；目前截图及关键流程验证并非完整无障碍审计。
